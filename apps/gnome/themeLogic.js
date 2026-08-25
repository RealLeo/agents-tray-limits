export const CLASSIC_THEME_ID = 'classic';
export const LEGACY_THEME_IDS = {
    'pipboy-classic': 'fallout-3',
};
export const THEME_MANIFEST_VERSION = 2;
export const LEGACY_THEME_MANIFEST_VERSION = 1;
export const THEME_STATUS_KEYS = ['good', 'worried', 'critical', 'dead'];

export const STATUS_DETAILS = {
    good: {key: 'status.good'},
    worried: {key: 'status.worried'},
    critical: {key: 'status.critical'},
    dead: {key: 'status.dead'},
};

function interpolate(template, params = {}) {
    return template.replace(/\{([a-zA-Z0-9_]+)\}/g, (match, key) =>
        Object.hasOwn(params, key) ? String(params[key]) : match);
}

function translate(i18n, key, params, fallback) {
    return i18n?.t ? i18n.t(key, params) : interpolate(fallback, params);
}

function translateCount(i18n, key, count, fallback) {
    return i18n?.tn
        ? i18n.tn(key, count)
        : interpolate(fallback, {count});
}

export function clampPercent(value) {
    const number = Number(value);
    if (!Number.isFinite(number))
        return null;
    return Math.max(0, Math.min(100, number));
}

export function displayPercent(value) {
    const percent = clampPercent(value);
    return percent === null ? null : Math.round(percent);
}

export function statusForRemaining(value) {
    // Status art must describe the same whole percentage that the user sees.
    // Without rounding here, a remaining value such as 0.4 was rendered as
    // "0%" while still selecting the critical art instead of dead.
    const remaining = displayPercent(value);
    if (remaining === null)
        return null;
    if (remaining === 0)
        return 'dead';
    if (remaining <= 20)
        return 'critical';
    if (remaining <= 50)
        return 'worried';
    return 'good';
}

export function mainAgentBucket(payload) {
    const ratePayload = payload?.rateLimits;
    if (!ratePayload || typeof ratePayload !== 'object')
        return null;

    const direct = ratePayload.rateLimits;
    if (direct && typeof direct === 'object')
        return direct;

    const byId = ratePayload.rateLimitsByLimitId;
    if (!byId || typeof byId !== 'object')
        return null;
    for (const id of ['codex', 'claude']) {
        if (byId[id] && typeof byId[id] === 'object')
            return byId[id];
    }
    return null;
}

export function mainCodexBucket(payload) {
    return mainAgentBucket(payload);
}

export function mainCodexRemaining(payload) {
    const bucket = mainCodexBucket(payload);
    if (!bucket)
        return null;

    const remaining = [bucket.primary, bucket.secondary]
        .filter(window => window && typeof window === 'object')
        .map(window => clampPercent(window.usedPercent))
        .filter(value => value !== null)
        .map(used => 100 - used);

    return remaining.length > 0 ? Math.min(...remaining) : null;
}

export function primaryCodexWindow(payload) {
    const primary = mainAgentBucket(payload)?.primary;
    return primary && typeof primary === 'object' ? primary : null;
}

export function primaryCodexRemaining(payload) {
    const used = clampPercent(primaryCodexWindow(payload)?.usedPercent);
    return used === null ? null : 100 - used;
}

export function formatPanelDuration(minutes, i18n = null) {
    const value = Math.max(0, Math.round(Number(minutes) || 0));
    if (value === 0)
        return translate(i18n, 'time.limitShort', {}, 'limit');
    if (value % 1440 === 0)
        return translateCount(i18n, 'time.dayShort', value / 1440, '{count}d');
    if (value % 60 === 0)
        return translateCount(i18n, 'time.hourShort', value / 60, '{count}h');
    return translateCount(i18n, 'time.minuteShort', value, '{count}m');
}

