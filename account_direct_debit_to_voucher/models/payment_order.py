# -*- coding: utf-8 -*-
#
#   See __openerp__.py about license
#

from openerp import models, api


class PaymentOrder(models.Model):
    _inherit = 'payment.order'

    @api.multi
    def _get_voucher_action(self):
        self.ensure_one()
        if self.payment_order_type == 'debit':
            action_res = self.env['ir.actions.act_window'].for_xml_id('account_voucher', 'action_vendor_receipt')
        else:
            action_res = super(PaymentOrder, self)._get_voucher_action()

        return action_res

    @api.multi
    def _build_voucher_header(self, partner_id, payment_lines):
        self.ensure_one()
        voucher_vals = super(PaymentOrder, self)._build_voucher_header(partner_id, payment_lines)

        if self.payment_order_type == 'debit':
            voucher_vals['type'] = 'receipt'
            voucher_vals['account_id'] = self.mode.journal.default_credit_account_id.id,

        return voucher_vals

    @api.model
    def _build_voucher_lines(self, payment_lines, voucher):
        vals_list = super(PaymentOrder, self)._build_voucher_lines(payment_lines, voucher)
        if voucher.type == 'receipt':
            for line in vals_list:
                line['type'] = 'cr'

        return vals_list
