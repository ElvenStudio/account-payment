# -*- coding: utf-8 -*-
# © 2018 Domenico Stragapede <d.stragapede@elvenstudio.it>
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl).

from openerp.osv import osv


class AccountVoucher(osv.osv):
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

        return_cls = self.pool.get('payment.return')
        move_line_cls = self.pool.get('account.move.line')

        deleted_line_cr_ids = []
        line_cr_by_move = {}
        for line in default['value']['line_cr_ids']:
            if type(line) == tuple:
                deleted_line_cr_ids.append(line)
            else:
                line_cr_by_move[line['move_line_id']] = line

        for move_line_id in line_cr_by_move.keys():
            move_line = move_line_cls.browse(cr, uid, [move_line_id], context=context)
            domain = [('move_id', '=', move_line.move_id.id)]
            return_id = return_cls.search(cr, uid, domain, context=context)
            if return_id:
                reconciled_lines = move_line.reconcile_partial_id.line_partial_ids
                lines_to_remove = reconciled_lines.filtered(lambda l: l.id < move_line_id)
                for line in lines_to_remove:
                    if line.id in line_cr_by_move:
                        line_cr_by_move.pop(line.id)

        line_cr_ids = [line_cr_by_move[move_id] for move_id in line_cr_by_move]
        default['value']['line_cr_ids'] = deleted_line_cr_ids + line_cr_ids
        return default