export function formatPanelReset(timestamp, nowSeconds = Date.now() / 1000, i18n = null) {
    const target = Number(timestamp);
    const now = Number(nowSeconds);
    if (!Number.isFinite(target) || target <= 0 || !Number.isFinite(now))
        return translate(i18n, 'panel.resetUnknown', {}, '—');
    if (target <= now)
        return translate(i18n, 'panel.resetNow', {}, 'now');

    const totalMinutes = Math.max(1, Math.ceil((target - now) / 60));
    const days = Math.floor(totalMinutes / 1440);
    const afterDays = totalMinutes % 1440;
    const hours = Math.floor(afterDays / 60);
    const minutes = afterDays % 60;

    const dayText = translateCount(i18n, 'time.dayShort', days, '{count}d');
    const hourText = translateCount(i18n, 'time.hourShort', hours, '{count}h');
    const minuteText = translateCount(i18n, 'time.minuteShort', minutes, '{count}m');
    if (days > 0)
        return hours > 0 ? `${dayText} ${hourText}` : dayText;
    if (hours > 0)
        return minutes > 0 ? `${hourText} ${minuteText}` : hourText;
    return minuteText;
}

export function formatPanelValue(
    payload,
    display = 'remaining',
    nowSeconds = Date.now() / 1000,
    i18n = null
) {
    const primary = primaryCodexWindow(payload);
    const used = clampPercent(primary?.usedPercent);
    if (!primary || used === null)
        return null;
    const roundedRemaining = displayPercent(100 - used);
    const roundedValue = display === 'used'
        ? 100 - roundedRemaining
        : roundedRemaining;
    return translate(i18n, 'panel.value', {
        value: i18n?.formatNumber
            ? i18n.formatNumber(roundedValue, {maximumFractionDigits: 0})
            : roundedValue,
        reset: formatPanelReset(primary.resetsAt, nowSeconds, i18n),
    }, '{value}% · reset {reset}');
}

export function migrateThemeId(themeId) {
    return LEGACY_THEME_IDS[themeId] ?? themeId;
}

export function isSafeRelativePath(value) {
    if (typeof value !== 'string' || !value || value.includes('\\'))
        return false;
    if (value.startsWith('/') || value.startsWith('~'))
        return false;
    const parts = value.split('/');
    return parts.every(part => part && part !== '.' && part !== '..');
}

function validateAnimation(animation) {
    if (animation === undefined)
        return {ok: true, animation: null};
    if (!animation || typeof animation !== 'object')
        return {ok: false, error: 'animation must be an object'};

    const intervalMs = Number(animation.intervalMs);
    if (!Number.isInteger(intervalMs) || intervalMs < 50 || intervalMs > 5000)
        return {ok: false, error: 'animation.intervalMs must be 50..5000'};
    if (!Array.isArray(animation.steps) || animation.steps.length < 1 ||
        animation.steps.length > 10)
        return {ok: false, error: 'animation.steps must contain 1..10 steps'};

    const steps = [];
    for (const raw of animation.steps) {
        if (!raw || typeof raw !== 'object')
            return {ok: false, error: 'animation step must be an object'};
        const x = Number(raw.x ?? 0);
        const y = Number(raw.y ?? 0);
        const opacity = Number(raw.opacity ?? 255);
        const scale = Number(raw.scale ?? 1);
        if (![x, y, opacity, scale].every(Number.isFinite) ||
            Math.abs(x) > 12 || Math.abs(y) > 12 ||
            opacity < 0 || opacity > 255 || scale < 0.8 || scale > 1.2)
            return {ok: false, error: 'animation step is outside safe bounds'};
        steps.push({x, y, opacity, scale});
    }
    return {ok: true, animation: {intervalMs, steps}};
}

