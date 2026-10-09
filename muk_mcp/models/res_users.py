import hashlib
import secrets
import uuid

from odoo import fields, models, _

from odoo.addons.base.models.res_users import check_identity


class ResUsers(models.Model):

    _inherit = 'res.users'

    # ----------------------------------------------------------
    # Fields
    # ----------------------------------------------------------

    mcp_key_ids = fields.One2many(
        comodel_name='muk_mcp.key',
        inverse_name='user_id',
        string="MCP Keys",
    )

    mcp_session_ids = fields.One2many(
        comodel_name='muk_mcp.session',
        inverse_name='user_id',
        string="MCP Sessions",
        domain=[('active', '=', True)],
    )

    mcp_oauth_client_id = fields.Char(
        string="MCP OAuth Client ID",
        readonly=True,
        copy=False,
        index=True,
    )

    mcp_oauth_client_secret_hash = fields.Char(
        string="MCP OAuth Client Secret Hash",
        readonly=True,
        copy=False,
    )

    mcp_oauth_client_secret_prefix = fields.Char(
        string="MCP OAuth Client Secret Prefix",
        readonly=True,
        copy=False,
        help="First 8 characters of the client secret, for identification.",
    )

    # ----------------------------------------------------------
    # Actions
    # ----------------------------------------------------------

    @check_identity
    def action_generate_mcp_key(self):
        return {
            'type': 'ir.actions.act_window',
            'name': 'New MCP Key',
            'res_model': 'muk_mcp.generate_key',
            'views': [(False, 'form')],
            'target': 'new',
            'context': {'default_user_id': self.id},
        }

    def action_revoke_mcp_sessions(self):
        sessions = self.env['muk_mcp.session'].sudo().search([
            ('user_id', '=', self.id),
            ('active', '=', True),
        ])
        sessions.write({'active': False})
        return {'type': 'ir.actions.client', 'tag': 'reload'}

    @check_identity
    def action_generate_oauth_credentials(self):
        self.ensure_one()
        raw_secret = secrets.token_urlsafe(32)
        client_id = str(uuid.uuid4())
        self.sudo().write({
            'mcp_oauth_client_id': client_id,
            'mcp_oauth_client_secret_hash': hashlib.sha256(
                raw_secret.encode()
            ).hexdigest(),
            'mcp_oauth_client_secret_prefix': raw_secret[:8],
        })
        return {
            'type': 'ir.actions.act_window',
            'name': _('MCP OAuth Credentials'),
            'res_model': 'muk_mcp.oauth.show',
            'views': [(False, 'form')],
            'target': 'new',
            'context': {
                'default_client_id': client_id,
                'default_client_secret': raw_secret,
            },
        }

    def action_revoke_oauth_credentials(self):
        self.ensure_one()
        self.sudo().write({
            'mcp_oauth_client_id': False,
            'mcp_oauth_client_secret_hash': False,
            'mcp_oauth_client_secret_prefix': False,
        })
        return {'type': 'ir.actions.client', 'tag': 'reload'}
