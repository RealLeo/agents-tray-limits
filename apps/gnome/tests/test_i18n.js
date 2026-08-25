import GLib from 'gi://GLib';

import {
    LANGUAGE_AUTONYMS,
    LANGUAGE_LOCALES,
    LANGUAGE_VALUES,
    createTranslator,
    resolveLanguage,
} from '../i18n.js';

const ROOT = GLib.get_current_dir();
const SHARED_ROOT = GLib.build_filenamev([ROOT, '..', '..', 'shared']);
const CATALOG_LANGUAGES = ['en', 'ru', 'de', 'fr', 'zh-CN'];
const PLACEHOLDER_PATTERN = /\{([A-Za-z][A-Za-z0-9_]*)\}/g;

const REQUIRED_KEYS = [
    'app.name', 'app.accessibleProfileValue',
    'status.good', 'status.worried', 'status.critical', 'status.dead',
    'panel.value',
    'time.limit', 'time.limitShort', 'time.day', 'time.hour', 'time.minute',
    'time.dayShort', 'time.hourShort', 'time.minuteShort',
    'time.resetUnknown', 'time.resetting', 'time.resetIn', 'time.resetInExact',
    'time.notUpdated', 'time.updatedNow', 'time.updatedSeconds',
    'time.updatedMinutes', 'time.updatedHours',
    'menu.connecting', 'menu.loading', 'menu.unavailable', 'menu.unknownError',
    'menu.errorCode', 'menu.accountViaCodex', 'menu.noActiveLimits',
    'menu.noPrimary', 'menu.limits', 'menu.noWindow', 'menu.primary',
    'menu.secondary', 'menu.used', 'menu.remaining', 'menu.limitReached',
    'menu.resetCredits', 'menu.activity', 'menu.tokenUnavailable', 'menu.today',
    'menu.last7', 'menu.lifetime', 'menu.peak', 'menu.streak', 'menu.tokens',
    'menu.days',
    'profiles.section', 'profiles.refreshing', 'profiles.error',
    'profiles.pending', 'profiles.remaining', 'profiles.select',
    'actions.refreshing', 'actions.refresh', 'actions.openCodex',
    'actions.openProvider', 'actions.settings', 'actions.openLinkFailed',
    'a11y.refresh', 'a11y.openCodex', 'a11y.openProvider',
    'a11y.settings', 'a11y.close',
    'errors.codex_not_found', 'errors.not_logged_in', 'errors.unsupported_auth',
    'errors.codex_too_old', 'errors.timeout', 'errors.app_server_stopped',
    'errors.protocol_error', 'errors.internal_error', 'errors.python_not_found',
    'errors.helper_start_failed', 'errors.helper_failed',
    'errors.invalid_helper_response', 'errors.unknown_error',
    'errors.app_server_start_failed', 'errors.app_server_error',
    'errors.no_rate_limits', 'errors.invalid_profile', 'errors.invalid_profile_path',
    'errors.claude_cache_missing', 'errors.claude_cache_invalid',
    'errors.claude_limits_unavailable', 'errors.claude_limits_stale',
    'errors.claude_settings_invalid', 'errors.claude_monitor_invalid',
    'errors.claude_monitor_conflict',
    'hints.codex_not_found', 'hints.not_logged_in', 'hints.unsupported_auth',
    'hints.codex_too_old', 'hints.timeout', 'hints.app_server_stopped',
    'hints.python_not_found', 'hints.claude_cache_missing',
    'hints.claude_limits_unavailable', 'hints.claude_limits_stale',
    'hints.claude_monitor_conflict',
    'themes.classic.name', 'themes.classic.description',
    'themes.fallout2.name', 'themes.fallout2.description',
    'themes.nightVideoDeck.name', 'themes.nightVideoDeck.description',
    'themes.userSuffix',
    'prefs.language.title', 'prefs.language.description',
    'prefs.language.rowTitle', 'prefs.language.rowSubtitle',
    'prefs.profiles.title', 'prefs.profiles.description', 'prefs.profiles.active',
    'prefs.profiles.activeSubtitle', 'prefs.profiles.defaultDirectory',
    'prefs.profiles.label', 'prefs.profiles.directory',
    'prefs.profiles.directoryTooltip', 'prefs.profiles.disableBeforePathChange',
    'prefs.profiles.loginCommand', 'prefs.profiles.copy',
    'prefs.profiles.claudeMonitor', 'prefs.profiles.claudeMonitorInstalled',
    'prefs.profiles.claudeMonitorDisabled', 'prefs.profiles.enableMonitor',
    'prefs.profiles.disableMonitor', 'prefs.profiles.actions',
    'prefs.profiles.save', 'prefs.profiles.remove', 'prefs.profiles.add',
    'prefs.profiles.addSubtitle', 'prefs.profiles.provider',
    'prefs.profiles.addAction', 'prefs.profiles.addButton',
    'prefs.profiles.validation.invalid', 'prefs.profiles.validation.duplicate_label',
    'prefs.profiles.validation.duplicate_location',
];

