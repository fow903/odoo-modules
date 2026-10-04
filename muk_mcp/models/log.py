import contextlib
import json

from odoo import _, api, tools, fields, models, SUPERUSER_ID
from odoo.modules.registry import Registry
from odoo.tools.misc import mute_logger


class MCPLog(models.Model):

    _name = 'muk_mcp.log'
    _description = "MCP Audit Log"
    _order = 'create_date desc, id desc'

    # ----------------------------------------------------------
    # Fields
    # ----------------------------------------------------------

    key_id = fields.Many2one(
        comodel_name='muk_mcp.key',
        string="API Key",
        readonly=True,
        index=True,
        ondelete='set null',
    )

    user_id = fields.Many2one(
        comodel_name='res.users',
        string="User",
        readonly=True,
        index=True,
        ondelete='set null',
    )

    method = fields.Char(
        string="Method",
        readonly=True,
        index=True,
    )

    tool_name = fields.Char(
        string="Tool",
        readonly=True,
        index=True,
    )

    model_name = fields.Char(
        string="Model",
        readonly=True,
    )

    res_id = fields.Integer(
        string="Record ID",
        readonly=True,
    )

    res_ids = fields.Text(
        string="Record IDs",
        readonly=True,
        help="JSON-encoded list of record IDs.",
    )

    request_data = fields.Text(
        string="Request",
        readonly=True,
    )

    response_data = fields.Text(
        string="Response",
        readonly=True,
    )

    ip_address = fields.Char(
        string="IP Address",
        readonly=True,
    )

    duration_ms = fields.Integer(
        string="Duration (ms)",
        readonly=True,
    )

    status = fields.Selection(
        selection=[
            ('ok', "OK"),
            ('error', "Error"),
            ('denied', "Denied"),
            ('rate_limited', "Rate Limited"),
        ],
        string="Status",
        readonly=True,
        index=True,
    )

    error_message = fields.Text(
        string="Error",
        readonly=True,
    )

    # ----------------------------------------------------------
    # Helper
    # ----------------------------------------------------------

    def _get_res_ids(self):
        self.ensure_one()
        if not self.res_ids:
            return []
        try:
            ids = json.loads(self.res_ids)
        except (TypeError, ValueError):
            return []
        return ids if isinstance(ids, list) else []

    # ----------------------------------------------------------
    # Actions
    # ----------------------------------------------------------

    def action_open_record(self):
        self.ensure_one()
        if not self.model_name or not self.res_id:
            return
        if (
            self.model_name not in self.env or
            not self.env[self.model_name].sudo().search_count(
                [('id', '=', self.res_id)],
            )
        ):
            return {'type': 'ir.actions.client', 'tag': 'display_notification', 'params': {
                'title': _('Record not found'),
                'message': _('%s(%s) no longer exists.') % (
                    self.model_name, self.res_id,
                ),
                'type': 'warning',
            }}
        return {
            'type': 'ir.actions.act_window',
            'res_model': self.model_name,
            'res_id': self.res_id,
            'views': [(False, 'form')],
            'target': 'current',
        }

    def action_open_records(self):
        self.ensure_one()
        res_ids = self._get_res_ids()
        if self.model_name and res_ids:
            return {
                'type': 'ir.actions.act_window',
                'name': self.model_name,
                'res_model': self.model_name,
                'domain': [('id', 'in', res_ids)],
                'views': [(False, 'list'), (False, 'form')],
                'target': 'current',
            }

    # ----------------------------------------------------------
    # Functions
    # ----------------------------------------------------------

    @api.model
    def log(self, **values):
        if isinstance(values.get('res_ids'), (list, tuple)):
            values['res_ids'] = json.dumps(list(values['res_ids']))
        with contextlib.suppress(Exception), mute_logger('odoo.sql_db'), Registry(
                self.env.cr.dbname
            ).cursor() as cr:
            env = api.Environment(cr, SUPERUSER_ID, {})
            env['muk_mcp.log'].create(values)

    # ----------------------------------------------------------
    # Cron
    # ----------------------------------------------------------

    @api.model
    def _autovacuum_logs(self):
        days = int(self.env['ir.config_parameter'].sudo().get_param(
            'muk_mcp.log_autovacuum_days',
            tools.config.get('mcp_log_autovacuum_days', 30)
        ))
        limit = fields.Datetime.subtract(
            fields.Datetime.now(), days=days
        )
        domain = [('create_date', '<', limit)]
        batch = self.search(domain, limit=5000)
        while batch:
            batch.unlink()
            self.env.cr.commit()
            batch = self.search(domain, limit=5000)
