import Clutter from 'gi://Clutter';
import Gio from 'gi://Gio';
import GLib from 'gi://GLib';
import GObject from 'gi://GObject';
import Meta from 'gi://Meta';
import Pango from 'gi://Pango';
import St from 'gi://St';

import {Extension} from 'resource:///org/gnome/shell/extensions/extension.js';
import * as Main from 'resource:///org/gnome/shell/ui/main.js';
import * as PanelMenu from 'resource:///org/gnome/shell/ui/panelMenu.js';
import * as PopupMenu from 'resource:///org/gnome/shell/ui/popupMenu.js';

import {createTranslator} from './i18n.js';

import {
    AnimationLoop,
    CLASSIC_THEME_ID,
    FrameAnimationLoop,
    FrameAnimationSession,
    RepeatingTimer,
    STATUS_DETAILS,
    StylesheetLifecycle,
    formatPanelValue,
    mainCodexBucket,
    migrateThemeId,
    primaryCodexRemaining,
    statusForRemaining,
} from './themeLogic.js';
import {loadThemeCatalog, resolveTheme} from './themeLoader.js';

const PANEL_PROGRESS_WIDTH = 270;
const CHATGPT_CODEX_URL = 'https://chatgpt.com/codex';

const PLAN_NAMES = {
    free: 'Free',
    plus: 'Plus',
    pro: 'Pro',
    team: 'Team',
    business: 'Business',
    enterprise: 'Enterprise',
    edu: 'Edu',
};

function clampPercent(value) {
    const number = Number(value);
    if (!Number.isFinite(number))
        return 0;
    return Math.max(0, Math.min(100, number));
}

function formatInteger(value, i18n) {
    const number = Number(value);
    if (!Number.isFinite(number))
        return '—';
    return i18n.formatNumber(number, {maximumFractionDigits: 0});
}

function formatCompactNumber(value, i18n) {
    const number = Number(value);
    if (!Number.isFinite(number))
        return '—';
    if (Math.abs(number) >= 10_000) {
        return i18n.formatNumber(number, {
            notation: 'compact',
            maximumFractionDigits: 2,
        });
    }
    return formatInteger(number, i18n);
}

function formatWindow(minutes, short, i18n) {
    const value = Math.max(0, Math.round(Number(minutes) || 0));
    if (value === 0)
        return i18n.t(short ? 'time.limitShort' : 'time.limit');
    if (value % 1440 === 0) {
        const days = value / 1440;
        return i18n.tn(short ? 'time.dayShort' : 'time.day', days);
    }
    if (value % 60 === 0) {
        const hours = value / 60;
        return i18n.tn(short ? 'time.hourShort' : 'time.hour', hours);
    }
    return i18n.tn(short ? 'time.minuteShort' : 'time.minute', value);
}

function formatRelativeReset(timestamp, i18n) {
    const target = Number(timestamp);
    if (!Number.isFinite(target) || target <= 0)
        return i18n.t('time.resetUnknown');

    const now = Math.floor(Date.now() / 1000);
    let seconds = Math.max(0, Math.round(target - now));
    if (seconds <= 0)
        return i18n.t('time.resetting');

    const days = Math.floor(seconds / 86400);
    seconds %= 86400;
    const hours = Math.floor(seconds / 3600);
    seconds %= 3600;
    const minutes = Math.floor(seconds / 60);

    const parts = [];
    if (days > 0)
        parts.push(i18n.tn('time.day', days));
    if (hours > 0 && parts.length < 2)
        parts.push(i18n.tn('time.hour', hours));
    if (days === 0 && parts.length < 2 && (minutes > 0 || parts.length === 0))
        parts.push(i18n.tn('time.minute', Math.max(1, minutes)));

    let exact = null;
    try {
        exact = i18n.formatDate(new Date(target * 1000), {
            day: '2-digit',
            month: '2-digit',
            hour: '2-digit',
            minute: '2-digit',
        });
    } catch (_error) {
        // Relative time remains useful if the platform cannot format the date.
    }
    return exact
        ? i18n.t('time.resetInExact', {relative: parts.join(' '), exact})
        : i18n.t('time.resetIn', {relative: parts.join(' ')});
}

function formatUpdated(timestamp, i18n) {
    const value = Number(timestamp);
    if (!Number.isFinite(value) || value <= 0)
        return i18n.t('time.notUpdated');
    const age = Math.max(0, Math.floor(Date.now() / 1000) - value);
    if (age < 15)
        return i18n.t('time.updatedNow');
    if (age < 60)
        return i18n.tn('time.updatedSeconds', age);
    if (age < 3600)
        return i18n.tn('time.updatedMinutes', Math.floor(age / 60));
    return i18n.tn('time.updatedHours', Math.floor(age / 3600));
}

function humanizeBucket(bucket) {
    const id = String(bucket?.limitId ?? '').trim();
    const name = String(bucket?.limitName ?? '').trim();
    if (name && name !== id)
        return name;
    if (!id || id === 'codex')
        return 'Codex';
    return id
        .replace(/^codex[_-]?/i, 'Codex ')
        .replace(/[_-]+/g, ' ')
        .replace(/\b\w/g, letter => letter.toUpperCase());
}

function planLabel(planType) {
    const key = String(planType ?? '').toLowerCase();
    return PLAN_NAMES[key] ?? (planType ? String(planType) : 'ChatGPT');
}

function defaultRateBucket(payload) {
    return mainCodexBucket(payload);
}

const UsageIndicator = GObject.registerClass(
class UsageIndicator extends PanelMenu.Button {
    _init(extension) {
        super._init(0.0, extension.metadata.name, false);
        this._extension = extension;

        this._box = new St.BoxLayout({
            style_class: 'agents-tray-limits-panel-box',
            y_align: Clutter.ActorAlign.CENTER,
        });
        this.add_child(this._box);

        this._defaultIconFile = Gio.File.new_for_path(GLib.build_filenamev([
            extension.path,
            'icons',
            'agents-tray-limits-symbolic.svg',
        ]));
        this._icon = new St.Icon({
            gicon: new Gio.FileIcon({file: this._defaultIconFile}),
            style_class: 'system-status-icon',
            y_align: Clutter.ActorAlign.CENTER,
        });
        this._label = new St.Label({
            text: '…',
            style_class: 'agents-tray-limits-panel-label',
            y_align: Clutter.ActorAlign.CENTER,
        });
        this._box.add_child(this._label);
        this._box.add_child(this._icon);

        this.accessible_name = extension._i18n.t('app.name');
        this.menu.connect('open-state-changed', (_menu, open) => {
            this._extension.onMenuStateChanged(open);
        });
    }

    setAppearance(showIcon) {
        this._icon.visible = showIcon;
    }

    setIconFile(path = null) {
        const file = path ? Gio.File.new_for_path(path) : this._defaultIconFile;
        this._icon.gicon = new Gio.FileIcon({file});
        this._icon.icon_size = path ? 22 : 16;
    }

    setPanelText(text, severity = 'normal') {
        this._label.text = text;
        this._label.set_style_class_name('agents-tray-limits-panel-label');
        if (severity === 'warning' || severity === 'critical')
            this._label.add_style_class_name(severity);
        this.accessible_name = this._extension._i18n.t('app.accessibleValue', {value: text});
    }
});

