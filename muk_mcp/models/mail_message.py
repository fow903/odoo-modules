from odoo import api, fields, models


class MailMessage(models.Model):

    _inherit = 'mail.message'

    # ----------------------------------------------------------
    # Fields
    # ----------------------------------------------------------

    mcp_name = fields.Char(
        string="MCP Key",
        readonly=True,
    )

    # ----------------------------------------------------------
    # Helper
    # ----------------------------------------------------------

    def _get_message_format_fields(self):
        return super()._get_message_format_fields() + ['mcp_name']

    # ----------------------------------------------------------
    # ORM
    # ----------------------------------------------------------

    @api.model_create_multi
    def create(self, vals_list):
        mcp_name = self.env.context.get('mcp_name')
        if mcp_name:
            for vals in vals_list:
                vals.setdefault('mcp_name', mcp_name)
        return super().create(vals_list)
