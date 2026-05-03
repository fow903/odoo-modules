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

    def _find_user_by_client_id(self, client_id, env=None):
        if not client_id:
            return None
        env = env or request.env
        return env['res.users'].sudo().search(
            [('mcp_oauth_client_id', '=', client_id)], limit=1
        )

    def _verify_client_secret(self, user, client_secret):
        if not user.mcp_oauth_client_secret_hash:
            return False
        secret_hash = hashlib.sha256(client_secret.encode()).hexdigest()
        return secret_hash == user.mcp_oauth_client_secret_hash

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
    # Routes
    # ----------------------------------------------------------

    @http.route(
        '/.well-known/oauth-authorization-server',
        type='http', auth='public', methods=['GET'],
        csrf=False, save_session=False,
    )
    def oauth_metadata(self, **kw):
        base = self._base_url()
        return self._json_response({
            'issuer': base,
            'authorization_endpoint': f'{base}/mcp/oauth/authorize',
            'token_endpoint': f'{base}/mcp/oauth/token',
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
        '/mcp/oauth/authorize',
        type='http', auth='public', methods=['GET'],
        csrf=False, save_session=True,
    )
    def oauth_authorize_get(
        self, response_type=None, client_id=None, redirect_uri=None,
        state=None, scope=None, code_challenge=None,
        code_challenge_method=None, **kw
    ):
        if response_type != 'code' or not client_id or not redirect_uri:
            return Response('Bad request: missing required parameters', status=400)

        owner = self._find_user_by_client_id(client_id)
        if not owner:
            return Response('Unknown client_id', status=400)

        uid = self._session_uid()
        if not uid:
            return_url = request.httprequest.url
            return request.redirect(
                '/web/login?redirect=' + urllib.parse.quote(return_url, safe='')
            )

        if uid != owner.id:
            return Response(
                'This client ID belongs to a different user account. '
                'Please log in as the correct user.',
                status=403,
            )

        return request.render('muk_mcp.oauth_authorize_form', {
            'client_id': client_id,
            'redirect_uri': redirect_uri,
            'state': state or '',
            'scope': scope or 'write',
            'code_challenge': code_challenge or '',
            'code_challenge_method': code_challenge_method or 'S256',
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
        action=None, csrf_token=None, **kw
    ):
        uid = self._session_uid()
        if not uid:
            return Response('Unauthorized', status=401)

        if not request.validate_csrf(csrf_token):
            return Response('CSRF check failed', status=403)

        if not client_id or not redirect_uri or action == 'deny':
            params = urllib.parse.urlencode({
                'error': 'access_denied',
                'state': state or '',
            })
            return request.redirect(f'{redirect_uri}?{params}')

        owner = self._find_user_by_client_id(client_id)
        if not owner or owner.id != uid:
            params = urllib.parse.urlencode({
                'error': 'access_denied',
                'error_description': 'client_id mismatch',
                'state': state or '',
            })
            return request.redirect(f'{redirect_uri}?{params}')

        raw_code = request.env['muk_mcp.oauth_code'].sudo().create_code(
            client_id=client_id,
            redirect_uri=redirect_uri,
            user_id=uid,
            scope=scope or 'write',
            code_challenge=code_challenge or None,
            code_challenge_method=code_challenge_method or 'S256',
        )
        params = {'code': raw_code}
        if state:
            params['state'] = state
        return request.redirect(
            f'{redirect_uri}?{urllib.parse.urlencode(params)}'
        )

    @http.route(
        '/mcp/oauth/token',
        type='http', auth='public', methods=['POST'],
        csrf=False, save_session=False,
    )
    def oauth_token(
        self, grant_type=None, code=None, redirect_uri=None,
        client_id=None, client_secret=None, code_verifier=None, **kw
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
                client_id = client_id or basic_id
                client_secret = client_secret or basic_secret
            except Exception:
                pass

        if not client_id:
            return self._token_error('invalid_client', 'Missing client_id', status=401)

        env = api.Environment(request.env.cr, SUPERUSER_ID, {})
        owner = self._find_user_by_client_id(client_id, env=env)
        if not owner:
            return self._token_error('invalid_client', 'Unknown client_id', status=401)

        auth_code = env['muk_mcp.oauth_code'].consume_code(code)
        if not auth_code:
            return self._token_error('invalid_grant', 'Invalid or expired code')

        if auth_code.client_id != client_id:
            return self._token_error('invalid_grant', 'client_id mismatch')

        if auth_code.user_id.id != owner.id:
            return self._token_error('invalid_grant', 'User mismatch')

        if redirect_uri and auth_code.redirect_uri != redirect_uri:
            return self._token_error('invalid_grant', 'redirect_uri mismatch')

        # Verify PKCE if challenge was used
        if auth_code.code_challenge:
            if not code_verifier:
                return self._token_error('invalid_grant', 'code_verifier required')
            if not self._verify_pkce(
                code_verifier,
                auth_code.code_challenge,
                auth_code.code_challenge_method,
            ):
                return self._token_error('invalid_grant', 'PKCE verification failed')
        elif client_secret:
            # No PKCE → require client_secret
            if not self._verify_client_secret(owner, client_secret):
                return self._token_error('invalid_client', 'Invalid client_secret', status=401)

        scope = auth_code.scope or 'write'
        rate_limit = int(env['ir.config_parameter'].get_param(
            'muk_mcp.rate_limit_requests', 60
        ))
        raw_key = secrets.token_urlsafe(32)
        env['muk_mcp.key'].create({
            'name': f'Claude Code Web ({owner.name})',
            'user_id': owner.id,
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
