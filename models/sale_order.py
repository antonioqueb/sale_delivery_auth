from odoo import models, fields, api

class SaleOrder(models.Model):
    _inherit = 'sale.order'

    delivery_auth_state = fields.Selection([
        ('pending', 'Pendiente de Pago/Auth'),
        ('requested', 'Autorización Solicitada'),
        ('authorized', 'Autorizado Manualmente'),
        ('paid', 'Pagado Totalmente')
    ], string='Estado Autorización Entrega', compute='_compute_delivery_auth_state', store=True, default='pending')

    @api.depends('invoice_ids.payment_state', 'amount_total', 'amount_residual')
    def _compute_delivery_auth_state(self):
        for order in self:
            # Lógica 1: Si está pagado al 100%
            # Verificamos si hay facturas y si el importe residual es 0 o el estado es pagado
            if order.invoice_ids and order.amount_residual == 0 and order.amount_total > 0:
                 # Si ya estaba autorizado manualmente, lo dejamos, si no, pasa a pagado
                 if order.delivery_auth_state != 'authorized':
                     order.delivery_auth_state = 'paid'
            elif order.delivery_auth_state == 'paid':
                # Si estaba marcado como pagado pero ya no lo está (ej. nota de crédito), regresa a pendiente
                order.delivery_auth_state = 'pending'
            
            # Asegurar que si no tiene valor, sea pending
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
