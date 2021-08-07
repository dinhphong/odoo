# coding: utf-8

import base64
import json
import binascii
from collections import OrderedDict
import hashlib
import hmac
import logging
from itertools import chain

from werkzeug import urls

from odoo import api, fields, models, tools, _
from odoo.addons.payment.models.payment_acquirer import ValidationError
from odoo.addons.payment_onepay.controllers.main import OnepayController
from odoo.tools.pycompat import to_text

_logger = logging.getLogger(__name__)

# https://mtf.onepay.vn/developer/resource/documents/docx/quy_trinh_tich_hop-noidia.pdf

CURRENCY_CODE_MAPS = {
    "BHD": 3,
    "CVE": 0,
    "DJF": 0,
    "GNF": 0,
    "IDR": 0,
    "JOD": 3,
    "JPY": 0,
    "KMF": 0,
    "KRW": 0,
    "KWD": 3,
    "LYD": 3,
    "OMR": 3,
    "PYG": 0,
    "RWF": 0,
    "TND": 3,
    "UGX": 0,
    "VND": 0,
    "VUV": 0,
    "XAF": 0,
    "XOF": 0,
    "XPF": 0,
}
"""
(Live) URL Payment: https://onepay.vn/onecomm-pay/vpc.op
(Test) URL Payment: https://mtf.onepay.vn/onecomm-pay/vpc.op

onepay_merchant_account
MerchantID: ONEPAY 

onepay_skin_code
Accesscode: D67342C2

onepay_skin_hmac_key
Hashcode: A3EFDFABA8653DF2342E8DAC29B51AF0
"""


class AcquirerOnepay(models.Model):
    _inherit = 'payment.acquirer'

    provider = fields.Selection(selection_add=[
        ('onepay', 'Onepay')
    ], ondelete={'onepay': 'set default'})
    onepay_merchant_account = fields.Char('Merchant Account', required_if_provider='onepay', groups='base.group_user')
    onepay_skin_code = fields.Char('Access code', required_if_provider='onepay', groups='base.group_user')
    onepay_skin_hmac_key = fields.Char('Hash code', required_if_provider='onepay', groups='base.group_user')

    @api.model
    def _onepay_convert_amount(self, amount, currency):
        """
        onepay requires the amount to be multiplied by 10^k,
        where k depends on the currency code.
        """
        #k = CURRENCY_CODE_MAPS.get(currency.name, 2)
        #vpc_Amount = int(tools.float_round(amount, k) * (10**k))
        return vpc_Amount

    @api.model
    def _get_onepay_urls(self, environment):
        """ TODO: debug """
        error_msg = _('>>>>> environment = (%s) ') % (environment)
        _logger.info(error_msg)
        if environment == 'prod':
            return {
                'onepay_form_url': 'https://onepay.vn/onecomm-pay/vpc.op'
            }
        else:
            return {
                'onepay_form_url': 'https://mtf.onepay.vn/onecomm-pay/vpc.op'
            }

    def _onepay_generate_merchant_sig_sha256(self, inout, values):
        """ Generate the shasign for incoming or outgoing communications., when using the SHA-256
        signature.

        :param string inout: 'in' (odoo contacting onepay) or
                            'out' (onepay contacting odoo).
                            In this last case only some fields should be contained
                            (see e-Commerce basic)
        :param dict values: transaction values

        :return string: shasign
        """
        def escapeVal(val):
            return val.replace(val.replace('\\', '\\\\')).replace(':', '\\:')

        def signParams(parms):
            signing_string = ':'.join(
                escapeVal(v)
                for v in chain(parms.keys(), parms.values())
            )
            hm = hmac.new(hmac_key, signing_string.encode('utf-8'), hashlib.sha256)
            return base64.b64encode(hm.digest())

        assert inout in ('in', 'out')
        assert self.provider == 'onepay'

        if inout == 'in':
            # All the fields sent to onepay must be included in the signature. ALL the fucking
            # fields, despite what is claimed in the documentation. For example, in
            # https://mtf.onepay.vn/developer, it is stated: "The resURL parameter does
            # not need to be included in the signature." It's a trap, it must be included as well!
            keys = [
                'vpc_MerchTxnRef', 'vpc_Amount', 'vpc_CurrencyCode', 'shipBeforeDate', 'vpc_AccessCode',
                'vpc_Merchant', 'sessionValidity', 'merchantReturnData', 'shopperEmail',
                'shopperReference', 'allowedMethods', 'blockedMethods', 'offset',
                'shopperStatement', 'recurringContract', 'billingAddressType',
                'deliveryAddressType', 'brandCode', 'countryCode', 'vpc_Locale', 'orderData',
                'offerEmail', 'resURL',
            ]
        else:
            keys = [
                'authResult', 'vpc_MerchTxnRef', 'merchantReturnData', 'paymentMethod',
                'pspReference', 'vpc_Locale', 'vpc_AccessCode',
            ]

        hmac_key = binascii.a2b_hex(self.onepay_skin_hmac_key.encode('ascii'))
        raw_values = {k: values.get(k, '') for k in keys if k in values}
        raw_values_ordered = OrderedDict(sorted(raw_values.items(), key=lambda t: t[0]))
        return signParams(raw_values_ordered)

    def _onepay_generate_merchant_sig(self, inout, values):
        """ Generate the shasign for incoming or outgoing communications, when using the SHA-1
        signature (deprecated by onepay).

        :param string inout: 'in' (odoo contacting onepay) or
                            'out' (onepay contacting odoo).
                             In this last case only some
                             fields should be contained (see e-Commerce basic)
        :param dict values: transaction values

        :return string: shasign
        """
        assert inout in ('in', 'out')
        assert self.provider == 'onepay'

        if inout == 'in':
            keys = "vpc_Amount vpc_CurrencyCode shipBeforeDate vpc_MerchTxnRef vpc_AccessCode vpc_Merchant sessionValidity shopperEmail shopperReference recurringContract allowedMethods blockedMethods shopperStatement merchantReturnData billingAddressType deliveryAddressType offset".split()
        else:
            keys = "authResult pspReference vpc_MerchTxnRef vpc_AccessCode merchantReturnData".split()

        def get_value(key):
            if values.get(key):
                return values[key]
            return ''

        sign = ''.join('%s' % get_value(k) for k in keys).encode('ascii')
        key = self.onepay_skin_hmac_key.encode('ascii')
        return base64.b64encode(hmac.new(key, sign, hashlib.sha1).digest())

    def onepay_form_generate_values(self, values):
        base_url = self.get_base_url()
        _logger.info('>>>>> base_url=%s', base_url)
        # tmp
        import datetime
        from dateutil import relativedelta

        vpc_Amount = self._onepay_convert_amount(values['amount'], values['currency'])
        tmp_date = datetime.date.today() + relativedelta.relativedelta(days=1)
        values.update({
            'vpc_MerchTxnRef': values['reference'],
            'vpc_Amount': '%d' % vpc_Amount,
            'vpc_CurrencyCode': values['currency'] and values['currency'].name or '',
            'shipBeforeDate': tmp_date,
            'vpc_AccessCode': self.onepay_skin_code,
            'vpc_Merchant': self.onepay_merchant_account,
            'vpc_Locale': values.get('partner_lang'),
            'sessionValidity': tmp_date,
            'resURL': urls.url_join(base_url, OnepayController._return_url),
            'vpc_Version': '2',
            'merchantReturnData': json.dumps({'return_url': '%s' % values.pop('return_url')}) if values.get(
                'return_url') else False,
        })
        values['vpc_SecureHash'] = self._onepay_generate_merchant_sig('in', values)
        return values

    def onepay_get_form_action_url(self):
        self.ensure_one()
        environment = 'prod' if self.state == 'enabled' else 'test'
        return self._get_onepay_urls(environment)['onepay_form_url']


