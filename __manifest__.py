{
    'name': 'Control de Autorización de Entregas',
    'version': '19.0.1.0.0',
    'category': 'Sales/Sales',
    'summary': 'Requiere autorización o pago total para marcar entregas como autorizadas',
    'description': """
        Este módulo añade un flujo informativo de control para las entregas:
        1. Si la Orden de Venta está 100% pagada, la entrega aparece como AUTORIZADA.
        2. Si no está pagada, el vendedor debe 'Solicitar Autorización'.
        3. Un gerente debe aprobar dicha solicitud.
        4. En el módulo de Inventario/Entregas aparece una alerta visual (Ribbon) indicando si se puede entregar o no.
    """,
    'author': 'Tu Nombre / Asistente AI',
    'depends': ['sale_management', 'stock', 'account'],
    'data': [
        'security/security.xml',
        'views/sale_order_views.xml',
        'views/stock_picking_views.xml',
    ],
    'installable': True,
    'application': False,
    'license': 'LGPL-3',
}
