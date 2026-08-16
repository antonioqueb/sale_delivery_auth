from odoo import models, fields, api, _
from odoo.tools.float_utils import float_compare


class SaleOrder(models.Model):
    _inherit = 'sale.order'

    def _som_schedule_logistics_activity(self, summary, note):
        """Crea una actividad en esta orden para CADA miembro del grupo
        'Logística — Avisos'. Silencioso si el grupo no tiene miembros."""
        group = self.env.ref(
            'sale_delivery_auth.group_delivery_logistics',
            raise_if_not_found=False,
        )
        if not group:
            return
        # OJO (Odoo 19): user_ids trae SOLO miembros directos. Quien tenga
        # el grupo por implicación de otro NO aparece ahí y se quedaba sin
        # aviso, en silencio. all_user_ids sí los incluye.
        destinatarios = (group.all_user_ids
                         if 'all_user_ids' in group._fields
                         else group.user_ids)
        if not destinatarios:
            return
        activity_type = self.env.ref(
            'mail.mail_activity_data_todo', raise_if_not_found=False)
        for order in self:
            for user in destinatarios:
                order.activity_schedule(
                    activity_type_id=activity_type.id if activity_type else False,
                    summary=summary,
                    note=note,
                    user_id=user.id,
                )

    delivery_auth_state = fields.Selection([
        ('pending', 'Pendiente de Pago/Auth'),
        ('requested', 'Autorización Solicitada'),
        ('authorized', 'Autorizado Manualmente'),
        ('paid', 'Pagado Totalmente'),
    ], string='Estado Autorización Entrega',
        compute='_compute_delivery_auth_state',
        store=True, default='pending', tracking=True,
    )

    # Autorización MANUAL: bandera + monto al que se autorizó. La autorización
    # solo es válida mientras el total de la orden no supere ese monto (proceso
    # vivo: si se agrega material y sube la deuda, se invalida y se vuelve a pedir
    # pago o autorización).
    delivery_auth_manual_authorized = fields.Boolean(
        string='Entrega Autorizada Manualmente',
        default=False, copy=False, tracking=True,
    )
    delivery_auth_authorized_amount = fields.Monetary(
        string='Monto Autorizado',
        default=0.0, copy=False, currency_field='currency_id',
        help='Snapshot informativo: total de la orden al momento de '
             'autorizar manualmente. La autorización NO caduca si el total '
             'cambia (regla de negocio 2026-08-11).',
    )

    # Pago real contra la orden (cobertura del 100%). Ambos ALMACENADOS y con el
    # mismo método: evita el warning de 'store'/'compute_sudo' inconsistentes.
    delivery_paid_amount = fields.Monetary(
        string='Pagado (entrega)',
        compute='_compute_delivery_paid', store=True, currency_field='currency_id',
    )
    delivery_is_fully_paid = fields.Boolean(
        string='Pagado 100%',
        compute='_compute_delivery_paid', store=True,
    )

    delivery_auth_request_ids = fields.One2many(
        'delivery.auth.request', 'sale_order_id',
        string='Solicitudes de Autorización',
    )
    delivery_auth_request_count = fields.Integer(
        compute='_compute_delivery_auth_request_count',
    )

    @api.depends('delivery_auth_request_ids')
    def _compute_delivery_auth_request_count(self):
        for order in self:
            order.delivery_auth_request_count = len(order.delivery_auth_request_ids)

    # =========================================================================
    # PAGO REAL: el 100% de la orden debe estar pagado.
    #
    # Se suma el dinero realmente recibido en las facturas POSTEADAS del cliente
    # (incluye anticipos/down payments) y se resta lo de las notas de crédito.
    # Pagar una parte (p. ej. una factura parcial de $20 de $1,000) NO marca la
    # orden como pagada: paid debe alcanzar amount_total.
    # =========================================================================
    @api.depends(
        'invoice_ids.amount_total',
        'invoice_ids.amount_residual',
        'invoice_ids.state',
        'invoice_ids.move_type',
        'amount_total',
        'currency_id',
    )
    def _compute_delivery_paid(self):
        for order in self:
            paid, has_posted = order._delivery_paid_live()
            order.delivery_paid_amount = paid
            rounding = order.currency_id.rounding or 0.01
            order.delivery_is_fully_paid = bool(
                order.amount_total > 0
                and has_posted
                and float_compare(paid, order.amount_total, precision_rounding=rounding) >= 0
            )

    def _delivery_paid_live(self):
        """Suma EN VIVO del dinero realmente recibido en las facturas posteadas
        del cliente (anticipos incluidos), menos notas de crédito.
        Devuelve (pagado, hay_factura_posteada)."""
        self.ensure_one()
        posted = self.invoice_ids.filtered(
            lambda m: m.state == 'posted' and m.move_type in ('out_invoice', 'out_refund')
        )
        paid = 0.0
        for inv in posted:
            inv_paid = (inv.amount_total or 0.0) - (inv.amount_residual or 0.0)
            paid += -inv_paid if inv.move_type == 'out_refund' else inv_paid
        return paid, bool(posted)

    @api.depends(
        'delivery_is_fully_paid',
        'amount_total',
        'delivery_auth_manual_authorized',
        'delivery_auth_authorized_amount',
        'delivery_auth_request_ids.state',
        'currency_id',
    )
    def _compute_delivery_auth_state(self):
        for order in self:
            if order.delivery_is_fully_paid:
                order.delivery_auth_state = 'paid'
                continue

            # REGLA DE NEGOCIO (2026-08-11): la autorización manual es
            # ABSOLUTA — para eso se autoriza. Vale aunque el total cambie
            # después (los flujos de entrega ajustan cantidades en caliente
            # y un tope por monto bloqueaba remisiones ya autorizadas).
            # delivery_auth_authorized_amount queda como snapshot informativo.
            if order.delivery_auth_manual_authorized:
                order.delivery_auth_state = 'authorized'
                continue

            has_pending = any(
                r.state in ('draft', 'requested') for r in order.delivery_auth_request_ids
            )
            order.delivery_auth_state = 'requested' if has_pending else 'pending'

    def _delivery_is_authorized_now(self):
        """Verificación EN VIVO al validar la entrega. NO se confía en el campo
        almacenado 'delivery_is_fully_paid' (puede quedar viejo si se agregó
        material después de pagar): se recalcula el pago contra el total ACTUAL.
        True si la orden está 100% pagada hoy, o autorizada manualmente
        (la autorización manual es absoluta: no caduca por cambios de
        total)."""
        self.ensure_one()
        rounding = self.currency_id.rounding or 0.01
        paid, has_posted = self._delivery_paid_live()
        fully_paid = bool(
            self.amount_total > 0
            and has_posted
            and float_compare(paid, self.amount_total, precision_rounding=rounding) >= 0
        )
        if fully_paid:
            return True
        # Autorización manual ABSOLUTA: pasa aunque el total haya cambiado.
        if self.delivery_auth_manual_authorized:
            return True
        return False

    def _set_manual_delivery_authorization(self):
        """Marca la entrega como autorizada manualmente al total ACTUAL."""
        for order in self:
            order.write({
                'delivery_auth_manual_authorized': True,
                'delivery_auth_authorized_amount': order.amount_total,
            })

    def action_create_delivery_auth_request(self):
        self.ensure_one()
        active_request = self.delivery_auth_request_ids.filtered(
            lambda r: r.state in ('draft', 'requested')
        )
        if active_request:
            return {
                'type': 'ir.actions.act_window',
                'name': _('Solicitud de Autorización'),
                'res_model': 'delivery.auth.request',
                'res_id': active_request[0].id,
                'view_mode': 'form',
                'target': 'current',
            }

        request = self.env['delivery.auth.request'].create({
            'sale_order_id': self.id,
            'state': 'draft',
        })
        # El estado de la orden lo deriva el cómputo (hay solicitud pendiente).
        return {
            'type': 'ir.actions.act_window',
            'name': _('Solicitud de Autorización'),
            'res_model': 'delivery.auth.request',
            'res_id': request.id,
            'view_mode': 'form',
            'target': 'current',
        }

    def action_view_delivery_auth_requests(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': _('Solicitudes de Autorización'),
            'res_model': 'delivery.auth.request',
            'view_mode': 'list,form',
            'domain': [('sale_order_id', '=', self.id)],
            'context': {'default_sale_order_id': self.id},
        }
