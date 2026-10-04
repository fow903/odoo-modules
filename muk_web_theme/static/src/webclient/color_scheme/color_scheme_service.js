import { _t } from "@web/core/l10n/translation";
import { registry } from "@web/core/registry";
import { browser } from "@web/core/browser/browser";
import { cookie } from "@web/core/browser/cookie";

export function getColorScheme() {
    return cookie.get("color_scheme") === "dark" ? "dark" : "light";
}

export function colorSchemeMenuItem(env) {
    return {
        type: "switch",
        id: "muk_web_theme.color_scheme",
        description: _t("Dark Mode"),
        isChecked: getColorScheme() === "dark",
        callback: () => {
            env.services.color_scheme.switchToColorScheme(
                getColorScheme() === "dark" ? "light" : "dark"
            );
        },
        sequence: 30,
    };
}

export const colorSchemeService = {
    dependencies: ["ui"],
    start(env, { ui }) {
        registry.category("user_menuitems").add(
            "muk_web_theme.color_scheme", colorSchemeMenuItem
        );
        return {
            getColorScheme,
            switchToColorScheme(scheme) {
                if (scheme === getColorScheme()) {
                    return;
                }
                cookie.set("color_scheme", scheme);
                ui.block();
                browser.location.reload();
            },
        };
    },
};

registry.category("services").add("color_scheme", colorSchemeService);
