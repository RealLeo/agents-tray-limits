import AgentsTrayCore
import AppKit
import SwiftUI

struct MenuContentView: View {
    @ObservedObject var store: AppStore

    var body: some View {
        ThemeContainerView(store: store)
            .overlay(alignment: .top) {
                if let error = store.lastActionError {
                    Text(error)
                        .font(.caption)
                        .foregroundStyle(.white)
                        .padding(7)
                        .background(.red.opacity(0.92), in: RoundedRectangle(cornerRadius: 7))
                        .padding(8)
                        .onTapGesture { store.lastActionError = nil }
                }
            }
    }
}

struct ClassicMenuView: View {
    @ObservedObject var store: AppStore
    let theme: LoadedTheme?

    var body: some View {
        VStack(alignment: .leading, spacing: 12) {
            ProfilePicker(store: store)
            if let profile = store.activeProfile {
                HStack(alignment: .top, spacing: 14) {
                    ThemeArtView(
                        theme: theme,
                        status: store.activeStatus ?? .worried,
                        animate: store.preferences.themeAnimation
                    )
                    .frame(width: 116, height: 116)
                    StatusDetailView(store: store, profile: profile)
                }
            } else {
                VStack(spacing: 8) {
                    Image(systemName: "person.crop.circle.badge.plus").font(.largeTitle)
                    Text(store.localizer.text("prefs.profiles.add")).font(.headline)
                }
                .frame(maxWidth: .infinity, minHeight: 120)
            }
            Divider()
            MenuActions(store: store)
        }
        .padding(16)
        .frame(width: 430)
    }
}

struct ProfilePicker: View {
    @ObservedObject var store: AppStore

    var body: some View {
        Picker(store.localizer.text("prefs.profiles.active"), selection: Binding(
            get: { store.preferences.activeProfileID },
            set: { store.selectProfile($0) }
        )) {
            ForEach(store.preferences.profiles.profiles) { profile in
                Text("\(profile.label) · \(profile.provider.displayName)").tag(profile.id)
            }
        }
        .labelsHidden()
        .accessibilityLabel(store.localizer.text("prefs.profiles.active"))
    }
}

struct StatusDetailView: View {
    @ObservedObject var store: AppStore
    let profile: AgentProfile

    var body: some View {
        VStack(alignment: .leading, spacing: 8) {
            HStack {
                Text(profile.label).font(.headline)
                Spacer()
                if store.refreshing.contains(profile.id) { ProgressView().controlSize(.small) }
            }
            if let snapshot = store.snapshots[profile.id] {
                if snapshot.ok {
                    LimitDetailsView(
                        snapshot: snapshot,
                        showAll: store.preferences.showAllBuckets,
                        showTokens: store.preferences.showTokens,
                        localizer: store.localizer
                    )
                } else {
                    Label(snapshot.message ?? "Unknown error", systemImage: "exclamationmark.triangle")
                        .foregroundStyle(.red)
                    if let details = snapshot.details, !details.isEmpty {
                        Text(details).font(.caption).foregroundStyle(.secondary).textSelection(.enabled)
                    }
                }
            } else {
                Text(store.localizer.text("profiles.pending")).foregroundStyle(.secondary)
            }
        }
        .frame(maxWidth: .infinity, alignment: .leading)
    }
}

struct LimitDetailsView: View {
    let snapshot: UsageSnapshot
    let showAll: Bool
    let showTokens: Bool
    let localizer: Localizer

    private var buckets: [(String, RateLimitBucket)] {
        if showAll, let byID = snapshot.rateLimits?.rateLimitsByLimitId, !byID.isEmpty {
            return byID.sorted { $0.key.localizedCaseInsensitiveCompare($1.key) == .orderedAscending }
        }
        if let bucket = snapshot.primaryBucket { return [(bucket.limitId ?? snapshot.provider.rawValue, bucket)] }
        return []
    }

    var body: some View {
        VStack(alignment: .leading, spacing: 9) {
            ForEach(Array(buckets.enumerated()), id: \.offset) { _, entry in
                let (id, bucket) = entry
                VStack(alignment: .leading, spacing: 5) {
                    Text(bucket.limitName ?? id).font(.subheadline.weight(.semibold))
                    if let primary = bucket.primary {
                        LimitWindowRow(title: localizer.text("menu.primary"), window: primary, localizer: localizer)
                    }
                    if let secondary = bucket.secondary {
                        LimitWindowRow(title: localizer.text("menu.secondary"), window: secondary, localizer: localizer)
                    }
                }
            }
            if showTokens, let summary = snapshot.usage?.objectValue?["summary"]?.objectValue {
                Divider()
                Text(localizer.text("menu.activity")).font(.subheadline.weight(.semibold))
                ForEach(summary.keys.sorted(), id: \.self) { key in
                    HStack {
                        Text(humanize(key)).foregroundStyle(.secondary)
                        Spacer()
                        Text(format(summary[key])).monospacedDigit()
                    }
                    .font(.caption)
                }
            }
        }
    }

