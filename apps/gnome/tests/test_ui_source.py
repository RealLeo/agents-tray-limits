import json
import struct
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
EXTENSION = ROOT
REPO_ROOT = Path(__file__).resolve().parents[3]
SHARED_ROOT = REPO_ROOT / "shared"
GOOD_RIG_ROOT = REPO_ROOT / "tools" / "animation-rig" / "v16"
STATE_RIG_ROOT = REPO_ROOT / "tools" / "animation-rig" / "v18"
SOURCE = (EXTENSION / "extension.js").read_text(encoding="utf-8")
PREFS = (EXTENSION / "prefs.js").read_text(encoding="utf-8")
CSS = (SHARED_ROOT / "themes" / "fallout-2" / "theme.css").read_text(encoding="utf-8")
ASSETS = SHARED_ROOT / "themes" / "fallout-2" / "assets"
VIDEO_ROOT = SHARED_ROOT / "themes" / "night-video-deck"
VIDEO_CSS = (VIDEO_ROOT / "theme.css").read_text(encoding="utf-8")
VIDEO_ASSETS = VIDEO_ROOT / "assets"
AMP_ROOT = SHARED_ROOT / "themes" / "agents-amp"
AMP_CSS = (AMP_ROOT / "theme.css").read_text(encoding="utf-8")
AMP_ASSETS = AMP_ROOT / "assets" / "status"
AMP_SOURCE = REPO_ROOT / "tools" / "theme-assets" / "agents-amp"


def png_header(path):
    with path.open("rb") as stream:
        if stream.read(8) != b"\x89PNG\r\n\x1a\n":
            raise AssertionError(f"not a PNG: {path}")
        length = struct.unpack(">I", stream.read(4))[0]
        if stream.read(4) != b"IHDR" or length != 13:
            raise AssertionError(f"missing PNG IHDR: {path}")
        width, height, _depth, color_type, *_rest = struct.unpack(">IIBBBBB", stream.read(13))
        return width, height, color_type


