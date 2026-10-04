import json

MCP_PROTOCOL_VERSION = '2025-11-25'
MCP_SERVER_NAME = 'odoo-mcp-server'
MCP_SERVER_VERSION = '1.0.0'

JSONRPC_VERSION = '2.0'

JSONRPC_PARSE_ERROR = -32700
JSONRPC_INVALID_REQUEST = -32600
JSONRPC_METHOD_NOT_FOUND = -32601
JSONRPC_INTERNAL_ERROR = -32603

MAX_BATCH_SIZE = 20


def coerce_json_value(value):
    if isinstance(value, str):
        try:
            return json.loads(value)
        except (TypeError, ValueError):
            return value
    return value


def exception_message(exc):
    # Odoo 13 exceptions keep the message in ``name``; str() on them
    # returns the repr of the ``(name, value)`` args tuple.
    message = getattr(exc, 'name', None)
    if isinstance(message, str) and message:
        return message
    return str(exc)
