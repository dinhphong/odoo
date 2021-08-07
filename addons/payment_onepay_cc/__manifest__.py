# -*- coding: utf-8 -*-

{
    'name': 'ONEPAY Credit/Debit Card Payment Acquirer',
    'category': 'Accounting/Payment Acquirers',
    'sequence': 365,
    'summary': 'Payment Acquirer: ONEPAY Credit/Debit Implementation',
    'version': '1.0',
    'description': """ONEPAY Credit/Debit Payment Acquirer""",
    'depends': ['payment'],
    'data': [
        'views/payment_views.xml',
        'views/payment_onepay_cc_templates.xml',
        'data/payment_acquirer_data.xml',
        'data/payment_onepay_cc_email_data.xml',
    ],
    'installable': True,
    'application': True,
    'post_init_hook': 'create_missing_journal_for_acquirers',
    'uninstall_hook': 'uninstall_hook',
    'license': 'LGPL-3',
}