class PipboyUiSourceTests(unittest.TestCase):
    def test_multi_profile_state_refresh_and_menu_contract(self):
        self.assertIn("const MAX_PARALLEL_REFRESHES = 3", SOURCE)
        refresh = SOURCE.split("_refresh() {", 1)[1].split("_updatePanelText() {", 1)[0]
        self.assertIn("for (const profile of this._profiles)", refresh)
        self.assertIn("this._runningRefreshes < MAX_PARALLEL_REFRESHES", refresh)
        self.assertIn("this._profileStates.get(profile.id)", refresh)
        self.assertIn("--provider", refresh)
        self.assertIn("--profile-id", refresh)
        self.assertIn("--config-dir", refresh)

        selection = SOURCE.split("_selectProfile(profileId) {", 1)[1]
        selection = selection.split("_rebuildCurrentMenu() {", 1)[0]
        self.assertIn("set_string('active-profile-id', profileId)", selection)
        self.assertNotIn("_refresh()", selection)
        self.assertGreaterEqual(SOURCE.count("this._addProfileSelector()"), 5)
        self.assertIn("this._profileStates = new Map()", SOURCE)
        self.assertIn("state.error = error", SOURCE)
        self.assertIn("state.data = payload", SOURCE)
        self.assertIn("providerUrl(activeProvider)", SOURCE)
        self.assertIn("app.accessibleProfileValue", SOURCE)

        self.assertIn("parseProfilesDocument(settings.get_string('profiles-json'))", PREFS)
        self.assertIn("--install-claude-monitor", PREFS)
        self.assertIn("--restore-claude-monitor", PREFS)
        self.assertIn("remaining[0]?.id ?? ''", PREFS)

    def test_language_switch_rebuilds_without_refreshing_data(self):
        setting_method = SOURCE.split("_onSettingChanged(key) {", 1)[1]
        setting_method = setting_method.split("_applyAppearance() {", 1)[0]
        language_branch = setting_method.split("if (key === 'language') {", 1)[1]
        language_branch = language_branch.split("\n        }", 1)[0]
        self.assertIn("createTranslator(", language_branch)
        self.assertNotIn("this._refresh()", language_branch)
        self.assertIn("key === 'theme-id' || key === 'language'", setting_method)
        self.assertIn("this._buildDataMenu()", setting_method)
        self.assertIn("if (key === 'codex-binary')\n            this._refresh()", setting_method)

        self.assertIn("settings.set_string('language', language)", PREFS)
        self.assertIn("window.remove(window._agentsTrayLimitsPage)", PREFS)
        self.assertIn("GLib.idle_add(GLib.PRIORITY_DEFAULT_IDLE", PREFS)
        self.assertIn("rebuild()", PREFS)

    def test_panel_orders_text_before_icon(self):
        init = SOURCE.split("class UsageIndicator", 1)[1]
        init = init.split("setAppearance(showIcon)", 1)[0]
        self.assertLess(
            init.index("this._box.add_child(this._label)"),
            init.index("this._box.add_child(this._icon)"),
        )

    def test_version_and_fixed_outer_geometry(self):
        metadata = json.loads((EXTENSION / "metadata.json").read_text(encoding="utf-8"))
        self.assertEqual(metadata["version"], 18)
        device_rule = CSS.split(".agents-tray-limits-pipboy-device {", 1)[1].split("}", 1)[0]
        self.assertIn("width: 680px", device_rule)
        self.assertIn("height: 520px", device_rule)
        self.assertIn("padding: 0", device_rule)
        self.assertIn("layout_manager: new Clutter.FixedLayout()", SOURCE)
        for geometry in (
            "x: 20,\n            y: 20,\n            width: 194,\n            height: 22",
            "x: 40,\n            y: 56,\n            width: 136,\n            height: 116",
            "x: 54,\n            y: 326,\n            width: 110,\n            height: 174",
            "x: 246,\n            y: 52,\n            width: 402,\n            height: 426",
        ):
            self.assertIn(geometry, SOURCE)

    def test_actions_are_centered_in_the_metal_bay(self):
        layout = SOURCE.split("const actionBay = new St.Widget({", 1)[1]
        layout = layout.split("const screenTitle", 1)[0]
        self.assertIn("layout_manager: new Clutter.BinLayout()", layout)
        self.assertIn("y_align: Clutter.ActorAlign.CENTER", layout)
        self.assertIn("actionBay.add_child(buttons)", layout)
        self.assertIn("device.add_child(actionBay)", layout)

    def test_badge_is_never_ellipsized(self):
        self.assertIn("text: 'PIP-BOY 2000'", SOURCE)
        self.assertIn("const badgeText = new St.Label", SOURCE)
        self.assertIn("const badge = new St.Bin", SOURCE)
        self.assertIn("child: badgeText", SOURCE)
        self.assertIn("badgeText.clutter_text.ellipsize = Pango.EllipsizeMode.NONE", SOURCE)
        self.assertIn("badgeText.clutter_text.single_line_mode = true", SOURCE)
        badge_rule = CSS.split(".agents-tray-limits-pipboy-badge {", 1)[1].split("}", 1)[0]
        self.assertIn("background-color: transparent", badge_rule)
        self.assertIn("border: 0", badge_rule)

    def test_decorative_status_rows_are_removed(self):
        begin = SOURCE.split("_beginPipboyLayout(status, remaining, mode) {", 1)[1]
        begin = begin.split("_createPipboyButton(", 1)[0]
        for text in ("['STATUS'", "['LIMITS'", "['ARCHIVES'"):
            self.assertNotIn(text, begin)

    def test_action_order_and_unshortened_refresh(self):
        method = SOURCE.split("_createPipboyButton(label, accessibleName", 1)[1]
        method = method.split("_addPipboyState(", 1)[0]
        self.assertLess(method.index("agents-tray-limits-pipboy-button-lens"),
                        method.index("agents-tray-limits-pipboy-button-label"))
        for label in ("'REFRESH'", "'CODEX'", "'SETTINGS'", "'CLOSE'"):
            self.assertIn(label, SOURCE)
        self.assertNotIn("REFRESH…", SOURCE)
        button_label_rule = CSS.split(".agents-tray-limits-pipboy-button-label {", 1)[1]
        button_label_rule = button_label_rule.split("}", 1)[0]
        self.assertIn("font-size: 12px", button_label_rule)
        self.assertIn("font-weight: 900", button_label_rule)
        button_rule = CSS.split(".agents-tray-limits-pipboy-button {", 1)[1].split("}", 1)[0]
        self.assertIn("min-height: 30px", button_rule)
        self.assertIn("padding: 0 2px", button_rule)
        buttons_rule = CSS.split(".agents-tray-limits-pipboy-buttons {", 1)[1]
        buttons_rule = buttons_rule.split("}", 1)[0]
        self.assertIn("spacing: 0", buttons_rule)
        content_rule = CSS.split(".agents-tray-limits-pipboy-button-content {", 1)[1]
        content_rule = content_rule.split("}", 1)[0]
        self.assertIn("spacing: 4px", content_rule)
        lens_rule = CSS.split(".agents-tray-limits-pipboy-button-lens {", 1)[1].split("}", 1)[0]
        self.assertIn("width: 28px", lens_rule)
        self.assertIn("height: 28px", lens_rule)
        self.assertIn("background-size: 28px 28px", lens_rule)

    def test_vault_boy_screen_is_subtly_lighter(self):
        art_rule = CSS.split(".agents-tray-limits-pipboy-art-frame {", 1)[1]
        art_rule = art_rule.split("}", 1)[0]
        self.assertIn("background-color: rgba(12, 18, 13, 0.9)", art_rule)
        diagnostic_rule = CSS.split(
            ".agents-tray-limits-pipboy-art-frame.error {", 1
        )[1].split("}", 1)[0]
        self.assertIn("background-color: rgba(2, 3, 3, 0.96)", diagnostic_rule)

    def test_crt_has_no_old_fixed_inner_widths(self):
        for declaration in ("width: 442px", "width: 382px", "min-width: 360px",
                            "max-width: 360px", "height: 430px", "height: 496px"):
            self.assertNotIn(declaration, CSS)
        self.assertIn("hscrollbar_policy: St.PolicyType.NEVER", SOURCE)
        self.assertIn("vscrollbar_policy: St.PolicyType.AUTOMATIC", SOURCE)
        self.assertIn("overlay_scrollbars: false", SOURCE)
        self.assertIn("Pango.WrapMode.WORD_CHAR", SOURCE)
        scroll_source = SOURCE.split("const scroll = new St.ScrollView({", 1)[1]
        scroll_source = scroll_source.split("device.add_child(scroll)", 1)[0]
        self.assertIn("clip_to_allocation: true", scroll_source)
        self.assertIn("scroll.update_fade_effect?.(new Clutter.Margin", scroll_source)
        self.assertIn("scroll.get_vadjustment().connect('notify::value'", scroll_source)
        self.assertIn("content.queue_redraw()", scroll_source)
        self.assertIn("scroll.queue_redraw()", scroll_source)
        self.assertIn("device.queue_redraw()", scroll_source)
        screen_rule = CSS.split(".agents-tray-limits-pipboy-screen {", 1)[1].split("}", 1)[0]
        self.assertIn("background-color: transparent", screen_rule)
        self.assertIn("border-radius: 0", screen_rule)
        self.assertIn("padding: 0", screen_rule)
        content_rule = CSS.split(".agents-tray-limits-pipboy-screen-content {", 1)[1]
        content_rule = content_rule.split("}", 1)[0]
        self.assertIn("padding: 8px 18px 10px 14px", content_rule)

    def test_v3_background_and_version_18_frame_set(self):
        expected = {
            "ui/device-shell-v3.png": (1360, 1040, 2),
            "ui/red-button-v4.png": (128, 128, 6),
            "ui/red-button-pressed-v4.png": (128, 128, 6),
        }
        actual = {
            path.relative_to(ASSETS).as_posix()
            for path in (ASSETS / "ui").glob("*.png")
        }
        self.assertEqual(actual, set(expected))
        for relative, header in expected.items():
            self.assertEqual(png_header(ASSETS / relative), header)
        frames = list((ASSETS / "animation").glob("*/*.png"))
        self.assertEqual(len(frames), 97)
        for frame in frames:
            self.assertEqual(png_header(frame), (512, 512, 6))
        self.assertIn('background-image: url("assets/ui/device-shell-v3.png")', CSS)
        self.assertIn('background-image: url("assets/ui/red-button-v4.png")', CSS)
        self.assertIn('background-image: url("assets/ui/red-button-pressed-v4.png")', CSS)

    def test_frame_switching_has_no_crossfade(self):
        self.assertNotIn("FRAME_CROSSFADE_MS", SOURCE)
        method = SOURCE.split("_showMenuArtFrame(index) {", 1)[1]
        method = method.split("_stopArtAnimation() {", 1)[0]
        self.assertNotIn(".ease({", method)
        self.assertNotIn("remove_all_transitions()", method)
        self.assertIn("actor.visible = false", method)
        self.assertIn("actor.opacity = 255", method)
        self.assertIn("this._menuArtFrames[safeIndex].visible = true", method)
        self.assertNotIn("_menuArtFrameIndex", SOURCE)
        self.assertNotIn("_cancelMenuArtTransitions", SOURCE)
        stop = SOURCE.split("_stopArtAnimation() {", 1)[1]
        stop = stop.split("_syncArtAnimation() {", 1)[0]
        self.assertIn("this._animationLoop?.stop()", stop)
        self.assertIn("this._frameAnimationLoop?.stop()", stop)

    def test_fallout_2_uses_three_animated_states_and_static_dead(self):
        manifest = json.loads(
            (SHARED_ROOT / "themes" / "fallout-2" / "theme.json").read_text(
                encoding="utf-8"
            )
        )
        animation = manifest["frameAnimation"]
        self.assertEqual(animation["intervalMs"], 28)
        self.assertNotIn("intervalMsByStatus", animation)
        self.assertEqual(animation["playback"], "once")
        for status in ("good", "worried", "critical"):
            self.assertEqual(len(animation["frames"][status]), 32)
            self.assertEqual(31 * animation["intervalMs"], 868)
            self.assertEqual(manifest["art"][status], f"assets/animation/{status}/32.png")
        self.assertEqual(animation["frames"]["dead"], ["assets/animation/dead/16.png"])
        self.assertEqual(manifest["art"]["dead"], "assets/animation/dead/16.png")
        sync = SOURCE.split("_syncArtAnimation() {", 1)[1].split("_reschedule() {", 1)[0]
        self.assertIn("this._menuArtFrames?.length > 1", sync)
        self.assertIn(
            "frameAnimationInterval(\n                frameAnimation, this._menuArtStatus",
            SOURCE,
        )

    def test_current_deterministic_rig_contracts(self):
        good = json.loads(
            (GOOD_RIG_ROOT / "perspective-preview-config-v6.json").read_text(
                encoding="utf-8"
            )
        )
        critical = json.loads(
            (STATE_RIG_ROOT / "configs" / "critical-back.json").read_text(
                encoding="utf-8"
            )
        )
        self.assertEqual(good["canvas"], [512, 512])
        self.assertEqual(good["frames"], 32)
        self.assertEqual(good["intervalMs"], 36)
        self.assertEqual(good["sourceDir"], "sources/master-v6")
        self.assertIn("finalRepairMask", good)
        self.assertEqual(critical["canvas"], [512, 512])
        self.assertEqual(critical["frames"], 32)
        self.assertEqual(critical["intervalMs"], 28)
        self.assertTrue(
            (STATE_RIG_ROOT / "rigs" / "critical-back.blend").is_file()
        )
        builder = (GOOD_RIG_ROOT / "build_master_rig.py").read_text(
            encoding="utf-8"
        )
        preparer = (STATE_RIG_ROOT / "prepare_assets.py").read_text(
            encoding="utf-8"
        )
        self.assertIn("--render-good", builder)
        self.assertIn("Image.Resampling.LANCZOS", preparer)
        self.assertNotIn("optical flow", (builder + preparer).lower())

    def test_lamps_have_no_runtime_actor_or_timer(self):
        runtime = SOURCE + CSS
        for marker in ("_lampAnimationLoop", "_lampChamber", "_lampGlow",
                       "LAMP_PULSE_STEPS", "pipboy-lamp-chamber",
                       "lamp-chamber-v3.png", "lamp-glow-v3.png"):
            self.assertNotIn(marker, runtime)
        self.assertIn("get_boolean('theme-animation')", SOURCE)
        self.assertIn("get_boolean('enable-animations')", SOURCE)

    def test_status_is_inside_vault_boy_screen(self):
        layout = SOURCE.split("_beginPipboyLayout(status, remaining, mode) {", 1)[1]
        layout = layout.split("_createPipboyButton(", 1)[0]
        self.assertIn("agents-tray-limits-pipboy-art-status", layout)
        self.assertIn("artFrame.add_child(artStatus)", layout)
        self.assertIn("icon_size: 98", layout)
        self.assertIn("layout_manager: new Clutter.FixedLayout()", layout)
        self.assertIn("x: 19,\n                    y: 0,\n                    width: 98,\n                    height: 98", layout)
        self.assertIn("x: 2,\n                y: 90,\n                width: 132,\n                height: 26", layout)
        self.assertIn("const offline = new St.Bin", layout)

    def test_popup_has_no_black_underlay(self):
        popup_rule = CSS.split(".agents-tray-limits-theme-fallout-2 .popup-menu-content {", 1)[1]
        popup_rule = popup_rule.split("}", 1)[0]
        for declaration in ("background-color: transparent", "border: 0",
                            "border-radius: 0", "box-shadow: none"):
            self.assertIn(declaration, popup_rule)
        device_rule = CSS.split(".agents-tray-limits-pipboy-device {", 1)[1].split("}", 1)[0]
        self.assertIn("background-color: transparent", device_rule)
        self.assertIn("box-shadow: none", device_rule)
        self.assertIn("-arrow-background-color: transparent", CSS)
        self.assertIn("-arrow-rise: 0", CSS)

    def test_pointer_cursor_lifecycle(self):
        self.assertIn("Meta.Cursor.POINTING_HAND", SOURCE)
        self.assertIn("Meta.Cursor.DEFAULT", SOURCE)
        self.assertIn("button.connect('enter-event'", SOURCE)
        self.assertIn("button.connect('leave-event'", SOURCE)
        self.assertGreaterEqual(SOURCE.count("this._setPointerCursor(false)"), 4)

    def test_hardware_actions_have_localized_tooltips(self):
        method = SOURCE.split("_createPipboyButton(label, accessibleName", 1)[1]
        method = method.split("_addPipboyState(", 1)[0]
        self.assertIn("accessible_name: accessibleName", method)
        self.assertIn("this._showPipboyTooltip(button, accessibleName)", method)
        self.assertIn("this._hidePipboyTooltip(button)", method)
        self.assertIn("button.connect('destroy'", method)
        self.assertGreaterEqual(SOURCE.count("this._hidePipboyTooltip()"), 3)
        self.assertIn(".agents-tray-limits-pipboy-tooltip {", CSS)


