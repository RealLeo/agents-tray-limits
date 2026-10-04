import assert from 'node:assert/strict';
import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';
import vm from 'node:vm';
import {fileURLToPath} from 'node:url';
import {spawnSync} from 'node:child_process';
import {resetAvailability, resetCreditExpiry} from '../resetLogic.js';

const now = Math.floor(Date.now() / 1000);
const credit = expiresAt => ({id: `credit-${expiresAt}`, resetType: 'codexRateLimits', status: 'available', expiresAt});
const summary = (...dates) => ({availableCount: dates.length, credits: dates.map(credit)});
for (const [remaining, urgency] of [[86401, 'normal'], [86400, 'warning'], [21600, 'warning'], [21599, 'critical'], [1, 'critical']]) {
    const result = resetCreditExpiry(summary(now + remaining), now);
    assert.equal(result.urgency, urgency, `boundary ${remaining}`);
    assert.equal(result.expiresAt, now + remaining);
    assert.equal(result.partial, false);
}
assert.equal(resetCreditExpiry(summary(now, now - 1), now).expiresAt, null);
assert.equal(resetCreditExpiry(summary(now, now - 1), now).expiredAt, now);
assert.equal(resetCreditExpiry(summary(now, now - 1), now).urgency, 'normal');
assert.equal(resetCreditExpiry(summary(now + 90000, now + 100, now + 80000), now).expiresAt, now + 100);
for (const count of [0, -1, undefined, null, '1', NaN])
    assert.equal(resetCreditExpiry({availableCount: count, credits: [credit(now + 1)]}, now), null);
for (const credits of [undefined, null, [], {}, [null], [credit(null)], [credit('123')], [credit(Infinity)], [credit(1e20)]]) {
    const result = resetCreditExpiry({availableCount: 1, credits}, now);
    assert.equal(result.expiresAt, null);
    assert.equal(result.urgency, 'normal');
}
{
    const data = summary(now + 20);
    data.credits.push({...credit(now + 1), status: 'redeemed'}, {...credit(now + 2), resetType: 'other'});
    assert.equal(resetCreditExpiry(data, now).expiresAt, now + 20);
    assert.equal(resetCreditExpiry(data, now).partial, false);
    data.availableCount = 3;
    assert.equal(resetCreditExpiry(data, now).partial, true);
    assert.equal(data.availableCount, 3, 'local expiry never changes the server count');
}

// Read an actual helper snapshot from fake-codex and render it with the real
// extension methods. Only GNOME actors/process scheduling are replaced here.
const root = fileURLToPath(new URL('..', import.meta.url));
const temporary = fs.mkdtempSync(path.join(os.tmpdir(), 'agents-tray-expiry-test-'));
let snapshot;
try {
    const result = spawnSync('/usr/bin/python3', [path.join(root, 'bin/agents-tray-limits-helper.py'),
        '--codex-bin', path.join(root, 'tests/fake-codex'), '--config-dir', path.join(temporary, 'codex'), '--timeout', '2'], {
        encoding: 'utf8', env: {...process.env, XDG_STATE_HOME: path.join(temporary, 'state'),
            FAKE_CODEX_SCENARIO: 'success', FAKE_CODEX_RESET_STORE: '', FAKE_CODEX_USED: '90',
            FAKE_CODEX_CREDITS: '2', FAKE_CODEX_CREDIT_DETAILS: JSON.stringify(summary(now + 100000, now + 86400).credits),
            FAKE_CODEX_REQUEST_LOG: path.join(temporary, 'requests.jsonl')},
    });
    assert.equal(result.status, 0, result.stderr);
    snapshot = JSON.parse(result.stdout);
    assert.deepEqual(snapshot.rateLimits.rateLimitResetCredits, summary(now + 100000, now + 86400));
    const methods = fs.readFileSync(path.join(temporary, 'requests.jsonl'), 'utf8').trim().split('\n').map(line => JSON.parse(line).method);
    assert.ok(methods.includes('account/rateLimits/read'));
    assert.ok(!methods.includes('account/rateLimitResetCredit/consume'), 'expiry monitoring never consumes a reset');
} finally {
    fs.rmSync(temporary, {recursive: true, force: true});
}

class Actor {
    constructor(props = {}) { Object.assign(this, props); this.clutter_text = {}; this.children = []; this.visible = true; }
    add_child(child) { this.children.push(child); }
    hide() { this.visible = false; }
    add_style_class_name(name) { this.style_class = `${this.style_class ?? ''} ${name}`.trim(); }
    remove_style_class_name(name) { this.style_class = this.style_class?.split(' ').filter(value => value !== name).join(' '); }
    has_style_class_name(name) { return this.style_class?.split(' ').includes(name) ?? false; }
}
const context = vm.createContext({
    Date, Set, Map, resetAvailability, resetCreditExpiry,
    Extension: class {}, PanelMenu: {Button: class {}}, GObject: {registerClass: cls => cls},
    St: {Label: Actor, BoxLayout: Actor}, Pango: {EllipsizeMode: {NONE: 0}, WrapMode: {WORD_CHAR: 0}},
    Clutter: {ActorAlign: {END: 0}}, PopupMenu: {PopupMenuItem: class extends Actor {constructor() {super(); this.label = new Actor();}}},
});
const source = fs.readFileSync(path.join(root, 'extension.js'), 'utf8')
    .replace(/^import[\s\S]*?;\n/gm, '')
    .replace('export default class AgentsTrayLimitsExtension', 'globalThis.TestExtension = class AgentsTrayLimitsExtension');
