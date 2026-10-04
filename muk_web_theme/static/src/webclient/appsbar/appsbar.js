import { useRef } from "@odoo/owl";
import { patch } from "@web/core/utils/patch";
import { useBus } from "@web/core/utils/hooks";
import { useSortable } from "@web/core/utils/sortable_owl";

import { AppsBar } from "@muk_web_appsbar/webclient/appsbar/appsbar";
import {
    APPS_REORDERED_EVENT,
    moveAppInOrder,
    saveAppsOrder,
} from "@muk_web_theme/webclient/appsmenu/apps_order";

patch(AppsBar.prototype, {
    setup() {
        super.setup();
        this.appsListRef = useRef("appsList");
        useBus(this.env.bus, APPS_REORDERED_EVENT, () => this.render());
        useSortable({
            ref: this.appsListRef,
            elements: "li.nav-item",
            cursor: "move",
            delay: 500,
            tolerance: 10,
            onDrop: ({ element, previous }) => this._onAppDrop(element, previous),
        });
    },
    _onAppDrop(element, previous) {
        const order = moveAppInOrder(
            this.appMenuService.getAppsMenuItems().map((app) => app.xmlid),
            element.dataset.menuXmlid,
            previous?.dataset.menuXmlid
        );
        return saveAppsOrder(this.env, order);
    },
});
