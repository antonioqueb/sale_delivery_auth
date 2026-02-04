from odoo import models, fields, api

class SaleOrder(models.Model):
    _inherit = 'sale.order'

    delivery_auth_state = fields.Selection([
        ('pending', 'Pendiente de Pago/Auth'),
        ('requested', 'Autorización Solicitada'),
        ('authorized', 'Autorizado Manualmente'),
        ('paid', 'Pagado Totalmente')
    ], string='Estado Autorización Entrega', compute='_compute_delivery_auth_state', store=True, default='pending')

    # --- AQUÍ ESTABA EL ERROR ---
    # NO poner 'amount_residual'. Usar 'invoice_ids.amount_residual'
    @api.depends('invoice_ids.payment_state', 'invoice_ids.state', 'invoice_ids.amount_residual', 'amount_total')
    def _compute_delivery_auth_state(self):
        for order in self:
            # Filtramos solo facturas publicadas
            valid_invoices = order.invoice_ids.filtered(lambda inv: inv.state == 'posted')
            
            # Calculamos el residual sumando las facturas
            total_residual = sum(valid_invoices.mapped('amount_residual'))
            
            # Verificamos pago total
            is_fully_paid = valid_invoices and total_residual == 0 and order.amount_total > 0

            if is_fully_paid:
                 if order.delivery_auth_state != 'authorized':
                     order.delivery_auth_state = 'paid'
            elif order.delivery_auth_state == 'paid':
                order.delivery_auth_state = 'pending'
            
            if not order.delivery_auth_state:
                order.delivery_auth_state = 'pending'

    def action_request_delivery_auth(self):
        """ El vendedor solicita autorización """
        for order in self:
            if order.delivery_auth_state == 'pending':
                order.delivery_auth_state = 'requested'

    def action_approve_delivery_auth(self):
        """ El gerente aprueba la entrega sin pago total """
        for order in self:
            order.delivery_auth_state = 'authorized'

    def action_reset_delivery_auth(self):
        """ Regresar a borrador la autorización """
        for order in self:
            order.delivery_auth_state = 'pending'