function fail(message) {
    throw new Error(message);
}

function assert(condition, message) {
    if (!condition)
        fail(message);
}

function assertEqual(actual, expected, message) {
    if (actual !== expected)
        fail(`${message}: expected ${JSON.stringify(expected)}, got ${JSON.stringify(actual)}`);
}

function readJson(path) {
    const [ok, bytes] = GLib.file_get_contents(path);
    assert(ok, `cannot read ${path}`);
    return JSON.parse(new TextDecoder('utf-8').decode(bytes));
}

function placeholders(value) {
    const found = [];
    for (const match of value.matchAll(PLACEHOLDER_PATTERN))
        found.push(match[1]);
    return [...new Set(found)].sort().join(',');
}

const catalogs = Object.fromEntries(CATALOG_LANGUAGES.map(language => [
    language,
    readJson(GLib.build_filenamev([SHARED_ROOT, 'locales', `${language}.json`])),
]));
const englishKeys = Object.keys(catalogs.en).filter(key => key !== '_meta').sort();

assertEqual(JSON.stringify(LANGUAGE_VALUES), JSON.stringify(['system', ...CATALOG_LANGUAGES]),
    'language setting values');
for (const language of CATALOG_LANGUAGES) {
    assert(LANGUAGE_AUTONYMS[language], `missing autonym for ${language}`);
    assert(LANGUAGE_LOCALES[language], `missing Intl locale for ${language}`);

    const catalog = catalogs[language];
    assertEqual(catalog._meta.language, language, `${language} metadata language`);
    assertEqual(catalog._meta.locale, LANGUAGE_LOCALES[language], `${language} metadata locale`);
    const keys = Object.keys(catalog).filter(key => key !== '_meta').sort();
    assertEqual(JSON.stringify(keys), JSON.stringify(englishKeys), `${language} catalog keys`);

    for (const key of englishKeys) {
        const reference = catalogs.en[key];
        const translated = catalog[key];
        assertEqual(Array.isArray(translated), false, `${language}:${key} must not be an array`);
        assertEqual(typeof translated, typeof reference, `${language}:${key} value type`);
        if (typeof reference === 'string') {
            assertEqual(placeholders(translated), placeholders(reference),
                `${language}:${key} placeholders`);
            continue;
        }

        assert(typeof translated.other === 'string', `${language}:${key} needs an other form`);
        const expectedPlaceholders = placeholders(reference.other);
        for (const [category, form] of Object.entries(translated)) {
            assert(typeof form === 'string', `${language}:${key}.${category} must be a string`);
            assertEqual(placeholders(form), expectedPlaceholders,
                `${language}:${key}.${category} placeholders`);
        }
    }
}

for (const key of REQUIRED_KEYS)
    assert(englishKeys.includes(key), `required UI key missing: ${key}`);

assertEqual(resolveLanguage('de', ['ru_RU.UTF-8']), 'de', 'explicit language');
assertEqual(resolveLanguage('system', ['ru_RU.UTF-8', 'en_US']), 'ru', 'Russian system locale');
assertEqual(resolveLanguage('system', ['zh_Hant_TW', 'en_US']), 'zh-CN', 'Chinese locale normalization');
assertEqual(resolveLanguage('system', ['C', 'es_ES.UTF-8']), 'en', 'unsupported system locale');
assertEqual(resolveLanguage('invalid', ['ru_RU.UTF-8']), 'en', 'invalid explicit language');

