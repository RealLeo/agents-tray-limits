import {
    DEFAULT_PROFILE_ID,
    PROFILE_CONFIG_VERSION,
    loginCommand,
    parseProfilesDocument,
    providerUrl,
    resolveActiveProfile,
    validateProfileCandidate,
} from '../profileLogic.js';

function assert(condition, message) {
    if (!condition)
        throw new Error(message);
}

function equal(actual, expected, message) {
    if (JSON.stringify(actual) !== JSON.stringify(expected))
        throw new Error(`${message}: expected ${JSON.stringify(expected)}, got ${JSON.stringify(actual)}`);
}

const migrated = parseProfilesDocument('');
assert(migrated.migrated, 'empty legacy settings should migrate');
equal(migrated.document, {
    version: PROFILE_CONFIG_VERSION,
    profiles: [{
        id: DEFAULT_PROFILE_ID,
        provider: 'codex',
        label: 'Codex',
        configDir: '',
    }],
}, 'default profile');

const source = {
    version: 1,
    profiles: [
        {id: 'personal', provider: 'codex', label: 'Personal', configDir: '~/.codex-personal'},
        {id: 'work', provider: 'claude', label: 'Work', configDir: '/tmp/claude-work'},
    ],
};
const parsed = parseProfilesDocument(JSON.stringify(source));
equal(parsed.document, source, 'valid profiles are preserved');
assert(!parsed.migrated, 'canonical valid document should not migrate');
equal(resolveActiveProfile(parsed.document.profiles, 'work'), source.profiles[1],
    'active profile selection');
equal(resolveActiveProfile(parsed.document.profiles, 'missing'), source.profiles[0],
    'missing active profile falls back');
equal(resolveActiveProfile([source.profiles[0]], 'work'), source.profiles[0],
    'deleting the active profile selects the first remaining profile');

assert(!validateProfileCandidate({
    id: 'duplicate', provider: 'claude', label: 'personal', configDir: '/tmp/other',
}, source.profiles).ok, 'duplicate label rejected');
assert(!validateProfileCandidate({
    id: 'duplicate', provider: 'claude', label: 'Other', configDir: '/tmp/claude-work',
}, source.profiles).ok, 'duplicate provider directory rejected');
assert(!validateProfileCandidate({
    id: 'relative', provider: 'codex', label: 'Relative', configDir: 'relative/path',
}, source.profiles).ok, 'relative directory rejected');
assert(!validateProfileCandidate({
    id: 'control', provider: 'codex', label: 'Control', configDir: '/tmp/bad\npath',
}, source.profiles).ok, 'control characters in directory rejected');
assert(!validateProfileCandidate({
    id: 'bad id', provider: 'codex', label: 'Bad ID', configDir: '/tmp/bad-id',
}, source.profiles).ok, 'invalid profile ID rejected');

equal(
    loginCommand(source.profiles[0]),
    'CODEX_HOME="$HOME"/\'.codex-personal\' codex -c \'cli_auth_credentials_store="file"\' login',
    'Codex login command'
);
equal(
    loginCommand(source.profiles[1]),
    'CLAUDE_CONFIG_DIR=\'/tmp/claude-work\' claude',
    'Claude login command'
);
equal(
    loginCommand({provider: 'codex', configDir: "/tmp/work's `$HOME`"}, '/tmp/my codex'),
    "CODEX_HOME='/tmp/work'\"'\"'s `$HOME`' '/tmp/my codex' " +
        "-c 'cli_auth_credentials_store=\"file\"' login",
    'Copied login commands quote shell metacharacters'
);
equal(providerUrl('claude'), 'https://claude.ai/code', 'Claude URL');

print('profile logic checks passed');
