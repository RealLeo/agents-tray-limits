import Gio from 'gi://Gio';
import GLib from 'gi://GLib';

import {createTranslator} from '../i18n.js';

import {
    AnimationLoop,
    FrameAnimationLoop,
    FrameAnimationSession,
    RepeatingTimer,
    StylesheetLifecycle,
    frameAnimationInterval,
    formatPanelDuration,
    formatPanelReset,
    formatPanelValue,
    migrateThemeId,
    mergeThemeLists,
    primaryCodexRemaining,
    statusForRemaining,
    validateThemeManifest,
} from '../themeLogic.js';
import {
    loadThemeCatalog,
    resolveTheme,
} from '../themeLoader.js';

function assertEqual(actual, expected, message) {
    if (actual !== expected)
        throw new Error(`${message}: expected ${expected}, got ${actual}`);
}

function assert(value, message) {
    if (!value)
        throw new Error(message);
}

const boundaries = new Map([
    [0, 'dead'],
    [0.49, 'dead'],
    [0.5, 'critical'],
    [1, 'critical'],
    [20, 'critical'],
    [20.49, 'critical'],
    [20.5, 'worried'],
    [21, 'worried'],
    [50, 'worried'],
    [50.49, 'worried'],
    [50.5, 'good'],
    [51, 'good'],
    [100, 'good'],
]);
for (const [remaining, expected] of boundaries)
    assertEqual(statusForRemaining(remaining), expected, `status boundary ${remaining}`);

const PANEL_NOW = 2_000_000_000;
const ROOT = GLib.get_current_dir();
const en = createTranslator(ROOT, 'en');
const ru = createTranslator(ROOT, 'ru');
const de = createTranslator(ROOT, 'de');
const fr = createTranslator(ROOT, 'fr');
const zh = createTranslator(ROOT, 'zh-CN');
const ratePayload = {
    rateLimits: {
        rateLimits: {
            limitId: 'codex',
            primary: {
                usedPercent: 34,
                windowDurationMins: 10080,
                resetsAt: PANEL_NOW + 4 * 86400 + 22 * 3600,
            },
            secondary: {usedPercent: 100, windowDurationMins: 300},
        },
        rateLimitsByLimitId: {
            codex: {limitId: 'codex', primary: {usedPercent: 34}},
            spark: {limitId: 'spark', primary: {usedPercent: 100}},
        },
    },
};
assertEqual(primaryCodexRemaining(ratePayload), 66, 'primary Codex remaining');
const localizedPanelLabels = [
    [en, '66% · reset 4d 22h'],
    [ru, '66% · сброс 4д 22ч'],
    [de, '66% · Reset 4T 22Std.'],
    [fr, '66 % · réinit. 4j 22h'],
    [zh, '66% · 4天 22小时重置'],
];
for (const [i18n, expected] of localizedPanelLabels) {
    assertEqual(formatPanelValue(ratePayload, 'remaining', PANEL_NOW, i18n),
        expected, `${i18n.language} remaining panel label`);
}
assertEqual(formatPanelValue(ratePayload, 'used', PANEL_NOW, en),
    '34% · reset 4d 22h', 'used panel label');
assertEqual(primaryCodexRemaining({
    rateLimits: {
        rateLimitsByLimitId: {
            codex: {
                limitId: 'codex',
                primary: {usedPercent: 30},
                secondary: {usedPercent: 20},
            },
            spark: {limitId: 'spark', primary: {usedPercent: 99}},
        },
    },
}), 70, 'primary ignores Codex secondary and Spark');
assertEqual(primaryCodexRemaining({rateLimits: {rateLimitsByLimitId: {
    spark: {primary: {usedPercent: 100}},
}}}), null, 'Spark alone does not create a status');
assertEqual(primaryCodexRemaining({rateLimits: {rateLimitsByLimitId: {
    claude: {
        limitId: 'claude',
        primary: {usedPercent: 25, windowDurationMins: 300},
        secondary: {usedPercent: 60, windowDurationMins: 10080},
    },
}}}), 75, 'Claude primary window drives the shared status model');
assertEqual(formatPanelValue({rateLimits: {rateLimits: {
    limitId: 'codex',
    primary: {usedPercent: 20, resetsAt: PANEL_NOW + 5 * 3600 + 30 * 60},
}}}, 'remaining', PANEL_NOW, en), '80% · reset 5h 30m', 'hour panel reset');
assertEqual(formatPanelValue({rateLimits: {rateLimits: {
    limitId: 'codex',
    primary: {usedPercent: 20, resetsAt: PANEL_NOW + 30 * 60},
}}}, 'remaining', PANEL_NOW, en), '80% · reset 30m', 'minute panel reset');
assertEqual(formatPanelValue({rateLimits: {rateLimits: {
    limitId: 'codex',
    primary: {usedPercent: 20, resetsAt: PANEL_NOW + 20},
}}}, 'remaining', PANEL_NOW, en), '80% · reset 1m', 'sub-minute panel reset');
assertEqual(formatPanelValue({rateLimits: {rateLimits: {
    limitId: 'codex',
    primary: {usedPercent: 20, resetsAt: PANEL_NOW},
}}}, 'remaining', PANEL_NOW, en), '80% · reset now', 'expired panel reset');
assertEqual(formatPanelValue({rateLimits: {rateLimits: {
    limitId: 'codex',
    primary: {usedPercent: 20},
}}}, 'remaining', PANEL_NOW, en), '80% · reset —', 'unknown panel reset');
const roundedDepletedPayload = {rateLimits: {rateLimits: {
    limitId: 'codex',
    primary: {usedPercent: 99.51},
}}};
assert(Math.abs(primaryCodexRemaining(roundedDepletedPayload) - 0.49) < 1e-9,
    'fractional primary remaining is preserved before display rounding');
