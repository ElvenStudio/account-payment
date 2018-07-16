# -*- encoding: utf-8 -*-
##############################################################################
#
#    Module Writen to OpenERP, Open Source Management Solution
#    Copyright (C) 2015 OBERTIX FREE SOLUTIONS (<http://obertix.net>).
#                       cubells <vicent@vcubells.net>
#
#    All Rights Reserved
#
#    This program is free software: you can redistribute it and/or modify
#    it under the terms of the GNU Affero General Public License as published
#    by the Free Software Foundation, either version 3 of the License, or
#    (at your option) any later version.
#
#    This program is distributed in the hope that it will be useful,
#    but WITHOUT ANY WARRANTY; without even the implied warranty of
#    MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
#    GNU Affero General Public License for more details.
#
#    You should have received a copy of the GNU Affero General Public License
#    along with this program.  If not, see <http://www.gnu.org/licenses/>.
##############################################################################

from openerp import models, fields, api, _


class AccountMoveLine(models.Model):
    _inherit = 'account.move.line'

    payment_mode_id = fields.Many2one(
        comodel_name='payment.mode',
        compute='_compute_payment_mode_id',
        inverse='_set_payment_mode_id',
        string="Payment Mode",
        store=True
    )

    @api.multi
    @api.depends('stored_invoice_id')
    def _compute_payment_mode_id(self):
        for line in self:
            if line.stored_invoice_id:
                line.payment_mode_id = line.stored_invoice_id.payment_mode_id

    @api.multi
    def _set_payment_mode_id(self):
        # dummy function, used to allow field write
        pass

    @api.model
    def create(self, vals):
        move_line = super(AccountMoveLine, self).create(vals)

        # if the payment mode is set,
        # create method will not store the value into the database
        # then just write it to keep stored
        if 'payment_mode_id' in vals:
            move_line.write({'payment_mode_id': vals['payment_mode_id']})

        return move_line
