# coding: utf-8

import json
import logging
import hmac
import hashlib
import binascii
import codecs
from collections import OrderedDict

import dateutil.parser
import pytz
from werkzeug import urls

from odoo import api, fields, models, _
from odoo.addons.payment.models.payment_acquirer import ValidationError
from odoo.addons.payment_onepay_cc.controllers.main import OnepayController
from odoo.tools.float_utils import float_compare
from odoo.http import request

_logger = logging.getLogger(__name__)


class AcquirerOnepay(models.Model):
    _inherit = 'payment.acquirer'

    provider = fields.Selection(selection_add=[
        ('onepay_cc', 'ONEPAY CC')
    ], ondelete={'onepay_cc': 'set default'})
    onepay_cc_email_account = fields.Char('Email', required_if_provider='onepay_cc', groups='base.group_user')
    onepay_cc_seller_account = fields.Char(
        'Merchant ID', groups='base.group_user',
        default='ONEPAY',
        help='The Merchant ID is used to ensure communications coming from Onepay are valid and secured.')
    onepay_cc_use_ipn = fields.Boolean('Use IPN', default=True, help='Onepay Instant Payment Notification', groups='base.group_user')
    onepay_cc_access_code = fields.Char(string='Access Code', default='D67342C2', help='Access Code provided by ONEPAY', groups='base.group_user')
    onepay_cc_secret_hash = fields.Char(string='Secret Hash', default='A3EFDFABA8653DF2342E8DAC29B51AF0', help='Secret Hash provided by ONEPAY', groups='base.group_user')
    onepay_cc_user = fields.Char(string='User',default='op01', help='User provided by ONEPAY', groups='base.group_user')
    onepay_cc_password = fields.Char(string='Password',default='op123456', help='Password provided by ONEPAY', groups='base.group_user')
    # Default onepay_cc fees
    fees_dom_fixed = fields.Float(default=0.35)
    fees_dom_var = fields.Float(default=3.4)
    fees_int_fixed = fields.Float(default=0.35)
    fees_int_var = fields.Float(default=3.9)

    def _get_feature_support(self):
        """Get advanced feature support by provider.

        Each provider should add its technical in the corresponding
        key for the following features:
            * fees: support payment fees computations
            * authorize: support authorizing payment (separates
                         authorization and capture)
            * tokenize: support saving payment data in a payment.tokenize
                        object
        """
        res = super(AcquirerOnepay, self)._get_feature_support()
        res['fees'].append('onepay_cc')
        return res

    @api.model
    def _get_onepay_cc_urls(self, environment = ''):
        """ Onepay URLS """
        return {
            'onepay_cc_form_url': 'https://onepay.vn/onecomm-pay/vpc.op',
            'onepay_cc_rest_url': 'https://onepay.vn/onecomm-pay/Vpcdps.op',
        }

    def onepay_cc_compute_fees(self, amount, currency_id, country_id):
        """ Compute onepay_cc fees.

            :param float amount: the amount to pay
            :param integer country_id: an ID of a res.country, or None. This is
                                       the customer's country, to be compared to
                                       the acquirer company country.
            :return float fees: computed fees
        """
        if not self.fees_active:
            return 0.0
        country = self.env['res.country'].browse(country_id)
        if country and self.company_id.sudo().country_id.id == country.id:
            percentage = self.fees_dom_var
            fixed = self.fees_dom_fixed
        else:
            percentage = self.fees_int_var
            fixed = self.fees_int_fixed
        fees = (percentage / 100.0 * amount + fixed) / (1 - percentage / 100.0)
        return fees

    def onepay_cc_form_generate_values(self, values):
        base_url = self.get_base_url()
        hashCode = ''       

        onepay_cc_tx_values = dict(values)
        onepay_cc_tx_values.update({
            'vpc_Version'       : 2,
            'vpc_Currency'      : values['currency'] and values['currency'].name or '',
            'vpc_Command'       :  'pay',
            'vpc_AccessCode'    : self.onepay_cc_access_code,
            'vpc_Merchant'      : self.onepay_cc_seller_account,
            'vpc_Locale'        : 'vn',
            'vpc_ReturnURL'     : urls.url_join(base_url, OnepayController._return_url),
            'vpc_MerchTxnRef'   : values['reference'],
            'vpc_OrderInfo'     : '%s: %s' % (self.company_id.name, values['reference']),
            'vpc_Amount'        : float(values['amount']) * 100,
            'vpc_TicketNo'      : request.httprequest.environ['REMOTE_ADDR'],
            'AgainLink'         : base_url,
            'Title'             : 'ONEPAY Payment Gateway',
            'vpc_SecureHash'    : hashCode,
            'vpc_Customer_Phone': values.get('partner_phone'),
            'vpc_Customer_Email': values.get('partner_email'),
            'vpc_Customer_Id'   : values.get('partner_id')
        })

        sorted_values = OrderedDict(sorted(onepay_cc_tx_values.items(), key=lambda x: x[0]))

        for key, value in sorted_values.items():
            if len(str(value)) > 0 and str(key)[0:4] == 'vpc_':
                hashCode += str(key)+"="+str(value)+"&"
        
        hashCode = hashCode.rstrip('&')
        secret = bytes.fromhex(self.onepay_cc_secret_hash)

        sorted_values['vpc_SecureHash'] = hmac.new(secret, bytes(hashCode, 'utf-8'), digestmod = hashlib.sha256).hexdigest().upper()

        return sorted_values

    def ksort(d, func = None):
        keys = d.keys()
        keys.sort(func)

        return keys      

    def onepay_cc_get_form_action_url(self):
        self.ensure_one()
        environment = 'prod' if self.state == 'enabled' else 'test'
        return self._get_onepay_cc_urls(environment)['onepay_cc_form_url']

    def onepay_cc_get_query_dr_url(self):
        self.ensure_one()
        environment = 'prod' if self.state == 'enabled' else 'test'
        return self._get_onepay_cc_urls(environment)['onepay_cc_rest_url']
    

