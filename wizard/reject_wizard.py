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
        self.request_id.sale_order_id.write({'delivery_auth_state': 'pending'})
        self.request_id.message_post(
            body=_(
                'Solicitud <b>RECHAZADA</b> por <b>%s</b>.<br/>Motivo: %s',
                self.env.user.name,
                self.rejection_notes,
            ),
            message_type='notification',
            subtype_xmlid='mail.mt_note',
        )
        return {'type': 'ir.actions.act_window_close'}