# -*- coding: utf-8 -*-
#
#   See __openerp__.py about license
#

from openerp import models, fields, api, _
from openerp.exceptions import Warning


class PaymentOrder(models.Model):
    _inherit = 'payment.order'

    has_payment_lines_to_pay = fields.Boolean(
        compute='_compute_has_payment_lines_to_pay'
    )

    has_vouchers = fields.Boolean(
        compute='_compute_has_vouchers'
    )

    voucher_ids = fields.Many2many(
        comodel_name='account.voucher',
        string=_('Vouchers'),
        readonly=True
    )

    @api.multi
    def _compute_has_vouchers(self):
        for order in self:
            order.has_vouchers = len(order.voucher_ids) > 0

    @api.multi
    def _compute_has_payment_lines_to_pay(self):
        for order in self:
            lines_to_pay = order.line_ids.filtered(lambda l: not l.move_line_id.reconcile_id)
            order.has_payment_lines_to_pay = len(lines_to_pay) > 0

    @api.multi
    def _get_lines_by_partner(self):
        self.ensure_one()

        if self.state != 'done':
            raise Warning(_("Payment order %s is not in 'done' state") % self.reference)

        lines_by_partner = {}
        for line in self.line_ids:
            if not line.move_line_id.reconcile_id:
                if line.partner_id.id not in lines_by_partner:
                    lines_by_partner[line.partner_id.id] = self.env['payment.line']

                lines_by_partner[line.partner_id.id] |= line

        if not lines_by_partner:
            raise Warning(_("Payment order %s is already fully reconciled") % self.reference)

        return lines_by_partner

    @api.multi
    def _get_voucher_action(self):
        self.ensure_one()
        return self.env['ir.actions.act_window'].for_xml_id('account_voucher', 'action_vendor_payment')

    @api.model
    def _compute_lines_total(self, payment_lines):
        return sum([l.amount_currency for l in payment_lines])

    @api.model
    def _get_currency_id(self, payment_lines):
        currency_ids = payment_lines.mapped('currency').ids
        if len(currency_ids) > 1:
            raise Warning(_("Every order lines must have the same currency"))

        return currency_ids[0]

    @api.multi
    def _build_voucher_header(self, partner_id, payment_lines):
        self.ensure_one()
        total = self._compute_lines_total(payment_lines)
        currency_id = self._get_currency_id(payment_lines)

        return {
            'type': 'payment',
            'name': self.reference,
            'partner_id': partner_id,
            'journal_id': self.mode.journal.id,
            'account_id': self.mode.journal.default_debit_account_id.id,
            'company_id': self.company_id.id,
            'currency_id': currency_id,
            'date': self.date_done,
            'amount': total,
        }

    @api.model
    def _build_voucher_lines(self, payment_lines, voucher):
        vals_list = []
        for line in payment_lines:
            vals = {
                'voucher_id': voucher.id,
                'type': 'dr',
                'account_id': line.move_line_id.account_id.id,
                'amount': line.amount_currency,
                'reconcile': True,
                'move_line_id': line.move_line_id.id,
            }
            vals_list.append(vals)

        return vals_list

    @api.multi
    def generate_vouchers(self):
        self.ensure_one()
        voucher_model = self.env['account.voucher']
        voucher_line_model = self.env['account.voucher.line']

        order_vouchers = self.env['account.voucher']
        lines_by_partner = self._get_lines_by_partner()
        for partner_id in lines_by_partner:
            payment_lines = lines_by_partner[partner_id]

            voucher_vals = self._build_voucher_header(partner_id, payment_lines)
            voucher = voucher_model.create(voucher_vals)

            line_vals_list = self._build_voucher_lines(payment_lines, voucher)

            for line_vals in line_vals_list:
                voucher_line_model.create(line_vals)

            order_vouchers |= voucher

        self.voucher_ids = order_vouchers.ids
        return self.show_vouchers()

    @api.multi
    def show_vouchers(self):
        self.ensure_one()
        action_res = self._get_voucher_action()
        action_res['domain'] = [('id', 'in', self.voucher_ids.ids)]
        return action_res