export default class AgentsTrayLimitsExtension extends Extension {
    enable() {
        this._enabled = true;
        this._data = null;
        this._error = null;
        this._refreshing = false;
        this._lastRefreshAttempt = 0;
        this._timeoutId = 0;
        this._process = null;
        this._cancellable = null;
        this._menuArt = null;
        this._menuArtFrames = [];
        this._menuArtStatus = null;
        this._pointerCursorActive = false;
        this._pipboyTooltip = null;
        this._pipboyTooltipAnchor = null;
        this._contentTarget = null;
        this._framePreloadBin = null;
        this._theme = null;
        this._themeClass = null;
        this._statusClass = null;

        this._settings = this.getSettings();
        this._i18n = createTranslator(
            this.path,
            this._settings.get_string('language')
        );
        const configuredTheme = this._settings.get_string('theme-id');
        const migratedTheme = migrateThemeId(configuredTheme);
        if (migratedTheme !== configuredTheme)
            this._settings.set_string('theme-id', migratedTheme);
        this._settingsChangedId = this._settings.connect('changed', (_settings, key) => {
            this._onSettingChanged(key);
        });

        this._indicator = new UsageIndicator(this);
        Main.panel.addToStatusArea(this.uuid, this._indicator);

        this._interfaceSettings = new Gio.Settings({
            schema_id: 'org.gnome.desktop.interface',
        });
        this._animationsChangedId = this._interfaceSettings.connect(
            'changed::enable-animations',
            () => this._syncArtAnimation()
        );
        this._stylesheetLifecycle = new StylesheetLifecycle(
            path => this._shellTheme().load_stylesheet(Gio.File.new_for_path(path)),
            path => this._shellTheme().unload_stylesheet(Gio.File.new_for_path(path))
        );
        this._animationLoop = new AnimationLoop(
            (interval, callback) => GLib.timeout_add(
                GLib.PRIORITY_DEFAULT,
                interval,
                callback
            ),
            sourceId => GLib.Source.remove(sourceId),
            step => this._applyAnimationStep(step)
        );
        this._frameAnimationLoop = new FrameAnimationLoop(
            (interval, callback) => GLib.timeout_add(
                GLib.PRIORITY_DEFAULT,
                interval,
                callback
            ),
            sourceId => GLib.Source.remove(sourceId),
            index => this._showMenuArtFrame(index)
        );
        this._frameAnimationSession = new FrameAnimationSession();
        this._panelClock = new RepeatingTimer(
            (interval, callback) => GLib.timeout_add_seconds(
                GLib.PRIORITY_DEFAULT,
                interval,
                callback
            ),
            sourceId => GLib.Source.remove(sourceId),
            () => this._updatePanelText()
        );

        this._reloadTheme();
        this._applyAppearance();
        this._buildLoadingMenu();
        this._reschedule();
        this._startPanelClock();
        this._refresh();
    }

    disable() {
        this._enabled = false;
        this._stopArtAnimation();
        this._setPointerCursor(false);
        this._hidePipboyTooltip();

        if (this._timeoutId) {
            GLib.Source.remove(this._timeoutId);
            this._timeoutId = 0;
        }
        this._panelClock?.stop();

        if (this._settings && this._settingsChangedId) {
            this._settings.disconnect(this._settingsChangedId);
            this._settingsChangedId = 0;
        }

        if (this._interfaceSettings && this._animationsChangedId) {
            this._interfaceSettings.disconnect(this._animationsChangedId);
            this._animationsChangedId = 0;
        }

        if (this._cancellable)
            this._cancellable.cancel();
        this._cancellable = null;

        if (this._process) {
            try {
                this._process.force_exit();
            } catch (_error) {
                // It may have exited between the check and force_exit().
            }
        }
        this._process = null;

        this._stylesheetLifecycle?.clear();
        this._stylesheetLifecycle = null;
        this._clearFramePreloads();
        this._animationLoop = null;
        this._frameAnimationLoop = null;
        this._frameAnimationSession = null;
        this._panelClock = null;
        this._removeThemeClasses();

        this._indicator?.destroy();
        this._indicator = null;
        this._settings = null;
        this._data = null;
        this._error = null;
        this._interfaceSettings = null;
        this._theme = null;
        this._i18n = null;
    }

    onMenuStateChanged(open) {
        if (!open) {
            this._stopArtAnimation();
            this._setPointerCursor(false);
            this._hidePipboyTooltip();
            this._frameAnimationSession?.reset();
            return;
        }

        if (!this._data || this._error) {
            this._refresh();
            return;
        }

        const interval = Math.max(60, this._settings.get_uint('refresh-interval'));
        const age = Math.floor(Date.now() / 1000) - Number(this._data.fetchedAt ?? 0);
        if (age >= interval)
            this._refresh();
        else
            this._buildDataMenu();
    }

    _onSettingChanged(key) {
        if (!this._enabled)
            return;

        if (key === 'language') {
            this._i18n = createTranslator(
                this.path,
                this._settings.get_string('language')
            );
        }

        if (key === 'theme-id' || key === 'language')
            this._reloadTheme();

        this._applyAppearance();
        if (key === 'refresh-interval')
            this._reschedule();
        if (this._error)
            this._buildErrorMenu();
        else if (this._data)
            this._buildDataMenu();

        if (key === 'codex-binary')
            this._refresh();
        if (key === 'theme-animation')
            this._syncArtAnimation();
    }

    _applyAppearance() {
        if (!this._indicator || !this._settings)
            return;
        this._indicator.setAppearance(this._settings.get_boolean('show-icon'));
        this._updatePanelText();
    }

    _setPointerCursor(active) {
        const enabled = Boolean(active);
        if (this._pointerCursorActive === enabled)
            return;
        this._pointerCursorActive = enabled;
        try {
            global.display.set_cursor(enabled
                ? Meta.Cursor.POINTING_HAND
                : Meta.Cursor.DEFAULT);
        } catch (_error) {
            // Older Shell builds may not expose cursor control to extensions.
        }
    }