function validateFrameAnimation(frameAnimation) {
    if (frameAnimation === undefined)
        return {ok: true, frameAnimation: null};
    if (!frameAnimation || typeof frameAnimation !== 'object')
        return {ok: false, error: 'frameAnimation must be an object'};

    const intervalMs = Number(frameAnimation.intervalMs);
    if (!Number.isInteger(intervalMs) || intervalMs < 20 || intervalMs > 5000)
        return {ok: false, error: 'frameAnimation.intervalMs must be 20..5000'};
    const intervalMsByStatus = {};
    if (frameAnimation.intervalMsByStatus !== undefined) {
        const overrides = frameAnimation.intervalMsByStatus;
        if (!overrides || typeof overrides !== 'object' || Array.isArray(overrides))
            return {ok: false, error: 'frameAnimation.intervalMsByStatus must be an object'};
        for (const status of Object.keys(overrides)) {
            if (!THEME_STATUS_KEYS.includes(status))
                return {ok: false, error: `unknown frameAnimation interval status: ${status}`};
            const value = Number(overrides[status]);
            if (!Number.isInteger(value) || value < 20 || value > 5000)
                return {ok: false, error: `frameAnimation.intervalMsByStatus.${status} must be 20..5000`};
            intervalMsByStatus[status] = value;
        }
    }
    if (frameAnimation.playback !== 'once')
        return {ok: false, error: 'frameAnimation.playback must be once'};
    if (!frameAnimation.frames || typeof frameAnimation.frames !== 'object')
        return {ok: false, error: 'frameAnimation.frames must contain four states'};

    const frames = {};
    for (const status of THEME_STATUS_KEYS) {
        const paths = frameAnimation.frames[status];
        if (!Array.isArray(paths) || paths.length < 1 || paths.length > 32)
            return {ok: false, error: `frameAnimation.frames.${status} must contain 1..32 frames`};
        if (!paths.every(isSafeRelativePath))
            return {ok: false, error: `invalid frameAnimation.frames.${status} path`};
        frames[status] = [...paths];
    }
    return {
        ok: true,
        frameAnimation: {intervalMs, intervalMsByStatus, playback: 'once', frames},
    };
}

export function frameAnimationInterval(frameAnimation, status) {
    return frameAnimation?.intervalMsByStatus?.[status] ??
        frameAnimation?.intervalMs ?? null;
}

