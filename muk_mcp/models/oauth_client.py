import hashlib
import json
import secrets
import time
import urllib.parse
import uuid

from odoo import api, fields, models


class MCPOAuthClient(models.Model):

    _name = 'muk_mcp.oauth_client'
    _description = "MCP OAuth Client (Dynamic Registration)"
    _order = 'create_date desc'

    # ----------------------------------------------------------
    # Fields
    # ----------------------------------------------------------

    client_id = fields.Char(
        string="Client ID",
        required=True,
        index=True,
        copy=False,
    )

    client_name = fields.Char(
        string="Client Name",
    )

    redirect_uris = fields.Text(
        string="Redirect URIs",
        help="JSON-encoded list of registered redirect URIs.",
    )

    client_secret_hash = fields.Char(
        string="Client Secret Hash",
        copy=False,
    )

    client_secret_prefix = fields.Char(
        string="Client Secret Prefix",
        copy=False,
        help="First 8 characters of the client secret, for identification.",
    )

    token_endpoint_auth_method = fields.Char(
        string="Token Endpoint Auth Method",
        default='client_secret_basic',
    )

    grant_types = fields.Char(
        string="Grant Types",
        default='authorization_code',
    )

    scope = fields.Char(
        string="Scope",
        default='write',
    )

    # ----------------------------------------------------------
    # Helper
    # ----------------------------------------------------------

    @staticmethod
    def _is_valid_redirect_uri(redirect_uri):
        try:
            parsed = urllib.parse.urlparse(redirect_uri)
        except Exception:
            return False
        if parsed.fragment:
            return False
        if parsed.scheme == 'https':
            return bool(parsed.netloc)
        # Local development clients are allowed over http on loopback only.
        if parsed.scheme == 'http':
            host = (parsed.hostname or '').lower()
            return host in ('localhost', '127.0.0.1', '::1')
        return False

    def get_redirect_uris(self):
        self.ensure_one()
        if not self.redirect_uris:
            return []
        try:
            uris = json.loads(self.redirect_uris)
        except (ValueError, TypeError):
            return []
        return uris if isinstance(uris, list) else []

    def is_redirect_uri_allowed(self, redirect_uri):
        self.ensure_one()
        registered = self.get_redirect_uris()
        # Legacy clients without registered URIs skip the exact-match check.
        if not registered:
            return True
        return redirect_uri in registered

    def is_confidential(self):
        self.ensure_one()
        return bool(self.client_secret_hash)

    def verify_secret(self, client_secret):
        self.ensure_one()
        if not self.client_secret_hash or not client_secret:
            return False
        secret_hash = hashlib.sha256(client_secret.encode()).hexdigest()
        return secrets.compare_digest(secret_hash, self.client_secret_hash)

    # ----------------------------------------------------------
    # Functions
    # ----------------------------------------------------------

    @api.model
    def find(self, client_id):
        if not client_id:
            return self.browse()
        return self.sudo().search(
            [('client_id', '=', client_id)], limit=1
        )

    @api.model
    def register(self, metadata):
        """Register a client per RFC 7591 and return the response document.

        Raises ValueError('invalid_redirect_uri') / ValueError('invalid_client_metadata')
        so the controller can map them to the proper HTTP error.
        """
        redirect_uris = metadata.get('redirect_uris')
        if not isinstance(redirect_uris, list) or not redirect_uris:
            raise ValueError('invalid_redirect_uri')
        for uri in redirect_uris:
            if not isinstance(uri, str) or not self._is_valid_redirect_uri(uri):
                raise ValueError('invalid_redirect_uri')

        auth_method = metadata.get(
            'token_endpoint_auth_method', 'client_secret_basic'
        )
        if auth_method not in (
            'none', 'client_secret_post', 'client_secret_basic',
        ):
            raise ValueError('invalid_client_metadata')

        grant_types = metadata.get('grant_types') or ['authorization_code']
        if isinstance(grant_types, list):
            grant_types = ' '.join(grant_types)

        client_id = str(uuid.uuid4())
        vals = {
            'client_id': client_id,
            'client_name': metadata.get('client_name') or 'MCP Client',
            'redirect_uris': json.dumps(redirect_uris),
            'token_endpoint_auth_method': auth_method,
            'grant_types': grant_types,
            'scope': metadata.get('scope') or 'write',
        }

        raw_secret = None
        if auth_method != 'none':
            raw_secret = secrets.token_urlsafe(32)
            vals['client_secret_hash'] = hashlib.sha256(
                raw_secret.encode()
            ).hexdigest()
            vals['client_secret_prefix'] = raw_secret[:8]

        self.sudo().create(vals)

        response = {
            'client_id': client_id,
            'client_id_issued_at': int(time.time()),
            'redirect_uris': redirect_uris,
            'client_name': vals['client_name'],
            'token_endpoint_auth_method': auth_method,
            'grant_types': grant_types.split(),
            'response_types': ['code'],
            'scope': vals['scope'],
        }
        if raw_secret:
            response['client_secret'] = raw_secret
            # 0 indicates the secret does not expire (RFC 7591).
            response['client_secret_expires_at'] = 0
        return response