    _showPipboyTooltip(button, text) {
        this._hidePipboyTooltip();
        const tooltip = new St.Label({
            text,
            reactive: false,
            style_class: 'agents-tray-limits-pipboy-tooltip',
        });
        Main.uiGroup.add_child(tooltip);
        const [buttonX, buttonY] = button.get_transformed_position();
        const [buttonWidth, buttonHeight] = button.get_transformed_size();
        const [, naturalWidth] = tooltip.get_preferred_width(-1);
        const [, naturalHeight] = tooltip.get_preferred_height(naturalWidth);
        tooltip.set_position(
            Math.round(buttonX + buttonWidth + 6),
            Math.round(buttonY + (buttonHeight - naturalHeight) / 2)
        );
        this._pipboyTooltip = tooltip;
        this._pipboyTooltipAnchor = button;
    }

    _hidePipboyTooltip(button = null) {
        if (button && this._pipboyTooltipAnchor !== button)
            return;
        this._pipboyTooltip?.destroy();
        this._pipboyTooltip = null;
        this._pipboyTooltipAnchor = null;
    }

    _shellTheme() {
        return St.ThemeContext.get_for_stage(global.stage).get_theme();
    }

    _themeActors() {
        return [this._indicator, this._indicator?.menu?.actor].filter(Boolean);
    }

    _removeThemeClasses() {
        for (const actor of this._themeActors()) {
            if (this._themeClass)
                actor.remove_style_class_name(this._themeClass);
            if (this._statusClass)
                actor.remove_style_class_name(this._statusClass);
        }
        this._themeClass = null;
        this._statusClass = null;
    }

    _reloadTheme() {
        if (!this._settings || !this._indicator)
            return;

        this._stopArtAnimation();
        this._setPointerCursor(false);
        this._hidePipboyTooltip();
        this._frameAnimationSession?.reset();
        this._stylesheetLifecycle?.clear();
        this._removeThemeClasses();

        const catalog = loadThemeCatalog(this.path, undefined, this._i18n);
        let theme = resolveTheme(catalog, this._settings.get_string('theme-id'));
        if (theme.stylesheetPath && !this._stylesheetLifecycle.apply(theme.stylesheetPath))
            theme = resolveTheme(catalog, CLASSIC_THEME_ID);
        this._theme = theme;
        this._preloadThemeFrames();

        if (theme.id !== CLASSIC_THEME_ID) {
            this._themeClass = `agents-tray-limits-theme-${theme.id}`;
            for (const actor of this._themeActors())
                actor.add_style_class_name(this._themeClass);
        }
    }

    _setThemeStatus(status) {
        for (const actor of this._themeActors()) {
            if (this._statusClass)
                actor.remove_style_class_name(this._statusClass);
        }
        this._statusClass = null;

        if (!status || this._theme?.id === CLASSIC_THEME_ID || !this._theme?.panelArtPaths) {
            this._indicator?.setIconFile();
            return;
        }

        this._statusClass = `agents-tray-limits-status-${status}`;
        for (const actor of this._themeActors())
            actor.add_style_class_name(this._statusClass);
        this._indicator?.setIconFile(this._theme.panelArtPaths[status]);
    }

    _clearFramePreloads() {
        this._framePreloadBin?.destroy();
        this._framePreloadBin = null;
    }

    _preloadThemeFrames() {
        this._clearFramePreloads();
        const pathsByStatus = this._theme?.frameAnimationPaths;
        if (!pathsByStatus)
            return;

        const bin = new St.Widget({
            layout_manager: new Clutter.BinLayout(),
            width: 1,
            height: 1,
            x: -512,
            y: -512,
            opacity: 0,
            reactive: false,
            clip_to_allocation: true,
        });
        for (const paths of Object.values(pathsByStatus)) {
            for (const path of paths) {
                bin.add_child(new St.Icon({
                    gicon: new Gio.FileIcon({file: Gio.File.new_for_path(path)}),
                    icon_size: 164,
                }));
            }
        }
        Main.uiGroup.add_child(bin);
        this._framePreloadBin = bin;
    }

    _applyAnimationStep(step) {
        if (!this._menuArt)
            return;
        this._menuArt.translation_x = step.x;
        this._menuArt.translation_y = step.y;
        this._menuArt.opacity = step.opacity;
        this._menuArt.scale_x = step.scale;
        this._menuArt.scale_y = step.scale;
    }

    _resetMenuArt() {
        if (!this._menuArt)
            return;
        this._applyAnimationStep({x: 0, y: 0, opacity: 255, scale: 1});
    }

    _showMenuArtFrame(index) {
        if (!this._menuArtFrames?.length)
            return;
        const safeIndex = Math.max(0, Math.min(this._menuArtFrames.length - 1, index));

        for (const actor of this._menuArtFrames) {
            actor.visible = false;
            actor.opacity = 255;
        }
        this._menuArtFrames[safeIndex].visible = true;
    }

    _stopArtAnimation() {
        this._animationLoop?.stop();
        this._frameAnimationLoop?.stop();
        this._resetMenuArt();
    }

    _syncArtAnimation() {
        this._stopArtAnimation();
        const frameAnimation = this._theme?.frameAnimation;
        if (this._menuArtFrames?.length && frameAnimation) {
            const finalIndex = this._menuArtFrames.length - 1;
            this._showMenuArtFrame(finalIndex);
            if (!this._indicator?.menu?.isOpen)
                return;
            if (!this._settings.get_boolean('theme-animation'))
                return;
            if (!this._interfaceSettings.get_boolean('enable-animations'))
                return;
            if (!this._frameAnimationSession.shouldPlay(this._menuArtStatus))
                return;
            this._frameAnimationSession.markPlayed(this._menuArtStatus);
            this._frameAnimationLoop.start(frameAnimation.intervalMs, this._menuArtFrames);
            return;
        }

        const animation = this._theme?.animation;
        if (!this._menuArt || !animation || !this._indicator?.menu?.isOpen)
            return;
        if (!this._settings.get_boolean('theme-animation'))
            return;
        if (!this._interfaceSettings.get_boolean('enable-animations'))
            return;
        this._animationLoop.start(animation.intervalMs, animation.steps);
    }

    _reschedule() {
        if (this._timeoutId) {
            GLib.Source.remove(this._timeoutId);
            this._timeoutId = 0;
        }
        if (!this._settings)
            return;

        const interval = Math.max(60, this._settings.get_uint('refresh-interval'));
        this._timeoutId = GLib.timeout_add_seconds(GLib.PRIORITY_DEFAULT, interval, () => {
            this._refresh();
            return GLib.SOURCE_CONTINUE;
        });
    }

