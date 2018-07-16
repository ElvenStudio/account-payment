# -*- coding: utf-8 -*-
##############################################################################
#
#    Copyright (c) 2008 Zikzakmedia S.L. (http://zikzakmedia.com)
#                       Jordi Esteve <jesteve@zikzakmedia.com>
#    Copyright (C) 2011 Domsense srl (<http://www.domsense.com>)
#    Copyright (C) 2011-2013 Agile Business Group sagl
#    (<http://www.agilebg.com>)
#    Ported to Odoo by Andrea Cometa <info@andreacometa.it>
#    Ported to v8 API by Eneko Lacunza <elacunza@binovo.es>
#    Copyright (c) 2015 Serv. Tecnol. Avanzados - Pedro M. Baeza
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
#
##############################################################################

from openerp import models, fields, api, _


class AccountMoveLine(models.Model):
    _inherit = 'account.move.line'

    invoice_origin = fields.Char(
        string='Source Doc',
        related='invoice.origin',
    )

    invoice_date = fields.Date(
        string='Invoice Date',
        related='invoice.date_invoice',
    )

    partner_ref = fields.Char(
        string='Partner Ref',
        related='partner_id.ref',
    )

    stored_invoice_id = fields.Many2one(
        string='Invoice',
        comodel_name='account.invoice',
        compute='_compute_invoice',
        store=True
    )

    invoice_user_id = fields.Many2one(
        string="Invoice salesperson",
        comodel_name='res.users',
        related='stored_invoice_id.user_id',
        store=True
    )

    payment_term_id = fields.Many2one(
        string='Payment Terms',
        comodel_name='account.payment.term',
        compute='_compute_payment_term_id',
        inverse='_set_payment_term_id',
        store=True,
    )

    maturity_residual = fields.Float(
        compute='_maturity_residual',
        string="Residual Amount",
        store=True,
        help="The residual amount on a receivable or payable of a journal "
             "entry expressed in the company currency."
    )

    @api.multi
    @api.depends('date_maturity', 'debit', 'credit', 'reconcile_id',
                 'reconcile_partial_id', 'account_id.reconcile',
                 'amount_currency', 'reconcile_partial_id.line_partial_ids',
                 'currency_id')
    def _maturity_residual(self):
        """
        Inspired by amount_residual
        """
        for move_line in self:
            sign = (move_line.debit - move_line.credit) < 0 and -1 or 1
            move_line.maturity_residual = move_line.amount_residual * sign

    @api.multi
    @api.depends('move_id', 'invoice.move_id')
    def _compute_invoice(self):
        for line in self:
            invoices = self.env['account.invoice'].search(
                [('move_id', '=', line.move_id.id)])
            line.stored_invoice_id = invoices[:1]

    @api.multi
    @api.depends('stored_invoice_id')
    def _compute_payment_term_id(self):
        for line in self:
            if line.stored_invoice_id:
                line.payment_term_id = line.stored_invoice_id.payment_term

    @api.multi
    def _set_payment_term_id(self):
        # dummy function, used to allow field write
        pass

    @api.model
    def fields_view_get(self, view_id=None, view_type='form', toolbar=False,
                        submenu=False):
        model_data_obj = self.env['ir.model.data']
        ids = model_data_obj.search([
            ('module', '=', 'account_due_list'),
            ('name', '=', 'view_payments_tree')])
        if ids:
            view_payments_tree_id = model_data_obj.get_object_reference(
                'account_due_list', 'view_payments_tree')
        if ids and view_id == view_payments_tree_id[1]:
            # Use due list
            result = super(models.Model, self).fields_view_get(
                view_id, view_type, toolbar=toolbar, submenu=submenu)
        else:
            # Use special views for account.move.line object
            # (for ex. tree view contains user defined fields)
            result = super(AccountMoveLine, self).fields_view_get(
                view_id, view_type, toolbar=toolbar, submenu=submenu)
        return result
