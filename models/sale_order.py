from odoo import models, fields, api, _


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

    @api.depends(
        'invoice_ids.payment_state',
        'invoice_ids.state',
        'invoice_ids.amount_residual',
        'amount_total',
    )
    def _compute_delivery_auth_state(self):
        for order in self:
            valid_invoices = order.invoice_ids.filtered(lambda inv: inv.state == 'posted')
            total_residual = sum(valid_invoices.mapped('amount_residual'))
            is_fully_paid = valid_invoices and total_residual == 0 and order.amount_total > 0

            if is_fully_paid:
                order.delivery_auth_state = 'paid'
            elif order.delivery_auth_state == 'paid':
                order.delivery_auth_state = 'pending'

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
        self.write({'delivery_auth_state': 'requested'})
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