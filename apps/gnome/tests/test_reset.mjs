import assert from 'node:assert/strict';
import fs from 'node:fs';
import vm from 'node:vm';
import {resetAvailability, resetResultMessage} from '../resetLogic.js';

const now = Date.now() / 1000;
const profile = {id: 'personal', label: 'Personal', provider: 'codex', configDir: '/isolated/personal'};
function state() {
    return {data: {
        ok: true, fetchedAt: Math.floor(now), resetAccount: 'a'.repeat(64),
        account: {type: 'chatgpt', email: 'personal@example.com'},
        rateLimits: {
            rateLimitsByLimitId: {codex: {
                primary: {usedPercent: 90, windowDurationMins: 300, resetsAt: now + 3600},
                secondary: {usedPercent: 50, windowDurationMins: 10080, resetsAt: now + 86400},
            }},
            rateLimitResetCredits: {availableCount: 2},
        },
    }};
}
const policy = value => resetAvailability(profile, value, now, 300);
assert.equal(policy(state()).enabled, true);
for (const [used, enabled] of [[89.99, false], [90, true], [100, true], [null, false], ['100', false], [NaN, false]]) {
    const value = state();
    value.data.rateLimits.rateLimitsByLimitId.codex.primary.usedPercent = used;
    assert.equal(policy(value).enabled, enabled);
}
for (const field of ['resetBusy', 'resetConfirming', 'refreshing', 'queued', 'resetUnsupported', 'error']) {
    const value = state(); value[field] = true;
    assert.equal(policy(value).enabled, false, field);
}
for (const count of [0, null, undefined, -1, '2']) {
    const value = state(); value.data.rateLimits.rateLimitResetCredits.availableCount = count;
    assert.equal(policy(value).enabled, false);
}
{
    const value = state(); const bucket = value.data.rateLimits.rateLimitsByLimitId.codex;
    bucket.primary.usedPercent = 1; bucket.secondary.usedPercent = 90;
    assert.equal(policy(value).enabled, true);
    bucket.secondary.resetsAt = now - 1;
    value.data.rateLimits.rateLimitsByLimitId.codex_other = {primary: {...bucket.primary, usedPercent: 100}};
    assert.equal(policy(value).enabled, false, 'other buckets cannot enable reset');
    value.data.fetchedAt = now - 301;
    assert.equal(policy(value).reason, 'reset.noData');
}
{
    const value = state();
    value.data.rateLimits.rateLimitResetCredits.availableCount = 0;
    value.resetAttempt = {idempotencyKey: 'saved-key', account: value.data.resetAccount};
    assert.equal(policy(value).enabled, true, 'pending attempts can be reconciled after a reset');
    value.resetAttempt.account = 'another-account';
    assert.equal(policy(value).reason, 'reset.accountChanged');
}
assert.equal(resetResultMessage({ok: true, outcome: 'reset'}), 'reset.success');
assert.equal(resetResultMessage({ok: true, outcome: 'alreadyRedeemed', refreshError: {}}), 'reset.successRefreshFailed');
assert.equal(resetResultMessage({ok: true, outcome: 'noCredit'}), 'reset.noCredit');
assert.equal(resetResultMessage({ok: true, outcome: 'nothingToReset'}), 'reset.nothingToReset');

// Execute the actual extension controller with native UI/process boundaries
// replaced by fakes; no GNOME display or real Codex account is involved.
class FakeDialog {
    constructor() { this.signals = {}; this.contentLayout = {add_child: content => { this.content = content; }}; }
    connect(name, fn) { this.signals[name] = fn; }
    setButtons(buttons) { this.buttons = buttons; }
    open() { return true; }
    close() { this.signals.closed?.(); this.destroy(); }
    destroy() { this.signals.destroy?.(); }
}
const calls = [];
const context = vm.createContext({
    console, Date, Set, Map, resetAvailability, resetResultMessage,
    Extension: class {}, PanelMenu: {Button: class {}}, GObject: {registerClass: cls => cls},
    ModalDialog: {ModalDialog: FakeDialog}, Dialog: {MessageDialogContent: class {constructor(options) {Object.assign(this, options);}}},
    Clutter: {KEY_Escape: 27},
    GLib: {uuid_string_random: () => 'bd185fea-b12c-4bf4-a4aa-3229655f2adb',
        find_program_in_path: () => '/usr/bin/python3', build_filenamev: parts => parts.join('/')},
    Gio: {Cancellable: class {}, SubprocessFlags: {STDOUT_PIPE: 1, STDERR_PIPE: 2},
        Subprocess: {new: argv => {
            const call = {argv}; calls.push(call);
            return {communicate_utf8_async: (_input, _cancel, callback) => {call.callback = callback;}};
        }}},
    providerName: provider => provider === 'claude' ? 'Claude Code' : 'Codex',
    providerUrl: provider => `https://${provider}.example`,
});
const source = fs.readFileSync(new URL('../extension.js', import.meta.url), 'utf8')
    .replace(/^import[\s\S]*?;\n/gm, '')
    .replace('export default class AgentsTrayLimitsExtension', 'globalThis.TestExtension = class AgentsTrayLimitsExtension');
