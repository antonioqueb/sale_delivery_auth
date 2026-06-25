{
    'name': 'Control de Autorización de Entregas',
    'version': '19.0.3.0.1',
    'category': 'Sales/Sales',
    'summary': 'Requiere autorización o pago total (100%) para permitir entregas de salida',
    'description': """
        Control profesional de autorizaciones de entrega (proceso VIVO):
        - Solo aplica a operaciones de SALIDA (outgoing).
        - Solo deja entregar si el 100% del total de la Orden está PAGADO
          (suma del dinero realmente recibido en facturas posteadas, incluidos
          anticipos; pagar una parte NO basta).
        - Si no está pagada, el vendedor debe Solicitar Autorización y un gerente
          aprueba/rechaza desde un tablero dedicado.
        - La autorización manual se hace al TOTAL del momento: si después se
          agrega material y sube la deuda, la autorización deja de ser válida y
          se vuelve a requerir pago o nueva autorización.
        - Verificación EN VIVO al validar la entrega.
        - Registro completo de quién solicitó, quién autorizó, cuándo, y notas.
    """,
    'author': 'Alphaqueb Consulting',
    'depends': ['sale_management', 'stock', 'account'],
    'data': [
        'security/security.xml',
        'security/ir.model.access.csv',
        'views/delivery_auth_request_views.xml',
        'views/sale_order_views.xml',
        'views/stock_picking_views.xml',
        'wizard/reject_wizard_views.xml',
    ],
    'installable': True,
    'application': False,
    'license': 'LGPL-3',
}