assertEqual(statusForRemaining(primaryCodexRemaining(roundedDepletedPayload)), 'dead',
    'displayed zero remaining must select dead art');
assertEqual(formatPanelValue(roundedDepletedPayload, 'remaining', PANEL_NOW, en),
    '0% · reset —', 'remaining display rounds depleted value to zero');
assertEqual(formatPanelValue(roundedDepletedPayload, 'used', PANEL_NOW, en),
    '100% · reset —', 'used display and remaining emotion share rounding');
const halfPercentPayload = {rateLimits: {rateLimits: {
    limitId: 'codex',
    primary: {usedPercent: 99.5},
}}};
assertEqual(statusForRemaining(primaryCodexRemaining(halfPercentPayload)), 'critical',
    'half a percent remaining rounds to one percent');
assertEqual(formatPanelValue(halfPercentPayload, 'used', PANEL_NOW, en),
    '99% · reset —', 'used display is the complement of rounded remaining');
assertEqual(formatPanelReset(PANEL_NOW + 2 * 86400, PANEL_NOW, en), '2d',
    'whole day panel reset');
assertEqual(formatPanelReset(PANEL_NOW + 5 * 3600, PANEL_NOW, en), '5h',
    'whole hour panel reset');
assertEqual(formatPanelDuration(10080, en), '7d', 'day duration');
assertEqual(formatPanelDuration(300, en), '5h', 'hour duration');
assertEqual(formatPanelDuration(30, en), '30m', 'minute duration');
assertEqual(formatPanelValue({rateLimits: {rateLimits: {limitId: 'codex'}}}), null,
    'missing primary must keep diagnostic panel state');
assertEqual(migrateThemeId('pipboy-classic'), 'fallout-3', 'legacy theme migration');
assertEqual(migrateThemeId('fallout-2'), 'fallout-2', 'current theme must not migrate');
assertEqual(migrateThemeId('classic'), 'classic', 'Classic must not migrate');

const validManifest = {
    version: 1,
    id: 'test_theme',
    name: 'Test Theme',
    stylesheet: 'theme.css',
    art: {
        good: 'assets/good.png',
        worried: 'assets/worried.png',
        critical: 'assets/critical.png',
        dead: 'assets/dead.png',
    },
    animation: {
        intervalMs: 140,
        steps: [{x: 0, y: 0, opacity: 255, scale: 1}],
    },
};
assert(validateThemeManifest(validManifest, 'test_theme').ok, 'valid manifest rejected');
assert(!validateThemeManifest({...validManifest, id: 'classic'}, 'classic').ok,
    'reserved Classic theme accepted');
assert(!validateThemeManifest({...validManifest, id: 'Bad ID'}).ok, 'invalid id accepted');
assert(!validateThemeManifest({
    ...validManifest,
    art: {...validManifest.art, dead: undefined},
}).ok, 'missing art accepted');
assert(!validateThemeManifest({
    ...validManifest,
    stylesheet: '../outside.css',
}).ok, 'stylesheet traversal accepted');
assert(!validateThemeManifest({
    ...validManifest,
    art: {...validManifest.art, good: 'assets/../../outside.png'},
}).ok, 'art traversal accepted');
const panelArt = {
    good: 'panel/good.png',
    worried: 'panel/worried.png',
    critical: 'panel/critical.png',
    dead: 'panel/dead.png',
};
assert(validateThemeManifest({...validManifest, panelArt}, 'test_theme').ok,
    'complete panelArt rejected');
