from odoo import models, fields, api


class StockPicking(models.Model):
    _inherit = 'stock.picking'

    sale_auth_state = fields.Selection(
        related='sale_id.delivery_auth_state',
        string="Estado Autorización Venta",
        store=False, readonly=True,
    )

    is_outgoing = fields.Boolean(
        compute='_compute_is_outgoing', store=False,
    )

    is_sale_unpaid = fields.Boolean(
        compute='_compute_sale_unpaid_flags', store=False,
    )

    is_delivery_authorized = fields.Boolean(
        compute='_compute_sale_unpaid_flags', store=False,
    )

    requires_delivery_auth = fields.Boolean(
        compute='_compute_sale_unpaid_flags', store=False,
    )

    @api.depends('picking_type_code')
    def _compute_is_outgoing(self):
        for picking in self:
            picking.is_outgoing = picking.picking_type_code == 'outgoing'

    @api.depends('sale_id', 'sale_id.delivery_auth_state', 'picking_type_code')
    def _compute_sale_unpaid_flags(self):
        for picking in self:
            has_sale = bool(picking.sale_id)
            auth_state = picking.sale_auth_state
            is_outgoing = picking.picking_type_code == 'outgoing'

            # ¿Viene de venta no pagada? (info para internos y outgoing)
            picking.is_sale_unpaid = (
                has_sale and auth_state not in ('paid', 'authorized', False)
            )

            # ¿Autorizado? Solo aplica a outgoing
            if is_outgoing and has_sale:
                picking.is_delivery_authorized = auth_state in ('paid', 'authorized')
            else:
                picking.is_delivery_authorized = True

            # ¿Requiere auth? Solo outgoing de venta sin pago/auth
            picking.requires_delivery_auth = (
                is_outgoing and has_sale
                and auth_state not in ('paid', 'authorized', False)
            )