    private func humanize(_ value: String) -> String {
        value.replacingOccurrences(of: "([a-z])([A-Z])", with: "$1 $2", options: .regularExpression)
            .capitalized
    }

    private func format(_ value: JSONValue?) -> String {
        switch value {
        case .number(let number): return number.formatted(.number.precision(.fractionLength(0)))
        case .string(let string): return string
        default: return "—"
        }
    }
}

struct LimitWindowRow: View {
    let title: String
    let window: LimitWindow
    let localizer: Localizer

    var body: some View {
        let remaining = max(0, min(100, 100 - (window.usedPercent ?? 0)))
        VStack(alignment: .leading, spacing: 3) {
            HStack {
                Text(title).foregroundStyle(.secondary)
                Spacer()
                Text("\(Int(remaining.rounded()))%")
                    .fontWeight(.semibold)
                    .monospacedDigit()
            }
            ProgressView(value: remaining, total: 100)
            Text(localizer.text("time.resetIn", [
                "relative": UsageFormatting.resetText(timestamp: window.resetsAt, localizer: localizer),
            ]))
                .font(.caption2)
                .foregroundStyle(.secondary)
        }
    }
}

struct MenuActions: View {
    @ObservedObject var store: AppStore

    var body: some View {
        HStack {
            Button {
                Task { await store.refreshAll() }
            } label: {
                Label(store.localizer.text("actions.refresh"), systemImage: "arrow.clockwise")
            }
            .disabled(!store.refreshing.isEmpty)
            if let provider = store.activeProfile?.provider {
                Button { store.openProvider(provider) } label: {
                    Label(provider.displayName, systemImage: "arrow.up.right.square")
                }
            }
            Spacer()
            Button { store.showSettings() } label: { Image(systemName: "gear") }
                .help(store.localizer.text("actions.settings"))
            Button { store.quit() } label: { Image(systemName: "power") }
                .help("Quit")
        }
        .buttonStyle(.borderless)
    }
}

struct SettingsView: View {
    @ObservedObject var store: AppStore

    var body: some View {
        TabView {
            GeneralSettingsView(store: store)
                .tabItem { Label(store.localizer.text("prefs.connection.title"), systemImage: "gearshape") }
            ProfilesSettingsView(store: store)
                .tabItem { Label(store.localizer.text("profiles.section"), systemImage: "person.2") }
            ThemeSettingsView(store: store)
                .tabItem { Label(store.localizer.text("prefs.theme.title"), systemImage: "paintpalette") }
            LegalSettingsView()
                .tabItem { Label("Legal", systemImage: "doc.text") }
        }
        .frame(width: 620, height: 470)
        .padding()
    }
}

struct GeneralSettingsView: View {
    @ObservedObject var store: AppStore
    private let intervals = [60, 300, 900, 1800, 3600]

    var body: some View {
        Form {
            Picker(store.localizer.text("prefs.language.title"), selection: $store.preferences.language) {
                ForEach(SupportedLanguage.allCases, id: \.self) { language in
                    Text(languageName(language)).tag(language)
                }
            }
            Picker(store.localizer.text("prefs.panelDisplay.title"), selection: $store.preferences.panelDisplay) {
                Text(store.localizer.text("prefs.panelDisplay.remaining")).tag(PanelDisplay.remaining)
                Text(store.localizer.text("prefs.panelDisplay.used")).tag(PanelDisplay.used)
            }
            Picker(store.localizer.text("prefs.refresh.title"), selection: $store.preferences.refreshInterval) {
                ForEach(intervals, id: \.self) { Text(duration($0)).tag($0) }
            }
            TextField(store.localizer.text("prefs.codexPath.title"), text: $store.preferences.codexBinary)
                .textFieldStyle(.roundedBorder)
            Toggle(store.localizer.text("prefs.showIcon.title"), isOn: $store.preferences.showIcon)
            Toggle(store.localizer.text("prefs.allBuckets.title"), isOn: $store.preferences.showAllBuckets)
            Toggle(store.localizer.text("prefs.tokens.title"), isOn: $store.preferences.showTokens)
            Toggle("Launch at login", isOn: Binding(
                get: { store.launchAtLogin },
                set: { store.setLaunchAtLogin($0) }
            ))
            if let error = store.lastActionError { Text(error).foregroundStyle(.red).font(.caption) }
        }
        .formStyle(.grouped)
    }

    private func duration(_ seconds: Int) -> String {
        let key: String
        switch seconds {
        case 60: key = "prefs.refresh.oneMinute"
        case 300: key = "prefs.refresh.fiveMinutes"
        case 900: key = "prefs.refresh.fifteenMinutes"
        case 1800: key = "prefs.refresh.thirtyMinutes"
        case 3600: key = "prefs.refresh.oneHour"
        default: return "\(seconds)s"
        }
        return store.localizer.text(key)
    }

    private func languageName(_ language: SupportedLanguage) -> String {
        store.localizer.text("language.\(language.rawValue)")
    }
}

struct ProfilesSettingsView: View {
    @ObservedObject var store: AppStore