    _startPanelClock() {
        this._panelClock?.start(60);
    }

    _refresh() {
        if (!this._enabled || this._refreshing)
            return;

        this._refreshing = true;
        this._lastRefreshAttempt = Math.floor(Date.now() / 1000);
        if (!this._data)
            this._buildLoadingMenu();
        else if (this._error)
            this._buildErrorMenu();
        else
            this._buildDataMenu();

        const helperPath = GLib.build_filenamev([
            this.path,
            'bin',
            'agents-tray-limits-helper.py',
        ]);
        const pythonPath = GLib.file_test('/usr/bin/python3', GLib.FileTest.IS_EXECUTABLE)
            ? '/usr/bin/python3'
            : GLib.find_program_in_path('python3');

        if (!pythonPath) {
            this._finishWithError({
                errorCode: 'python_not_found',
                message: this._i18n.t('errors.python_not_found'),
            });
            return;
        }

        const argv = [pythonPath, helperPath, '--timeout', '15'];
        const configuredCodex = this._settings.get_string('codex-binary').trim();
        if (configuredCodex)
            argv.push('--codex-bin', configuredCodex);

        try {
            this._cancellable = new Gio.Cancellable();
            this._process = Gio.Subprocess.new(
                argv,
                Gio.SubprocessFlags.STDOUT_PIPE | Gio.SubprocessFlags.STDERR_PIPE
            );
            this._process.communicate_utf8_async(
                null,
                this._cancellable,
                (process, result) => this._onHelperFinished(process, result)
            );
        } catch (error) {
            this._finishWithError({
                errorCode: 'helper_start_failed',
                message: this._i18n.t('errors.helper_start_failed'),
                details: error.message,
            });
        }
    }

    _onHelperFinished(process, result) {
        if (!this._enabled)
            return;

        let stdout = '';
        let stderr = '';
        try {
            [, stdout, stderr] = process.communicate_utf8_finish(result);
        } catch (error) {
            if (error.matches?.(Gio.io_error_quark(), Gio.IOErrorEnum.CANCELLED))
                return;
            this._finishWithError({
                errorCode: 'helper_failed',
                message: this._i18n.t('errors.helper_failed'),
                details: error.message,
            });
            return;
        } finally {
            this._process = null;
            this._cancellable = null;
        }

        let payload;
        try {
            payload = JSON.parse((stdout ?? '').trim());
        } catch (error) {
            this._finishWithError({
                errorCode: 'invalid_helper_response',
                message: this._i18n.t('errors.invalid_helper_response'),
                details: (stderr || stdout || error.message).trim().slice(-1200),
            });
            return;
        }

        if (!payload?.ok) {
            this._finishWithError(payload ?? {
                errorCode: 'unknown_error',
                message: this._i18n.t('errors.unknown_error'),
            });
            return;
        }

        this._refreshing = false;
        this._error = null;
        this._data = payload;
        this._updatePanelText();
        this._buildDataMenu();
    }

    _finishWithError(error) {
        this._refreshing = false;
        this._process = null;
        this._cancellable = null;
        this._error = error;
        const code = String(error?.errorCode ?? 'unknown_error');
        const technical = String(error?.details ?? error?.message ?? '').trim();
        if (technical)
            console.error(`[Agents Tray Limits] ${code}: ${technical}`);
        this._updatePanelText();
        this._buildErrorMenu();
    }

    _updatePanelText() {
        if (!this._indicator || !this._settings)
            return;

        if (this._refreshing && !this._data) {
            this._setThemeStatus(null);
            this._indicator.setPanelText('…');
            return;
        }
        if (this._error) {
            this._setThemeStatus(null);
            this._indicator.setPanelText('!', 'critical');
            return;
        }

        const bucket = defaultRateBucket(this._data);
        if (!bucket) {
            this._setThemeStatus(null);
            this._indicator.setPanelText('—');
            return;
        }

        const primary = bucket.primary;
        if (!primary || typeof primary !== 'object') {
            this._setThemeStatus(null);
            this._indicator.setPanelText('—');
            return;
        }

        const status = statusForRemaining(primaryCodexRemaining(this._data));
        this._setThemeStatus(status);

        const display = this._settings.get_string('panel-display');
        const text = formatPanelValue(
            this._data,
            display,
            Date.now() / 1000,
            this._i18n
        );
        if (!text) {
            this._setThemeStatus(null);
            this._indicator.setPanelText('—');
            return;
        }
        const used = clampPercent(primary.usedPercent);
        const severity = used >= 90 ? 'critical' : used >= 70 ? 'warning' : 'normal';
        this._indicator.setPanelText(text, severity);
    }

    _buildLoadingMenu() {
        if (!this._indicator)
            return;
        this._prepareMenu();
        if (this._usesPipboyLayout()) {
            this._beginPipboyLayout(null, null, 'loading');
            this._addHeader('PIP-BOY 2000', this._i18n.t('menu.connecting'));
            this._addMessage(this._i18n.t('menu.loading'));
            this._endPipboyLayout();
            return;
        }
        this._addHeader(this._i18n.t('app.name'), this._i18n.t('menu.connecting'));
        this._addMessage(this._i18n.t('menu.loading'));
        this._addCommonActions(false);
    }

    _buildErrorMenu() {
        if (!this._indicator)
            return;
        this._prepareMenu();

        const error = this._error ?? {};
        if (this._usesPipboyLayout())
            this._beginPipboyLayout(null, null, 'error');
        this._addHeader(this._i18n.t('app.name'), this._i18n.t('menu.unavailable'));
        this._addMessage(this._errorMessage(error.errorCode, error.message), true);

        const hint = this._errorHint(error.errorCode);
        if (hint)
            this._addMessage(hint);

        const code = error.errorCode
            ? this._i18n.t('menu.errorCode', {code: error.errorCode})
            : null;
        if (code)
            this._addMutedLine(code);

        if (this._usesPipboyLayout())
            this._endPipboyLayout();
        else
            this._addCommonActions(true);
    }

