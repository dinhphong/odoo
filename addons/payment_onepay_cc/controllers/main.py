# -*- coding: utf-8 -*-

import json
import logging
import pprint
from collections import OrderedDict
import hmac
import hashlib
import binascii

import requests
import werkzeug
from werkzeug import urls

from odoo import http
from odoo.addons.payment.models.payment_acquirer import ValidationError
from odoo.http import request

_logger = logging.getLogger(__name__)


class OnepayController(http.Controller):
    _notify_url = '/payment/onepay_cc/ipn/'
    _return_url = '/payment/onepay_cc/dpn/'
    _cancel_url = '/payment/onepay_cc/cancel/'

    def _parse_pdt_response(self, response):
        lines = [line for line in response.split('&') if line]
        status = 'FAIL'

        for line in lines:
            split = line.split('=')
            if split[0] == 'vpc_TxnResponseCode' and int(split[1]) == 0:
                status = 'SUCCESS'

        return status

    def onepay_cc_validate_data(self, **post):
        """ Onepay IPN: three steps validation to ensure data correctness

         - step 1: return an empty HTTP 200 response -> will be done at the end
           by returning ''
         - step 2: POST the complete, unaltered message back to Onepay (preceded
           by cmd=_notify-validate or _notify-synch for PDT), with same encoding
         - step 3: onepay_cc send either VERIFIED or INVALID (single word) for IPN
                   or SUCCESS or FAIL (+ data) for PDT

        Once data is validated, process it. """
        res = False
        post['cmd'] = '_notify-validate'
        reference = post.get('vpc_MerchTxnRef')
        tx = None
        if reference:
            tx = request.env['payment.transaction'].sudo().search([('reference', '=', reference)])
        if not tx:
            # we have seemingly received a notification for a payment that did not come from
            # odoo, acknowledge it otherwise onepay_cc will keep trying
            _logger.warning('received notification for unknown payment reference')
            return False

        onepay_cc_url = tx.acquirer_id.onepay_cc_get_query_dr_url()

        params = dict({
            'vpc_AccessCode': tx.acquirer_id.onepay_cc_access_code,
            'vpc_Command': 'queryDR',
            'vpc_Version': '1',
            'vpc_MerchTxnRef': post['vpc_MerchTxnRef'],
            'vpc_Merchant': tx.acquirer_id.onepay_cc_seller_account,
            'vpc_Password': tx.acquirer_id.onepay_cc_password,
            'vpc_SecureHash': '',
            'vpc_User': tx.acquirer_id.onepay_cc_user
        })

        sorted_values = OrderedDict(sorted(params.items(), key=lambda x: x[0]))  
        secret = bytes.fromhex(tx.acquirer_id.onepay_cc_secret_hash)

        url = ''
        
        for key, value in sorted_values.items():
            if len(str(value)) > 0 and str(key)[0:4] == 'vpc_':
                url += str(key)+"="+str(value)+"&"

        url = url.rstrip('&')  
        sorted_values['vpc_SecureHash'] = hmac.new(secret, bytes(url, 'utf-8'), digestmod = hashlib.sha256).hexdigest().upper()

        urequest = requests.get(onepay_cc_url + '?' + url)
        urequest.raise_for_status()
        resp = urequest.text

        resp = self._parse_pdt_response(resp)

        if resp == 'SUCCESS':
            _logger.info('ONEPAY CC: validated data')
            res = request.env['payment.transaction'].sudo().form_feedback(post, 'onepay_cc')
            if not res and tx:
                tx._set_transaction_error('Validation error occured. Please contact your administrator.')
        elif resp == 'FAIL':
            _logger.warning('ONEPAY CC: answered INVALID/FAIL on data verification')
            if tx:
                tx._set_transaction_error('Transaction failed, please try again or contact administrator.')
        else:
            _logger.warning('ONEPAY CC: unrecognized onepay_cc answer, received %s instead of VERIFIED/SUCCESS or INVALID/FAIL (validation: %s)' % (resp, 'IPN/DPN'))
            if tx:
                tx._set_transaction_error('Unrecognized error from Onepay. Please contact your administrator.')
        return res

    @http.route('/payment/onepay_cc/ipn/', type='http', auth='public', methods=['POST'], csrf=False)
    def onepay_cc_ipn(self, **post):
        """ Onepay IPN. """
        _logger.info('Beginning Onepay IPN form_feedback with post data %s', pprint.pformat(post))  # debug
        try:
            self.onepay_cc_validate_data(**post)
        except ValidationError:
            _logger.exception('Unable to validate the Onepay payment')
        return ''

    @http.route('/payment/onepay_cc/dpn', type='http', auth="public", methods=['POST', 'GET'], csrf=False)
    def onepay_cc_dpn(self, **post):
        """ Onepay DPN """
        _logger.info('Beginning Onepay DPN form_feedback with post data %s', pprint.pformat(post))  # debug
        try:
            res = self.onepay_cc_validate_data(**post)
        except ValidationError:
            _logger.exception('Unable to validate the Onepay payment')
        return werkzeug.utils.redirect('/payment/process')

    @http.route('/payment/onepay_cc/cancel', type='http', auth="public", csrf=False)
    def onepay_cc_cancel(self, **post):
        """ When the user cancels its Onepay payment: GET on this route """
        _logger.info('Beginning Onepay cancel with post data %s', pprint.pformat(post))  # debug
        return werkzeug.utils.redirect('/payment/process')
