import hashlib
import secrets
from datetime import timedelta

from odoo import api, fields, models


class MCPOAuthCode(models.Model):

    _name = 'muk_mcp.oauth_code'
    _description = "MCP OAuth Authorization Code"
    _order = 'create_date desc'

    # ----------------------------------------------------------
    # Fields
    # ----------------------------------------------------------

    code_hash = fields.Char(
        string="Code Hash",
        required=True,
        index=True,
    )

    client_id = fields.Char(
        string="Client ID",
        required=True,
    )

    redirect_uri = fields.Char(
        string="Redirect URI",
        required=True,
    )

    user_id = fields.Many2one(
        comodel_name='res.users',
        string="User",
        required=True,
        ondelete='cascade',
    )

    scope = fields.Char(
        string="Scope",
        default='write',
    )

    code_challenge = fields.Char(
        string="Code Challenge",
    )

    code_challenge_method = fields.Char(
        string="Challenge Method",
        default='S256',
    )

    resource = fields.Char(
        string="Resource",
        help="RFC 8707 resource indicator the token is requested for.",
    )

    expires_at = fields.Datetime(
        string="Expires At",
        required=True,
    )

    used = fields.Boolean(
        string="Used",
        default=False,
    )

    # ----------------------------------------------------------
    # Functions
    # ----------------------------------------------------------

    @api.model
    def create_code(self, client_id, redirect_uri, user_id, scope='write',
                    code_challenge=None, code_challenge_method='S256',
                    resource=None):
        raw_code = secrets.token_urlsafe(32)
        self.sudo().create({
            'code_hash': hashlib.sha256(raw_code.encode()).hexdigest(),
            'client_id': client_id,
            'redirect_uri': redirect_uri,
            'user_id': user_id,
            'scope': scope,
            'code_challenge': code_challenge,
            'code_challenge_method': code_challenge_method or 'S256',
            'resource': resource,
            'expires_at': fields.Datetime.now() + timedelta(minutes=10),
        })
        return raw_code

    @api.model
    def consume_code(self, code):
        code_hash = hashlib.sha256(code.encode()).hexdigest()
        record = self.sudo().search([
            ('code_hash', '=', code_hash),
            ('used', '=', False),
            ('expires_at', '>', fields.Datetime.now()),
        ], limit=1)
        if not record:
            return None
        record.write({'used': True})
        return record

    # ----------------------------------------------------------
    # Cron
    # ----------------------------------------------------------

    @api.autovacuum
    def _autovacuum_codes(self):
        self.sudo().search([('expires_at', '<', fields.Datetime.now())]).unlink()
