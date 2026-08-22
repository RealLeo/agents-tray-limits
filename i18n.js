import GLib from 'gi://GLib';

export const LANGUAGE_VALUES = Object.freeze([
    'system',
    'en',
    'ru',
    'de',
    'fr',
    'zh-CN',
]);

export const LANGUAGE_AUTONYMS = Object.freeze({
    system: 'System',
    en: 'English',
    ru: 'Русский',
    de: 'Deutsch',
    fr: 'Français',
    'zh-CN': '简体中文',
});

export const LANGUAGE_LOCALES = Object.freeze({
    en: 'en-US',
    ru: 'ru-RU',
    de: 'de-DE',
    fr: 'fr-FR',
    'zh-CN': 'zh-CN',
});

const SUPPORTED_LANGUAGES = new Set(Object.keys(LANGUAGE_LOCALES));
const PLACEHOLDER_PATTERN = /\{([A-Za-z][A-Za-z0-9_]*)\}/g;

function languageFromLocale(value) {
    const normalized = String(value ?? '')
        .trim()
        .replace(/\..*$/, '')
        .replace(/@.*$/, '')
        .replaceAll('_', '-')
        .toLowerCase();

    if (!normalized || normalized === 'c' || normalized === 'posix')
        return null;
    if (normalized === 'zh' || normalized.startsWith('zh-'))
        return 'zh-CN';

    const language = normalized.split('-', 1)[0];
    return SUPPORTED_LANGUAGES.has(language) ? language : null;
}

export function resolveLanguage(selected = 'system', systemLanguages = GLib.get_language_names()) {
    if (selected !== 'system')
        return SUPPORTED_LANGUAGES.has(selected) ? selected : 'en';

    const candidates = Array.isArray(systemLanguages)
        ? systemLanguages
        : [...(systemLanguages ?? [])];
    for (const candidate of candidates) {
        const language = languageFromLocale(candidate);
        if (language)
            return language;
    }
    return 'en';
}

function readCatalog(extensionPath, language) {
    const path = GLib.build_filenamev([extensionPath, 'locales', `${language}.json`]);
    try {
        const [ok, contents] = GLib.file_get_contents(path);
        if (!ok)
            return null;
        const catalog = JSON.parse(new TextDecoder('utf-8').decode(contents));
        return catalog && typeof catalog === 'object' && !Array.isArray(catalog)
            ? catalog
            : null;
    } catch (error) {
        console.warn(`[Agents Tray Limits] Cannot load locale ${language}: ${error.message}`);
        return null;
    }
}

function stringEntry(catalog, key) {
    const value = catalog?.[key];
    return typeof value === 'string' ? value : null;
}

function pluralEntry(catalog, key) {
    const value = catalog?.[key];
    return value && typeof value === 'object' && !Array.isArray(value)
        ? value
        : null;
}

function interpolate(template, params = {}) {
    return template.replace(PLACEHOLDER_PATTERN, (placeholder, name) =>
        Object.hasOwn(params, name) ? String(params[name]) : placeholder
    );
}

export function createTranslator(
    extensionPath,
    selected = 'system',
    systemLanguages = GLib.get_language_names()
) {
    const language = resolveLanguage(selected, systemLanguages);
    const locale = LANGUAGE_LOCALES[language];
    const english = readCatalog(extensionPath, 'en') ?? {};
    const catalog = language === 'en'
        ? english
        : readCatalog(extensionPath, language) ?? {};
    const pluralRules = new Intl.PluralRules(locale);
    const numberFormat = new Intl.NumberFormat(locale, {maximumFractionDigits: 20});

    const t = (key, params = {}) => {
        const template = stringEntry(catalog, key) ?? stringEntry(english, key) ?? key;
        return interpolate(template, params);
    };

    const tn = (key, count, params = {}) => {
        const numericCount = Number(count);
        const safeCount = Number.isFinite(numericCount) ? numericCount : 0;
        const category = pluralRules.select(safeCount);
        const localized = pluralEntry(catalog, key);
        const fallback = pluralEntry(english, key);
        const template = localized?.[category] ?? localized?.other ??
            fallback?.[category] ?? fallback?.other ?? key;
        const values = Object.hasOwn(params, 'count')
            ? params
            : {...params, count: numberFormat.format(safeCount)};
        return interpolate(template, values);
    };

    const formatNumber = (value, options = {}) =>
        new Intl.NumberFormat(locale, options).format(value);
    const formatDate = (value, options = {}) =>
        new Intl.DateTimeFormat(locale, options).format(value);

    return Object.freeze({language, locale, t, tn, formatNumber, formatDate});
}
