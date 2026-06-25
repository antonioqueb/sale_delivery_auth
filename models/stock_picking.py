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
        """Bloquear validación de entregas de salida sin autorización.

        Verificación EN VIVO (no se confía solo en el campo almacenado): la
        orden debe estar 100% pagada o tener autorización manual vigente para el
        total ACTUAL. Si se agregó material y subió la deuda, la autorización
        previa ya no aplica.
        """
        for picking in self:
            if picking.picking_type_code != 'outgoing' or not picking.sale_id:
                continue
            order = picking.sale_id
            if not order._delivery_is_authorized_now():
                raise UserError(_(
                    'No se puede validar la entrega "%s".\n\n'
                    'La orden de venta %s debe estar 100%% PAGADA o tener una '
                    'autorización de entrega vigente para el total actual.\n\n'
                    'Pagado: %s de %s %s.\n\n'
                    'Si se agregó material después de pagar/autorizar, vuelve a '
                    'pagar el saldo o solicita una nueva autorización desde la '
                    'Orden de Venta.',
                    picking.name,
                    order.name,
                    '{:,.2f}'.format(order.delivery_paid_amount or 0.0),
                    '{:,.2f}'.format(order.amount_total or 0.0),
                    order.currency_id.name or '',
                ))
        return super().button_validate()