# -*- coding: utf-8 -*-
# © 2011-2012 7 i TRIA <http://www.7itria.cat>
# © 2011-2012 Avanzosc <http://www.avanzosc.com>
# © 2013 Pedro M. Baeza <pedro.baeza@tecnativa.com>
# © 2014 Markus Schneider <markus.schneider@initos.com>
# © 2016 Carlos Dauden <carlos.dauden@tecnativa.com>
# © 2018 Domenico Stragapede <d.stragapede@elvenstudio.it>
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl).

from openerp import models, fields, api, _
from openerp.exceptions import Warning as UserError
import openerp.addons.decimal_precision as dp
from openerp.tools.float_utils import float_compare

import logging
_log = logging.getLogger(__name__)


class PaymentReturn(models.Model):
    _name = "payment.return"
    _inherit = ['mail.thread']
    _description = 'Payment return'
    _order = 'date DESC, id DESC'

    company_id = fields.Many2one(
        comodel_name='res.company',
        string=_('Company'),
        states={
            'done': [('readonly', True)],
            'cancelled': [('readonly', True)]
        },
        default=lambda self: self.env['res.company']._company_default_get('account'),
        required=True
    )

    date = fields.Date(
        string=_('Return date'),
        help=_('This date will be used as the account entry date.'),
        states={
            'done': [('readonly', True)],
            'cancelled': [('readonly', True)]
        },
        default=lambda x: fields.Date.today()
    )

    name = fields.Char(
        string=_("Reference"),
        states={
            'done': [('readonly', True)],
            'cancelled': [('readonly', True)]
        },
        default=lambda self: self.env['ir.sequence'].next_by_code('payment.return'),
        required=True,
    )

    period_id = fields.Many2one(
        comodel_name='account.period',
        string=_('Forced period'),
        states={
            'done': [('readonly', True)],
            'cancelled': [('readonly', True)]
        }
    )

    line_ids = fields.One2many(
        comodel_name='payment.return.line',
        inverse_name='return_id',
        states={
            'done': [('readonly', True)],
            'cancelled': [('readonly', True)]
        }
    )

    journal_id = fields.Many2one(
        comodel_name='account.journal',
        string=_('Bank journal'),
        required=True,
        states={
            'done': [('readonly', True)],
            'cancelled': [('readonly', True)]
        }
    )

    account_id = fields.Many2one(
        comodel_name='account.account',
        string=_('Account'),
        readonly=True,
        required=True,
        states={'draft': [('readonly', False)]},
        help=_('Use this account to register the payment return')
    )

    reconcile_mode = fields.Selection(
        selection=[
            ('auto-reconcile', _('Automatic reconcile')),
            ('manual-return', _('Manual return'))
        ],
        default='auto-reconcile',
        required=True,
        readonly=True,
        states={'draft': [('readonly', False)]},
        help=_(
            'Choose how you want reopen the partner debit: \n'
            ' - Automatic reconcile: specify for each partner '
            'the list of payment returned. When you confirm the return, '
            'it will automatically reconcile the payment. \n'
            ' - Manual return: specify for each partner only the amount returned. \n'
            'It will reopen the debt, but no reconciliation will be done.'
        )
    )

    customer_debit_account_id = fields.Many2one(
        comodel_name='account.account',
        string=_('Account'),
        readonly=True,
        states={'draft': [('readonly', False)]},
        help=_(
            'Use this account to reopen the customer debt '
            'when manual return mode is selected.'
        )
    )

    move_id = fields.Many2one(
        comodel_name='account.move',
        string=_('Entry Move'),
        states={
            'done': [('readonly', True)],
            'cancelled': [('readonly', True)]
        }
    )

    state = fields.Selection(
        string=_('State'),
        selection=[
            ('draft', 'Draft'),
            ('imported', 'Imported'),
            ('done', 'Done'),
            ('cancelled', 'Cancelled')
        ],
        readonly=True,
        default='draft',
        track_visibility='onchange'
    )

    @api.one
    @api.onchange('date')
    def onchange_date(self):
        if self.date:
            self.period_id = self.period_id.find(self.date)

    @api.one
    @api.onchange('journal_id')
    def onchange_journal_id(self):
        if self.journal_id:
            self.account_id = self.journal_id.default_credit_account_id

    @api.multi
    @api.constrains('line_ids')
    def _check_duplicate_move_line(self):
        def append_error(error_line):
            error_list.append(
                _("Payment Line: %s (%s) in Payment Return: %s") % (
                    ', '.join(error_line.mapped('move_line_ids.name')),
                    error_line.partner_id.name,
                    error_line.return_id.name
                )
            )
        error_list = []
        all_move_lines = self.env['account.move.line']
        for line in self.mapped('line_ids'):
            for move_line in line.move_line_ids:
                if move_line in all_move_lines:
                    append_error(line)
                all_move_lines |= move_line
        if (not error_list) and all_move_lines:
            duplicate_lines = self.env['payment.return.line'].search([
                ('move_line_ids', 'in', all_move_lines.ids),
                ('return_id.state', '=', 'done'),
            ])
            if duplicate_lines:
                for line in duplicate_lines:
                    append_error(line)
        if error_list:
            raise UserError(
                "Payment reference must be unique!\n"
                "%s" % '\n'.join(error_list)
            )

    @api.model
    def _get_invoices(self, move_lines):
        invoice_moves = move_lines.filtered('debit').mapped('move_id')
        domain = [('move_id', 'in', invoice_moves.ids)]
        return self.env['account.invoice'].search(domain)

    @api.model
    def _get_move_amount(self, return_line, move_line):
        return move_line.credit

    @api.multi
    def _prepare_invoice_returned_vals(self):
        return {'returned_payment': True}

    @api.multi
    def _prepare_invoice_returned_cancel_vals(self):
        return {'returned_payment': False}

    @api.model
    def create(self, vals):
        if 'account_id' not in vals:
            journal = self.env['account.journal'].browse(vals['journal_id'])
            vals['account_id'] = journal.default_credit_account_id.id

        return super(PaymentReturn, self).create(vals)

    @api.multi
    def unlink(self):
        if self.filtered(lambda x: x.state == 'done'):
            raise UserError(_(
                "You can not remove a payment return if state is 'Done'"))
        return super(PaymentReturn, self).unlink()

    @api.multi
    def button_match(self):
        self.mapped('line_ids').filtered(
            lambda x: ((not x.move_line_ids) and x.reference)
        )._find_match()

        self._check_duplicate_move_line()

    @api.multi
    def _prepare_return_move_vals(self):
        """Prepare the values for the journal entry created from the return.

        :return: Dictionary with the record values.
        """
        self.ensure_one()
        return {
            'name': '/',
            'ref': _('Return %s') % self.name,
            'journal_id': self.journal_id.id,
            'date': self.date,
            'company_id': self.company_id.id,
            'period_id': (self.period_id.id or self.period_id.with_context(
                company_id=self.company_id.id).find(self.date).id),
        }

    @api.multi
    def _get_move_line_credit_defaults(self, move, original_move_line, move_amount):
        """
        Prepare the default values for the credit move line
        :param move: the account move
        :param original_move_line: the original move line to use for default values
        :param move_amount: the amount to use in the new move line
        :return: Dictionary with the record values.
        """
        self.ensure_one()
        return {
            'move_id': move.id,
            'name': _('Payment return charge %s') % move.ref,
            'account_id': self.account_id.id,
            'debit': 0,
            'credit': move_amount,
        }

    @api.multi
    def _get_move_line_debit_defaults(self, move, original_move_line, move_amount):
        """
        Prepare the default values for the debit move line
        :param move: the account move
        :param original_move_line: the original move line to use for default values
        :param move_amount: the amount to use in the new move line
        :return: Dictionary with the record values.
        """
        self.ensure_one()
        ref = original_move_line.ref if original_move_line else ''

        values = {
            'move_id': move.id,
            'name': _('Returned payment %s') % ref,
            'debit': move_amount,
            'credit': 0,
        }

        if original_move_line.date_maturity:
            values['date_maturity'] = original_move_line.date_maturity

        return values

    @api.multi
    def action_confirm(self):
        self.ensure_one()

        # Check for incomplete lines
        if self.reconcile_mode == 'auto-reconcile' and \
           self.line_ids.filtered(lambda x: not x.move_line_ids):
            raise UserError(_(
                "You must input all moves references in the payment "
                "return."
            ))

        move_vals = self._prepare_return_move_vals()
        move = self.env['account.move'].create(move_vals)

        invoices_returned = self.env['account.invoice']
        move_line_obj = self.env['account.move.line']
        for return_line in self.line_ids:

            credit_defaults = self._get_move_line_credit_defaults(move, return_line.move_line_ids, return_line.amount)

            if return_line.move_line_ids:
                return_line.move_line_ids[0].copy(default=credit_defaults)

                for move_line in return_line.move_line_ids:
                    lines2reconcile = move_line.reconcile_id.mapped('line_id')
                    lines2reconcile |= move_line.reconcile_partial_id.mapped('line_partial_ids')
                    invoices_returned |= self._get_invoices(lines2reconcile)

                    move_amount = self._get_move_amount(return_line, move_line)
                    debit_defaults = self._get_move_line_debit_defaults(move, move_line, move_amount)
                    if return_line.date_maturity:
                        debit_defaults['date_maturity'] = return_line.date_maturity

                    move_line2 = move_line.copy(default=debit_defaults)
                    lines2reconcile |= move_line2

                    # Break old reconcile
                    move_line.reconcile_id.unlink()
                    move_line.reconcile_partial_id.unlink()

                    # create new reconciliation
                    if len(lines2reconcile) > 1:
                        lines2reconcile.reconcile_partial()

            else:
                partner_id = return_line.partner_id.id
                credit_defaults.update({'partner_id': partner_id})
                move_line_obj.create(credit_defaults)

                debit_defaults = self._get_move_line_debit_defaults(move, move_line_obj, return_line.amount)
                debit_defaults.update(
                    {
                        'name': _('Returned payment %s') % return_line.reference,
                        'account_id': self.customer_debit_account_id.id,
                        'partner_id': partner_id,
                        'date_maturity': return_line.date_maturity
                    }
                )
                move_line_obj.create(debit_defaults)

            extra_lines_vals = return_line._prepare_extra_move_lines(move)
            for extra_line_vals in extra_lines_vals:
                move_line_obj.create(extra_line_vals)

        # Mark invoice as payment refused
        invoices_returned.write(self._prepare_invoice_returned_vals())
        move.button_validate()
        return self.write({'state': 'done', 'move_id': move.id})

    @api.multi
    def action_cancel(self):
        self.ensure_one()
        if self.move_id:
            invoices = self.env['account.invoice']
            for return_line in self.line_ids:
                move_lines = return_line.reconcile_ids.mapped('line_id')
                move_lines |= return_line.reconcile_ids.mapped('line_partial_ids')
                extra_lines = move_lines.filtered(
                    lambda l:
                        not l.invoice and
                        l.id not in return_line.move_line_ids.ids and
                        l.id not in self.move_id.line_id.ids
                )

                if extra_lines:
                    raise UserError(_(
                        'Cannot cancel return payment because is '
                        'already reconciled with other payments!. \n'
                        'Please remove them before continue!'
                    ))

                for reconcile in return_line.reconcile_ids:
                    # this is a complete reconciliation
                    if reconcile.line_id:
                        reconciled_lines = reconcile.line_id

                    # otherwise is a partial reconciliation
                    else:
                        reconciled_lines = reconcile.line_partial_ids

                    lines2reconcile = reconciled_lines.filtered(
                        lambda x: x.move_id != self.move_id)

                    invoices |= self._get_invoices(lines2reconcile)
                    reconcile.unlink()

                    if lines2reconcile and len(lines2reconcile) > 1:
                        lines2reconcile.reconcile_partial()

            # Remove payment refused flag on invoice
            invoices.write(self._prepare_invoice_returned_cancel_vals())

            self.move_id.button_cancel()
            self.move_id.unlink()

        self.write({'state': 'cancelled', 'move_id': False})
        return True

    @api.multi
    def action_draft(self):
        return self.write({'state': 'draft'})

    @api.multi
    def action_show_return_move(self):
        self.ensure_one()
        ir_model_data = self.env['ir.model.data']
        act_window = self.env['ir.actions.act_window']

        action_name = 'action_move_journal_line'
        form_name = 'view_move_form'
        action_res = act_window.for_xml_id('account', action_name)
        res_view = ir_model_data.get_object_reference('account', form_name)

        action_res['views'] = [(res_view and res_view[1] or False, 'form')]
        action_res['res_id'] = self.move_id.id
        # action_res['domain'] = [('id', 'in', self.move_id.ids)]
        return action_res


