# -*- coding: utf-8 -*-

import json
import logging
import pprint
import werkzeug

from odoo import http
from odoo.http import request

_logger = logging.getLogger(__name__)


class OnepayController(http.Controller):
    _return_url = '/payment/onepay/return/'

    @http.route([
        '/payment/onepay/return',
    ], type='http', auth='public', csrf=False)
    def onepay_return(self, **post):
        _logger.info('Beginning onepay form_feedback with post data %s', pprint.pformat(post))  # debug
        if post.get('authResult') not in ['CANCELLED']:
            request.env['payment.transaction'].sudo().form_feedback(post, 'onepay')
        return werkzeug.utils.redirect('/payment/process')

    @http.route([
        '/payment/onepay/notification',
    ], type='http', auth='public', methods=['POST'], csrf=False)
    def onepay_notification(self, **post):
        tx = post.get('vpc_MerchTxnRef') and request.env['payment.transaction'].sudo().search([('reference', 'in', [post.get('vpc_MerchTxnRef')])], limit=1)
        if post.get('eventCode') in ['AUTHORISATION'] and tx:
            states = (post.get('vpc_MerchTxnRef'), post.get('success'), tx.state)
            if (post.get('success') == 'true' and tx.state == 'done') or (post.get('success') == 'false' and tx.state in ['cancel', 'error']):
                _logger.info('Notification from onepay for the reference %s: received %s, state is %s', states)
            else:
                _logger.warning('Notification from onepay for the reference %s: received %s but state is %s', states)
        return '[accepted]'