assert(!validateThemeManifest({
    ...validManifest,
    panelArt: {...panelArt, dead: undefined},
}).ok, 'incomplete panelArt accepted');
assert(!validateThemeManifest({
    ...validManifest,
    panelArt: {...panelArt, good: '../outside.png'},
}).ok, 'panelArt traversal accepted');
assert(!validateThemeManifest({
    ...validManifest,
    panelArt: {...panelArt, good: '/outside.png'},
}).ok, 'absolute panelArt accepted');
assert(!validateThemeManifest({
    ...validManifest,
    animation: {
        intervalMs: 140,
        steps: Array.from({length: 11}, () => ({x: 0, y: 0, opacity: 255, scale: 1})),
    },
}).ok, 'more than ten animation steps accepted');

const videoDeckManifest = {
    ...validManifest,
    version: 2,
    stylesheet: undefined,
    layout: undefined,
    platforms: {
        gnome: {stylesheet: 'theme.css', layout: 'video-deck'},
        macos: {
            layout: 'classic',
            palette: {background: '#080D14FF', primary: '#79C9F5FF'},
            typography: {family: 'monospaced', scale: 0.95},
        },
    },
};
const videoDeckResult = validateThemeManifest(videoDeckManifest, 'test_theme');
assert(videoDeckResult.ok, 'valid video-deck v2 manifest rejected');
assertEqual(videoDeckResult.manifest.layout, 'video-deck', 'video-deck layout was not normalized');
assertEqual(videoDeckResult.manifest.platforms.macos.layout, 'classic',
    'video-deck macOS fallback was not preserved');
assert(!validateThemeManifest({
    ...videoDeckManifest,
    platforms: {
        ...videoDeckManifest.platforms,
        gnome: {stylesheet: 'theme.css', layout: 'unknown'},
    },
}, 'test_theme').ok, 'unknown GNOME v2 layout accepted');
assert(!validateThemeManifest({
    ...videoDeckManifest,
    platforms: {...videoDeckManifest.platforms, windows: {}},
}, 'test_theme').ok, 'unknown v2 platform accepted');

const tenFramePaths = Object.fromEntries(['good', 'worried', 'critical', 'dead'].map(status => [
    status,
    Array.from({length: 10}, (_value, index) => `frames/${status}/${index + 1}.png`),
]));
const frameManifest = {
    ...validManifest,
    layout: 'pipboy-2000',
    animation: undefined,
    frameAnimation: {
        intervalMs: 110,
        playback: 'once',
        frames: tenFramePaths,
    },
};
assert(validateThemeManifest(frameManifest, 'test_theme').ok,
    'valid frame animation rejected');
assert(!validateThemeManifest({...frameManifest, layout: 'unknown'}, 'test_theme').ok,
    'unknown layout accepted');
assert(!validateThemeManifest({...frameManifest, animation: validManifest.animation}, 'test_theme').ok,
    'transform and frame animations accepted together');
assert(!validateThemeManifest({
    ...frameManifest,
    frameAnimation: {
        ...frameManifest.frameAnimation,
        frames: {...tenFramePaths, dead: undefined},
    },
}, 'test_theme').ok, 'incomplete frame state accepted');
const staticDeadManifest = {
    ...frameManifest,
    frameAnimation: {
        ...frameManifest.frameAnimation,
        frames: {...tenFramePaths, dead: ['frames/dead/16.png']},
    },
};
assert(validateThemeManifest(staticDeadManifest, 'test_theme').ok,
    'one-frame static state rejected');
