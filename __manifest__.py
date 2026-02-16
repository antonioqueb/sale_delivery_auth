{
    'name': 'Control de Autorización de Entregas',
    'version': '19.0.2.0.0',
    'category': 'Sales/Sales',
    'summary': 'Requiere autorización o pago total para permitir entregas de salida',
    'description': """
        Control profesional de autorizaciones de entrega:
        - Solo aplica a operaciones de SALIDA (outgoing).
        - Si la Orden de Venta está 100% pagada, la entrega se marca como AUTORIZADA automáticamente.
        - Si no está pagada, el vendedor debe Solicitar Autorización.
        - Un gerente aprueba/rechaza desde un tablero dedicado de solicitudes.
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