    var body: some View {
        VStack(spacing: 10) {
            HStack {
                Text(store.localizer.text("prefs.profiles.title")).font(.title2.weight(.semibold))
                Spacer()
                Menu {
                    Button("Codex") { store.addProfile(provider: .codex) }
                    Button("Claude Code") { store.addProfile(provider: .claude) }
                } label: { Label(store.localizer.text("prefs.profiles.addButton"), systemImage: "plus") }
            }
            ScrollView {
                LazyVStack(spacing: 10) {
                    ForEach(store.preferences.profiles.profiles) { profile in
                        ProfileEditor(store: store, profile: profile)
                    }
                }
            }
            if let error = store.lastActionError { Text(error).foregroundStyle(.red).font(.caption) }
        }
        .padding()
    }
}

struct ProfileEditor: View {
    @ObservedObject var store: AppStore
    let original: AgentProfile
    @State private var label: String
    @State private var configDir: String

    init(store: AppStore, profile: AgentProfile) {
        self.store = store
        original = profile
        _label = State(initialValue: profile.label)
        _configDir = State(initialValue: profile.configDir)
    }

    var body: some View {
        GroupBox {
            Grid(alignment: .leading, horizontalSpacing: 10, verticalSpacing: 8) {
                GridRow {
                    Text(original.provider.displayName).fontWeight(.semibold)
                    TextField(store.localizer.text("prefs.profiles.label"), text: $label)
                    Button(store.localizer.text("prefs.profiles.save")) {
                        store.updateProfile(AgentProfile(
                            id: original.id,
                            provider: original.provider,
                            label: label,
                            configDir: configDir
                        ))
                    }
                    Button(role: .destructive) { store.removeProfile(original) } label: {
                        Image(systemName: "trash")
                    }
                    .help(store.localizer.text("prefs.profiles.remove"))
                }
                GridRow {
                    Text(store.localizer.text("prefs.profiles.directory")).foregroundStyle(.secondary)
                    TextField(original.provider == .claude ? "~/.claude" : "~/.codex", text: $configDir)
                        .gridCellColumns(2)
                    if original.provider == .claude {
                        Button(monitorLabel) { store.toggleClaudeMonitor(original) }
                    }
                }
                GridRow {
                    Text(store.localizer.text("prefs.profiles.loginCommand")).foregroundStyle(.secondary)
                    Text(LoginCommand.forProfile(original, codexBinary: store.preferences.codexBinary.isEmpty ? "codex" : store.preferences.codexBinary))
                        .font(.caption.monospaced())
                        .textSelection(.enabled)
                        .gridCellColumns(3)
                }
            }
        }
    }

    private var monitorLabel: String {
        switch ClaudeMonitorManager.status(profile: original) {
        case .notInstalled: return store.localizer.text("prefs.profiles.enableMonitor")
        case .installed: return store.localizer.text("prefs.profiles.disableMonitor")
        case .updateAvailable: return store.localizer.text("prefs.reloadThemes.button")
        case .conflict: return store.localizer.text("errors.claude_monitor_conflict")
        }
    }
}

struct ThemeSettingsView: View {
    @ObservedObject var store: AppStore

    var body: some View {
        Form {
            Picker(store.localizer.text("prefs.theme.title"), selection: $store.preferences.themeID) {
                Text(store.localizer.text("themes.classic.name")).tag("classic")
                ForEach(store.themes) { theme in
                    Text(themeName(theme) + (theme.isUserTheme ? " · \(store.localizer.text("themes.userSuffix"))" : "")).tag(theme.id)
                }
            }
            Toggle(store.localizer.text("prefs.themeAnimation.title"), isOn: $store.preferences.themeAnimation)
            HStack {
                Button(store.localizer.text("prefs.reloadThemes.button")) { store.reloadThemes() }
                Button(store.localizer.text("prefs.userThemes.openFolder")) { store.openThemeFolder() }
            }
            Text("User themes use Theme Manifest v2. GNOME CSS is never executed by the macOS application.")
                .font(.caption)
                .foregroundStyle(.secondary)
        }
        .formStyle(.grouped)
    }

    private func themeName(_ theme: LoadedTheme) -> String {
        switch theme.id {
        case "fallout-2": return store.localizer.text("themes.fallout2.name")
        default: return theme.manifest.name
        }
    }
}

struct LegalSettingsView: View {
    var body: some View {
        ScrollView {
            VStack(alignment: .leading, spacing: 12) {
                Text("Agents Tray Limits").font(.title2.bold())
                Text("Unofficial community build. Not affiliated with OpenAI, Anthropic, Bethesda Softworks, ZeniMax Media, Apple, or GNOME.")
                Text("Project code is available under the MIT License. Fallout, Pip-Boy, and Vault Boy-inspired raster artwork is excluded from the MIT License. Redistribution may require additional permissions.")
                Text("The app reads provider limits through locally installed official CLIs. It does not read credential files and sends no telemetry.")
            }
            .frame(maxWidth: .infinity, alignment: .leading)
        }
        .padding()
    }
}
