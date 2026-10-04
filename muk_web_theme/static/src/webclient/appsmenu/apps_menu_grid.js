import { Component, useRef, useState } from "@odoo/owl";
import { useBus, useService } from "@web/core/utils/hooks";
import { useSortable } from "@web/core/utils/sortable_owl";

import { DropdownItem } from "@web/core/dropdown/dropdown_item";
import {
    APPS_REORDERED_EVENT,
    moveAppInOrder,
    saveAppsOrder,
} from "@muk_web_theme/webclient/appsmenu/apps_order";

export class AppsMenuGrid extends Component {
    static template = "muk_web_theme.AppsMenuGrid";
    static components = { DropdownItem };
    static props = {
        onSelect: Function,
    };
    setup() {
        this.appMenuService = useService("app_menu");
        this.rootRef = useRef("root");
        this.state = useState({
            apps: this.appMenuService.getAppsMenuItems(),
        });
        useBus(this.env.bus, APPS_REORDERED_EVENT, () => {
            this.state.apps = this.appMenuService.getAppsMenuItems();
        });
        useSortable({
            ref: this.rootRef,
            elements: ".o_app",
            cursor: "move",
            delay: 500,
            tolerance: 10,
            onDrop: ({ element, previous }) => this.onAppDrop(element, previous),
        });
    }
    onAppDrop(element, previous) {
        const order = moveAppInOrder(
            this.state.apps.map((app) => app.xmlid),
            element.dataset.menuXmlid,
            previous?.dataset.menuXmlid
        );
        const appsByXmlid = Object.fromEntries(
            this.state.apps.map((app) => [app.xmlid, app])
        );
        this.state.apps = order.map((xmlid) => appsByXmlid[xmlid]);
        saveAppsOrder(this.env, order);
    }
}