    _buildDataMenu() {
        if (!this._indicator || !this._data)
            return;

        if (this._usesPipboyLayout()) {
            this._buildPipboyDataMenu();
            return;
        }

        const menu = this._indicator.menu;
        this._prepareMenu();

        const account = this._data.account ?? {};
        const plan = planLabel(account.planType);
        const accountTitle = plan === 'ChatGPT' ? 'ChatGPT' : `ChatGPT ${plan}`;
        const accountSubtitle = account.email || this._i18n.t('menu.accountViaCodex');
        this._addHeader(
            accountTitle,
            accountSubtitle,
            formatUpdated(this._data.fetchedAt, this._i18n)
        );

        const remaining = primaryCodexRemaining(this._data);
        const status = statusForRemaining(remaining);
        if (status && this._theme?.id !== CLASSIC_THEME_ID)
            this._addThemeStatusCard(status, Math.round(remaining));

        const buckets = this._getBuckets();
        if (buckets.length === 0) {
            this._addMessage(this._i18n.t('menu.noActiveLimits'));
        } else {
            for (const [index, bucket] of buckets.entries()) {
                const title = buckets.length > 1
                    ? humanizeBucket(bucket)
                    : this._i18n.t('menu.limits');
                this._addSection(title);
                this._addBucket(bucket);
                if (index === buckets.length - 1)
                    this._addResetCredits();
            }
        }

        if (this._settings.get_boolean('show-tokens'))
            this._addTokenUsage();

        this._addCommonActions(true);
        this._syncArtAnimation();
    }

    _prepareMenu() {
        this._stopArtAnimation();
        this._setPointerCursor(false);
        this._hidePipboyTooltip();
        this._menuArt = null;
        this._menuArtFrames = [];
        this._menuArtStatus = null;
        this._contentTarget = null;
        this._indicator.menu.removeAll();
    }

    _usesPipboyLayout() {
        return this._theme?.layout === 'pipboy-2000';
    }

    _buildPipboyDataMenu() {
        this._prepareMenu();

        const remaining = primaryCodexRemaining(this._data);
        const status = statusForRemaining(remaining);
        this._beginPipboyLayout(status, remaining, 'normal');

        const account = this._data.account ?? {};
        const plan = planLabel(account.planType);
        const accountTitle = plan === 'ChatGPT' ? 'ChatGPT' : `ChatGPT ${plan}`;
        const accountSubtitle = account.email || this._i18n.t('menu.accountViaCodex');
        this._addHeader(
            accountTitle,
            accountSubtitle,
            formatUpdated(this._data.fetchedAt, this._i18n)
        );
        if (status)
            this._addPipboyState(status, Math.round(remaining));
        else
            this._addMessage(this._i18n.t('menu.noPrimary'));

        const buckets = this._getBuckets();
        if (buckets.length === 0) {
            this._addMessage(this._i18n.t('menu.noActiveLimits'));
        } else {
            for (const [index, bucket] of buckets.entries()) {
                const title = buckets.length > 1
                    ? humanizeBucket(bucket)
                    : this._i18n.t('menu.limits');
                this._addSection(title);
                this._addBucket(bucket);
                if (index === buckets.length - 1)
                    this._addResetCredits();
            }
        }

        if (this._settings.get_boolean('show-tokens'))
            this._addTokenUsage();

        this._endPipboyLayout();
        this._syncArtAnimation();
    }

    _beginPipboyLayout(status, remaining, mode) {
        const item = new PopupMenu.PopupMenuItem('', {
            reactive: false,
            can_focus: false,
            hover: false,
            style_class: 'agents-tray-limits-pipboy-item',
        });
        item.label.hide();

        const device = new St.Widget({
            layout_manager: new Clutter.FixedLayout(),
            width: 680,
            height: 520,
            clip_to_allocation: true,
            style_class: 'agents-tray-limits-pipboy-device',
        });
        const badgeText = new St.Label({
            text: 'PIP-BOY 2000',
            style_class: 'agents-tray-limits-pipboy-badge',
        });
        badgeText.clutter_text.ellipsize = Pango.EllipsizeMode.NONE;
        badgeText.clutter_text.line_wrap = false;
        badgeText.clutter_text.single_line_mode = true;
        const badge = new St.Bin({
            x: 20,
            y: 20,
            width: 194,
            height: 22,
            x_align: Clutter.ActorAlign.CENTER,
            y_align: Clutter.ActorAlign.CENTER,
            child: badgeText,
        });
        device.add_child(badge);

        const artFrame = new St.Widget({
            layout_manager: new Clutter.FixedLayout(),
            x: 40,
            y: 56,
            width: 136,
            height: 116,
            clip_to_allocation: true,
            style_class: `agents-tray-limits-pipboy-art-frame ${mode}`,
        });
        if (status && this._theme?.artPaths?.[status]) {
            const paths = this._theme.frameAnimationPaths?.[status] ??
                [this._theme.artPaths[status]];
            for (const path of paths) {
                const icon = new St.Icon({
                    gicon: new Gio.FileIcon({file: Gio.File.new_for_path(path)}),
                    icon_size: 98,
                    x: 19,
                    y: 0,
                    width: 98,
                    height: 98,
                    style_class: 'agents-tray-limits-pipboy-art',
                });
                icon.visible = true;
                icon.opacity = 0;
                artFrame.add_child(icon);
                this._menuArtFrames.push(icon);
            }
            this._menuArtStatus = status;
            if (this._menuArtFrames.length === 1)
                this._menuArt = this._menuArtFrames[0];
            this._showMenuArtFrame(this._menuArtFrames.length - 1);

            const artStatus = new St.BoxLayout({
                vertical: true,
                x: 2,
                y: 90,
                width: 132,
                height: 26,
                style_class: 'agents-tray-limits-pipboy-art-status',
            });
            artStatus.add_child(new St.Label({
                text: this._i18n.t(STATUS_DETAILS[status].key),
                x_align: Clutter.ActorAlign.CENTER,
                style_class: 'agents-tray-limits-pipboy-rail-state',
            }));
            artStatus.add_child(new St.Label({
                text: this._i18n.t('status.remainingUpper', {
                    value: Math.round(remaining),
                }),
                x_align: Clutter.ActorAlign.CENTER,
                style_class: 'agents-tray-limits-pipboy-rail-value',
            }));
            artFrame.add_child(artStatus);
        } else {
            const offline = new St.Bin({
                x: 0,
                y: 0,
                width: 136,
                height: 116,
                x_align: Clutter.ActorAlign.CENTER,
                y_align: Clutter.ActorAlign.CENTER,
                child: new St.Label({
                    text: this._i18n.t(
                        mode === 'loading' ? 'pipboy.standby' : 'pipboy.offline'
                    ),
                    style_class: 'agents-tray-limits-pipboy-offline',
                }),
            });
            artFrame.add_child(offline);
        }
        device.add_child(artFrame);

        const actionBay = new St.Widget({
            layout_manager: new Clutter.BinLayout(),
            x: 54,
            y: 326,
            width: 110,
            height: 174,
        });
        const buttons = new St.BoxLayout({
            vertical: true,
            x_expand: true,
            x_align: Clutter.ActorAlign.FILL,
            y_align: Clutter.ActorAlign.CENTER,
            style_class: 'agents-tray-limits-pipboy-buttons',
        });
        buttons.add_child(this._createPipboyButton(
            'REFRESH',
            this._i18n.t('a11y.refresh'),
            () => this._refresh(),
            !this._refreshing
        ));
        buttons.add_child(this._createPipboyButton(
            'CODEX',
            this._i18n.t('a11y.openCodex'),
            () => {
                this._indicator.menu.close();
                this._openUrl(CHATGPT_CODEX_URL);
            }
        ));
        buttons.add_child(this._createPipboyButton(
            'SETTINGS',
            this._i18n.t('a11y.settings'),
            () => {
                this._indicator.menu.close();
                this.openPreferences();
            }
        ));
        buttons.add_child(this._createPipboyButton(
            'CLOSE',
            this._i18n.t('a11y.close'),
            () => this._indicator.menu.close()
        ));
        actionBay.add_child(buttons);
        device.add_child(actionBay);

        const screenTitle = new St.Label({
            text: this._i18n.t(mode === 'normal'
                ? 'pipboy.terminalOnline'
                : 'pipboy.terminalDiagnostics'),
            x: 246,
            y: 36,
            width: 402,
            height: 16,
            x_align: Clutter.ActorAlign.CENTER,
            style_class: 'agents-tray-limits-pipboy-screen-title',
        });
        screenTitle.clutter_text.ellipsize = Pango.EllipsizeMode.NONE;
        screenTitle.clutter_text.line_wrap = false;
        screenTitle.clutter_text.single_line_mode = true;
        device.add_child(screenTitle);
        const scroll = new St.ScrollView({
            x: 246,
            y: 52,
            width: 402,
            height: 426,
            clip_to_allocation: true,
            hscrollbar_policy: St.PolicyType.NEVER,
            vscrollbar_policy: St.PolicyType.AUTOMATIC,
            overlay_scrollbars: false,
            enable_mouse_scrolling: true,
            style_class: 'agents-tray-limits-pipboy-screen',
        });
        scroll.update_fade_effect?.(new Clutter.Margin({
            top: 0,
            right: 0,
            bottom: 0,
            left: 0,
        }));
        const content = new St.BoxLayout({
            vertical: true,
            x_expand: true,
            x_align: Clutter.ActorAlign.FILL,
            style_class: 'agents-tray-limits-pipboy-screen-content',
        });
        scroll.set_child(content);
        scroll.get_vadjustment().connect('notify::value', () => {
            content.queue_redraw();
            scroll.queue_redraw();
            device.queue_redraw();
        });
        device.add_child(scroll);

        item.add_child(device);
        this._indicator.menu.addMenuItem(item);
        this._contentTarget = content;
    }

