from odoo import models, fields, api, _
from odoo.exceptions import UserError


class DeliveryAuthRejectWizard(models.TransientModel):
    _name = 'delivery.auth.reject.wizard'
    _description = 'Wizard para Rechazar Solicitud de Autorización'

    request_id = fields.Many2one(
        'delivery.auth.request', string='Solicitud',
        required=True, ondelete='cascade',
    )
    rejection_notes = fields.Text(
        string='Motivo del Rechazo', required=True,
    )

    def action_confirm_reject(self):
        self.ensure_one()
        if not self.rejection_notes:
            raise UserError(_('Debe indicar un motivo de rechazo.'))

        self.request_id.write({
            'state': 'rejected',
            'approved_by_id': self.env.uid,
            'approval_date': fields.Datetime.now(),
            'rejection_notes': self.rejection_notes,
        })
        # El estado de la orden lo deriva el cómputo (solicitud rechazada).
        self.request_id.message_post(
            body=_(
                'Solicitud <b>RECHAZADA</b> por <b>%s</b>.<br/>Motivo: %s',
                self.env.user.name,
                self.rejection_notes,
            ),
            message_type='notification',
            subtype_xmlid='mail.mt_note',
        )
        # Avisar al solicitante (la nota no notifica).
        req = self.request_id
        if req.requested_by_id and req.requested_by_id.id != self.env.uid:
            req.activity_schedule(
                'mail.mail_activity_data_todo',
                user_id=req.requested_by_id.id,
                summary=_('Entrega rechazada: %s') % (req.sale_order_id.name or ''),
                note=_('%(user)s rechazó la autorización de entrega. Motivo: %(reason)s') % {
                    'user': self.env.user.name,
                    'reason': self.rejection_notes,
                },
            )
            req.message_post(
                body=_(
                    '<p>Autorización de entrega de <b>%s</b> rechazada por %s.</p>',
                    req.sale_order_id.name or '',
                    self.env.user.name,
                ),
                partner_ids=req.requested_by_id.partner_id.ids,
                message_type='comment',
                subtype_xmlid='mail.mt_comment',
            )
        return {'type': 'ir.actions.act_window_close'}