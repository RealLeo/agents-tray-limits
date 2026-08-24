import Adw from 'gi://Adw';
import Gdk from 'gi://Gdk';
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
import {
    PROFILE_CONFIG_VERSION,
    loginCommand,
    parseProfilesDocument,
    providerName,
    validateProfileCandidate,
} from './profileLogic.js';

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

        page.add(this._buildProfilesGroup(settings, i18n, rebuild));

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

    _buildProfilesGroup(settings, i18n, rebuild) {
        const parsed = parseProfilesDocument(settings.get_string('profiles-json'));
        if (parsed.migrated)
            settings.set_string('profiles-json', parsed.serialized);
        const profiles = parsed.document.profiles;
        const group = new Adw.PreferencesGroup({
            title: i18n.t('prefs.profiles.title'),
            description: i18n.t('prefs.profiles.description'),
        });

        const activeIds = profiles.map(profile => profile.id);
        const currentActive = settings.get_string('active-profile-id');
        const activeRow = new Adw.ComboRow({
            title: i18n.t('prefs.profiles.active'),
            subtitle: i18n.t('prefs.profiles.activeSubtitle'),
            model: stringList(profiles.map(profile =>
                `${providerName(profile.provider)} · ${profile.label}`
            )),
            selected: Math.max(0, selectedIndex(activeIds, currentActive)),
        });
        activeRow.connect('notify::selected', row => {
            const profileId = activeIds[row.selected];
            if (profileId)
                settings.set_string('active-profile-id', profileId);
        });
        group.add(activeRow);

        for (const profile of profiles)
            group.add(this._profileEditorRow(profile, profiles, settings, i18n, rebuild));
        group.add(this._newProfileRow(profiles, settings, i18n, rebuild));
        return group;
    }

    _profileEditorRow(profile, profiles, settings, i18n, rebuild) {
        const installed = profile.provider === 'claude' &&
            this._claudeMonitorBackup(profile).query_exists(null);
        const row = new Adw.ExpanderRow({
            title: profile.label,
            subtitle: `${providerName(profile.provider)} · ` +
                (profile.configDir || i18n.t('prefs.profiles.defaultDirectory')),
        });
        row.add_prefix(new Gtk.Image({
            icon_name: profile.provider === 'claude'
                ? 'applications-science-symbolic'
                : 'utilities-terminal-symbolic',
            valign: Gtk.Align.CENTER,
        }));

        const labelRow = new Adw.EntryRow({
            title: i18n.t('prefs.profiles.label'),
            text: profile.label,
        });
        row.add_row(labelRow);
        const directoryRow = new Adw.EntryRow({
            title: profile.provider === 'claude'
                ? 'CLAUDE_CONFIG_DIR'
                : 'CODEX_HOME',
            text: profile.configDir,
            sensitive: !installed,
        });
        directoryRow.set_tooltip_text(installed
            ? i18n.t('prefs.profiles.disableBeforePathChange')
            : i18n.t('prefs.profiles.directoryTooltip'));
        row.add_row(directoryRow);

        const commandRow = new Adw.ActionRow({
            title: i18n.t('prefs.profiles.loginCommand'),
            subtitle: loginCommand(profile, settings.get_string('codex-binary').trim() || 'codex'),
        });
        const copyButton = new Gtk.Button({
            label: i18n.t('prefs.profiles.copy'),
            valign: Gtk.Align.CENTER,
        });
        copyButton.connect('clicked', () => {
            Gdk.Display.get_default()?.get_clipboard().set_text(commandRow.subtitle);
        });
        commandRow.add_suffix(copyButton);
        commandRow.activatable_widget = copyButton;
        row.add_row(commandRow);

        if (profile.provider === 'claude') {
            const monitorRow = new Adw.ActionRow({
                title: i18n.t('prefs.profiles.claudeMonitor'),
                subtitle: i18n.t(installed
                    ? 'prefs.profiles.claudeMonitorInstalled'
                    : 'prefs.profiles.claudeMonitorDisabled'),
            });
            const monitorButton = new Gtk.Button({
                label: i18n.t(installed
                    ? 'prefs.profiles.disableMonitor'
                    : 'prefs.profiles.enableMonitor'),
                valign: Gtk.Align.CENTER,
            });
            monitorButton.connect('clicked', () => {
                monitorButton.sensitive = false;
                const operation = installed
                    ? '--restore-claude-monitor'
                    : '--install-claude-monitor';
                this._runClaudeMonitor(profile, operation, payload => {
                    if (payload?.ok)
                        rebuild();
                    else {
                        monitorButton.sensitive = true;
                        monitorRow.subtitle = this._helperError(payload, i18n);
                    }
                });
            });
            monitorRow.add_suffix(monitorButton);
            monitorRow.activatable_widget = monitorButton;
            row.add_row(monitorRow);
        }

        const actions = new Adw.ActionRow({
            title: i18n.t('prefs.profiles.actions'),
        });
        const saveButton = new Gtk.Button({
            label: i18n.t('prefs.profiles.save'),
            valign: Gtk.Align.CENTER,
        });
        saveButton.connect('clicked', () => {
            const candidate = {
                ...profile,
                label: labelRow.text,
                configDir: directoryRow.text,
            };
            const validation = validateProfileCandidate(candidate, profiles, profile.id);
            if (!validation.ok) {
                row.subtitle = i18n.t(`prefs.profiles.validation.${validation.error}`);
                return;
            }
            this._replaceProfile(settings, profiles, validation.profile);
            rebuild();
        });
        actions.add_suffix(saveButton);

        const deleteButton = new Gtk.Button({
            label: i18n.t('prefs.profiles.remove'),
            valign: Gtk.Align.CENTER,
            sensitive: profiles.length > 1,
            css_classes: ['destructive-action'],
        });
        deleteButton.connect('clicked', () => {
            const remove = () => {
                const remaining = profiles.filter(item => item.id !== profile.id);
                this._writeProfiles(settings, remaining);
                if (settings.get_string('active-profile-id') === profile.id)
                    settings.set_string('active-profile-id', remaining[0]?.id ?? '');
                rebuild();
            };
            if (profile.provider === 'claude' && installed) {
                deleteButton.sensitive = false;
                this._runClaudeMonitor(profile, '--restore-claude-monitor', payload => {
                    if (payload?.ok)
                        remove();
                    else {
                        deleteButton.sensitive = true;
                        row.subtitle = this._helperError(payload, i18n);
                    }
                });
            } else {
                remove();
            }
        });
        actions.add_suffix(deleteButton);
        row.add_row(actions);
        return row;
    }

    _newProfileRow(profiles, settings, i18n, rebuild) {
        const row = new Adw.ExpanderRow({
            title: i18n.t('prefs.profiles.add'),
            subtitle: i18n.t('prefs.profiles.addSubtitle'),
        });
        row.add_prefix(new Gtk.Image({
            icon_name: 'list-add-symbolic',
            valign: Gtk.Align.CENTER,
        }));
        const providerRow = new Adw.ComboRow({
            title: i18n.t('prefs.profiles.provider'),
            model: stringList(['Codex', 'Claude Code']),
            selected: 0,
        });
        row.add_row(providerRow);
        const labelRow = new Adw.EntryRow({title: i18n.t('prefs.profiles.label')});
        row.add_row(labelRow);
        const directoryRow = new Adw.EntryRow({
            title: i18n.t('prefs.profiles.directory'),
        });
        row.add_row(directoryRow);
        const addRow = new Adw.ActionRow({title: i18n.t('prefs.profiles.addAction')});
        const addButton = new Gtk.Button({
            label: i18n.t('prefs.profiles.addButton'),
            valign: Gtk.Align.CENTER,
            css_classes: ['suggested-action'],
        });
        addButton.connect('clicked', () => {
            const candidate = {
                id: GLib.uuid_string_random(),
                provider: providerRow.selected === 1 ? 'claude' : 'codex',
                label: labelRow.text,
                configDir: directoryRow.text,
            };
            const validation = validateProfileCandidate(candidate, profiles);
            if (!validation.ok) {
                row.subtitle = i18n.t(`prefs.profiles.validation.${validation.error}`);
                return;
            }
            this._writeProfiles(settings, [...profiles, validation.profile]);
            settings.set_string('active-profile-id', validation.profile.id);
            rebuild();
        });
        addRow.add_suffix(addButton);
        addRow.activatable_widget = addButton;
        row.add_row(addRow);
        return row;
    }

    _replaceProfile(settings, profiles, replacement) {
        this._writeProfiles(settings, profiles.map(profile =>
            profile.id === replacement.id ? replacement : profile
        ));
    }

    _writeProfiles(settings, profiles) {
        settings.set_string('profiles-json', JSON.stringify({
            version: PROFILE_CONFIG_VERSION,
            profiles,
        }));
    }

    _expandedProfileDirectory(profile) {
        if (profile.configDir.startsWith('~/'))
            return GLib.build_filenamev([GLib.get_home_dir(), profile.configDir.slice(2)]);
        if (profile.configDir)
            return profile.configDir;
        return GLib.build_filenamev([GLib.get_home_dir(), '.claude']);
    }

    _claudeMonitorBackup(profile) {
        return Gio.File.new_for_path(GLib.build_filenamev([
            this._expandedProfileDirectory(profile),
            'agents-tray-limits',
            'statusline-backup.json',
        ]));
    }

    _runClaudeMonitor(profile, operation, callback) {
        const pythonPath = GLib.file_test('/usr/bin/python3', GLib.FileTest.IS_EXECUTABLE)
            ? '/usr/bin/python3'
            : GLib.find_program_in_path('python3');
        if (!pythonPath) {
            callback({ok: false, errorCode: 'python_not_found'});
            return;
        }
        const helperPath = GLib.build_filenamev([
            this.path,
            'bin',
            'agents-tray-limits-helper.py',
        ]);
        const argv = [
            pythonPath,
            helperPath,
            '--provider',
            'claude',
            '--profile-id',
            profile.id,
            operation,
        ];
        if (profile.configDir)
            argv.push('--config-dir', profile.configDir);
        try {
            const process = Gio.Subprocess.new(
                argv,
                Gio.SubprocessFlags.STDOUT_PIPE | Gio.SubprocessFlags.STDERR_PIPE
            );
            process.communicate_utf8_async(null, null, (source, result) => {
                try {
                    const [, stdout, stderr] = source.communicate_utf8_finish(result);
                    const payload = JSON.parse((stdout ?? '').trim());
                    if (!payload.ok && stderr)
                        payload.details ??= stderr.trim();
                    callback(payload);
                } catch (error) {
                    callback({ok: false, errorCode: 'helper_failed', details: error.message});
                }
            });
        } catch (error) {
            callback({ok: false, errorCode: 'helper_start_failed', details: error.message});
        }
    }

    _helperError(payload, i18n) {
        const key = `errors.${payload?.errorCode ?? 'unknown_error'}`;
        const translated = i18n.t(key);
        return translated === key
            ? String(payload?.message ?? payload?.details ?? i18n.t('errors.unknown_error'))
            : translated;
    }
}