assert(!validateThemeManifest({
    ...frameManifest,
    frameAnimation: {
        ...frameManifest.frameAnimation,
        frames: {...tenFramePaths, dead: []},
    },
}, 'test_theme').ok, 'empty static state accepted');
assert(!validateThemeManifest({
    ...frameManifest,
    frameAnimation: {
        ...frameManifest.frameAnimation,
        frames: {
            ...tenFramePaths,
            good: Array.from({length: 33}, (_value, index) => `frames/good/${index + 1}.png`),
        },
    },
}, 'test_theme').ok, 'more than thirty-two frames accepted');
const thirtyTwoFramePaths = Object.fromEntries(
    ['good', 'worried', 'critical', 'dead'].map(status => [
        status,
        Array.from({length: 32}, (_value, index) => `frames/${status}/${index + 1}.png`),
    ])
);
assert(validateThemeManifest({
    ...frameManifest,
    frameAnimation: {
        ...frameManifest.frameAnimation,
        intervalMs: 20,
        frames: thirtyTwoFramePaths,
    },
}, 'test_theme').ok, 'thirty-two frame animation at 20 ms rejected');
assert(!validateThemeManifest({
    ...frameManifest,
    frameAnimation: {...frameManifest.frameAnimation, intervalMs: 19},
}, 'test_theme').ok, 'frame interval below 20 ms accepted');
const statusIntervalResult = validateThemeManifest({
    ...frameManifest,
    frameAnimation: {
        ...frameManifest.frameAnimation,
        intervalMs: 36,
        intervalMsByStatus: {good: 28},
    },
}, 'test_theme');
assert(statusIntervalResult.ok, 'valid per-status frame interval rejected');
assertEqual(statusIntervalResult.manifest.frameAnimation.intervalMsByStatus.good, 28,
    'per-status frame interval was not preserved');
assertEqual(frameAnimationInterval(statusIntervalResult.manifest.frameAnimation, 'good'), 28,
    'good interval override was not resolved');
assertEqual(frameAnimationInterval(statusIntervalResult.manifest.frameAnimation, 'worried'), 36,
    'missing status interval did not fall back to the base interval');
for (const invalidOverrides of [
    {good: 19},
    {good: 28.5},
    {unknown: 28},
]) {
    assert(!validateThemeManifest({
        ...frameManifest,
        frameAnimation: {
            ...frameManifest.frameAnimation,
            intervalMsByStatus: invalidOverrides,
        },
    }, 'test_theme').ok, `invalid per-status intervals accepted: ${JSON.stringify(invalidOverrides)}`);
}
for (const unsafe of ['../outside.png', '/outside.png']) {
    assert(!validateThemeManifest({
        ...frameManifest,
        frameAnimation: {
            ...frameManifest.frameAnimation,
            frames: {...tenFramePaths, good: [unsafe, ...tenFramePaths.good.slice(1)]},
        },
    }, 'test_theme').ok, `unsafe frame path accepted: ${unsafe}`);
}

const bundledTheme = {id: 'green', name: 'Bundled'};
const userTheme = {id: 'green', name: 'User'};
const catalog = mergeThemeLists([bundledTheme], [userTheme]);
const classic = {id: 'classic', name: 'Classic'};
catalog.set('classic', classic);
assertEqual(catalog.get('green').name, 'User', 'user theme must override bundled theme');
assertEqual(resolveTheme(catalog, 'missing'), classic, 'missing theme must fall back to Classic');

const realCatalog = loadThemeCatalog(GLib.get_current_dir(), '/nonexistent/theme-test-root');
assert(realCatalog.has('fallout-2'), 'built-in Fallout 2 theme was not discovered');
assert(realCatalog.has('fallout-3'), 'built-in Fallout 3 theme was not discovered');
assert(realCatalog.has('night-video-deck'), 'built-in Night Video Deck theme was not discovered');
assert(!realCatalog.has('pipboy-classic'), 'legacy Pip-Boy theme must not be listed');
assertEqual(realCatalog.get('fallout-2').layout, 'pipboy-2000', 'Fallout 2 layout');
assertEqual(realCatalog.get('fallout-2').animation, null,
    'Fallout 2 must not use transform animation');
assertEqual(realCatalog.get('fallout-2').frameAnimation.intervalMs, 28,
    'Fallout 2 frame interval');
for (const status of ['good', 'worried', 'critical'])
    assertEqual(realCatalog.get('fallout-2').frameAnimationPaths[status].length, 32,
        `Fallout 2 ${status} frame count`);
assertEqual(realCatalog.get('fallout-2').frameAnimationPaths.dead.length, 1,
    'Fallout 2 dead must be static');
assertEqual(realCatalog.get('fallout-2').source, 'built-in', 'Fallout 2 source');
assert(realCatalog.get('fallout-2').panelArtPaths.good.endsWith('/assets/panel/good.png'),
    'Fallout 2 panel art was not loaded');
assertEqual(realCatalog.get('fallout-3').panelArtPaths.good,
    realCatalog.get('fallout-3').artPaths.good, 'panelArt must fall back to art');
assertEqual(realCatalog.get('fallout-3').animation.steps.length, 8,
    'Fallout 3 transform animation changed');