vm.runInContext(source, context);
const locales = path.join(root, '../../shared/locales');
for (const layout of ['classic', 'pipboy-2000', 'video-deck', 'agents-amp']) {
    for (const language of ['en', 'ru', 'de', 'fr', 'zh-CN']) {
        const catalog = JSON.parse(fs.readFileSync(path.join(locales, `${language}.json`)));
        const ext = new context.TestExtension();
        const profile = {id: 'personal', provider: 'codex'};
        const state = {data: structuredClone(snapshot)};
        ext._profiles = [profile]; ext._profileStates = new Map([[profile.id, state]]);
        ext._activeProfile = () => profile; ext._activeState = () => state;
        ext._data = state.data; ext._theme = {layout}; ext._resetExpiryLabels = [];
        ext._settings = {get_uint: () => 300};
        ext._i18n = {
            t: (key, params = {}) => catalog[key].replace(/\{(\w+)\}/g, (_, name) => params[name]),
            formatNumber: (value, options) => new Intl.NumberFormat(catalog._meta.locale, options).format(value),
            formatDate: (value, options) => new Intl.DateTimeFormat(catalog._meta.locale, options).format(value),
        };
        const content = new Actor();
        ext._indicator = {menu: {addMenuItem: item => content.add_child(item)}};
        if (layout === 'agents-amp') ext._agentsAmpPlaylistContent = content;
        else if (layout !== 'classic') ext._contentTarget = content;
        ext._refresh = () => {ext.reads = (ext.reads ?? 0) + 1;};
        ext._addResetStatus(); ext._addResetCredits();
        assert.equal(ext._resetExpiryLabels.length, 2, `${layout}/${language}: expiry next to both counts`);
        const label = ext._resetExpiryLabels[0];
        const originalChildren = [...content.children];
        for (const [time, urgency] of [[now - 1, 'normal'], [now, 'warning'], [now + 64800, 'warning'], [now + 64801, 'critical']]) {
            ext._updateResetExpiries(time);
            assert.equal(label.has_style_class_name('warning'), urgency === 'warning');
            assert.equal(label.has_style_class_name('critical'), urgency === 'critical');
            assert.equal(label.accessible_name, label.text);
            assert.deepEqual(content.children, originalChildren, 'clock ticks preserve actors and scroll container');
        }
        assert.equal(ext.reads, undefined, 'color updates do not fetch data');
        const expectedDate = ext._i18n.formatDate(new Date((now + 86400) * 1000), {
            year: 'numeric', month: '2-digit', day: '2-digit', hour: '2-digit', minute: '2-digit',
        });
        assert.equal(label.text, ext._i18n.t('menu.resetExpiry', {date: expectedDate}));
        state.resetBusy = true;
        ext._updateResetExpiries(now + 86400);
        assert.equal(ext.reads, undefined, 'do not overlap a confirmed reset');
        state.resetBusy = false;
        ext._updateResetExpiries(now + 86400);
        assert.equal(ext.reads, 1);
        assert.ok(!label.text.includes(expectedDate), 'expired date is replaced by the next future date');
        assert.ok(label.text.startsWith(catalog['menu.resetExpiryKnown'].split('{date}')[0]));
        ext._updateResetExpiries(now + 86401);
        assert.equal(ext.reads, 1, 'stale replies do not cause a refresh loop');
        ext._updateResetExpiries(now + 100000);
        assert.equal(ext.reads, 2, 'refresh again when the next credit expires');
        assert.equal(label.text, catalog['menu.resetExpiryUnknown']);
        assert.equal(label.has_style_class_name('critical'), false);
        assert.equal(state.data.rateLimits.rateLimitResetCredits.availableCount, 2);
        // Switching profiles must immediately use the new profile's data.
        ext._data = {rateLimits: {rateLimitResetCredits: {availableCount: 1, credits: null}}};
        ext._updateResetExpiries(now);
        assert.equal(label.text, catalog['menu.resetExpiryUnknown']);
        ext._data.rateLimits.rateLimitResetCredits.availableCount = 0;
        ext._updateResetExpiries(now);
        assert.equal(label.visible, false);
        ext._activeProfile = () => ({provider: 'claude'});
        const before = content.children.length;
        ext._addResetCredits();
        assert.equal(content.children.length, before, 'Claude UI unchanged');
    }
}
console.log('Reset expiry: boundaries, fake helper, all layouts/locales and clock updates passed');
