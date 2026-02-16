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

    @api.depends('sale_order_id.invoice_ids.amount_residual', 'sale_order_id.invoice_ids.state')
    def _compute_amount_residual(self):
        for rec in self:
            valid_invoices = rec.sale_order_id.invoice_ids.filtered(
                lambda inv: inv.state == 'posted'
            )
            rec.amount_residual = sum(valid_invoices.mapped('amount_residual'))

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
            rec.sale_order_id.write({'delivery_auth_state': 'authorized'})
            rec.message_post(
                body=_(
                    'Autorización de entrega <b>APROBADA</b> por <b>%s</b>.',
                    self.env.user.name,
                ),
                message_type='notification',
                subtype_xmlid='mail.mt_note',
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
            rec.sale_order_id.write({'delivery_auth_state': 'pending'})
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
            rec.sale_order_id.write({'delivery_auth_state': 'pending'})

    def _check_approver_rights(self):
        if not self.env.user.has_group('sale_delivery_auth.group_delivery_approver'):
            raise UserError(_(
                'Solo los usuarios del grupo "Gerente de Aprobación de Entregas" '
                'pueden aprobar o rechazar solicitudes.'
            ))