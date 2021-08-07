# -*- coding: utf-8 -*-
#############################################################################
#
#    Copyright (C) 2021-TODAY TIFLA (<https://www.tifla.vn>)
#    Author: Phong Phan & M.Thien
#
#    You can modify it under the terms of the GNU LESSER
#    GENERAL PUBLIC LICENSE (LGPL v3), Version 3.
#
#    This program is distributed in the hope that it will be useful,
#    but WITHOUT ANY WARRANTY; without even the implied warranty of
#    MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
#    GNU LESSER GENERAL PUBLIC LICENSE (LGPL v3) for more details.
#
#    You should have received a copy of the GNU LESSER GENERAL PUBLIC LICENSE
#    (LGPL v3) along with this program.
#    If not, see <http://www.gnu.org/licenses/>.
#
#############################################################################
{
    'name': 'OnePAY Payment Acquirer',
    'category': 'Accounting/Payment Acquirers',
    'sequence': 368,
    'summary': 'Payment Acquirer: OnePAY Implementation',
    'version': '1.0',
    'description': """OnePAY Payment Acquirer""",
    'depends': ['payment'],
    'data': [
        'views/payment_views.xml',
        'views/payment_onepay_templates.xml',
        'data/payment_acquirer_data.xml',
        'data/payment_onepay_email_data.xml',
    ],
    'installable': True,
    'application': True,
    'post_init_hook': 'create_missing_journal_for_acquirers',
    'uninstall_hook': 'uninstall_hook',
    'license': 'LGPL-3',
    'price': 99.99,
    'currency': 'USD',
}
