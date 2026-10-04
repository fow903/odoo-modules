from odoo import fields, models


class ResUsersSettings(models.Model):

    _inherit = 'res.users.settings'

    #----------------------------------------------------------
    # Fields
    #----------------------------------------------------------

    homemenu_config = fields.Json(
        string='Home Menu Configuration',
        readonly=True,
    )
