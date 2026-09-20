# -*- coding: utf-8 -*-
from odoo import api, fields, models, _
from odoo.exceptions import UserError


class DeliveryAuthSendWizard(models.TransientModel):
    """«Entregar sin pago»: UN solo paso. El vendedor escribe el motivo
    (opcional) y pulsa «Enviar solicitud»: la solicitud nace y se envía a
    los aprobadores en el mismo clic. Antes había que crear el borrador y
    después pulsar «Enviar Solicitud» en otra pantalla (ambiguo)."""
    _name = 'delivery.auth.send.wizard'
    _description = 'Entregar sin pago: enviar solicitud de autorización'

    sale_order_id = fields.Many2one('sale.order', string='Orden', required=True, readonly=True)
    request_notes = fields.Text(
        string='Motivo',
        help="Por qué se pide entregar sin el pago completo. Lo ven los aprobadores.")
    amount_pending = fields.Monetary(string='Saldo pendiente', compute='_compute_amount_pending',
                                     currency_field='currency_id')
    currency_id = fields.Many2one(related='sale_order_id.currency_id')

    @api.depends('sale_order_id')
    def _compute_amount_pending(self):
        for wiz in self:
            order = wiz.sale_order_id
            paid = order.delivery_paid_amount if 'delivery_paid_amount' in order._fields else 0.0
            wiz.amount_pending = max((order.amount_total or 0.0) - (paid or 0.0), 0.0)

    def action_send(self):
        self.ensure_one()
        order = self.sale_order_id
        reason = order._som_delivery_staff_lock_reason()
        if reason:
            raise UserError(reason)
        Request = self.env['delivery.auth.request']
        active = order.delivery_auth_request_ids.filtered(lambda r: r.state in ('draft', 'requested'))
        request = active[:1]
        if request and request.state == 'requested':
            raise UserError(_('La orden %s ya tiene una solicitud enviada, pendiente de autorización.') % order.name)
        if request:  # borrador heredado del flujo anterior: se reutiliza
            request.request_notes = self.request_notes
        else:
            request = Request.create({
                'sale_order_id': order.id,
                'state': 'draft',
                'request_notes': self.request_notes,
            })
        request.action_request()
        return {
            'type': 'ir.actions.act_window',
            'name': _('Solicitud de Autorización'),
            'res_model': 'delivery.auth.request',
            'res_id': request.id,
            'view_mode': 'form',
            'target': 'current',
        }
