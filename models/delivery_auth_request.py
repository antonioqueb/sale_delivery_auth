from odoo import models, fields, api, _
from odoo.exceptions import UserError


class DeliveryAuthRequest(models.Model):
    _name = 'delivery.auth.request'
    _description = 'Solicitud de Autorización de Entrega'
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _order = 'create_date desc'
    _rec_name = 'display_name'

    # ── Relaciones principales ──
    sale_order_id = fields.Many2one(
        'sale.order', string='Orden de Venta',
        required=True, readonly=True, ondelete='cascade',
        tracking=True,
    )
    picking_ids = fields.One2many(
        'stock.picking', related='sale_order_id.picking_ids',
        string='Entregas Relacionadas',
    )
    partner_id = fields.Many2one(
        related='sale_order_id.partner_id',
        string='Cliente', store=True, readonly=True,
    )
    company_id = fields.Many2one(
        related='sale_order_id.company_id',
        string='Compañía', store=True, readonly=True,
    )
    currency_id = fields.Many2one(
        related='sale_order_id.currency_id',
        string='Moneda',
    )

    # ── Montos informativos ──
    amount_total = fields.Monetary(
        related='sale_order_id.amount_total',
        string='Monto Total', currency_field='currency_id',
    )
    amount_residual = fields.Monetary(
        string='Saldo Pendiente', compute='_compute_amount_residual',
        currency_field='currency_id',
    )

    # ── Estado ──
    state = fields.Selection([
        ('draft', 'Borrador'),
        ('requested', 'Solicitado'),
        ('approved', 'Aprobado'),
        ('rejected', 'Rechazado'),
        ('cancelled', 'Cancelado'),
    ], string='Estado', default='draft', tracking=True, required=True)

    # ── Quién solicita / quién aprueba ──
    requested_by_id = fields.Many2one(
        'res.users', string='Solicitado por',
        readonly=True, tracking=True,
    )
    request_date = fields.Datetime(
        string='Fecha de Solicitud', readonly=True,
    )
    approved_by_id = fields.Many2one(
        'res.users', string='Aprobado/Rechazado por',
        readonly=True, tracking=True,
    )
    approval_date = fields.Datetime(
        string='Fecha de Aprobación/Rechazo', readonly=True,
    )

    # ── Notas ──
    request_notes = fields.Text(
        string='Motivo de Solicitud',
        help='Razón por la que se solicita entregar sin pago total.',
    )
    rejection_notes = fields.Text(
        string='Motivo de Rechazo', readonly=True,
    )

    # ── Display name ──
    display_name = fields.Char(compute='_compute_display_name', store=True)

    @api.depends('sale_order_id.name', 'state')
    def _compute_display_name(self):
        for rec in self:
            so_name = rec.sale_order_id.name or 'Nuevo'
            state_label = dict(rec._fields['state'].selection).get(rec.state, '')
            rec.display_name = f"AUTH/{so_name} - {state_label}"

    @api.depends('sale_order_id.amount_total', 'sale_order_id.delivery_paid_amount')
    def _compute_amount_residual(self):
        for rec in self:
            order = rec.sale_order_id
            rec.amount_residual = (order.amount_total or 0.0) - (order.delivery_paid_amount or 0.0)

    # ── Acciones ──
    def action_request(self):
        for rec in self:
            if rec.state != 'draft':
                raise UserError(_('Solo se pueden enviar solicitudes en estado Borrador.'))
            rec.write({
                'state': 'requested',
                'requested_by_id': self.env.uid,
                'request_date': fields.Datetime.now(),
            })
            rec.message_post(
                body=_(
                    'Solicitud de autorización de entrega enviada por <b>%s</b>.<br/>Motivo: %s',
                    self.env.user.name,
                    rec.request_notes or 'Sin especificar',
                ),
                message_type='notification',
                subtype_xmlid='mail.mt_note',
            )
            # Los aprobadores DEBEN enterarse: actividad + mención en el
            # chatter (inbox/correo). Una nota (mt_note) no notifica a nadie.
            rec._som_notify_approvers()

    def _som_group_users(self, group):
        """Usuarios de un grupo, tolerante a Odoo 19: res.groups ya no tiene
        'users'; se resuelve por el campo que exista. all_user_ids va PRIMERO
        y se UNE con user_ids: solo user_ids omite a quienes reciben el grupo
        por IMPLICACIÓN de otro grupo (aprobadores sin notificar)."""
        Users = self.env['res.users']
        if not group:
            return Users
        users = Users
        for fname in ('all_user_ids', 'user_ids', 'users'):
            if fname in group._fields:
                users |= group[fname]
        if users:
            return users.filtered(lambda u: u.active and not u.share)
        for fname in ('all_group_ids', 'group_ids', 'groups_id'):
            if fname in Users._fields:
                return Users.search([
                    (fname, 'in', group.id), ('active', '=', True)])
        return Users

    def _som_notify_approvers(self):
        self.ensure_one()
        group = self.env.ref(
            'sale_delivery_auth.group_delivery_approver',
            raise_if_not_found=False)
        if not group:
            return
        approvers = self._som_group_users(group).filtered(
            lambda u: u.id != self.env.uid)
        if not approvers:
            return
        order = self.sale_order_id
        summary = _('Autorizar entrega: %s') % (order.name or '')
        note = _(
            '%(user)s solicita autorización de ENTREGA para la orden '
            '%(order)s (cliente: %(partner)s). Saldo pendiente: %(residual).2f. '
            'Motivo: %(reason)s'
        ) % {
            'user': self.env.user.name,
            'order': order.name or '',
            'partner': order.partner_id.display_name or '',
            'residual': self.amount_residual or 0.0,
            'reason': self.request_notes or _('Sin especificar'),
        }
        for user in approvers:
            self.activity_schedule(
                'mail.mail_activity_data_todo',
                user_id=user.id,
                summary=summary,
                note=note,
            )
        self.message_post(
            body=_('<p><b>%s</b></p><p>%s</p>', summary, note),
            partner_ids=approvers.partner_id.ids,
            message_type='comment',
            subtype_xmlid='mail.mt_comment',
        )

    def unlink(self):
        """Borrar una solicitud APROBADA retira la autorización manual de su
        orden (si ninguna otra solicitud aprobada la respalda). Sin esto, la
        orden quedaba en un limbo: flags de autorizada viejos, candado de
        entrega activo y botón de Solicitar Entrega oculto."""
        orders = self.filtered(
            lambda r: r.state == 'approved').mapped('sale_order_id')
        res = super().unlink()
        for order in orders:
            if not order.exists():
                continue
            still_approved = order.delivery_auth_request_ids.filtered(
                lambda r: r.state == 'approved')
            if not still_approved and order.delivery_auth_manual_authorized:
                order.write({
                    'delivery_auth_manual_authorized': False,
                    'delivery_auth_authorized_amount': 0.0,
                })
                order.message_post(body=(
                    'Se eliminó la solicitud de autorización aprobada: la '
                    'autorización manual de entrega quedó RETIRADA. Solicita '
                    'una nueva si se requiere entregar sin pago completo.'))
        return res

    def action_approve(self):
        self._check_approver_rights()
        for rec in self:
            if rec.state != 'requested':
                raise UserError(_('Solo se pueden aprobar solicitudes en estado Solicitado.'))
            rec.write({
                'state': 'approved',
                'approved_by_id': self.env.uid,
                'approval_date': fields.Datetime.now(),
            })
            # Autoriza al TOTAL ACTUAL de la orden. Si luego se agrega material y
            # el total sube, la autorización deja de ser válida automáticamente.
            rec.sale_order_id._set_manual_delivery_authorization()
            rec.message_post(
                body=_(
                    'Autorización de entrega <b>APROBADA</b> por <b>%s</b>.',
                    self.env.user.name,
                ),
                message_type='notification',
                subtype_xmlid='mail.mt_note',
            )
            # Avisar al solicitante (la nota de arriba no notifica).
            if rec.requested_by_id and rec.requested_by_id.id != self.env.uid:
                rec.activity_schedule(
                    'mail.mail_activity_data_todo',
                    user_id=rec.requested_by_id.id,
                    summary=_('Entrega autorizada: %s') % (rec.sale_order_id.name or ''),
                    note=_('%s aprobó la autorización de entrega.') % self.env.user.name,
                )
                rec.message_post(
                    body=_(
                        '<p>Entrega de <b>%s</b> autorizada por %s.</p>',
                        rec.sale_order_id.name or '',
                        self.env.user.name,
                    ),
                    partner_ids=rec.requested_by_id.partner_id.ids,
                    message_type='comment',
                    subtype_xmlid='mail.mt_comment',
                )
            # Aviso operativo: logística debe preparar/programar la entrega.
            rec.sale_order_id._som_schedule_logistics_activity(
                summary=_('Entrega autorizada — %s') % rec.sale_order_id.name,
                note=_(
                    '<p>Se <b>autorizó la entrega</b> de la orden '
                    '<b>%(order)s</b> (cliente: %(partner)s) por %(user)s.</p>'
                    '<p>Programar/preparar la entrega del material.</p>'
                ) % {
                    'order': rec.sale_order_id.name,
                    'partner': rec.sale_order_id.partner_id.display_name or '',
                    'user': self.env.user.name,
                },
            )

    def action_reject(self):
        self.ensure_one()
        self._check_approver_rights()
        return {
            'type': 'ir.actions.act_window',
            'name': _('Rechazar Solicitud'),
            'res_model': 'delivery.auth.reject.wizard',
            'view_mode': 'form',
            'target': 'new',
            'context': {'default_request_id': self.id},
        }

    def action_cancel(self):
        for rec in self:
            if rec.state in ('approved',):
                raise UserError(_('No se puede cancelar una solicitud ya aprobada.'))
            rec.write({'state': 'cancelled'})
            # El estado de la orden lo deriva el cómputo (ya no hay solicitud
            # pendiente). No se toca la autorización manual previa, si existiera.
            rec.message_post(
                body=_('Solicitud <b>CANCELADA</b> por <b>%s</b>.', self.env.user.name),
                message_type='notification',
                subtype_xmlid='mail.mt_note',
            )

    def action_reset_draft(self):
        for rec in self:
            if rec.state not in ('cancelled', 'rejected'):
                raise UserError(_('Solo se pueden restablecer solicitudes canceladas o rechazadas.'))
            rec.write({
                'state': 'draft',
                'approved_by_id': False,
                'approval_date': False,
                'rejection_notes': False,
            })

    def _check_approver_rights(self):
        if not self.env.user.has_group('sale_delivery_auth.group_delivery_approver'):
            raise UserError(_(
                'Solo los usuarios del grupo "Gerente de Aprobación de Entregas" '
                'pueden aprobar o rechazar solicitudes.'
            ))