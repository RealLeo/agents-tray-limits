import Adw from 'gi://Adw';
import Gio from 'gi://Gio';
import GLib from 'gi://GLib';
import Gtk from 'gi://Gtk';

import {ExtensionPreferences} from 'resource:///org/gnome/Shell/Extensions/js/extensions/prefs.js';

import {
    LANGUAGE_AUTONYMS,
    LANGUAGE_VALUES,
    createTranslator,
} from './i18n.js';
import {
    loadThemeCatalog,
    sortedThemes,
    userThemesDirectory,
} from './themeLoader.js';
import {migrateThemeId} from './themeLogic.js';

const CHATGPT_CODEX_URL = 'https://chatgpt.com/codex';
const DISPLAY_VALUES = ['remaining', 'used'];
const INTERVAL_VALUES = [60, 300, 900, 1800, 3600];

function stringList(items) {
    const model = new Gtk.StringList();
    for (const item of items)
        model.append(item);
    return model;
}

function selectedIndex(values, current, fallback = 0) {
    const index = values.indexOf(current);
    return index >= 0 ? index : fallback;
}

export default class AgentsTrayLimitsPreferences extends ExtensionPreferences {
    fillPreferencesWindow(window) {
        const settings = this.getSettings();
        const configuredTheme = settings.get_string('theme-id');
        const migratedTheme = migrateThemeId(configuredTheme);
        if (migratedTheme !== configuredTheme)
            settings.set_string('theme-id', migratedTheme);

        window._agentsTrayLimitsSettings = settings;
        window.set_default_size(640, 700);

        const rebuild = () => {
            if (window._agentsTrayLimitsPage)
                window.remove(window._agentsTrayLimitsPage);

            const i18n = createTranslator(
                this.path,
                settings.get_string('language')
            );
            const page = this._buildPage(window, settings, i18n, rebuild);
            window._agentsTrayLimitsPage = page;
            window.add(page);
        };

        rebuild();
    }