export function validateThemeManifest(manifest, directoryName = null) {
    if (!manifest || typeof manifest !== 'object' || Array.isArray(manifest))
        return {ok: false, error: 'theme manifest must be an object'};
    const version = Number(manifest.version);
    if (![LEGACY_THEME_MANIFEST_VERSION, THEME_MANIFEST_VERSION].includes(version))
        return {ok: false, error: 'theme manifest version must be 1 or 2'};

    const id = String(manifest.id ?? '');
    if (!/^[a-z0-9_-]+$/.test(id))
        return {ok: false, error: 'invalid theme id'};
    if (id === CLASSIC_THEME_ID)
        return {ok: false, error: 'classic is reserved'};
    if (directoryName !== null && id !== directoryName)
        return {ok: false, error: 'theme id must match its directory name'};
    if (typeof manifest.name !== 'string' || !manifest.name.trim())
        return {ok: false, error: 'theme name is required'};
    if (manifest.description !== undefined && typeof manifest.description !== 'string')
        return {ok: false, error: 'theme description must be a string'};
    let stylesheet = manifest.stylesheet ?? null;
    let layout = manifest.layout ?? null;
    let platforms = null;
    if (version === THEME_MANIFEST_VERSION) {
        if (!manifest.platforms || typeof manifest.platforms !== 'object' ||
            Array.isArray(manifest.platforms) || Object.keys(manifest.platforms).length === 0)
            return {ok: false, error: 'theme platforms are required'};
        const unknownPlatforms = Object.keys(manifest.platforms)
            .filter(key => !['gnome', 'macos'].includes(key));
        if (unknownPlatforms.length > 0)
            return {ok: false, error: `unknown theme platform: ${unknownPlatforms[0]}`};

        const gnome = manifest.platforms.gnome;
        if (gnome !== undefined && (!gnome || typeof gnome !== 'object' || Array.isArray(gnome)))
            return {ok: false, error: 'platforms.gnome must be an object'};
        stylesheet = gnome?.stylesheet ?? null;
        layout = gnome?.layout ?? null;
        if (stylesheet !== null && !isSafeRelativePath(stylesheet))
            return {ok: false, error: 'invalid platforms.gnome.stylesheet path'};

        const macos = manifest.platforms.macos;
        if (macos !== undefined) {
            if (!macos || typeof macos !== 'object' || Array.isArray(macos))
                return {ok: false, error: 'platforms.macos must be an object'};
            if (!['classic', 'pipboy-2000', 'pipboy-3000'].includes(macos.layout))
                return {ok: false, error: 'unsupported macOS theme layout'};
            const palette = macos.palette ?? {};
            const paletteKeys = [
                'background', 'surface', 'primary', 'secondary',
                'text', 'muted', 'warning', 'critical',
            ];
            if (!palette || typeof palette !== 'object' || Array.isArray(palette))
                return {ok: false, error: 'platforms.macos.palette must be an object'};
            for (const [key, value] of Object.entries(palette)) {
                if (!paletteKeys.includes(key) ||
                    typeof value !== 'string' || !/^#[0-9A-Fa-f]{6}([0-9A-Fa-f]{2})?$/.test(value))
                    return {ok: false, error: `invalid platforms.macos.palette.${key}`};
            }
            const typography = macos.typography ?? {};
            if (!typography || typeof typography !== 'object' || Array.isArray(typography))
                return {ok: false, error: 'platforms.macos.typography must be an object'};
            if (typography.family !== undefined &&
                !['system', 'monospaced'].includes(typography.family))
                return {ok: false, error: 'unsupported macOS theme font family'};
            const scale = Number(typography.scale ?? 1);
            if (!Number.isFinite(scale) || scale < 0.75 || scale > 1.5)
                return {ok: false, error: 'macOS theme font scale must be 0.75..1.5'};
        }
        platforms = {
            gnome: gnome ? {stylesheet, layout} : null,
            macos: macos ? {
                layout: macos.layout,
                palette: {...(macos.palette ?? {})},
                typography: {
                    family: macos.typography?.family ?? 'system',
                    scale: Number(macos.typography?.scale ?? 1),
                },
            } : null,
        };
    } else if (stylesheet !== null && !isSafeRelativePath(stylesheet)) {
        return {ok: false, error: 'invalid stylesheet path'};
    }

    if (!manifest.art || typeof manifest.art !== 'object')
        return {ok: false, error: 'four art paths are required'};
    const art = {};
    for (const status of THEME_STATUS_KEYS) {
        if (!isSafeRelativePath(manifest.art[status]))
            return {ok: false, error: `invalid art.${status} path`};
        art[status] = manifest.art[status];
    }

    let panelArt = null;
    if (manifest.panelArt !== undefined) {
        if (!manifest.panelArt || typeof manifest.panelArt !== 'object')
            return {ok: false, error: 'panelArt must contain four paths'};
        panelArt = {};
        for (const status of THEME_STATUS_KEYS) {
            if (!isSafeRelativePath(manifest.panelArt[status]))
                return {ok: false, error: `invalid panelArt.${status} path`};
            panelArt[status] = manifest.panelArt[status];
        }
    }

    const animationResult = validateAnimation(manifest.animation);
    if (!animationResult.ok)
        return animationResult;
    const frameAnimationResult = validateFrameAnimation(manifest.frameAnimation);
    if (!frameAnimationResult.ok)
        return frameAnimationResult;
    if (animationResult.animation && frameAnimationResult.frameAnimation)
        return {ok: false, error: 'animation and frameAnimation are mutually exclusive'};

    if (layout !== null && !['pipboy-2000', 'video-deck'].includes(layout))
        return {ok: false, error: 'unsupported theme layout'};

    return {
        ok: true,
        manifest: {
            version,
            id,
            name: manifest.name.trim(),
            description: String(manifest.description ?? '').trim(),
            stylesheet,
            art,
            panelArt,
            layout,
            animation: animationResult.animation,
            frameAnimation: frameAnimationResult.frameAnimation,
            platforms,
        },
    };
}

export function mergeThemeLists(bundled, user) {
    const themes = new Map();
    for (const theme of bundled)
        themes.set(theme.id, theme);
    for (const theme of user) {
        if (theme.id !== CLASSIC_THEME_ID)
            themes.set(theme.id, theme);
    }
    return themes;
}

export class StylesheetLifecycle {
    constructor(load, unload) {
        this._load = load;
        this._unload = unload;
        this._path = null;
    }

    apply(path) {
        this.clear();
        if (!path)
            return true;
        try {
            this._load(path);
            this._path = path;
            return true;
        } catch (error) {
            console.warn(`[Agents Tray Limits] Theme stylesheet failed: ${error.message}`);
            return false;
        }
    }

    clear() {
        if (!this._path)
            return;
        try {
            this._unload(this._path);
        } catch (error) {
            console.warn(`[Agents Tray Limits] Theme stylesheet unload failed: ${error.message}`);
        }
        this._path = null;
    }

    get path() {
        return this._path;
    }
}

export class AnimationLoop {
    constructor(schedule, cancel, applyStep) {
        this._schedule = schedule;
        this._cancel = cancel;
        this._applyStep = applyStep;
        this._sourceId = 0;
        this._steps = [];
        this._index = 0;
    }

    start(intervalMs, steps) {
        this.stop();
        if (!Array.isArray(steps) || steps.length === 0)
            return;
        this._steps = steps;
        this._index = 0;
        this._applyStep(this._steps[0]);
        this._sourceId = this._schedule(intervalMs, () => {
            this._index = (this._index + 1) % this._steps.length;
            this._applyStep(this._steps[this._index]);
            return true;
        });
    }

    stop() {
        if (this._sourceId)
            this._cancel(this._sourceId);
        this._sourceId = 0;
        this._steps = [];
        this._index = 0;
    }

    get running() {
        return this._sourceId !== 0;
    }
}

export class RepeatingTimer {
    constructor(schedule, cancel, tick) {
        this._schedule = schedule;
        this._cancel = cancel;
        this._tick = tick;
        this._sourceId = 0;
    }

    start(intervalSeconds) {
        this.stop();
        this._sourceId = this._schedule(intervalSeconds, () => {
            this._tick();
            return true;
        });
    }

    stop() {
        if (this._sourceId)
            this._cancel(this._sourceId);
        this._sourceId = 0;
    }

    get running() {
        return this._sourceId !== 0;
    }
}

export class FrameAnimationLoop {
    constructor(schedule, cancel, applyFrame) {
        this._schedule = schedule;
        this._cancel = cancel;
        this._applyFrame = applyFrame;
        this._sourceId = 0;
        this._frames = [];
        this._index = 0;
    }

    start(intervalMs, frames) {
        this.stop();
        if (!Array.isArray(frames) || frames.length === 0)
            return;
        this._frames = frames;
        this._index = 0;
        this._applyFrame(0, this._frames[0]);
        if (this._frames.length === 1)
            return;
        this._sourceId = this._schedule(intervalMs, () => {
            this._index++;
            this._applyFrame(this._index, this._frames[this._index]);
            if (this._index >= this._frames.length - 1) {
                this._sourceId = 0;
                return false;
            }
            return true;
        });
    }

    stop() {
        if (this._sourceId)
            this._cancel(this._sourceId);
        this._sourceId = 0;
        this._frames = [];
        this._index = 0;
    }

    get running() {
        return this._sourceId !== 0;
    }
}

export class FrameAnimationSession {
    constructor() {
        this._playedStatus = null;
    }

    shouldPlay(status) {
        return Boolean(status) && this._playedStatus !== status;
    }

    markPlayed(status) {
        this._playedStatus = status;
    }

    reset() {
        this._playedStatus = null;
    }
}
