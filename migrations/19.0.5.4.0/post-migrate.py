"""Borra las actividades acumuladas de autorización de ENTREGA.

Cada solicitud creaba una actividad por aprobador, y al autorizar nadie las
cerraba: quedaban abiertas para siempre. El reloj del systray se llenaba de
pendientes que ya no existían y dejaba de significar algo.

A partir de esta versión el flujo NO crea actividades (avisa por mención de
chatter, que sí notifica por inbox y correo). Esto limpia las que ya se
acumularon.

ALCANCE: SOLO las actividades cuyo documento es una solicitud de
autorización de entrega (res_model = 'delivery.auth.request'). Ese modelo
no tiene otro uso, así que no hay forma de llevarse por delante una
actividad ajena. NO se tocan:
  · las de Logística sobre la orden de venta (pago confirmado, autorización
    manual, entregar material a taller) — esas SÍ son trabajo que alguien
    cierra;
  · las de autorización de PRECIOS, que se limpian desde
    inventory_shopping_cart.
"""
import logging

from odoo import api, SUPERUSER_ID

_logger = logging.getLogger(__name__)


def migrate(cr, version):
    if not version:
        return

    env = api.Environment(cr, SUPERUSER_ID, {})
    actividades = env['mail.activity'].search(
        [('res_model', '=', 'delivery.auth.request')])
    if not actividades:
        _logger.info(
            '[sale_delivery_auth] No había actividades de autorización de '
            'entrega que borrar.')
        return

    # Se deja constancia de a quién se le limpió el reloj: si alguien
    # reclama un pendiente perdido, aquí está el detalle.
    por_usuario = {}
    for act in actividades:
        login = act.user_id.login or '(sin usuario)'
        por_usuario[login] = por_usuario.get(login, 0) + 1
    _logger.info(
        '[sale_delivery_auth] Borrando %s actividad(es) de autorización de '
        'entrega: %s',
        len(actividades),
        ', '.join('%s=%s' % (k, v) for k, v in sorted(por_usuario.items())))

    actividades.unlink()
