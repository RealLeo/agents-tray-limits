import Gio from 'gi://Gio';
import GLib from 'gi://GLib';

import {
    CLASSIC_THEME_ID,
    THEME_STATUS_KEYS,
    mergeThemeLists,
    validateThemeManifest,
} from './themeLogic.js';

const DIRECTORY_ATTRIBUTES = 'standard::name,standard::type';

export function userThemesDirectory() {
    return GLib.build_filenamev([
        GLib.get_user_data_dir(),
        'agents-tray-limits',
        'themes',
    ]);
}

function childDirectories(path) {
    const directory = Gio.File.new_for_path(path);
    if (!directory.query_exists(null))
        return [];

    const children = [];
    let enumerator = null;
    try {
        enumerator = directory.enumerate_children(
            DIRECTORY_ATTRIBUTES,
            Gio.FileQueryInfoFlags.NOFOLLOW_SYMLINKS,
            null
        );
        let info;
        while ((info = enumerator.next_file(null)) !== null) {
            if (info.get_file_type() === Gio.FileType.DIRECTORY)
                children.push(info.get_name());
        }
    } catch (error) {
        console.warn(`[Agents Tray Limits] Cannot enumerate themes in ${path}: ${error.message}`);
    } finally {
        try {
            enumerator?.close(null);
        } catch (_error) {
            // The directory may already be closed after an enumeration error.
        }
    }
    return children.sort();
}

function readJson(path) {
    const file = Gio.File.new_for_path(path);
    const [, bytes] = file.load_contents(null);
    return JSON.parse(new TextDecoder().decode(bytes));
}

function isRegularPathInside(themePath, relativePath, extensions) {
    const parts = relativePath.split('/');
    const extension = relativePath.toLowerCase().split('.').pop();
    if (!extensions.includes(extension))
        return false;

    let current = themePath;
    for (const part of parts) {
        current = GLib.build_filenamev([current, part]);
        const file = Gio.File.new_for_path(current);
        const type = file.query_file_type(Gio.FileQueryInfoFlags.NOFOLLOW_SYMLINKS, null);
        if (type === Gio.FileType.SYMBOLIC_LINK || type === Gio.FileType.UNKNOWN)
            return false;
    }
    return Gio.File.new_for_path(current).query_file_type(
        Gio.FileQueryInfoFlags.NOFOLLOW_SYMLINKS,
        null
    ) === Gio.FileType.REGULAR;
}

