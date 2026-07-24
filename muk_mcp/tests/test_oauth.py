import hashlib
import json
import re
import urllib.parse

from odoo.tests import HttpCase, tagged


@tagged('post_install', '-at_install')
class TestMcpOAuth(HttpCase):

    # ----------------------------------------------------------
    # Setup
    # ----------------------------------------------------------

    CLAUDE_REDIRECT = 'https://claude.ai/api/mcp/auth_callback'

    def _register_public_client(self):
        return self.env['muk_mcp.oauth_client'].register({
            'redirect_uris': [self.CLAUDE_REDIRECT],
            'client_name': 'Claude',
            'token_endpoint_auth_method': 'none',
        })

    def _key_for_token(self, token):
        key_hash = hashlib.sha256(token.encode()).hexdigest()
        return self.env['muk_mcp.key'].sudo().search([
            ('key_hash', '=', key_hash),
        ], limit=1)

    # ----------------------------------------------------------
    # Discovery
    # ----------------------------------------------------------

    def test_protected_resource_metadata(self):
        response = self.url_open('/.well-known/oauth-protected-resource')
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertTrue(data['resource'].endswith('/mcp'))
        self.assertTrue(data['authorization_servers'])
        self.assertEqual(data['bearer_methods_supported'], ['header'])

    def test_protected_resource_metadata_mcp_suffix(self):
        response = self.url_open('/.well-known/oauth-protected-resource/mcp')
        self.assertEqual(response.status_code, 200)

    def test_authorization_server_metadata_has_registration(self):
        response = self.url_open('/.well-known/oauth-authorization-server')
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertIn('registration_endpoint', data)
        self.assertTrue(data['registration_endpoint'].endswith('/mcp/oauth/register'))
        self.assertIn('S256', data['code_challenge_methods_supported'])

    # ----------------------------------------------------------
    # Dynamic Client Registration (RFC 7591)
    # ----------------------------------------------------------

    def test_dynamic_client_registration_public(self):
        response = self.url_open(
            '/mcp/oauth/register',
            data=json.dumps({
                'redirect_uris': [self.CLAUDE_REDIRECT],
                'client_name': 'Claude',
                'token_endpoint_auth_method': 'none',
            }),
            headers={'Content-Type': 'application/json'},
        )
        self.assertEqual(response.status_code, 201)
        data = response.json()
        self.assertTrue(data['client_id'])
        # Public clients (PKCE) must not receive a secret.
        self.assertNotIn('client_secret', data)

    def test_dynamic_client_registration_confidential(self):
        response = self.url_open(
            '/mcp/oauth/register',
            data=json.dumps({
                'redirect_uris': [self.CLAUDE_REDIRECT],
                'token_endpoint_auth_method': 'client_secret_post',
            }),
            headers={'Content-Type': 'application/json'},
        )
        self.assertEqual(response.status_code, 201)
        self.assertTrue(response.json().get('client_secret'))

    def test_dcr_rejects_invalid_redirect_uri(self):
        response = self.url_open(
            '/mcp/oauth/register',
            data=json.dumps({'redirect_uris': ['http://evil.example.com/cb']}),
            headers={'Content-Type': 'application/json'},
        )
        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json()['error'], 'invalid_redirect_uri')

    def test_dcr_requires_redirect_uris(self):
        response = self.url_open(
            '/mcp/oauth/register',
            data=json.dumps({'client_name': 'Claude'}),
            headers={'Content-Type': 'application/json'},
        )
        self.assertEqual(response.status_code, 400)

    # ----------------------------------------------------------
    # 401 discovery header (RFC 9728)
    # ----------------------------------------------------------

    def test_mcp_401_includes_www_authenticate(self):
        response = self.url_open('/mcp', data=json.dumps({
            'jsonrpc': '2.0', 'id': 1, 'method': 'initialize', 'params': {},
        }), headers={'Content-Type': 'application/json'})
        self.assertEqual(response.status_code, 401)
        www_auth = response.headers.get('WWW-Authenticate', '')
        self.assertIn('resource_metadata', www_auth)
        self.assertIn('oauth-protected-resource', www_auth)

    # ----------------------------------------------------------
    # Per-user identity regression (the core fix)
    # ----------------------------------------------------------

    def test_token_identity_is_bound_to_authorizing_user(self):
        """A single org-wide client_id must mint a distinct key/identity
        for each user that authorizes — never a shared owner identity."""
        registration = self._register_public_client()
        client_id = registration['client_id']

        user_a = self.env['res.users'].create({
            'name': 'MCP User A', 'login': 'mcp_user_a',
        })
        user_b = self.env['res.users'].create({
            'name': 'MCP User B', 'login': 'mcp_user_b',
        })

        code_a = self.env['muk_mcp.oauth_code'].create_code(
            client_id=client_id, redirect_uri=self.CLAUDE_REDIRECT,
            user_id=user_a.id, scope='write',
        )
        code_b = self.env['muk_mcp.oauth_code'].create_code(
            client_id=client_id, redirect_uri=self.CLAUDE_REDIRECT,
            user_id=user_b.id, scope='write',
        )

        response_a = self.url_open('/mcp/oauth/token', data={
            'grant_type': 'authorization_code',
            'code': code_a,
            'client_id': client_id,
            'redirect_uri': self.CLAUDE_REDIRECT,
        })
        response_b = self.url_open('/mcp/oauth/token', data={
            'grant_type': 'authorization_code',
            'code': code_b,
            'client_id': client_id,
            'redirect_uri': self.CLAUDE_REDIRECT,
        })
        self.assertEqual(response_a.status_code, 200)
        self.assertEqual(response_b.status_code, 200)

        key_a = self._key_for_token(response_a.json()['access_token'])
        key_b = self._key_for_token(response_b.json()['access_token'])
        self.assertEqual(key_a.user_id, user_a)
        self.assertEqual(key_b.user_id, user_b)
        self.assertNotEqual(key_a.user_id, key_b.user_id)

    def test_token_rejects_unknown_client(self):
        code = self.env['muk_mcp.oauth_code'].create_code(
            client_id='does-not-exist', redirect_uri=self.CLAUDE_REDIRECT,
            user_id=self.env.ref('base.user_admin').id, scope='write',
        )
        response = self.url_open('/mcp/oauth/token', data={
            'grant_type': 'authorization_code',
            'code': code,
            'client_id': 'does-not-exist',
            'redirect_uri': self.CLAUDE_REDIRECT,
        })
        self.assertEqual(response.status_code, 401)
        self.assertEqual(response.json()['error'], 'invalid_client')

    def test_consent_redirects_back_to_external_client(self):
        """Regression: after consent the browser must be redirected to the
        external client host (Claude), not stripped to this server's own
        path. Odoo's request.redirect(local=True) default caused the code
        to land on our own /api/mcp/auth_callback, so Claude never got it."""
        registration = self._register_public_client()
        client_id = registration['client_id']
        challenge = 'E9Melhoa2OwvFrEMTJguCHaoeK1t8URWbuGJSstw-cM'

        self.env['res.users'].create({
            'name': 'Consent User',
            'login': 'mcp_consent',
            'password': 'mcp_consent_pw',
        })
        self.authenticate('mcp_consent', 'mcp_consent_pw')

        authorize_url = (
            '/mcp/oauth/authorize?response_type=code'
            f'&client_id={client_id}'
            '&redirect_uri=' + urllib.parse.quote(self.CLAUDE_REDIRECT, safe='')
            + f'&state=xyz&code_challenge={challenge}'
            '&code_challenge_method=S256'
        )
        form = self.url_open(authorize_url).text
        match = re.search(r'name="csrf_token"\s+value="([^"]+)"', form)
        self.assertTrue(match, 'CSRF token not found in consent form')

        response = self.url_open('/mcp/oauth/authorize', data={
            'client_id': client_id,
            'redirect_uri': self.CLAUDE_REDIRECT,
            'state': 'xyz',
            'scope': 'write',
            'code_challenge': challenge,
            'code_challenge_method': 'S256',
            'action': 'allow',
            'csrf_token': match.group(1),
        }, allow_redirects=False)

        self.assertIn(response.status_code, (302, 303))
        location = response.headers.get('Location', '')
        self.assertTrue(
            location.startswith('https://claude.ai/api/mcp/auth_callback'),
            f'Expected redirect back to Claude, got: {location!r}',
        )
        self.assertIn('code=', location)

    def test_authorize_rejects_unregistered_redirect_uri(self):
        registration = self._register_public_client()
        params = {
            'response_type': 'code',
            'client_id': registration['client_id'],
            'redirect_uri': 'https://evil.example.com/steal',
            'state': 'xyz',
        }
        response = self.url_open(
            '/mcp/oauth/authorize?' + '&'.join(
                f'{k}={v}' for k, v in params.items()
            ),
            allow_redirects=False,
        )
        self.assertEqual(response.status_code, 400)