assertEqual(realCatalog.get('fallout-3').frameAnimation, null,
    'Fallout 3 unexpectedly gained frame animation');
assertEqual(realCatalog.get('night-video-deck').layout, 'video-deck',
    'Night Video Deck GNOME layout');
assertEqual(realCatalog.get('night-video-deck').animation.intervalMs, 900,
    'Night Video Deck CRT animation interval');
assertEqual(realCatalog.get('night-video-deck').platforms.macos.layout, 'classic',
    'Night Video Deck macOS fallback');
assert(realCatalog.get('night-video-deck').panelArtPaths.dead.endsWith('/assets/panel/dead.png'),
    'Night Video Deck panel art was not loaded');
const localizedCatalog = loadThemeCatalog(
    GLib.get_current_dir(), '/nonexistent/theme-test-root', ru
);
assertEqual(localizedCatalog.get('night-video-deck').name, 'Night Video Deck',
    'Night Video Deck localized name');
assert(localizedCatalog.get('night-video-deck').description.includes('одним серым табби'),
    'Night Video Deck localized description');

function writeTheme(root, id, options = {}) {
    const themePath = GLib.build_filenamev([root, id]);
    GLib.mkdir_with_parents(GLib.build_filenamev([themePath, 'assets']), 0o700);
    const manifest = {
        ...validManifest,
        id,
        stylesheet: undefined,
        panelArt: options.panelArt ? {
            good: 'assets/panel-good.png',
            worried: 'assets/panel-worried.png',
            critical: 'assets/panel-critical.png',
            dead: 'assets/panel-dead.png',
        } : undefined,
        animation: options.frameAnimation ? undefined : validManifest.animation,
        frameAnimation: options.frameAnimation ? {
            intervalMs: 110,
            playback: 'once',
            frames: Object.fromEntries(['good', 'worried', 'critical', 'dead'].map(status => [
                status,
                Array.from({length: 10}, (_value, index) =>
                    `assets/frames-${status}-${index + 1}.png`),
            ])),
        } : undefined,
    };
    GLib.file_set_contents(
        GLib.build_filenamev([themePath, 'theme.json']),
        JSON.stringify(manifest)
    );
    for (const status of ['good', 'worried', 'critical', 'dead']) {
        GLib.file_set_contents(
            GLib.build_filenamev([themePath, 'assets', `${status}.png`]),
            'png'
        );
        if (options.panelArt) {
            GLib.file_set_contents(
                GLib.build_filenamev([themePath, 'assets', `panel-${status}.png`]),
                'png'
            );
        }
        if (options.frameAnimation) {
            for (let index = 1; index <= 10; index++) {
                GLib.file_set_contents(
                    GLib.build_filenamev([
                        themePath,
                        'assets',
                        `frames-${status}-${index}.png`,
                    ]),
                    'png'
                );
            }
        }
    }
    return themePath;
}

const temporaryRoot = GLib.dir_make_tmp('chatgpt-theme-tests-XXXXXX');
const temporaryExtension = GLib.build_filenamev([temporaryRoot, 'extension']);
const bundledRoot = GLib.build_filenamev([temporaryExtension, 'themes']);
const userRoot = GLib.build_filenamev([temporaryRoot, 'user']);
writeTheme(bundledRoot, 'override');
writeTheme(userRoot, 'override');
const overrideCatalog = loadThemeCatalog(temporaryExtension, userRoot);
assertEqual(overrideCatalog.get('override').source, 'user',
    'user theme must override a built-in theme on disk');

const linkedThemePath = writeTheme(userRoot, 'panel-link', {panelArt: true});
const linkedPanelPath = GLib.build_filenamev([linkedThemePath, 'assets', 'panel-good.png']);
Gio.File.new_for_path(linkedPanelPath).delete(null);
const outsidePath = GLib.build_filenamev([temporaryRoot, 'outside.png']);
GLib.file_set_contents(outsidePath, 'png');
Gio.File.new_for_path(linkedPanelPath).make_symbolic_link(outsidePath, null);
const linkedCatalog = loadThemeCatalog(temporaryExtension, userRoot);
assert(!linkedCatalog.has('panel-link'), 'symlinked panelArt accepted');

const frameLinkedThemePath = writeTheme(userRoot, 'frame-link', {frameAnimation: true});
const linkedFramePath = GLib.build_filenamev([
    frameLinkedThemePath,
    'assets',
    'frames-good-1.png',
]);
Gio.File.new_for_path(linkedFramePath).delete(null);
Gio.File.new_for_path(linkedFramePath).make_symbolic_link(outsidePath, null);
const frameLinkedCatalog = loadThemeCatalog(temporaryExtension, userRoot);
assert(!frameLinkedCatalog.has('frame-link'), 'symlinked frame accepted');