function validateStylesheet(themePath, relativePath) {
    if (!isRegularPathInside(themePath, relativePath, ['css']))
        return false;
    let css;
    try {
        const file = Gio.File.new_for_path(GLib.build_filenamev([
            themePath,
            ...relativePath.split('/'),
        ]));
        const [, bytes] = file.load_contents(null);
        css = new TextDecoder().decode(bytes);
    } catch (_error) {
        return false;
    }
    if (/@import\b/i.test(css))
        return false;

    const urls = css.matchAll(/url\s*\(([^)]+)\)/gi);
    for (const match of urls) {
        const value = match[1].trim().replace(/^(['"])(.*)\1$/, '$2');
        if (!isSafeThemeCssAsset(themePath, value))
            return false;
    }
    return true;
}

function isSafeThemeCssAsset(themePath, value) {
    if (!value || value.startsWith('data:') || value.includes('://') ||
        value.startsWith('/') || value.includes('\\'))
        return false;
    const parts = value.split('/');
    if (!parts.every(part => part && part !== '.' && part !== '..'))
        return false;
    return isRegularPathInside(themePath, value, ['png', 'jpg', 'jpeg', 'webp']);
}

function loadTheme(themeRoot, directoryName, source) {
    const themePath = GLib.build_filenamev([themeRoot, directoryName]);
    const manifestPath = GLib.build_filenamev([themePath, 'theme.json']);
    let raw;
    try {
        raw = readJson(manifestPath);
    } catch (error) {
        console.warn(`[Agents Tray Limits] Invalid ${manifestPath}: ${error.message}`);
        return null;
    }

    const result = validateThemeManifest(raw, directoryName);
    if (!result.ok) {
        console.warn(`[Agents Tray Limits] Ignoring theme ${directoryName}: ${result.error}`);
        return null;
    }

    const manifest = result.manifest;
    const artPaths = {};
    for (const status of THEME_STATUS_KEYS) {
        const relative = manifest.art[status];
        if (!isRegularPathInside(themePath, relative, ['png', 'jpg', 'jpeg', 'webp'])) {
            console.warn(`[Agents Tray Limits] Ignoring theme ${directoryName}: invalid art.${status}`);
            return null;
        }
        artPaths[status] = GLib.build_filenamev([themePath, ...relative.split('/')]);
    }

    let panelArtPaths = artPaths;
    if (manifest.panelArt) {
        panelArtPaths = {};
        for (const status of THEME_STATUS_KEYS) {
            const relative = manifest.panelArt[status];
            if (!isRegularPathInside(themePath, relative, ['png', 'jpg', 'jpeg', 'webp'])) {
                console.warn(`[Agents Tray Limits] Ignoring theme ${directoryName}: invalid panelArt.${status}`);
                return null;
            }
            panelArtPaths[status] = GLib.build_filenamev([
                themePath,
                ...relative.split('/'),
            ]);
        }
    }

    let frameAnimationPaths = null;
    if (manifest.frameAnimation) {
        frameAnimationPaths = {};
        for (const status of THEME_STATUS_KEYS) {
            frameAnimationPaths[status] = [];
            for (const relative of manifest.frameAnimation.frames[status]) {
                if (!isRegularPathInside(themePath, relative, ['png', 'jpg', 'jpeg', 'webp'])) {
                    console.warn(`[Agents Tray Limits] Ignoring theme ${directoryName}: invalid frameAnimation.frames.${status}`);
                    return null;
                }
                frameAnimationPaths[status].push(GLib.build_filenamev([
                    themePath,
                    ...relative.split('/'),
                ]));
            }
        }
    }

    let stylesheetPath = null;
    if (manifest.stylesheet) {
        if (!validateStylesheet(themePath, manifest.stylesheet)) {
            console.warn(`[Agents Tray Limits] Ignoring theme ${directoryName}: invalid stylesheet`);
            return null;
        }
        stylesheetPath = GLib.build_filenamev([
            themePath,
            ...manifest.stylesheet.split('/'),
        ]);
    }

    return {
        ...manifest,
        source,
        directory: themePath,
        stylesheetPath,
        artPaths,
        panelArtPaths,
        frameAnimationPaths,
    };
}

function loadRoot(root, source) {
    return childDirectories(root)
        .map(name => loadTheme(root, name, source))
        .filter(Boolean);
}

function localizeBuiltInTheme(theme, i18n) {
    if (!i18n?.t || theme.source !== 'built-in')
        return theme;
    const key = {
        'fallout-2': 'fallout2',
        'night-video-deck': 'nightVideoDeck',
    }[theme.id];
    if (!key)
        return theme;
    return {
        ...theme,
        name: i18n.t(`themes.${key}.name`),
        description: i18n.t(`themes.${key}.description`),
    };
}

export function loadThemeCatalog(
    extensionPath,
    userRoot = userThemesDirectory(),
    i18n = null
) {
    const packagedRoot = GLib.build_filenamev([extensionPath, 'themes']);
    const developmentRoot = GLib.build_filenamev([
        extensionPath, '..', '..', 'shared', 'themes',
    ]);
    const builtInRoot = GLib.file_test(packagedRoot, GLib.FileTest.IS_DIR)
        ? packagedRoot
        : developmentRoot;
    const catalog = mergeThemeLists(
        loadRoot(builtInRoot, 'built-in').map(theme => localizeBuiltInTheme(theme, i18n)),
        loadRoot(userRoot, 'user')
    );
    catalog.set(CLASSIC_THEME_ID, {
        id: CLASSIC_THEME_ID,
        name: i18n?.t('themes.classic.name') ?? 'Classic',
        description: i18n?.t('themes.classic.description') ??
            'The native GNOME appearance without visual overrides.',
        source: 'built-in',
        stylesheetPath: null,
        artPaths: null,
        panelArtPaths: null,
        layout: null,
        animation: null,
        frameAnimation: null,
        frameAnimationPaths: null,
    });
    return catalog;
}

export function resolveTheme(catalog, requestedId) {
    return catalog.get(requestedId) ?? catalog.get(CLASSIC_THEME_ID);
}

export function sortedThemes(catalog, locale = 'en') {
    return [...catalog.values()].sort((left, right) => {
        if (left.id === CLASSIC_THEME_ID)
            return -1;
        if (right.id === CLASSIC_THEME_ID)
            return 1;
        return left.name.localeCompare(right.name, locale);
    });
}