class PaymentReturnLine(models.Model):
    _name = "payment.return.line"
    _description = 'Payment return lines'

    return_id = fields.Many2one(
        comodel_name='payment.return',
        string=_('Payment return'),
        required=True,
        ondelete='cascade'
    )

    return_reconcile_mode = fields.Selection(
        selection=[
            ('auto-reconcile', _('Automatic reconcile')),
            ('manual-return', _('Manual return'))
        ],
        compute='_get_return_reconcile_mode',
    )

    concept = fields.Char(
        string=_('Concept'),
        help=_("Read from imported file. Only for reference.")
    )

    reason = fields.Many2one(
        comodel_name='payment.return.reason',
        string=_('Return reason'),
    )

    reference = fields.Char(
        string=_('Reference'),
        help="Reference to match moves from related documents"
    )

    move_line_ids = fields.Many2many(
        comodel_name='account.move.line',
        string=_('Payment Reference')
    )

    date = fields.Date(string=_('Return date'))

    date_maturity = fields.Date(string=_('Maturity date'))

    partner_name = fields.Char(
        string=_('Partner name'),
        readonly=True,
        help="Read from imported file. Only for reference."
    )

    partner_id = fields.Many2one(
        comodel_name='res.partner',
        string=_('Customer'),
        domain="[('customer', '=', True)]",
        required=True
    )

    amount = fields.Float(
        string=_('Amount'),
        help=_("Returned amount. Can be different from the move amount"),
        digits_compute=dp.get_precision('Account')
    )

    amount_residual = fields.Float(
        string=_('Amount residual'),
        digits_compute=dp.get_precision('Account'),
        compute='_compute_return_line_fields',
        readonly=True
    )

    reconcile_ids = fields.One2many(
        string=_('Reconcile'),
        comodel_name='account.move.reconcile',
        compute='_compute_return_line_fields',
        help=_("Reference to the reconcile object.")
    )

    state = fields.Selection(
        selection=[
            ('open', _('Open')),
            ('paid', _('Paid'))
        ],
        compute='_compute_return_line_fields',
        readonly=True
    )

    @api.one
    @api.depends('return_id', 'return_id.reconcile_mode')
    def _get_return_reconcile_mode(self):
        return_id = self.return_id or self.env.context.get('return_id', False)
        if return_id:
            self.return_reconcile_mode = return_id.reconcile_mode

    @api.one
    @api.depends('return_id.move_id',
                 'return_id.move_id.line_id.reconcile_id',
                 'return_id.move_id.line_id.reconcile_partial_id')
    def _compute_return_line_fields(self):
        amount_residual = self.amount
        state = 'open'
        if self.return_id.move_id:
            if self.move_line_ids:
                # payment return from specified move lines
                reconcile_ids = self.move_line_ids.mapped('reconcile_id')
                reconcile_ids |= self.move_line_ids.mapped('reconcile_partial_id')
                self.reconcile_ids = reconcile_ids
                amount_residual = sum(-1 * move.amount_residual for move in self.move_line_ids)
                state = 'open' if amount_residual > 0 else 'paid'
            else:
                # manual return, find its manual return move line
                account_digits = dp.get_precision('Account')(self._cr)[1]
                return_line_ids = self.return_id.move_id.line_id.filtered(
                    lambda l: float_compare(l.debit, self.amount, precision_digits=account_digits) == 0
                              and l.partner_id.id == self.partner_id.id
                )

                if return_line_ids:
                    amount_residual = sum(move.amount_residual for move in return_line_ids)
                    state = 'open' if amount_residual > 0 else 'paid'

        self.amount_residual = amount_residual
        self.state = state

    @api.multi
    def _compute_amount(self):
        for line in self:
            line.amount = sum(move.credit for move in line.move_line_ids)

    @api.multi
    def _get_partner_from_move(self):
        for line in self.filtered(lambda x: not x.partner_id):
            partners = line.move_line_ids.mapped('partner_id')
            if len(partners) > 1:
                raise UserError(
                    "All payments must be owned by the same partner")
            line.partner_id = partners[:1].id
            line.partner_name = partners[:1].name

    @api.onchange('move_line_ids')
    def _onchange_move_line(self):
        self._compute_amount()

    @api.multi
    def match_invoice(self):
        for line in self:
            if line.partner_id:
                domain = [('partner_id', '=', line.partner_id.id)]
            else:
                domain = []
            domain.append(('number', '=', line.reference))
            invoice = self.env['account.invoice'].search(domain)
            if invoice:
                payments = invoice.payment_ids.filtered(
                    lambda x: x.credit > 0.0)
                if payments:
                    line.move_line_ids = payments[0].ids
                    if not line.concept:
                        line.concept = _('Invoice: %s') % invoice.number

    @api.multi
    def match_move_lines(self):
        for line in self:
            if line.partner_id:
                domain = [('partner_id', '=', line.partner_id.id)]
            else:
                domain = []
            domain += [
                ('account_id.type', '=', 'receivable'),
                ('credit', '>', 0.0),
                ('reconcile_ref', '!=', False),
                '|',
                ('name', '=', line.reference),
                ('ref', '=', line.reference),
            ]
            move_lines = self.env['account.move.line'].search(domain)
            if move_lines:
                line.move_line_ids = move_lines.ids
                if not line.concept:
                    line.concept = (_('Move lines: %s') %
                                    ', '.join(move_lines.mapped('name')))

    @api.multi
    def match_move(self):
        for line in self:
            if line.partner_id:
                domain = [('partner_id', '=', line.partner_id.id)]
            else:
                domain = []
            domain.append(('name', '=', line.reference))
            move = self.env['account.move'].search(domain)
            if move:
                if len(move) > 1:
                    raise UserError(
                        "More than one matches to move reference: %s" %
                        self.reference)
                line.move_line_ids = move.line_id.filtered(lambda l: (
                    l.account_id.type == 'receivable' and
                    l.credit > 0 and
                    l.reconcile_ref
                )).ids
                if not line.concept:
                    line.concept = _('Move: %s') % move.ref

    @api.multi
    def _find_match(self):
        # we filter again to remove all ready matched lines in inheritance
        lines2match = self.filtered(lambda x: (
            (not x.move_line_ids) and x.reference))
        lines2match.match_invoice()

        lines2match = lines2match.filtered(lambda x: (
            (not x.move_line_ids) and x.reference))
        lines2match.match_move_lines()

        lines2match = lines2match.filtered(lambda x: (
            (not x.move_line_ids) and x.reference))
        lines2match.match_move()
        self._get_partner_from_move()
        self.filtered(lambda x: not x.amount)._compute_amount()

    @api.multi
    def _prepare_extra_move_lines(self, move):
        """Include possible extra lines in the return journal entry for other
        return concepts.

        :param self: Reference to the payment return line.
        :param move: Reference to the journal entry created for the return.
        :return: A list with dictionaries of the extra move lines to add
        """
        self.ensure_one()
        return []

