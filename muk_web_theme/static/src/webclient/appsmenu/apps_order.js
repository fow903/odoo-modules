import { user } from "@web/core/user";

export const APPS_REORDERED_EVENT = "MUK_WEB_THEME:APPS-REORDERED";

export function moveAppInOrder(order, xmlid, previousXmlid) {
    const newOrder = order.filter((item) => item !== xmlid);
    const previousIndex = previousXmlid ? newOrder.indexOf(previousXmlid) : -1;
    newOrder.splice(previousIndex + 1, 0, xmlid);
    return newOrder;
}

export async function saveAppsOrder(env, order) {
    await user.setUserSettings("homemenu_config", JSON.stringify(order));
    env.bus.trigger(APPS_REORDERED_EVENT, { order });
}
