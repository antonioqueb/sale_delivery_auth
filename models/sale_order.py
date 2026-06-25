from odoo import models, fields, api, _
from odoo.tools.float_utils import float_compare


class SaleOrder(models.Model):
    _inherit = 'sale.order'

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
        help='Total de la orden al momento de autorizar manualmente. Si el total '
             'sube por encima de este monto, la autorización deja de ser válida.',
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
            posted = order.invoice_ids.filtered(
                lambda m: m.state == 'posted' and m.move_type in ('out_invoice', 'out_refund')
            )
            paid = 0.0
            for inv in posted:
                inv_paid = (inv.amount_total or 0.0) - (inv.amount_residual or 0.0)
                paid += -inv_paid if inv.move_type == 'out_refund' else inv_paid
            order.delivery_paid_amount = paid
            rounding = order.currency_id.rounding or 0.01
            order.delivery_is_fully_paid = bool(
                order.amount_total > 0
                and posted
                and float_compare(paid, order.amount_total, precision_rounding=rounding) >= 0
            )

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

            # La autorización manual solo vale si el total NO supera lo autorizado.
            if order.delivery_auth_manual_authorized:
                rounding = order.currency_id.rounding or 0.01
                still_valid = float_compare(
                    order.amount_total, order.delivery_auth_authorized_amount,
                    precision_rounding=rounding,
                ) <= 0
                if still_valid:
                    order.delivery_auth_state = 'authorized'
                    continue

            has_pending = any(
                r.state in ('draft', 'requested') for r in order.delivery_auth_request_ids
            )
            order.delivery_auth_state = 'requested' if has_pending else 'pending'

    def _delivery_is_authorized_now(self):
        """Verificación EN VIVO (se usa al validar la entrega): True si la orden
        está 100% pagada, o autorizada manualmente y el total no supera el monto
        autorizado."""
        self.ensure_one()
        if self.delivery_is_fully_paid:
            return True
        if self.delivery_auth_manual_authorized:
            rounding = self.currency_id.rounding or 0.01
            return float_compare(
                self.amount_total, self.delivery_auth_authorized_amount,
                precision_rounding=rounding,
            ) <= 0
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
