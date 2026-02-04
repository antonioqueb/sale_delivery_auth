from odoo import models, fields, api

class SaleOrder(models.Model):
    _inherit = 'sale.order'

    delivery_auth_state = fields.Selection([
        ('pending', 'Pendiente de Pago/Auth'),
        ('requested', 'Autorización Solicitada'),
        ('authorized', 'Autorizado Manualmente'),
        ('paid', 'Pagado Totalmente')
    ], string='Estado Autorización Entrega', compute='_compute_delivery_auth_state', store=True, default='pending')

    # CORRECCIÓN: Eliminado 'amount_residual' de depends. Agregado 'invoice_ids.amount_residual'
    @api.depends('invoice_ids.payment_state', 'invoice_ids.state', 'invoice_ids.amount_residual', 'amount_total')
    def _compute_delivery_auth_state(self):
        for order in self:
            # Lógica 1: Calcular si está pagado al 100% basándonos en las facturas
            
            # Filtramos solo facturas publicadas (ni borradores ni canceladas)
            valid_invoices = order.invoice_ids.filtered(lambda inv: inv.state == 'posted')
            
            # Calculamos el residual total sumando el residual de las facturas válidas
            total_residual = sum(valid_invoices.mapped('amount_residual'))
            
            # Verificamos si hay facturas validas y si el saldo pendiente es 0
            # Nota: Agregamos chequeo de amount_total > 0 para evitar falsos positivos en órdenes vacías
            is_fully_paid = valid_invoices and total_residual == 0 and order.amount_total > 0

            if is_fully_paid:
                 # Si ya estaba autorizado manualmente, lo dejamos, si no, pasa a pagado
                 if order.delivery_auth_state != 'authorized':
                     order.delivery_auth_state = 'paid'
            
            elif order.delivery_auth_state == 'paid':
                # Si estaba marcado como pagado pero ya no lo está (ej. nota de crédito o factura reabierta), regresa a pendiente
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