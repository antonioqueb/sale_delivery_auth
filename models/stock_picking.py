from odoo import models, fields, api, _
from odoo.exceptions import UserError


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

            picking.is_sale_unpaid = (
                has_sale and auth_state not in ('paid', 'authorized', False)
            )

            if is_outgoing and has_sale:
                picking.is_delivery_authorized = auth_state in ('paid', 'authorized')
            else:
                picking.is_delivery_authorized = True

            picking.requires_delivery_auth = (
                is_outgoing and has_sale
                and auth_state not in ('paid', 'authorized', False)
            )

    def button_validate(self):
        """Bloquear validación de entregas de salida sin autorización."""
        for picking in self:
            if picking.requires_delivery_auth:
                raise UserError(_(
                    'No se puede validar la entrega "%s".\n\n'
                    'La orden de venta %s no está pagada ni tiene autorización '
                    'de entrega aprobada.\n\n'
                    'Solicite la autorización desde la Orden de Venta antes de '
                    'validar esta entrega.',
                    picking.name,
                    picking.sale_id.name,
                ))
        return super().button_validate()