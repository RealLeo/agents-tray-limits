export const PROFILE_CONFIG_VERSION = 1;
export const DEFAULT_PROFILE_ID = 'default-codex';
export const PROVIDERS = ['codex', 'claude'];
const PROFILE_ID_PATTERN = /^[A-Za-z0-9._-]{1,128}$/;
const CONTROL_CHARACTER_PATTERN = /[\x00-\x1f\x7f]/;

function cleanText(value) {
    return typeof value === 'string' ? value.trim() : '';
}

function cleanProfile(raw) {
    if (!raw || typeof raw !== 'object' || Array.isArray(raw))
        return null;

    const id = cleanText(raw.id);
    const provider = cleanText(raw.provider).toLowerCase();
    const label = cleanText(raw.label);
    const configDir = cleanText(raw.configDir);
    if (!PROFILE_ID_PATTERN.test(id) || !PROVIDERS.includes(provider) || !label ||
        CONTROL_CHARACTER_PATTERN.test(label))
        return null;
    if (CONTROL_CHARACTER_PATTERN.test(configDir) ||
        (configDir && !configDir.startsWith('/') && !configDir.startsWith('~/')))
        return null;
    return {id, provider, label, configDir};
}

export function defaultProfilesDocument() {
    return {
        version: PROFILE_CONFIG_VERSION,
        profiles: [{
            id: DEFAULT_PROFILE_ID,
            provider: 'codex',
            label: 'Codex',
            configDir: '',
        }],
    };
}

export function parseProfilesDocument(value, createDefault = true) {
    let parsed = null;
    try {
        parsed = typeof value === 'string' && value.trim()
            ? JSON.parse(value)
            : null;
    } catch (_error) {
        parsed = null;
    }

    const source = parsed?.version === PROFILE_CONFIG_VERSION &&
        Array.isArray(parsed.profiles)
        ? parsed.profiles
        : [];
    const profiles = [];
    const seenIds = new Set();
    const seenLabels = new Set();
    const seenLocations = new Set();
    for (const raw of source) {
        const profile = cleanProfile(raw);
        if (!profile)
            continue;
        const labelKey = profile.label.toLocaleLowerCase();
        const locationKey = `${profile.provider}\0${profile.configDir}`;
        if (seenIds.has(profile.id) || seenLabels.has(labelKey) ||
            seenLocations.has(locationKey))
            continue;
        seenIds.add(profile.id);
        seenLabels.add(labelKey);
        seenLocations.add(locationKey);
        profiles.push(profile);
    }

    const document = profiles.length > 0 || !createDefault
        ? {version: PROFILE_CONFIG_VERSION, profiles}
        : defaultProfilesDocument();
    return {
        document,
        serialized: JSON.stringify(document),
        migrated: JSON.stringify(parsed) !== JSON.stringify(document),
    };
}

export function resolveActiveProfile(profiles, activeId) {
    if (!Array.isArray(profiles) || profiles.length === 0)
        return null;
    return profiles.find(profile => profile.id === activeId) ?? profiles[0];
}

export function validateProfileCandidate(candidate, profiles, editingId = null) {
    const profile = cleanProfile(candidate);
    if (!profile)
        return {ok: false, error: 'invalid'};

    const others = (profiles ?? []).filter(item => item.id !== editingId);
    if (others.some(item => item.label.toLocaleLowerCase() ===
        profile.label.toLocaleLowerCase()))
        return {ok: false, error: 'duplicate_label'};
    if (others.some(item => item.provider === profile.provider &&
        item.configDir === profile.configDir))
        return {ok: false, error: 'duplicate_location'};
    return {ok: true, profile};
}

function shellQuote(value) {
    return `'${String(value).replaceAll("'", `'\"'\"'`)}'`;
}

function commandDirectory(path) {
    if (!path)
        return '';
    if (path.startsWith('~/'))
        return `"$HOME"/${shellQuote(path.slice(2))}`;
    return shellQuote(path);
}

function commandBinary(value, fallback) {
    const binary = cleanText(value) || fallback;
    return binary === fallback ? fallback : shellQuote(binary);
}

export function loginCommand(profile, codexBinary = 'codex') {
    const directory = commandDirectory(profile?.configDir);
    if (profile?.provider === 'claude')
        return directory ? `CLAUDE_CONFIG_DIR=${directory} claude` : 'claude';
    const binary = commandBinary(codexBinary, 'codex');
    if (!directory)
        return `${binary} login`;
    return `CODEX_HOME=${directory} ${binary} ` +
        `-c 'cli_auth_credentials_store="file"' login`;
}

export function providerUrl(provider) {
    return provider === 'claude'
        ? 'https://claude.ai/code'
        : 'https://chatgpt.com/codex';
}

export function providerName(provider) {
    return provider === 'claude' ? 'Claude Code' : 'Codex';
}
