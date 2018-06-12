# -*- coding: utf-8 -*-
# © 2018 Domenico Stragapede <d.stragapede@elvenstudio.it>
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl).

from openerp import models


class AccountVoucher(models.Model):
    _inherit = 'account.voucher'

    def recompute_voucher_lines(
            self, cr, uid, ids,
            partner_id, journal_id, price, currency_id, ttype, date,
            context=None):

        # call the super and evaluate all the voucher lines
        default = super(AccountVoucher, self).recompute_voucher_lines(
            cr, uid, ids,
            partner_id, journal_id, price, currency_id, ttype, date,
            context=context)

        if 'value' not in default or 'line_cr_ids' not in default['value']:
            return default

        return_line_cls = self.pool.get('payment.return.line')
        move_line_cls = self.pool.get('account.move.line')

        new_line_cr_ids = []
        for line in default['value']['line_cr_ids']:
            add_new_line = True

            # find the related move line
            ids = [line['move_line_id']]
            move_line = move_line_cls.browse(cr, uid, ids, context=context)

            # if the line is partially reconciled,
            # check if is related to a payment return
            if move_line.reconcile_partial_id:
                reconcile_partial_id = move_line.reconcile_partial_id.id
                domain = [('reconcile_id', '=', reconcile_partial_id)]
                return_line_id = return_line_cls.search(cr, uid, domain, context=context)

                if return_line_id:
                    return_line = return_line_cls.browse(
                        cr, uid, return_line_id, context=context)

                    # if the move is partially reconciled with a return,
                    # check if the move is into the return.
                    # if not, then the move is already reconciled but
                    # the method _remove_noise_in_o2m in account_voucher
                    # does not intercept this line as noise.
                    if move_line.move_id.id != return_line.return_id.move_id.id:
                        add_new_line = False

            if add_new_line:
                new_line_cr_ids.append(line)

        default['value']['line_cr_ids'] = new_line_cr_ids
        return default