class TxOnepay(models.Model):
    _inherit = 'payment.transaction'

    onepay_cc_txn_type = fields.Char('Transaction type')

    # --------------------------------------------------
    # FORM RELATED METHODS
    # --------------------------------------------------

    @api.model
    def _onepay_cc_form_get_tx_from_data(self, data):
        reference, txn_id = data.get('vpc_MerchTxnRef'), data.get('vpc_MerchTxnRef')
        if not reference or not txn_id:
            error_msg = _('ONEPAY CC: received data with missing reference (%s) or txn_id (%s)') % (reference, txn_id)
            _logger.info(error_msg)
            raise ValidationError(error_msg)

        # find tx -> @TDENOTE use txn_id ?
        txs = self.env['payment.transaction'].search([('reference', '=', reference)])
        if not txs or len(txs) > 1:
            error_msg = 'ONEPAY CC: received data for reference %s' % (reference)
            if not txs:
                error_msg += '; no order found'
            else:
                error_msg += '; multiple order found'
            _logger.info(error_msg)
            raise ValidationError(error_msg)
        return txs[0]

    def _onepay_cc_form_get_invalid_parameters(self, data):
        invalid_parameters = []
        _logger.info('Received a notification from Onepay with IPN version %s', data.get('notify_version'))
        if data.get('test_ipn'):
            _logger.warning(
                'Received a notification from Onepay using sandbox'
            ),

        # TODO: txn_id: shoudl be false at draft, set afterwards, and verified with txn details
        if self.acquirer_reference and data.get('vpc_MerchTxnRef') != self.acquirer_reference:
            invalid_parameters.append(('vpc_MerchTxnRef', data.get('vpc_MerchTxnRef'), self.acquirer_reference))
        # check what is buyed
        if float_compare(float(data.get('vpc_Amount', '0.0')) / 100, (self.amount + self.fees), 2) != 0:
            invalid_parameters.append(('vpc_Amount', data.get('vpc_Amount') / 100, '%.2f' % (self.amount + self.fees)))  # mc_gross is amount + fees
        if data.get('vpc_Currency', 'VND') != self.currency_id.name:
            invalid_parameters.append(('vpc_Currency', data.get('vpc_Currency', 'VND'), self.currency_id.name))
        if 'handling_amount' in data and float_compare(float(data.get('handling_amount')), self.fees, 2) != 0:
            invalid_parameters.append(('handling_amount', data.get('handling_amount'), self.fees))
        # check buyer
        if self.payment_token_id and data.get('vpc_CustomerId') != self.payment_token_id.acquirer_ref:
            invalid_parameters.append(('vpc_CustomerId', data.get('vpc_CustomerId'), self.payment_token_id.acquirer_ref))
        # check seller
        if data.get('receiver_id') and self.acquirer_id.onepay_cc_seller_account and data['receiver_id'] != self.acquirer_id.onepay_cc_seller_account:
            invalid_parameters.append(('receiver_id', data.get('receiver_id'), self.acquirer_id.onepay_cc_seller_account))
        if not data.get('receiver_id') or not self.acquirer_id.onepay_cc_seller_account:
            # Check receiver_email only if receiver_id was not checked.
            # In Onepay, this is possible to configure as receiver_email a different email than the business email (the login email)
            # In Odoo, there is only one field for the Onepay email: the business email. This isn't possible to set a receiver_email
            # different than the business email. Therefore, if you want such a configuration in your Onepay, you are then obliged to fill
            # the Merchant ID in the Onepay payment acquirer in Odoo, so the check is performed on this variable instead of the receiver_email.
            # At least one of the two checks must be done, to avoid fraudsters.
            if data.get('receiver_email') and data.get('receiver_email') != self.acquirer_id.onepay_cc_email_account:
                invalid_parameters.append(('receiver_email', data.get('receiver_email'), self.acquirer_id.onepay_cc_email_account))
            if data.get('business') and data.get('business') != self.acquirer_id.onepay_cc_email_account:
                invalid_parameters.append(('business', data.get('business'), self.acquirer_id.onepay_cc_email_account))

        return invalid_parameters

    def _onepay_cc_form_validate(self, data):
        status = int(data.get('vpc_TxnResponseCode'))
        former_tx_state = self.state
        res = {
            'acquirer_reference': data.get('vpc_MerchTxnRef'),
            'onepay_cc_txn_type': data.get('vpc_Command'),
        }
        if not self.acquirer_id.onepay_cc_access_code and not self.acquirer_id.onepay_cc_seller_account and status == 0:
            template = self.env.ref('payment_onepay_cc.mail_template_onepay_cc_invite_user_to_configure', False)
            if template:
                render_template = template._render({
                    'acquirer': self.acquirer_id,
                }, engine='ir.qweb')
                mail_body = self.env['mail.render.mixin']._replace_local_links(render_template)
                mail_values = {
                    'body_html': mail_body,
                    'subject': _('Add your Onepay account to Odoo'),
                    'email_to': self.acquirer_id.onepay_cc_email_account,
                    'email_from': self.acquirer_id.create_uid.email_formatted,
                    'author_id': self.acquirer_id.create_uid.partner_id.id,
                }
                self.env['mail.mail'].sudo().create(mail_values).send()

        if status == 0:
            try:
                # dateutil and pytz don't recognize abbreviations PDT/PST
                tzinfos = {
                    'PST': -8 * 3600,
                    'PDT': -7 * 3600,
                }
                date = dateutil.parser.parse(data.get('vpc_AuthenticationDate'), tzinfos=tzinfos).astimezone(pytz.utc).replace(tzinfo=None)
            except:
                date = fields.Datetime.now()
            res.update(date=date)
            self._set_transaction_done()
            if self.state == 'done' and self.state != former_tx_state:
                _logger.info('Validated Onepay payment for tx %s: set as done' % (self.reference))
                return self.write(res)
            return True
        elif status != 0:
            res.update(state_message=data.get('pending_reason', ''))
            self._set_transaction_pending()
            if self.state == 'pending' and self.state != former_tx_state:
                _logger.info('Received notification for Onepay payment %s: set as pending' % (self.reference))
                return self.write(res)
            return True
        else:
            error = 'Received unrecognized status for Onepay payment %s: %s, set as error' % (self.reference, status)
            res.update(state_message=error)
            self._set_transaction_cancel()
            if self.state == 'cancel' and self.state != former_tx_state:
                _logger.info(error)
                return self.write(res)
            return True
