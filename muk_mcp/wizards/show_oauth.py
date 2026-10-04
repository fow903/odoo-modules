from odoo import fields, models


class MCPOAuthShow(models.TransientModel):

    _name = 'muk_mcp.oauth.show'
    _description = "Show MCP OAuth Credentials"
    _order = 'id desc'
    _transient_max_hours = 0.1

    # ----------------------------------------------------------
    # Fields
    # ----------------------------------------------------------

    client_id = fields.Char(
        string="Client ID",
        readonly=True,
    )

    client_secret = fields.Char(
        string="Client Secret",
        readonly=True,
    )
