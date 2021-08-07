# -*- coding: utf-8 -*-

{
    'name': 'Onepay Payment Acquirer',
    'category': 'Accounting/Payment Acquirers',
    'sequence': 342,
    'summary': 'Payment Acquirer: Onepay Implementation',
    'version': '1.0',
    'description': """Onepay Payment Acquirer""",
    'depends': ['payment'],
    'data': [
        'views/payment_views.xml',
        'views/payment_onepay_templates.xml',
        'data/payment_acquirer_data.xml',
    ],
    'installable': True,
    'application': True,
    'post_init_hook': 'create_missing_journal_for_acquirers',
    'uninstall_hook': 'uninstall_hook',
}
