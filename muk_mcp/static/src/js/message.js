odoo.define('muk_mcp.AbstractMessage', function (require) {
"use strict";

var AbstractMessage = require('mail.model.AbstractMessage');

AbstractMessage.include({

    //--------------------------------------------------------------------------
    // Public
    //--------------------------------------------------------------------------

    init: function (parent, data) {
        this._super.apply(this, arguments);
        this._mcpName = data.mcp_name || false;
    },
    getMcpName: function () {
        return this._mcpName;
    },
});

});