vm.runInContext(source, context);
const ExtensionClass = context.TestExtension;
function extension() {
    const ext = new ExtensionClass(); const value = state();
    ext.path = '/extension'; ext._enabled = true; ext._resetDialog = null;
    ext._profileStates = new Map([[profile.id, value]]);
    ext._activeProfile = () => profile; ext._activeState = () => value;
    ext._settings = {get_uint: () => 300, get_string: () => '/usr/bin/codex'};
    ext._i18n = {t: (key, params) => `${key}${params ? JSON.stringify(params) : ''}`};
    ext._indicator = {menu: {close() {}}};
    ext._rebuildCurrentMenu = () => {}; ext._profileStateChanged = id => {ext.changedProfile = id;};
    ext._refresh = () => {ext.reads = (ext.reads ?? 0) + 1;};
    return [ext, value];
}
{
    const [ext, value] = extension();
    ext._runningRefreshes = 1; ext._drainRefreshQueue = () => {};
    ext._onProfileHelperFinished(profile.id, value,
        {communicate_utf8_finish: () => [true, JSON.stringify(value.data), '']}, {});
    assert.equal(value.resetMessage, undefined, 'ordinary monitoring does not report a reset result');
    value.resetAttempt = {idempotencyKey: 'completed-key', account: value.data.resetAccount};
    const snapshot = {...value.data, resetLastResult: {idempotencyKey: 'completed-key', ok: true, outcome: 'reset'}};
    ext._onProfileHelperFinished(profile.id, value,
        {communicate_utf8_finish: () => [true, JSON.stringify(snapshot), '']}, {});
    assert.equal(value.resetMessage, 'reset.success', 'recover a completed result after lost stdout');
    assert.equal(value.resetAttempt, null);
}
{
    const [ext, value] = extension();
    ext._requestReset();
    const dialog = ext._resetDialog;
    assert.match(dialog.content.description, /Personal/);
    assert.match(dialog.content.description, /personal@example.com/);
    ext._requestReset(); assert.equal(ext._resetDialog, dialog, 'only one confirmation');
    dialog.buttons[0].action();
    assert.equal(calls.length, 0, 'cancel never starts helper');
    assert.equal(value.resetConfirming, false);
}
{
    const [ext, value] = extension();
    ext._requestReset(); const dialog = ext._resetDialog;
    ext._activeProfile = () => ({...profile, id: 'work'});
    dialog.buttons[1].action(); dialog.buttons[1].action();
    assert.equal(calls.length, 1, 'double confirmation sends one request');
    const call = calls.at(-1);
    assert.equal(call.argv[call.argv.indexOf('--profile-id') + 1], 'personal');
    assert.equal(call.argv[call.argv.indexOf('--config-dir') + 1], '/isolated/personal');
    assert.equal(value.resetBusy, true);
    ext._runReset(profile, value, value.resetAttempt);
    assert.equal(calls.length, 1, 'busy state prevents duplicate subprocess');
    call.callback({communicate_utf8_finish: () => [true, JSON.stringify({ok: true, outcome: 'reset',
        snapshot: {...value.data, resetAttempt: null}}), '']}, {});
    assert.equal(value.resetBusy, false);
    assert.equal(value.resetMessage, 'reset.success');
    assert.equal(value.resetAttempt, null);
    assert.equal(ext.changedProfile, 'personal', 'reply updates captured profile');
}
{
    const [ext, value] = extension();
    const savedKey = 'dc080fba-0e13-4266-970a-a095671c6792';
    value.data.resetAttempt = {idempotencyKey: savedKey, account: value.data.resetAccount};
    value.data.rateLimits.rateLimitResetCredits.availableCount = 0;
    ext._requestReset(); ext._resetDialog.buttons[1].action();
    const call = calls.at(-1);
    assert.equal(call.argv[call.argv.indexOf('--idempotency-key') + 1], savedKey);
    call.callback({communicate_utf8_finish: () => {throw new Error('lost response');}}, {});
    assert.equal(value.resetAttempt.idempotencyKey, savedKey);
    assert.equal(value.resetMessage, 'reset.uncertain');
    assert.equal(ext.reads, 1, 'recovery reads only');
}
{
    const [ext, value] = extension();
    ext._requestReset(); const dialog = ext._resetDialog;
    ext._profileStates.set(profile.id, state());
    const before = calls.length; dialog.buttons[1].action();
    assert.equal(calls.length, before, 'changed profile configuration cancels old confirmation');
    assert.equal(value.resetBusy, undefined);
}
{
    const [ext] = extension();
    const action = ext._providerAction();
    assert.equal(action.label, 'RESET'); assert.equal(action.sensitive, true);
    ext._activeProfile = () => ({provider: 'claude'});
    let opened;
    ext._openUrl = url => {opened = url;};
    ext._providerAction().activate();
    assert.equal(opened, 'https://claude.example');
}
// Every layout consumes the same tested action and renders a visible reason.
for (const method of ['_beginPipboyLayout', '_beginVideoDeckLayout', '_beginAgentsAmpLayout']) {
    const start = source.indexOf(`    ${method}(`);
    assert.ok(start >= 0, method);
    const body = source.slice(start, source.indexOf('\n    }', start));
    assert.match(body, /_providerAction\(/, method);
}
for (const method of ['_addProfileSelector', '_populateAgentsAmpPlaylist']) {
    const body = ExtensionClass.prototype[method].toString();
    assert.match(body, /_addResetStatus\(/, method);
}
console.log('Reset policy and controller tests passed');
