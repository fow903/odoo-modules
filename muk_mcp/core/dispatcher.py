import json

from odoo import http
from odoo.http import Response


# Odoo 13 turns every ``application/json`` request into a ``JsonRequest``,
# which wraps the payload in Odoo's own JSON-RPC envelope. MCP (and the
# RFC 7591 client registration) need the raw body and full control over the
# response, so these paths are served as plain ``HttpRequest`` instead.
MCP_RAW_JSON_PATHS = frozenset({
    '/mcp',
    '/mcp/oauth/register',
})


def is_mcp_request(req):
    httprequest = getattr(req, 'httprequest', None)
    return bool(httprequest) and httprequest.path == '/mcp'


def make_json_response(data, status=200, headers=None):
    response_headers = {'Content-Type': 'application/json; charset=utf-8'}
    if headers:
        response_headers.update(headers)
    return Response(
        json.dumps(data, ensure_ascii=False, default=str),
        status=status,
        headers=list(response_headers.items()),
    )


def parse_json_body(req):
    """Return ``(data, batch)`` parsed from the raw request body."""
    if req.httprequest.mimetype != 'application/json':
        return None, None
    body = req.httprequest.get_data(as_text=True)
    if not body:
        return None, None
    try:
        data = json.loads(body)
    except (TypeError, ValueError):
        return None, None
    if isinstance(data, dict):
        return data, None
    if isinstance(data, list):
        return None, data
    return None, None


def _patch_get_request():
    origin = http.Root.get_request
    if getattr(origin, '_muk_mcp_patched', False):
        return

    def get_request(self, httprequest):
        if httprequest.path in MCP_RAW_JSON_PATHS:
            return http.HttpRequest(httprequest)
        return origin(self, httprequest)

    get_request._muk_mcp_patched = True
    http.Root.get_request = get_request


_patch_get_request()