    _createPipboyButton(label, accessibleName, callback, sensitive = true) {
        const button = new St.Button({
            reactive: sensitive,
            can_focus: sensitive,
            track_hover: sensitive,
            x_expand: true,
            accessible_name: accessibleName,
            style_class: 'agents-tray-limits-pipboy-button',
        });
        const content = new St.BoxLayout({
            x_expand: true,
            y_align: Clutter.ActorAlign.CENTER,
            style_class: 'agents-tray-limits-pipboy-button-content',
        });
        content.add_child(new St.Widget({
            y_align: Clutter.ActorAlign.CENTER,
            style_class: 'agents-tray-limits-pipboy-button-lens',
        }));
        const buttonLabel = new St.Label({
            text: label,
            x_expand: true,
            y_align: Clutter.ActorAlign.CENTER,
            style_class: 'agents-tray-limits-pipboy-button-label',
        });
        buttonLabel.clutter_text.ellipsize = Pango.EllipsizeMode.NONE;
        buttonLabel.clutter_text.line_wrap = false;
        buttonLabel.clutter_text.single_line_mode = true;
        content.add_child(buttonLabel);
        button.set_child(content);
        if (!sensitive)
            button.add_style_pseudo_class('insensitive');
        if (sensitive) {
            button.connect('enter-event', () => {
                this._setPointerCursor(true);
                this._showPipboyTooltip(button, accessibleName);
                return Clutter.EVENT_PROPAGATE;
            });
            button.connect('leave-event', () => {
                this._setPointerCursor(false);
                this._hidePipboyTooltip(button);
                return Clutter.EVENT_PROPAGATE;
            });
        }
        button.connect('destroy', () => this._hidePipboyTooltip(button));
        button.connect('clicked', callback);
        button.connect_after('button-press-event', () => Clutter.EVENT_STOP);
        button.connect_after('button-release-event', () => Clutter.EVENT_STOP);
        return button;
    }

    _addPipboyState(status, remaining) {
        const row = new St.BoxLayout({
            x_expand: true,
            style_class: 'agents-tray-limits-pipboy-state-row',
        });
        row.add_child(new St.Label({
            text: this._i18n.t(STATUS_DETAILS[status].key),
            x_expand: true,
            style_class: 'agents-tray-limits-theme-state',
        }));
        row.add_child(new St.Label({
            text: this._i18n.t('status.remainingUpper', {value: remaining}),
            style_class: 'agents-tray-limits-theme-remaining',
        }));
        this._addStaticActor(row);
    }

    _endPipboyLayout() {
        this._contentTarget = null;
    }

    _addThemeStatusCard(status, remaining) {
        const artPath = this._theme?.artPaths?.[status];
        if (!artPath)
            return;

        const box = new St.BoxLayout({
            x_expand: true,
            y_align: Clutter.ActorAlign.CENTER,
            style_class: 'agents-tray-limits-theme-card',
        });
        this._menuArt = new St.Icon({
            gicon: new Gio.FileIcon({file: Gio.File.new_for_path(artPath)}),
            icon_size: 112,
            width: 112,
            height: 112,
            y_align: Clutter.ActorAlign.CENTER,
            style_class: 'agents-tray-limits-theme-art',
        });
        box.add_child(this._menuArt);

        const labels = new St.BoxLayout({
            vertical: true,
            x_expand: true,
            y_align: Clutter.ActorAlign.CENTER,
            style_class: 'agents-tray-limits-theme-card-labels',
        });
        labels.add_child(new St.Label({
            text: this._i18n.t(STATUS_DETAILS[status].key),
            style_class: 'agents-tray-limits-theme-state',
        }));
        labels.add_child(new St.Label({
            text: this._i18n.t('status.remaining', {value: remaining}),
            style_class: 'agents-tray-limits-theme-remaining',
        }));
        box.add_child(labels);
        this._addStaticActor(box);
    }

