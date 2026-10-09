from odoo import fields, models


class MCPOAuthShow(models.AbstractModel):

    _name = 'muk_mcp.oauth.show'
    _description = "Show MCP OAuth Credentials"

    id = fields.Id(string="ID")

    client_id = fields.Char(
        string="Client ID",
        readonly=True,
    )

    client_secret = fields.Char(
        string="Client Secret",
        readonly=True,
    )
