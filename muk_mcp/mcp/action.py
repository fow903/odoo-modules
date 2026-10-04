from odoo import _, api, models
from odoo.exceptions import AccessError, UserError
from odoo.models import check_method_name

from odoo.addons.muk_mcp.core.tool import mcp_tool
from odoo.addons.muk_mcp.tools.common import coerce_json_value, exception_message


def get_public_method(model, name):
    check_method_name(name)
    func = getattr(type(model), name, None)
    if not callable(func):
        raise AttributeError(
            _("The method '%s' does not exist on the model '%s'")
            % (name, model._name)
        )
    return func


class MCPMixin(models.AbstractModel):

    _inherit = 'muk_mcp.mixin'

    # ----------------------------------------------------------
    # Functions
    # ----------------------------------------------------------

    @api.model
    @mcp_tool(
        name='call_method',
        description=(
            "Call a public method on an Odoo model or recordset. Use this "
            "for business logic actions like confirming a sale order "
            "(model='sale.order', method='action_confirm', ids=[42]) or "
            "posting an invoice (model='account.move', "
            "method='action_post', ids=[10]). Common methods: "
            "action_confirm (sales/purchases), action_post (invoices), "
            "action_done (pickings), action_assign (pickings), "
            "action_cancel (most documents). Private methods (starting "
            "with '_') are blocked for safety."
        ),
        input_schema={
            'type': 'object',
            'properties': {
                'model': {
                    'type': 'string',
                    'description': 'Technical model name.',
                },
                'method': {
                    'type': 'string',
                    'description': (
                        "Public method name (e.g. 'action_confirm', "
                        "'action_post', 'message_post')."
                    ),
                },
                'ids': {
                    'type': 'array',
                    'items': {'type': 'integer'},
                    'description': (
                        'Record IDs to call the method on. Omit for '
                        '@api.model methods.'
                    ),
                },
                'args': {
                    'type': 'string',
                    'description': (
                        'JSON-encoded array of positional arguments. '
                        'Example: "[42, true]". Pass "[]" or omit if none.'
                    ),
                },
                'kwargs': {
                    'type': 'object',
                    'description': (
                        'Keyword arguments to pass to the method.'
                    ),
                },
                'context': {
                    'type': 'object',
                    'description': 'Optional Odoo context overrides.',
                },
            },
            'required': ['model', 'method'],
        },
        category='write',
    )
    def _mcp_call_method(
        self,
        model,
        method,
        ids=None,
        args=None,
        kwargs=None,
    ):
        target = self._resolve_model(model)
        try:
            unbound = get_public_method(target, method)
        except (AccessError, AttributeError) as exc:
            raise UserError(exception_message(exc))
        target_ids = self._normalize_ids(ids)
        if getattr(unbound, '_api', None) == 'model':
            recordset = target
        else:
            recordset = (
                target.browse(target_ids)
                if target_ids else target
            )
        positional = coerce_json_value(args) or []
        keyword = coerce_json_value(kwargs) or {}
        return unbound(recordset, *positional, **keyword)