    _getBuckets() {
        const ratePayload = this._data?.rateLimits ?? {};
        const byId = ratePayload.rateLimitsByLimitId;
        const showAll = this._settings.get_boolean('show-all-buckets');
        let buckets = [];

        if (showAll && byId && typeof byId === 'object')
            buckets = Object.values(byId).filter(value => value && typeof value === 'object');
        if (buckets.length === 0 && ratePayload.rateLimits)
            buckets = [ratePayload.rateLimits];
        if (buckets.length === 0 && byId && typeof byId === 'object')
            buckets = Object.values(byId).slice(0, 1);

        buckets.sort((left, right) => {
            if (left.limitId === 'codex')
                return -1;
            if (right.limitId === 'codex')
                return 1;
            return humanizeBucket(left).localeCompare(
                humanizeBucket(right),
                this._i18n.locale
            );
        });
        return buckets;
    }

    _addBucket(bucket) {
        const windows = [
            [this._i18n.t('menu.primary'), bucket.primary],
            [this._i18n.t('menu.secondary'), bucket.secondary],
        ].filter(([, window]) => window && typeof window === 'object');

        if (windows.length === 0) {
            this._addMessage(this._i18n.t('menu.noWindow'));
            return;
        }

        for (const [kind, window] of windows)
            this._addLimitWindow(kind, window, bucket.rateLimitReachedType);
    }

    _addLimitWindow(kind, window, reachedType) {
        const used = clampPercent(window.usedPercent);
        const remaining = Math.max(0, 100 - used);
        const display = this._settings.get_string('panel-display');
        const value = display === 'used'
            ? this._i18n.t('menu.used', {value: Math.round(used)})
            : this._i18n.t('menu.remaining', {value: Math.round(remaining)});
        const duration = formatWindow(window.windowDurationMins, false, this._i18n);
        const title = this._i18n.t('menu.windowTitle', {kind, duration});

        const box = new St.BoxLayout({
            vertical: true,
            x_expand: true,
            style_class: 'agents-tray-limits-limit',
        });
        const top = new St.BoxLayout({
            x_expand: true,
            style_class: 'agents-tray-limits-limit-top',
        });
        const titleLabel = new St.Label({
            text: title,
            x_expand: true,
            y_align: Clutter.ActorAlign.CENTER,
            style_class: 'agents-tray-limits-limit-title',
        });
        const valueLabel = new St.Label({
            text: value,
            y_align: Clutter.ActorAlign.CENTER,
            style_class: 'agents-tray-limits-limit-value',
        });
        this._preparePipboyLabel(titleLabel);
        this._preparePipboyLabel(valueLabel, false);
        top.add_child(titleLabel);
        top.add_child(valueLabel);
        box.add_child(top);

        const track = new St.BoxLayout({
            width: PANEL_PROGRESS_WIDTH,
            height: 6,
            style_class: 'agents-tray-limits-progress-track',
        });
        const severity = used >= 90 ? 'critical' : used >= 70 ? 'warning' : '';
        const fillWidth = used > 0
            ? Math.max(2, Math.round(PANEL_PROGRESS_WIDTH * used / 100))
            : 0;
        const fill = new St.Widget({
            width: fillWidth,
            height: 6,
            style_class: `agents-tray-limits-progress-fill${severity ? ` ${severity}` : ''}`,
        });
        track.add_child(fill);
        box.add_child(track);

        const resetLabel = new St.Label({
            text: formatRelativeReset(window.resetsAt, this._i18n),
            x_expand: true,
            style_class: 'agents-tray-limits-muted',
        });
        this._preparePipboyLabel(resetLabel);
        box.add_child(resetLabel);

        if (reachedType) {
            const reachedLabel = new St.Label({
                text: this._i18n.t('menu.limitReached', {type: reachedType}),
                x_expand: true,
                style_class: 'agents-tray-limits-critical-text',
            });
            this._preparePipboyLabel(reachedLabel);
            box.add_child(reachedLabel);
        }

        this._addStaticActor(box);
    }

    _addResetCredits() {
        const credits = this._data?.rateLimits?.rateLimitResetCredits;
        const count = Number(credits?.availableCount);
        if (!Number.isFinite(count) || count <= 0)
            return;
        this._addMutedLine(this._i18n.t('menu.resetCredits', {
            count: formatInteger(count, this._i18n),
        }));
    }

    _addTokenUsage() {
        const usage = this._data?.usage;
        const summary = usage?.summary;
        const buckets = Array.isArray(usage?.dailyUsageBuckets)
            ? usage.dailyUsageBuckets
            : [];

        if (!summary && buckets.length === 0) {
            if (this._data?.usageError) {
                this._addSection(this._i18n.t('menu.activity'));
                this._addMutedLine(this._i18n.t('menu.tokenUnavailable'));
            }
            return;
        }

        this._addSection(this._i18n.t('menu.activity'));
        const rows = [];
        const today = this._tokensToday(buckets);
        const lastSevenDays = this._tokensLastDays(buckets, 7);
        if (today !== null)
            rows.push([
                this._i18n.t('menu.today'),
                this._i18n.tn('menu.tokens', today, {
                    count: formatCompactNumber(today, this._i18n),
                }),
            ]);
        if (lastSevenDays !== null)
            rows.push([
                this._i18n.t('menu.last7'),
                this._i18n.tn('menu.tokens', lastSevenDays, {
                    count: formatCompactNumber(lastSevenDays, this._i18n),
                }),
            ]);
        if (summary?.lifetimeTokens !== null && summary?.lifetimeTokens !== undefined)
            rows.push([
                this._i18n.t('menu.lifetime'),
                this._i18n.tn('menu.tokens', summary.lifetimeTokens, {
                    count: formatCompactNumber(summary.lifetimeTokens, this._i18n),
                }),
            ]);
        if (summary?.peakDailyTokens !== null && summary?.peakDailyTokens !== undefined)
            rows.push([
                this._i18n.t('menu.peak'),
                this._i18n.tn('menu.tokens', summary.peakDailyTokens, {
                    count: formatCompactNumber(summary.peakDailyTokens, this._i18n),
                }),
            ]);
        if (summary?.currentStreakDays !== null && summary?.currentStreakDays !== undefined)
            rows.push([
                this._i18n.t('menu.streak'),
                this._i18n.tn('menu.days', summary.currentStreakDays, {
                    count: formatInteger(summary.currentStreakDays, this._i18n),
                }),
            ]);

        if (rows.length > 0)
            this._addStatsRows(rows);
    }

