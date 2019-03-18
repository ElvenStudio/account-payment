# -*- coding: utf-8 -*-

from openerp import models, api, _
from openerp.exceptions import ValidationError


class AccountMoveLine(models.Model):
    _inherit = 'account.move.line'

    @api.multi
    def unlink(self):
        payment_return_lines = self.env['payment.return.line'].search(
            [('move_line_ids', 'in', self.ids)])

        if payment_return_lines:
            move_ref = ', '.join(self.mapped('move_id').mapped('name'))
            return_ref = ', '.join(payment_return_lines.mapped('return_id').mapped('name'))
            raise ValidationError(_(
                'You cannot delete %s ! \n'
                'One or more payment returns are linked to it. '
                'Please cancel them before.\n'
                'Related payment returns: %s') % (move_ref, return_ref))

        return super(AccountMoveLine, self).unlink()
