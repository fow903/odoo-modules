import re

import werkzeug

from odoo import api, models, SUPERUSER_ID
from odoo.tools.misc import str2bool
from odoo.http import request

from odoo.addons.muk_mcp.core.dispatcher import is_mcp_request, make_json_response


class IrHttp(models.AbstractModel):

    _inherit = 'ir.http'

    # ----------------------------------------------------------
    # Helper
    # ----------------------------------------------------------

    @classmethod
    def _auth_method_mcp(cls):
        env = api.Environment(request.cr, SUPERUSER_ID, {})
        token = None
        header = request.httprequest.headers.get('Authorization', '')
        match = re.match(r'^bearer\s+(.+)$', header, re.IGNORECASE)
        if match:
            token = match.group(1).strip()
        if not token:
            token = (
                request.httprequest.args.get('token') or
                request.httprequest.args.get('api_key')
            )
        if not token:
            raise werkzeug.exceptions.Unauthorized()
        mcp_key = env['muk_mcp.key'].authenticate(token)
        if not mcp_key:
            raise werkzeug.exceptions.Unauthorized()
        request.uid = mcp_key.user_id.id
        annotate = env['ir.config_parameter'].get_param(
            'muk_mcp.annotate_messages', 'True',
        )
        request._mcp_key = mcp_key
        if str2bool(annotate, default=True):
            request.context = dict(
                request.context, mcp_name=mcp_key.name,
            )

    @classmethod
    def _handle_exception(cls, exception):
        if is_mcp_request(request):
            if isinstance(exception, werkzeug.exceptions.HTTPException):
                headers = {}
                if exception.code == 401:
                    # RFC 9728 §5.1: point clients at the protected resource
                    # metadata so they can discover the authorization server.
                    env = api.Environment(request.cr, SUPERUSER_ID, {})
                    base = env['ir.config_parameter'].get_param(
                        'web.base.url', ''
                    ).rstrip('/')
                    headers['WWW-Authenticate'] = (
                        'Bearer resource_metadata='
                        f'"{base}/.well-known/oauth-protected-resource"'
                    )
                return make_json_response({
                    'jsonrpc': '2.0',
                    'id': None,
                    'error': {
                        'code': -32603,
                        'message': str(exception),
                    },
                }, status=exception.code, headers=headers)
            return make_json_response({
                'jsonrpc': '2.0',
                'id': None,
                'error': {
                    'code': -32603,
                    'message': str(exception),
                },
            }, status=500)
        return super()._handle_exception(exception)
