import base64
import hashlib
import json
import secrets
import urllib.parse

from odoo import api, http, SUPERUSER_ID
from odoo.http import request, Response


class MCPOAuthController(http.Controller):

    # ----------------------------------------------------------
    # Helper
    # ----------------------------------------------------------

    def _base_url(self):
        return request.env['ir.config_parameter'].sudo().get_param(
            'web.base.url', ''
        ).rstrip('/')

    def _resource_url(self):
        return f'{self._base_url()}/mcp'

    def _find_user_by_client_id(self, client_id, env=None):
        if not client_id:
            return None
        env = env or request.env
        return env['res.users'].sudo().search(
            [('mcp_oauth_client_id', '=', client_id)], limit=1
        )

    def _resolve_client(self, client_id, env=None):
        """Resolve an OAuth client from either the dynamic-registration
        model or the legacy per-user credentials.

        Returns a dict with a uniform interface, or None when unknown.
        The returned client is user-agnostic: the identity of the issued
        token is decided by whoever authenticates in the browser, not by
        who owns the client_id.
        """
        env = env or request.env
        client = env['muk_mcp.oauth_client'].find(client_id)
        if client:
            return {
                'redirect_ok': client.is_redirect_uri_allowed,
                'confidential': client.is_confidential(),
                'verify_secret': client.verify_secret,
            }
        owner = self._find_user_by_client_id(client_id, env=env)
        if owner:
            return {
                # Legacy clients have no registered redirect URIs.
                'redirect_ok': lambda uri: True,
                'confidential': bool(owner.mcp_oauth_client_secret_hash),
                'verify_secret': (
                    lambda secret: self._verify_client_secret(owner, secret)
                ),
            }
        return None

    def _verify_client_secret(self, user, client_secret):
        if not user.mcp_oauth_client_secret_hash or not client_secret:
            return False
        secret_hash = hashlib.sha256(client_secret.encode()).hexdigest()
        return secrets.compare_digest(
            secret_hash, user.mcp_oauth_client_secret_hash
        )

    def _verify_pkce(self, code_verifier, code_challenge, method='S256'):
        if method == 'S256':
            digest = hashlib.sha256(code_verifier.encode('ascii')).digest()
            expected = base64.urlsafe_b64encode(digest).rstrip(b'=').decode()
            return expected == code_challenge
        if method == 'plain':
            return code_verifier == code_challenge
        return False

    def _json_response(self, data, status=200, extra_headers=None):
        headers = {'Content-Type': 'application/json', 'Cache-Control': 'no-store'}
        if extra_headers:
            headers.update(extra_headers)
        return Response(json.dumps(data), status=status, headers=headers)

    def _token_error(self, error, description=None, status=400):
        body = {'error': error}
        if description:
            body['error_description'] = description
        return self._json_response(body, status=status)

    def _session_uid(self):
        uid = request.session.uid
        if not uid:
            return None
        public_id = request.env.ref('base.public_user').id
        return uid if uid != public_id else None

    # ----------------------------------------------------------
    # Discovery (RFC 8414 / RFC 9728)
    # ----------------------------------------------------------

    @http.route(
        [
            '/.well-known/oauth-authorization-server',
            '/.well-known/oauth-authorization-server/mcp',
        ],
        type='http', auth='public', methods=['GET'],
        csrf=False, save_session=False,
    )
    def oauth_metadata(self, **kw):
        base = self._base_url()
        return self._json_response({
            'issuer': base,
            'authorization_endpoint': f'{base}/mcp/oauth/authorize',
            'token_endpoint': f'{base}/mcp/oauth/token',
            'registration_endpoint': f'{base}/mcp/oauth/register',
            'scopes_supported': ['read', 'write'],
            'response_types_supported': ['code'],
            'grant_types_supported': ['authorization_code'],
            'code_challenge_methods_supported': ['S256'],
            'token_endpoint_auth_methods_supported': [
                'client_secret_post',
                'client_secret_basic',
                'none',
            ],
        })

    @http.route(
        [
            '/.well-known/oauth-protected-resource',
            '/.well-known/oauth-protected-resource/mcp',
        ],
        type='http', auth='public', methods=['GET'],
        csrf=False, save_session=False,
    )
    def oauth_protected_resource(self, **kw):
        base = self._base_url()
        return self._json_response({
            'resource': f'{base}/mcp',
            'authorization_servers': [base],
            'scopes_supported': ['read', 'write'],
            'bearer_methods_supported': ['header'],
        })

    # ----------------------------------------------------------
    # Dynamic Client Registration (RFC 7591)
    # ----------------------------------------------------------

    @http.route(
        '/mcp/oauth/register',
        type='http', auth='public', methods=['POST'],
        csrf=False, save_session=False,
    )
    def oauth_register(self, **kw):
        try:
            metadata = json.loads(request.httprequest.get_data() or b'{}')
        except (ValueError, TypeError):
            return self._token_error('invalid_client_metadata', 'Invalid JSON')
        if not isinstance(metadata, dict):
            return self._token_error('invalid_client_metadata', 'Invalid body')

        env = api.Environment(request.env.cr, SUPERUSER_ID, {})
        try:
            response = env['muk_mcp.oauth_client'].register(metadata)
        except ValueError as exc:
            return self._token_error(str(exc), status=400)
        return self._json_response(response, status=201)

    # ----------------------------------------------------------
    # Authorization
    # ----------------------------------------------------------

    @http.route(
        '/mcp/oauth/authorize',
        type='http', auth='public', methods=['GET'],
        csrf=False, save_session=True,
    )
    def oauth_authorize_get(
        self, response_type=None, client_id=None, redirect_uri=None,
        state=None, scope=None, code_challenge=None,
        code_challenge_method=None, resource=None, **kw
    ):
        if response_type != 'code' or not client_id or not redirect_uri:
            return Response('Bad request: missing required parameters', status=400)

        client = self._resolve_client(client_id)
        if not client:
            return Response('Unknown client_id', status=400)

        if not client['redirect_ok'](redirect_uri):
            return Response('Invalid redirect_uri', status=400)

        uid = self._session_uid()
        if not uid:
            return_url = request.httprequest.url
            return request.redirect(
                '/web/login?redirect=' + urllib.parse.quote(return_url, safe='')
            )

        return request.render('muk_mcp.oauth_authorize_form', {
            'client_id': client_id,
            'redirect_uri': redirect_uri,
            'state': state or '',
            'scope': scope or 'write',
            'code_challenge': code_challenge or '',
            'code_challenge_method': code_challenge_method or 'S256',
            'resource': resource or '',
            'csrf_token': request.csrf_token(),
        })

    @http.route(
        '/mcp/oauth/authorize',
        type='http', auth='public', methods=['POST'],
        csrf=False, save_session=True,
    )
    def oauth_authorize_post(
        self, client_id=None, redirect_uri=None, state=None,
        scope=None, code_challenge=None, code_challenge_method=None,
        resource=None, action=None, csrf_token=None, **kw
    ):
        uid = self._session_uid()
        if not uid:
            return Response('Unauthorized', status=401)

        if not request.validate_csrf(csrf_token):
            return Response('CSRF check failed', status=403)

        if not client_id or not redirect_uri:
            return Response('Bad request: missing required parameters', status=400)

        client = self._resolve_client(client_id)
        if not client:
            return Response('Unknown client_id', status=400)

        # Validate the redirect target BEFORE any external redirect, both to
        # satisfy the OAuth spec and to avoid an open-redirect vector.
        if not client['redirect_ok'](redirect_uri):
            return Response('Invalid redirect_uri', status=400)

        if action == 'deny':
            params = urllib.parse.urlencode({
                'error': 'access_denied',
                'state': state or '',
            })
            # local=False: redirect_uri points at the external client
            # (e.g. https://claude.ai/...). Odoo strips the host when
            # local=True (the default), which would send the browser to
            # this server's own path instead of back to the client.
            return request.redirect(f'{redirect_uri}?{params}', local=False)

        # The token identity is bound to the authenticated browser user,
        # NOT to whoever owns the client_id. This lets a single org-wide
        # connector serve each member with their own Odoo identity.
        raw_code = request.env['muk_mcp.oauth_code'].sudo().create_code(
            client_id=client_id,
            redirect_uri=redirect_uri,
            user_id=uid,
            scope=scope or 'write',
            code_challenge=code_challenge or None,
            code_challenge_method=code_challenge_method or 'S256',
            resource=resource or None,
        )
        params = {'code': raw_code}
        if state:
            params['state'] = state
        # local=False so the browser is sent back to the external client
        # (Claude) with the code, instead of to this server's own domain.
        return request.redirect(
            f'{redirect_uri}?{urllib.parse.urlencode(params)}',
            local=False,
        )

    @http.route(
        '/api/mcp/auth_callback',
        type='http', auth='public', methods=['GET'],
        csrf=False, save_session=False,
    )
    def auth_callback(
        self, code=None, state=None, error=None,
        error_description=None, **kw
    ):
        if error:
            return request.render('muk_mcp.oauth_callback_error', {
                'error': error,
                'error_description': error_description or '',
            })

        if not code:
            return Response('Bad request: missing code', status=400)

        env = api.Environment(request.env.cr, SUPERUSER_ID, {})
        auth_code = env['muk_mcp.oauth_code'].consume_code(code)
        if not auth_code:
            return request.render('muk_mcp.oauth_callback_error', {
                'error': 'invalid_grant',
                'error_description': 'Authorization code is invalid or expired.',
            })

        rate_limit = int(env['ir.config_parameter'].get_param(
            'muk_mcp.rate_limit_requests', 60
        ))
        raw_key = secrets.token_urlsafe(32)
        env['muk_mcp.key'].create({
            'name': f'OAuth ({auth_code.user_id.name})',
            'user_id': auth_code.user_id.id,
            'key_hash': hashlib.sha256(raw_key.encode()).hexdigest(),
            'key_prefix': raw_key[:8],
            'scope': auth_code.scope if auth_code.scope in ('read', 'write') else 'write',
            'rate_limit': rate_limit,
        })

        base = self._base_url()
        return request.render('muk_mcp.oauth_callback_success', {
            'access_token': raw_key,
            'mcp_url': f'{base}/mcp',
            'scope': auth_code.scope or 'write',
        })

    # ----------------------------------------------------------
    # Token
    # ----------------------------------------------------------

    @http.route(
        '/mcp/oauth/token',
        type='http', auth='public', methods=['POST'],
        csrf=False, save_session=False,
    )
    def oauth_token(
        self, grant_type=None, code=None, redirect_uri=None,
        client_id=None, client_secret=None, code_verifier=None,
        resource=None, **kw
    ):
        if grant_type != 'authorization_code':
            return self._token_error('unsupported_grant_type')
        if not code:
            return self._token_error('invalid_request', 'Missing code')

        # Support HTTP Basic for client credentials
        auth_header = request.httprequest.headers.get('Authorization', '')
        if auth_header.lower().startswith('basic '):
            try:
                decoded = base64.b64decode(auth_header[6:]).decode()
                basic_id, basic_secret = decoded.split(':', 1)
                client_id = client_id or urllib.parse.unquote(basic_id)
                client_secret = client_secret or urllib.parse.unquote(basic_secret)
            except Exception:
                pass

        if not client_id:
            return self._token_error('invalid_client', 'Missing client_id', status=401)

        env = api.Environment(request.env.cr, SUPERUSER_ID, {})
        client = self._resolve_client(client_id, env=env)
        if not client:
            return self._token_error('invalid_client', 'Unknown client_id', status=401)

        auth_code = env['muk_mcp.oauth_code'].consume_code(code)
        if not auth_code:
            return self._token_error('invalid_grant', 'Invalid or expired code')

        if auth_code.client_id != client_id:
            return self._token_error('invalid_grant', 'client_id mismatch')

        if redirect_uri and auth_code.redirect_uri != redirect_uri:
            return self._token_error('invalid_grant', 'redirect_uri mismatch')

        # Verify PKCE if a challenge was used; otherwise require the
        # client secret for confidential clients.
        if auth_code.code_challenge:
            if not code_verifier:
                return self._token_error('invalid_grant', 'code_verifier required')
            if not self._verify_pkce(
                code_verifier,
                auth_code.code_challenge,
                auth_code.code_challenge_method,
            ):
                return self._token_error('invalid_grant', 'PKCE verification failed')
        elif client['confidential']:
            if not client['verify_secret'](client_secret):
                return self._token_error('invalid_client', 'Invalid client_secret', status=401)

        # Audience binding (RFC 8707): if the client bound the grant to a
        # resource, the token request must target the same MCP endpoint.
        if auth_code.resource and resource and auth_code.resource != resource:
            return self._token_error('invalid_target', 'resource mismatch')

        scope = auth_code.scope or 'write'
        rate_limit = int(env['ir.config_parameter'].get_param(
            'muk_mcp.rate_limit_requests', 60
        ))
        raw_key = secrets.token_urlsafe(32)
        env['muk_mcp.key'].create({
            'name': f'Claude Web ({auth_code.user_id.name})',
            'user_id': auth_code.user_id.id,
            'key_hash': hashlib.sha256(raw_key.encode()).hexdigest(),
            'key_prefix': raw_key[:8],
            'scope': scope if scope in ('read', 'write') else 'write',
            'rate_limit': rate_limit,
        })

        return self._json_response({
            'access_token': raw_key,
            'token_type': 'bearer',
            'expires_in': 31536000,
            'scope': scope,
        })
