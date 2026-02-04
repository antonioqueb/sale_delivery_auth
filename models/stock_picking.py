from odoo import models, fields

class StockPicking(models.Model):
    _inherit = 'stock.picking'

    # Campo relacionado para leer el estado desde la Orden de Venta
    sale_auth_state = fields.Selection(related='sale_id.delivery_auth_state', string="Estado Autorización Venta", store=False, readonly=True)
    
    # Campo computado booleano para facilitar la vista (Ribbon)
    is_delivery_authorized = fields.Boolean(compute='_compute_is_delivery_authorized')

    def _compute_is_delivery_authorized(self):
        for picking in self:
            # Se considera autorizado si está pagado o autorizado manualmente
            # Si no viene de una venta (ej. recepción), no aplica esta lógica (True por defecto)
            if picking.sale_id:
                picking.is_delivery_authorized = picking.sale_auth_state in ['paid', 'authorized']
            else:
                picking.is_delivery_authorized = True