    _tokensToday(buckets) {
        const now = GLib.DateTime.new_now_local();
        const today = now ? now.format('%F') : null;
        if (!today)
            return null;
        const row = buckets.find(bucket => bucket?.startDate === today);
        const value = Number(row?.tokens);
        return Number.isFinite(value) ? value : 0;
    }

    _tokensLastDays(buckets, days) {
        if (!Array.isArray(buckets) || buckets.length === 0)
            return null;
        const startOfToday = new Date();
        startOfToday.setHours(0, 0, 0, 0);
        const threshold = startOfToday.getTime() - (days - 1) * 86400 * 1000;
        let total = 0;
        let found = false;
        for (const bucket of buckets) {
            const timestamp = Date.parse(`${bucket?.startDate ?? ''}T00:00:00`);
            const tokens = Number(bucket?.tokens);
            if (Number.isFinite(timestamp) && timestamp >= threshold && Number.isFinite(tokens)) {
                total += tokens;
                found = true;
            }
        }
        return found ? total : 0;
    }

    _addStatsRows(rows) {
        const box = new St.BoxLayout({
            vertical: true,
            x_expand: true,
            style_class: 'agents-tray-limits-stats',
        });
        for (const [title, value] of rows) {
            const row = new St.BoxLayout({x_expand: true, style_class: 'agents-tray-limits-stat-row'});
            const titleLabel = new St.Label({
                text: title,
                x_expand: true,
                style_class: 'agents-tray-limits-muted',
            });
            const valueLabel = new St.Label({
                text: value,
                style_class: 'agents-tray-limits-stat-value',
            });
            this._preparePipboyLabel(titleLabel);
            this._preparePipboyLabel(valueLabel);
            row.add_child(titleLabel);
            row.add_child(valueLabel);
            box.add_child(row);
        }
        this._addStaticActor(box);
    }

    _preparePipboyLabel(label, wrap = true) {
        if (!this._usesPipboyLayout())
            return label;
        label.clutter_text.ellipsize = Pango.EllipsizeMode.NONE;
        label.clutter_text.line_wrap = wrap;
        label.clutter_text.single_line_mode = !wrap;
        if (wrap)
            label.clutter_text.line_wrap_mode = Pango.WrapMode.WORD_CHAR;
        return label;
    }

    _addHeader(title, subtitle, meta = null) {
        const box = new St.BoxLayout({
            vertical: true,
            x_expand: true,
            style_class: 'agents-tray-limits-header',
        });
        const titleLabel = new St.Label({
            text: title,
            x_expand: true,
            style_class: 'agents-tray-limits-header-title',
        });
        this._preparePipboyLabel(titleLabel);
        box.add_child(titleLabel);
        if (subtitle) {
            const subtitleLabel = new St.Label({
                text: subtitle,
                x_expand: true,
                style_class: 'agents-tray-limits-muted',
            });
            this._preparePipboyLabel(subtitleLabel);
            box.add_child(subtitleLabel);
        }
        if (meta) {
            const metaLabel = new St.Label({
                text: meta,
                x_expand: true,
                style_class: 'agents-tray-limits-muted',
            });
            this._preparePipboyLabel(metaLabel);
            box.add_child(metaLabel);
        }
        this._addStaticActor(box);
    }

    _addMessage(text, error = false) {
        const label = new St.Label({
            text,
            x_expand: true,
            style_class: error ? 'agents-tray-limits-error' : 'agents-tray-limits-message',
        });
        label.clutter_text.line_wrap = true;
        this._preparePipboyLabel(label);
        this._addStaticActor(label);
    }

    _addMutedLine(text) {
        const label = new St.Label({
            text,
            x_expand: true,
            style_class: 'agents-tray-limits-muted',
        });
        this._preparePipboyLabel(label);
        this._addStaticActor(label);
    }

    _addSection(title = '') {
        if (this._contentTarget) {
            const label = new St.Label({
                text: title.toUpperCase(),
                x_expand: true,
                style_class: 'agents-tray-limits-pipboy-section',
            });
            this._preparePipboyLabel(label);
            this._contentTarget.add_child(label);
            return;
        }
        this._indicator.menu.addMenuItem(new PopupMenu.PopupSeparatorMenuItem(title));
    }

    _addStaticActor(actor) {
        if (this._contentTarget) {
            actor.x_expand = true;
            this._contentTarget.add_child(actor);
            return actor;
        }
        const item = new PopupMenu.PopupMenuItem('', {
            reactive: false,
            can_focus: false,
            hover: false,
            style_class: 'agents-tray-limits-static-item',
        });
        item.label.hide();
        actor.x_expand = true;
        item.add_child(actor);
        this._indicator.menu.addMenuItem(item);
        return item;
    }

    _addCommonActions(includeOpenCodex) {
        const menu = this._indicator.menu;
        menu.addMenuItem(new PopupMenu.PopupSeparatorMenuItem());

        const refreshItem = new PopupMenu.PopupImageMenuItem(
            this._i18n.t(this._refreshing ? 'actions.refreshing' : 'actions.refresh'),
            'view-refresh-symbolic'
        );
        refreshItem.sensitive = !this._refreshing;
        refreshItem.connect('activate', () => this._refresh());
        menu.addMenuItem(refreshItem);

        if (includeOpenCodex) {
            const openItem = new PopupMenu.PopupImageMenuItem(
                this._i18n.t('actions.openCodex'),
                'web-browser-symbolic'
            );
            openItem.connect('activate', () => this._openUrl(CHATGPT_CODEX_URL));
            menu.addMenuItem(openItem);
        }

        const preferencesItem = new PopupMenu.PopupImageMenuItem(
            this._i18n.t('actions.settings'),
            'preferences-system-symbolic'
        );
        preferencesItem.connect('activate', () => this.openPreferences());
        menu.addMenuItem(preferencesItem);
    }

    _openUrl(url) {
        try {
            Gio.AppInfo.launch_default_for_uri(url, null);
        } catch (error) {
            Main.notifyError(
                this._i18n.t('app.name'),
                this._i18n.t('actions.openLinkFailed', {message: error.message})
            );
        }
    }

    _errorHint(code) {
        const key = `hints.${code ?? ''}`;
        const value = this._i18n.t(key);
        return value === key ? null : value;
    }

    _errorMessage(code, technicalMessage = null) {
        const key = `errors.${code ?? 'unknown_error'}`;
        const value = this._i18n.t(key);
        if (value !== key)
            return value;
        return String(technicalMessage ?? '').trim() || this._i18n.t('menu.unknownError');
    }
}