class TxOnepay(models.Model):
    _inherit = 'payment.transaction'

    # --------------------------------------------------
    # FORM RELATED METHODS
    # --------------------------------------------------

    @api.model
    def _onepay_form_get_tx_from_data(self, data):
        reference, pspReference = data.get('vpc_MerchTxnRef'), data.get('pspReference')
        if not reference or not pspReference:
            error_msg = _('onepay: received data with missing reference (%s) or missing pspReference (%s)') % (reference, pspReference)
            _logger.info(error_msg)
            raise ValidationError(error_msg)

        # find tx -> @TDENOTE use pspReference ?
        tx = self.env['payment.transaction'].search([('reference', '=', reference)])
        if not tx or len(tx) > 1:
            error_msg = _('onepay: received data for reference %s') % (reference)
            if not tx:
                error_msg += _('; no order found')
            else:
                error_msg += _('; multiple order found')
            _logger.info(error_msg)
            raise ValidationError(error_msg)

        # verify shasign
        if len(tx.acquirer_id.onepay_skin_hmac_key) == 64:
            shasign_check = tx.acquirer_id._onepay_generate_merchant_sig_sha256('out', data)
        else:
            shasign_check = tx.acquirer_id._onepay_generate_merchant_sig('out', data)
        if to_text(shasign_check) != to_text(data.get('vpc_SecureHash')):
            error_msg = _('onepay: invalid SecureHash, received %s, computed %s') % (data.get('vpc_SecureHash'), shasign_check)
            _logger.warning(error_msg)
            raise ValidationError(error_msg)

        return tx

    def _onepay_form_get_invalid_parameters(self, data):
        invalid_parameters = []

        # reference at acquirer: pspReference
        if self.acquirer_reference and data.get('pspReference') != self.acquirer_reference:
            invalid_parameters.append(('pspReference', data.get('pspReference'), self.acquirer_reference))
        # seller
        if data.get('vpc_AccessCode') != self.acquirer_id.onepay_skin_code:
            invalid_parameters.append(('vpc_AccessCode', data.get('vpc_AccessCode'), self.acquirer_id.onepay_skin_code))
        # result
        if not data.get('authResult'):
            invalid_parameters.append(('authResult', data.get('authResult'), 'something'))

        return invalid_parameters

    def _onepay_form_validate(self, data):
        status = data.get('authResult', 'PENDING')
        if status == 'AUTHORISED':
            self.write({'acquirer_reference': data.get('pspReference')})
            self._set_transaction_done()
            return True
        elif status == 'PENDING':
            self.write({'acquirer_reference': data.get('pspReference')})
            self._set_transaction_pending()
            return True
        else:
            error = _('onepay: feedback error')
            _logger.info(error)
            self.write({'state_message': error})
            self._set_transaction_cancel()
            return False