const styleEvents = [];
const styles = new StylesheetLifecycle(
    path => styleEvents.push(`load:${path}`),
    path => styleEvents.push(`unload:${path}`)
);
assert(styles.apply('/one.css'), 'first stylesheet did not load');
assert(styles.apply('/two.css'), 'second stylesheet did not load');
styles.clear();
assertEqual(
    styleEvents.join(','),
    'load:/one.css,unload:/one.css,load:/two.css,unload:/two.css',
    'stylesheet lifecycle order'
);

let panelClockCallback = null;
let panelClockCancelled = 0;
let panelClockTicks = 0;
const panelClock = new RepeatingTimer(
    (interval, callback) => {
        assertEqual(interval, 60, 'panel clock interval');
        panelClockCallback = callback;
        return 21;
    },
    sourceId => {
        assertEqual(sourceId, 21, 'panel clock source id');
        panelClockCancelled++;
    },
    () => panelClockTicks++
);
panelClock.start(60);
assert(panelClock.running, 'panel clock did not start');
assertEqual(panelClockCallback(), true, 'panel clock callback must repeat');
assertEqual(panelClockTicks, 1, 'panel clock did not update the panel');
panelClock.stop();
assertEqual(panelClockCancelled, 1, 'panel clock source was not removed');
assert(!panelClock.running, 'panel clock still running after stop');

let timerCallback = null;
let cancelled = 0;
const appliedSteps = [];
const animation = new AnimationLoop(
    (_interval, callback) => {
        timerCallback = callback;
        return 42;
    },
    sourceId => {
        assertEqual(sourceId, 42, 'animation source id');
        cancelled++;
    },
    step => appliedSteps.push(step.x)
);
animation.start(140, [{x: 0}, {x: 1}]);
assert(animation.running, 'animation did not start');
timerCallback();
animation.stop();
assertEqual(appliedSteps.join(','), '0,1', 'animation did not advance');
assertEqual(cancelled, 1, 'animation source was not cancelled');
assert(!animation.running, 'animation did not stop');

let frameTimerCallback = null;
let frameCancelled = 0;
let frameInterval = 0;
const appliedFrames = [];
const frameAnimation = new FrameAnimationLoop(
    (interval, callback) => {
        frameInterval = interval;
        frameTimerCallback = callback;
        return 84;
    },
    sourceId => {
        assertEqual(sourceId, 84, 'frame animation source id');
        frameCancelled++;
    },
    index => appliedFrames.push(index)
);
frameAnimation.start(50, Array.from({length: 16}, (_value, index) => index));
assertEqual(frameInterval, 50, 'frame animation interval');
assert(frameAnimation.running, 'frame animation did not start');
for (let index = 1; index < 16; index++) {
    const keepRunning = frameTimerCallback();
    assertEqual(keepRunning, index < 15, `frame callback result ${index}`);
}
assertEqual(appliedFrames.join(','), '0,1,2,3,4,5,6,7,8,9,10,11,12,13,14,15',
    'frame animation did not play 1→16 once');
assert(!frameAnimation.running, 'completed frame animation still running');
frameAnimation.stop();
assertEqual(frameCancelled, 0, 'completed frame animation was cancelled twice');

frameAnimation.start(110, [0, 1]);
frameAnimation.stop();
assertEqual(frameCancelled, 1, 'active frame animation was not cancelled');

const scheduledBeforeStatic = frameTimerCallback;
frameAnimation.start(110, ['dead']);
assert(!frameAnimation.running, 'one-frame static state scheduled a timer');
assertEqual(appliedFrames.at(-1), 0, 'one-frame static state was not displayed');
assertEqual(frameTimerCallback, scheduledBeforeStatic,
    'one-frame static state replaced the timer callback');

const frameSession = new FrameAnimationSession();
assert(frameSession.shouldPlay('good'), 'first menu open did not request playback');
frameSession.markPlayed('good');
assert(!frameSession.shouldPlay('good'), 'refresh restarted same open-menu animation');
assert(frameSession.shouldPlay('worried'), 'status change did not request playback');
frameSession.markPlayed('worried');
frameSession.reset();
assert(frameSession.shouldPlay('worried'), 'new menu open did not request playback');

console.log('Theme tests: OK');