const en = createTranslator(ROOT, 'en');
const ru = createTranslator(ROOT, 'ru');
const de = createTranslator(ROOT, 'de');
const fr = createTranslator(ROOT, 'fr');
const zh = createTranslator(ROOT, 'zh-CN');
assertEqual(en.locale, 'en-US', 'English Intl locale');
assertEqual(ru.locale, 'ru-RU', 'Russian Intl locale');
assertEqual(en.t('menu.errorCode', {code: 'timeout'}), 'Code: timeout', 'named interpolation');
assertEqual(en.t('menu.errorCode'), 'Code: {code}', 'missing placeholder remains visible');
assertEqual(en.t('missing.key'), 'missing.key', 'missing canonical key');
assertEqual(en.tn('menu.tokens', 1), '1 token', 'English singular');
assertEqual(en.tn('menu.tokens', 2), '2 tokens', 'English plural');
assertEqual(en.tn('menu.tokens', 1200, {count: '1.2k'}), '1.2k tokens',
    'caller-formatted count is preserved');
assertEqual(ru.tn('menu.tokens', 1), '1 токен', 'Russian one');
assertEqual(ru.tn('menu.tokens', 2), '2 токена', 'Russian few');
assertEqual(ru.tn('menu.tokens', 5), '5 токенов', 'Russian many');
assertEqual(de.tn('time.day', 2), '2 Tage', 'German plural');
assertEqual(fr.tn('time.day', 1), '1 jour', 'French singular');
assertEqual(zh.tn('menu.tokens', 2), '2 令牌', 'Chinese other form');
assertEqual(en.tn('menu.tokens', 12_500, {count: '12.5K'}), '12.5K tokens',
    'preformatted compact count');

const statusFormats = [
    [en, ['ALL GOOD', 'WORRIED', 'CRITICAL', 'DEPLETED']],
    [ru, ['ВСЁ ХОРОШО', 'ВОЛНИТЕЛЬНО', 'КРИТИЧНО', 'СМЕРТЬ']],
    [de, ['ALLES GUT', 'BESORGT', 'KRITISCH', 'AUFGEBRAUCHT']],
    [fr, ['TOUT VA BIEN', 'INQUIÉTANT', 'CRITIQUE', 'ÉPUISÉ']],
    [zh, ['状态良好', '令人担忧', '严重', '已耗尽']],
];
for (const [translator, expected] of statusFormats) {
    const actual = ['good', 'worried', 'critical', 'dead']
        .map(status => translator.t(`status.${status}`));
    assertEqual(JSON.stringify(actual), JSON.stringify(expected),
        `${translator.language} status labels`);
}

const numberFormats = [
    [en, '12,345.6'],
    [ru, '12 345,6'],
    [de, '12.345,6'],
    [fr, '12 345,6'],
    [zh, '12,345.6'],
];
const dateFormats = [
    [en, '08/23, 12:34 PM'],
    [ru, '23.08, 12:34'],
    [de, '23.08., 12:34'],
    [fr, '23/08 12:34'],
    [zh, '08/23 12:34'],
];
const sampleDate = new Date(Date.UTC(2026, 7, 23, 12, 34));
for (const [translator, expected] of numberFormats) {
    assertEqual(translator.formatNumber(12_345.6), expected,
        `${translator.language} number format`);
}
for (const [translator, expected] of dateFormats) {
    assertEqual(translator.formatDate(sampleDate, {
        day: '2-digit',
        month: '2-digit',
        hour: '2-digit',
        minute: '2-digit',
        timeZone: 'UTC',
    }), expected, `${translator.language} date format`);
}

const temporaryRoot = GLib.dir_make_tmp('agents-tray-i18n-XXXXXX');
const temporaryLocales = GLib.build_filenamev([temporaryRoot, 'locales']);
GLib.mkdir_with_parents(temporaryLocales, 0o700);
const temporaryEnglish = GLib.build_filenamev([temporaryLocales, 'en.json']);
const temporaryRussian = GLib.build_filenamev([temporaryLocales, 'ru.json']);
GLib.file_set_contents(temporaryEnglish, JSON.stringify({
    greeting: 'Hello, {name}!',
    things: {one: '{count} thing', other: '{count} things'},
}));
GLib.file_set_contents(temporaryRussian, JSON.stringify({
    things: {one: '{count} вещь', few: '{count} вещи', many: '{count} вещей', other: '{count} вещи'},
}));
const partial = createTranslator(temporaryRoot, 'ru');
assertEqual(partial.t('greeting', {name: 'Ada'}), 'Hello, Ada!', 'English key fallback');
GLib.unlink(temporaryEnglish);
GLib.unlink(temporaryRussian);
GLib.rmdir(temporaryLocales);
GLib.rmdir(temporaryRoot);

print(`i18n checks passed (${englishKeys.length} keys, ${CATALOG_LANGUAGES.length} catalogs)`);