    _buildPage(window, settings, i18n, rebuild) {
        const page = new Adw.PreferencesPage({
            title: i18n.t('app.name'),
            icon_name: 'view-statistics-symbolic',
        });

        const languageGroup = new Adw.PreferencesGroup({
            title: i18n.t('prefs.language.title'),
            description: i18n.t('prefs.language.description'),
        });
        page.add(languageGroup);

        const languageLabels = LANGUAGE_VALUES.map(value => value === 'system'
            ? i18n.t('language.system')
            : LANGUAGE_AUTONYMS[value]);
        let updatingLanguage = false;
        const languageRow = new Adw.ComboRow({
            title: i18n.t('prefs.language.rowTitle'),
            subtitle: i18n.t('prefs.language.rowSubtitle'),
            model: stringList(languageLabels),
            selected: selectedIndex(
                LANGUAGE_VALUES,
                settings.get_string('language')
            ),
        });
        languageRow.connect('notify::selected', row => {
            if (updatingLanguage)
                return;

            const language = LANGUAGE_VALUES[row.selected] ?? 'system';
            if (settings.get_string('language') === language)
                return;

            updatingLanguage = true;
            settings.set_string('language', language);
            GLib.idle_add(GLib.PRIORITY_DEFAULT_IDLE, () => {
                rebuild();
                return GLib.SOURCE_REMOVE;
            });
        });
        languageGroup.add(languageRow);

        const appearanceGroup = new Adw.PreferencesGroup({
            title: i18n.t('prefs.panel.title'),
            description: i18n.t('prefs.panel.description'),
        });
        page.add(appearanceGroup);

        const displayRow = new Adw.ComboRow({
            title: i18n.t('prefs.panelDisplay.title'),
            subtitle: i18n.t('prefs.panelDisplay.subtitle'),
            model: stringList([
                i18n.t('prefs.panelDisplay.remaining'),
                i18n.t('prefs.panelDisplay.used'),
            ]),
            selected: selectedIndex(
                DISPLAY_VALUES,
                settings.get_string('panel-display')
            ),
        });
        displayRow.connect('notify::selected', row => {
            settings.set_string(
                'panel-display',
                DISPLAY_VALUES[row.selected] ?? 'remaining'
            );
        });
        appearanceGroup.add(displayRow);

        const intervalRow = new Adw.ComboRow({
            title: i18n.t('prefs.refresh.title'),
            subtitle: i18n.t('prefs.refresh.subtitle'),
            model: stringList([
                i18n.t('prefs.refresh.oneMinute'),
                i18n.t('prefs.refresh.fiveMinutes'),
                i18n.t('prefs.refresh.fifteenMinutes'),
                i18n.t('prefs.refresh.thirtyMinutes'),
                i18n.t('prefs.refresh.oneHour'),
            ]),
            selected: selectedIndex(
                INTERVAL_VALUES,
                settings.get_uint('refresh-interval'),
                1
            ),
        });
        intervalRow.connect('notify::selected', row => {
            settings.set_uint(
                'refresh-interval',
                INTERVAL_VALUES[row.selected] ?? 300
            );
        });
        appearanceGroup.add(intervalRow);

        const showIconRow = new Adw.SwitchRow({
            title: i18n.t('prefs.showIcon.title'),
            subtitle: i18n.t('prefs.showIcon.subtitle'),
        });
        settings.bind(
            'show-icon',
            showIconRow,
            'active',
            Gio.SettingsBindFlags.DEFAULT
        );
        appearanceGroup.add(showIconRow);

        const themesGroup = new Adw.PreferencesGroup({
            title: i18n.t('prefs.themes.title'),
            description: i18n.t('prefs.themes.description'),
        });
        page.add(themesGroup);

        let themeIds = [];
        let updatingThemes = false;
        const themeRow = new Adw.ComboRow({
            title: i18n.t('prefs.theme.title'),
            subtitle: i18n.t('prefs.theme.subtitle'),
        });
        const refreshThemeModel = () => {
            const themes = sortedThemes(
                loadThemeCatalog(this.path, undefined, i18n),
                i18n.locale
            );
            themeIds = themes.map(theme => theme.id);
            updatingThemes = true;
            themeRow.model = stringList(themes.map(theme => {
                const suffix = theme.source === 'user'
                    ? ` · ${i18n.t('themes.userSuffix')}`
                    : '';
                return `${theme.name}${suffix}`;
            }));
            themeRow.selected = selectedIndex(
                themeIds,
                settings.get_string('theme-id')
            );
            updatingThemes = false;
        };
        themeRow.connect('notify::selected', row => {
            if (!updatingThemes) {
                settings.set_string(
                    'theme-id',
                    themeIds[row.selected] ?? 'classic'
                );
            }
        });
        refreshThemeModel();
        themesGroup.add(themeRow);

        const animationRow = new Adw.SwitchRow({
            title: i18n.t('prefs.themeAnimation.title'),
            subtitle: i18n.t('prefs.themeAnimation.subtitle'),
        });
        settings.bind(
            'theme-animation',
            animationRow,
            'active',
            Gio.SettingsBindFlags.DEFAULT
        );
        themesGroup.add(animationRow);

        const themeFolderRow = new Adw.ActionRow({
            title: i18n.t('prefs.userThemes.title'),
            subtitle: '~/.local/share/agents-tray-limits/themes/',
        });
        themeFolderRow.add_prefix(new Gtk.Image({
            icon_name: 'folder-symbolic',
            valign: Gtk.Align.CENTER,
        }));
        const openThemesButton = new Gtk.Button({
            label: i18n.t('prefs.userThemes.openFolder'),
            valign: Gtk.Align.CENTER,
        });
        openThemesButton.connect('clicked', () => {
            const path = userThemesDirectory();
            try {
                GLib.mkdir_with_parents(path, 0o700);
                Gio.AppInfo.launch_default_for_uri(
                    Gio.File.new_for_path(path).get_uri(),
                    null
                );
            } catch (error) {
                console.error(`[Agents Tray Limits] ${error.message}`);
            }
        });
        themeFolderRow.add_suffix(openThemesButton);
        themeFolderRow.activatable_widget = openThemesButton;
        themesGroup.add(themeFolderRow);

        const reloadThemesRow = new Adw.ActionRow({
            title: i18n.t('prefs.reloadThemes.title'),
            subtitle: i18n.t('prefs.reloadThemes.subtitle'),
        });
        reloadThemesRow.add_prefix(new Gtk.Image({
            icon_name: 'view-refresh-symbolic',
            valign: Gtk.Align.CENTER,
        }));
        const reloadThemesButton = new Gtk.Button({
            label: i18n.t('prefs.reloadThemes.button'),
            valign: Gtk.Align.CENTER,
        });
        reloadThemesButton.connect('clicked', () => {
            const selectedTheme = settings.get_string('theme-id');
            refreshThemeModel();
            if (selectedTheme !== 'classic' && themeIds.includes(selectedTheme)) {
                settings.set_string('theme-id', 'classic');
                GLib.idle_add(GLib.PRIORITY_DEFAULT_IDLE, () => {
                    settings.set_string('theme-id', selectedTheme);
                    return GLib.SOURCE_REMOVE;
                });
            }
        });
        reloadThemesRow.add_suffix(reloadThemesButton);
        reloadThemesRow.activatable_widget = reloadThemesButton;
        themesGroup.add(reloadThemesRow);

        const detailsGroup = new Adw.PreferencesGroup({
            title: i18n.t('prefs.menu.title'),
            description: i18n.t('prefs.menu.description'),
        });
        page.add(detailsGroup);

        const allBucketsRow = new Adw.SwitchRow({
            title: i18n.t('prefs.allBuckets.title'),
            subtitle: i18n.t('prefs.allBuckets.subtitle'),
        });
        settings.bind(
            'show-all-buckets',
            allBucketsRow,
            'active',
            Gio.SettingsBindFlags.DEFAULT
        );
        detailsGroup.add(allBucketsRow);

        const tokensRow = new Adw.SwitchRow({
            title: i18n.t('prefs.tokens.title'),
            subtitle: i18n.t('prefs.tokens.subtitle'),
        });
        settings.bind(
            'show-tokens',
            tokensRow,
            'active',
            Gio.SettingsBindFlags.DEFAULT
        );
        detailsGroup.add(tokensRow);

        const connectionGroup = new Adw.PreferencesGroup({
            title: i18n.t('prefs.connection.title'),
            description: i18n.t('prefs.connection.description'),
        });
        page.add(connectionGroup);

        const pathRow = new Adw.EntryRow({
            title: i18n.t('prefs.codexPath.title'),
        });
        pathRow.set_tooltip_text(i18n.t('prefs.codexPath.tooltip'));
        settings.bind(
            'codex-binary',
            pathRow,
            'text',
            Gio.SettingsBindFlags.DEFAULT
        );
        connectionGroup.add(pathRow);

        const authRow = new Adw.ActionRow({
            title: i18n.t('prefs.auth.title'),
            subtitle: i18n.t('prefs.auth.subtitle'),
        });
        authRow.add_prefix(new Gtk.Image({
            icon_name: 'system-lock-screen-symbolic',
            valign: Gtk.Align.CENTER,
        }));
        const openButton = new Gtk.Button({
            label: i18n.t('prefs.auth.openCodex'),
            valign: Gtk.Align.CENTER,
        });
        openButton.connect('clicked', () => {
            try {
                Gio.AppInfo.launch_default_for_uri(CHATGPT_CODEX_URL, null);
            } catch (error) {
                console.error(`[Agents Tray Limits] ${error.message}`);
            }
        });
        authRow.add_suffix(openButton);
        authRow.activatable_widget = openButton;
        connectionGroup.add(authRow);

        const privacyGroup = new Adw.PreferencesGroup({
            title: i18n.t('prefs.privacy.title'),
        });
        page.add(privacyGroup);

        const sourceRow = new Adw.ActionRow({
            title: i18n.t('prefs.source.title'),
            subtitle: i18n.t('prefs.source.subtitle'),
        });
        sourceRow.add_prefix(new Gtk.Image({
            icon_name: 'security-high-symbolic',
            valign: Gtk.Align.CENTER,
        }));
        privacyGroup.add(sourceRow);

        const scopeRow = new Adw.ActionRow({
            title: i18n.t('prefs.scope.title'),
            subtitle: i18n.t('prefs.scope.subtitle'),
        });
        scopeRow.add_prefix(new Gtk.Image({
            icon_name: 'dialog-information-symbolic',
            valign: Gtk.Align.CENTER,
        }));
        privacyGroup.add(scopeRow);

        return page;
    }
}
