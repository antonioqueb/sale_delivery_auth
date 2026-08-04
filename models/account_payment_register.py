# -*- coding: utf-8 -*-
"""Al registrar un pago de facturas ligadas a órdenes de venta, se crea una
actividad para el grupo 'Logística — Avisos' en cada orden: con el pago
registrado, logística puede programar/preparar la entrega."""
from odoo import models, _


class AccountPaymentRegister(models.TransientModel):
    _inherit = 'account.payment.register'

    def _create_payments(self):
        payments = super()._create_payments()
        for wizard in self:
            orders = wizard.line_ids.mapped(
                'move_id.invoice_line_ids.sale_line_ids.order_id')
            if not orders:
                continue
            payment = payments[:1]
            amount_txt = ''
            if payment:
                amount_txt = '%s %s' % (
                    '{:,.2f}'.format(payment.amount or 0.0),
                    payment.currency_id.name or '',
                )
            orders._som_schedule_logistics_activity(
                summary=_('Pago registrado — programar entrega'),
                note=_(
                    '<p>Se <b>registró un pago</b>%(amount)s aplicado a esta '
                    'orden (cliente: %(partner)s).</p>'
                    '<p>Validar condiciones y programar la entrega.</p>'
                ) % {
                    'amount': (' de <b>%s</b>' % amount_txt) if amount_txt else '',
                    'partner': orders[:1].partner_id.display_name or '',
                },
            )
        return payments