class NightVideoDeckUiSourceTests(unittest.TestCase):
    def test_fixed_geometry_matches_the_production_shell(self):
        method = SOURCE.split("_beginVideoDeckLayout(status, remaining, mode) {", 1)[1]
        method = method.split("\n    _createVideoDeckButton(", 1)[0]
        for geometry in (
            "width: 680,\n            height: 520",
            "x: 27,\n            y: 48,\n            width: 200,\n            height: 172",
            "x: 257,\n            y: 65,\n            width: 391,\n            height: 350",
        ):
            self.assertIn(geometry, method)
        self.assertIn("layout_manager: new Clutter.FixedLayout()", method)
        self.assertIn("hscrollbar_policy: St.PolicyType.NEVER", method)
        self.assertIn("vscrollbar_policy: St.PolicyType.AUTOMATIC", method)
        device_rule = VIDEO_CSS.split(
            ".agents-tray-limits-video-deck-device {", 1
        )[1].split("}", 1)[0]
        self.assertIn("width: 680px", device_rule)
        self.assertIn("height: 520px", device_rule)
        self.assertIn('background-image: url("assets/ui/device-shell.png")', device_rule)

    def test_real_actions_surround_decorative_transport_controls(self):
        method = SOURCE.split("_beginVideoDeckLayout(status, remaining, mode) {", 1)[1]
        method = method.split("_createVideoDeckButton(\n        label", 1)[0]
        self.assertEqual(method.count("this._createVideoDeckButton("), 4)
        buttons = ((20, 74), (96, 74), (497, 80), (579, 80))
        for x, width in buttons:
            self.assertIn(f"{x}, 451, {width}, 58", method)
        self.assertEqual(buttons[1][0] - sum(buttons[0]), 2)
        self.assertEqual(buttons[3][0] - sum(buttons[2]), 2)
        self.assertLess(buttons[1][0] + buttons[1][1], 207)
        self.assertGreater(buttons[2][0], 486)
        self.assertIn("videoDeck.refresh", method)
        self.assertIn("videoDeck.settings", method)
        self.assertIn("videoDeck.close", method)
        self.assertIn("activeProvider === 'claude' ? 'CLAUDE' : 'CODEX'", method)
        button = SOURCE.split("_createVideoDeckButton(\n        label", 1)[1]
        button = button.split("_addVideoDeckState(", 1)[0]
        self.assertIn("can_focus: sensitive", button)
        self.assertIn("accessible_name: accessibleName", button)
        self.assertIn("translation_y: -2", button)
        self.assertNotIn("this._showPipboyTooltip", button)
        self.assertNotIn("this._hidePipboyTooltip", button)
        self.assertNotIn("media-skip", button)

    def test_normal_loading_and_error_use_one_video_deck_shell(self):
        loading = SOURCE.split("_buildLoadingMenu() {", 1)[1].split(
            "_buildErrorMenu() {", 1
        )[0]
        self.assertIn("this._beginVideoDeckLayout(null, null, 'loading')", loading)
        self.assertIn("this._endVideoDeckLayout()", loading)

        error = SOURCE.split("_buildErrorMenu() {", 1)[1].split(
            "_buildDataMenu() {", 1
        )[0]
        self.assertIn("this._beginVideoDeckLayout('dead', null, 'error')", error)
        self.assertIn("this._syncArtAnimation()", error)

        data = SOURCE.split("_buildVideoDeckDataMenu() {", 1)[1].split(
            "\n    _beginVideoDeckLayout", 1
        )[0]
        for marker in (
            "this._addProfileSelector()",
            "this._addVideoDeckState(status, Math.round(remaining))",
            "this._addBucket(bucket)",
            "this._addResetCredits()",
            "this._addTokenUsage()",
            "this._syncArtAnimation()",
        ):
            self.assertIn(marker, data)

    def test_assets_manifest_and_crt_animation_contract(self):
        manifest = json.loads((VIDEO_ROOT / "theme.json").read_text(encoding="utf-8"))
        self.assertEqual(manifest["id"], "night-video-deck")
        self.assertEqual(manifest["platforms"]["gnome"]["layout"], "video-deck")
        self.assertEqual(manifest["platforms"]["macos"]["layout"], "classic")
        self.assertEqual(manifest["animation"]["intervalMs"], 900)
        self.assertEqual(len(manifest["animation"]["steps"]), 4)
        self.assertTrue(all(abs(step.get("x", 0)) <= 1 for step in manifest["animation"]["steps"]))
        self.assertTrue(all(abs(step.get("y", 0)) <= 1 for step in manifest["animation"]["steps"]))

        self.assertEqual(png_header(VIDEO_ASSETS / "ui" / "device-shell.png"), (1360, 1040, 2))
        for group, size in (("art", 512), ("panel", 256)):
            actual = {path.name for path in (VIDEO_ASSETS / group).glob("*.png")}
            self.assertEqual(actual, {"good.png", "worried.png", "critical.png", "dead.png"})
            for status in actual:
                self.assertEqual(png_header(VIDEO_ASSETS / group / status), (size, size, 6))

    def test_video_deck_css_keeps_dynamic_surfaces_clear(self):
        popup = VIDEO_CSS.split(
            ".agents-tray-limits-theme-night-video-deck .popup-menu-content {", 1
        )[1].split("}", 1)[0]
        self.assertIn("background-color: transparent", popup)
        self.assertIn("box-shadow: none", popup)
        screen = VIDEO_CSS.split(
            ".agents-tray-limits-video-deck-screen {", 1
        )[1].split("}", 1)[0]
        self.assertIn("background-color: transparent", screen)
        content = VIDEO_CSS.split(
            ".agents-tray-limits-video-deck-screen-content {", 1
        )[1].split("}", 1)[0]
        self.assertIn("padding: 8px 18px 12px 12px", content)
        hover = VIDEO_CSS.split(
            ".agents-tray-limits-video-deck-button:hover {", 1
        )[1].split("}", 1)[0]
        self.assertIn("background-color: transparent", hover)
        self.assertIn("border-color: transparent", hover)
        self.assertIn("box-shadow: none", hover)
        focus = VIDEO_CSS.split(
            ".agents-tray-limits-video-deck-button:focus {", 1
        )[1].split("}", 1)[0]
        self.assertIn("background-color: transparent", focus)
        self.assertIn("border-color: rgba(105, 188, 226, 0.55)", focus)
        self.assertIn("box-shadow: none", focus)
        active = VIDEO_CSS.split(
            ".agents-tray-limits-video-deck-button:active {", 1
        )[1].split("}", 1)[0]
        self.assertIn("background-color: transparent", active)
        self.assertIn("border-color: rgba(62, 112, 136, 0.65)", active)
        self.assertIn(".agents-tray-limits-video-deck-button:insensitive", VIDEO_CSS)
        self.assertNotIn(".agents-tray-limits-pipboy-tooltip", VIDEO_CSS)

    def test_agents_amp_fixed_geometry_and_real_widget_layout(self):
        manifest = json.loads((AMP_ROOT / "theme.json").read_text(encoding="utf-8"))
        self.assertEqual(manifest["id"], "agents-amp")
        self.assertEqual(manifest["platforms"]["gnome"]["layout"], "agents-amp")
        self.assertEqual(manifest["platforms"]["macos"]["layout"], "agents-amp")
        layout = SOURCE.split("_beginAgentsAmpLayout(status, remaining, mode) {", 1)[1]
        layout = layout.split("_createAgentsAmpButton(", 1)[0]
        self.assertIn("width: 680", layout)
        self.assertIn("height: 520", layout)
        self.assertIn("[[0, 160], [164, 138], [306, 214]]", layout)
        self.assertIn("new St.ScrollView", layout)
        self.assertIn("new St.BoxLayout", layout)
        self.assertNotIn("background-image", layout)
        device_rule = AMP_CSS.split(
            ".agents-tray-limits-theme-agents-amp .agents-tray-limits-agents-amp-device {", 1
        )[1].split("}", 1)[0]
        self.assertIn("width: 680px", device_rule)
        self.assertIn("height: 520px", device_rule)

    def test_agents_amp_actions_and_decorative_transport_contract(self):
        layout = SOURCE.split("_beginAgentsAmpLayout(status, remaining, mode) {", 1)[1]
        layout = layout.split("\n    _createAgentsAmpButton(", 1)[0]
        self.assertIn("const transport =", layout)
        self.assertIn("['◀◀', '▶', '▮▮', '■', '▶▶', '▲', 'SHUF', 'REP']", layout)
        self.assertIn("reactive: false", layout)
        self.assertIn("can_focus: false", SOURCE.split("_addAgentsAmpDecoration", 1)[1])
        for key in (
            "agentsAmp.refresh", "agentsAmp.profile", "agentsAmp.settings", "agentsAmp.close"
        ):
            self.assertIn(key, layout)
        for asset_key in ("refresh", "profile", "settings", "close"):
            self.assertIn(f"'{asset_key}'", layout)
            self.assertIn(f"agents-tray-limits-agents-amp-button-{asset_key}", AMP_CSS)
        self.assertIn("providerUrl(activeProvider)", layout)
        self.assertIn("this.openPreferences()", layout)
        self.assertIn("this._indicator.menu.close()", layout)

    def test_agents_amp_loading_error_normal_and_animation_lifecycle(self):
        loading = SOURCE.split("_buildLoadingMenu() {", 1)[1].split("_buildErrorMenu() {", 1)[0]
        error = SOURCE.split("_buildErrorMenu() {", 1)[1].split("_buildDataMenu() {", 1)[0]
        data = SOURCE.split("_buildAgentsAmpDataMenu() {", 1)[1].split(
            "_addAgentsAmpTitle", 1
        )[0]
        self.assertIn("_beginAgentsAmpLayout(null, null, 'loading')", loading)
        self.assertIn("_beginAgentsAmpLayout('dead', 0, 'error')", error)
        self.assertIn("this._populateAgentsAmpPlaylist('loading')", loading)
        self.assertIn("this._populateAgentsAmpPlaylist('error', error)", error)
        for marker in ("this._populateAgentsAmpPlaylist('normal')", "this._syncThemeAnimations()"):
            self.assertIn(marker, data)
        self.assertNotIn("this._addProfileSelector()", data)
        custom_playlist = SOURCE.split("_populateAgentsAmpPlaylist(mode, error = null) {", 1)[1]
        custom_playlist = custom_playlist.split("_createAgentsAmpButton(", 1)[0]
        self.assertIn("this._addAgentsAmpProfileRow(profile)", custom_playlist)
        self.assertIn("this._addAgentsAmpLimitRow(bucket, kind, window)", custom_playlist)
        self.assertIn("this._addAgentsAmpStatRow", custom_playlist)
        sync = SOURCE.split("_syncAgentsAmpEqualizerAnimation() {", 1)[1].split(
            "_endAgentsAmpLayout()", 1
        )[0]
        self.assertIn("this._agentsAmpMode !== 'normal'", sync)
        self.assertIn("this._agentsAmpBars?.length !== 28", sync)
        self.assertIn("menu?.isOpen", sync)
        self.assertIn("get_boolean('theme-animation')", sync)
        self.assertIn("get_boolean('enable-animations')", sync)
        self.assertIn("start(120, 28)", sync)
        self.assertGreaterEqual(SOURCE.count("this._stopAgentsAmpEqualizerAnimation()"), 4)

    def test_agents_amp_status_assets_and_css(self):
        manifest = json.loads((AMP_ROOT / "theme.json").read_text(encoding="utf-8"))
        self.assertNotIn("winamp", json.dumps(manifest).lower())
        for status in ("good", "worried", "critical", "dead"):
            self.assertEqual(manifest["art"][status], f"assets/status/{status}.png")
            self.assertEqual(png_header(AMP_ASSETS / f"{status}.png"), (128, 128, 6))
        self.assertEqual(len(list(AMP_SOURCE.glob("monitor*.xpm"))), 4)
        self.assertIn("MIT License", (AMP_SOURCE / "README.md").read_text(encoding="utf-8"))
        self.assertIn("MIT License", (AMP_SOURCE / "LICENSE").read_text(encoding="utf-8"))
        ui_root = AMP_ROOT / "assets" / "ui"
        expected_ui = {
            "chrome-shell-v2.png": (1360, 1040, 6),
            "button-refresh-idle-v1.png": (280, 62, 6),
            "button-refresh-pressed-v1.png": (280, 62, 6),
            "button-profile-idle-v1.png": (248, 62, 6),
            "button-profile-pressed-v1.png": (248, 62, 6),
            "button-settings-idle-v1.png": (420, 62, 6),
            "button-settings-pressed-v1.png": (420, 62, 6),
            "button-close-idle-v1.png": (324, 62, 6),
            "button-close-pressed-v1.png": (324, 62, 6),
        }
        for filename, expected in expected_ui.items():
            self.assertEqual(png_header(ui_root / filename), expected)
        chrome_source = (AMP_SOURCE / "chrome-shell.svg").read_text(encoding="utf-8")
        self.assertNotIn("Winamp", chrome_source)
        provenance = (AMP_SOURCE / "IMAGEGEN.md").read_text(encoding="utf-8")
        self.assertIn("Variant A", provenance)
        self.assertIn("style reference only", provenance)
        self.assertEqual(
            png_header(AMP_SOURCE / "imagegen" / "device-shell-master-v1.png"),
            (1360, 1040, 6),
        )
        for marker in (
            "agents-tray-limits-agents-amp-spectrum-cell",
            "agents-tray-limits-agents-amp-spectrum-cell.peak",
            "assets/ui/chrome-shell-v2.png",
            "assets/ui/button-refresh-idle-v1.png",
            "assets/ui/button-close-pressed-v1.png",
            "agents-tray-limits-status-worried",
            "agents-tray-limits-status-critical",
            "agents-tray-limits-status-dead",
        ):
            self.assertIn(marker, AMP_CSS)

    def test_agents_amp_segmented_equalizer_sliders_and_reset_counters(self):
        layout = SOURCE.split("_beginAgentsAmpLayout(status, remaining, mode) {", 1)[1]
        layout = layout.split("_createAgentsAmpButton(", 1)[0]
        self.assertIn("for (let index = 0; index < 28; index++)", layout)
        self.assertIn("for (let level = 1; level <= 12; level++)", layout)
        self.assertIn("this._agentsAmpBars.push({cells})", layout)
        self.assertIn("'PRE', '60', '170', '310', '600', '1K', '3K', '6K', '12K', '16K'", layout)
        self.assertIn("const counters = this._agentsAmpResetCounters", layout)
        self.assertIn("x: 584", layout)
        self.assertIn("width: 82", layout)
        frame = SOURCE.split("_applyAgentsAmpEqualizerFrame(levels, peaks) {", 1)[1]
        frame = frame.split("_stopAgentsAmpEqualizerAnimation()", 1)[0]
        self.assertIn("actors.cells.forEach", frame)
        self.assertIn("this._agentsAmpMode === 'error'", frame)
        self.assertNotIn("set_height", frame)


if __name__ == "__main__":
    unittest.main()
