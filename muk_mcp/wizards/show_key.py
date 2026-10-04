from odoo import fields, models


class MCPKeyShow(models.TransientModel):

    _name = 'muk_mcp.key.show'
    _description = "Show MCP Key"
    _order = 'id desc'
    _transient_max_hours = 0.1

    # ----------------------------------------------------------
    # Fields
    # ----------------------------------------------------------

    key = fields.Char(
        string="API Key",
        readonly=True,
    )
