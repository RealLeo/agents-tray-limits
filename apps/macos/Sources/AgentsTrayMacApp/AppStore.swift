import AgentsTrayCore
import AppKit
import Combine
import Foundation
import ServiceManagement

@MainActor
final class AppStore: ObservableObject {
    @Published var preferences: AppPreferences {
        didSet {
            PreferencesPersistence.save(preferences)
            reloadLocalizer()
            restartRefreshLoop()
        }
    }
    @Published private(set) var snapshots: [String: UsageSnapshot] = [:]
    @Published private(set) var refreshing = Set<String>()
    @Published private(set) var themes: [LoadedTheme] = []
    @Published var lastActionError: String?
    @Published private(set) var clock = Date()

    private let codexProvider = CodexProvider()
    private let claudeProvider = ClaudeProvider()
    private var refreshLoop: Task<Void, Never>?
    private var clockLoop: Task<Void, Never>?
    private(set) var localizer: Localizer

    init() {
        let initial = PreferencesPersistence.load()
        preferences = initial
        localizer = Localizer(language: initial.language, localeRoot: AppResources.locales)
        reloadThemes()
        clockLoop = Task { [weak self] in
            while !Task.isCancelled {
                try? await Task.sleep(nanoseconds: 60_000_000_000)
                guard let self else { return }
                self.clock = Date()
            }
        }
        restartRefreshLoop()
        Task { await refreshAll() }
    }

    deinit {
        refreshLoop?.cancel()
        clockLoop?.cancel()
    }

    var activeProfile: AgentProfile? { preferences.activeProfile }
    var activeSnapshot: UsageSnapshot? {
        guard let profile = activeProfile else { return nil }
        return snapshots[profile.id]
    }
    var activeStatus: LimitStatus? {
        guard let snapshot = activeSnapshot else { return nil }
        return UsageFormatting.status(forRemaining: UsageFormatting.remaining(snapshot))
    }
    var panelText: String {
        guard let profile = activeProfile else { return "—" }
        if refreshing.contains(profile.id), snapshots[profile.id] == nil { return "…" }
        guard let snapshot = snapshots[profile.id] else { return "—" }
        if !snapshot.ok { return localizer.text("profiles.error") }
        return UsageFormatting.panelText(
            snapshot,
            display: preferences.panelDisplay,
            now: clock.timeIntervalSince1970,
            localizer: localizer
        ) ?? "—"
    }
    var selectedTheme: LoadedTheme? {
        themes.first(where: { $0.id == preferences.themeID })
    }
    var panelImage: NSImage? {
        guard preferences.showIcon,
              let theme = selectedTheme,
              let status = activeStatus,
              let relative = theme.manifest.panelArt?[status] else { return nil }
        return NSImage(contentsOf: theme.root.appendingPathComponent(relative))
    }
    var launchAtLogin: Bool { SMAppService.mainApp.status == .enabled }

    func refreshAll() async {
        let profiles = preferences.profiles.profiles
        guard !profiles.isEmpty else { return }
        let binary = preferences.codexBinary.isEmpty ? nil : preferences.codexBinary
        let localizer = self.localizer
        refreshing.formUnion(profiles.map(\.id))

        for start in stride(from: 0, to: profiles.count, by: 3) {
            let chunk = Array(profiles[start..<min(start + 3, profiles.count)])
            await withTaskGroup(of: (String, UsageSnapshot).self) { group in
                for profile in chunk {
                    let codexProvider = self.codexProvider
                    let claudeProvider = self.claudeProvider
                    group.addTask {
                        let snapshot: UsageSnapshot
                        do {
                            switch profile.provider {
                            case .codex:
                                snapshot = try await codexProvider.fetch(
                                    profile: profile,
                                    explicitBinary: binary
                                )
                            case .claude:
                                snapshot = try await claudeProvider.fetch(profile: profile)
                            }
                        } catch let error as ProviderError {
                            let localized = Self.localizedError(error, using: localizer)
                            snapshot = .failure(
                                profileId: profile.id,
                                provider: profile.provider,
                                code: error.code,
                                message: localized.message,
                                details: localized.details
                            )
                        } catch {
                            snapshot = .failure(
                                profileId: profile.id,
                                provider: profile.provider,
                                code: "internal_error",
                                message: error.localizedDescription
                            )
                        }
                        return (profile.id, snapshot)
                    }
                }
                for await (id, snapshot) in group {
                    snapshots[id] = snapshot
                    refreshing.remove(id)
                }
            }
        }
    }

    func selectProfile(_ id: String) {
        guard preferences.profiles.profiles.contains(where: { $0.id == id }) else { return }
        preferences.activeProfileID = id
    }

    func addProfile(provider: Provider) {
        let base = provider.displayName
        var label = base, index = 2
        while preferences.profiles.profiles.contains(where: { $0.label.caseInsensitiveCompare(label) == .orderedSame }) {
            label = "\(base) \(index)"
            index += 1
        }
        let profile = AgentProfile(
            id: UUID().uuidString.lowercased(),
            provider: provider,
            label: label
        )
        preferences.profiles.profiles.append(profile)
        preferences.activeProfileID = profile.id
    }

    func updateProfile(_ candidate: AgentProfile) {
        guard let index = preferences.profiles.profiles.firstIndex(where: { $0.id == candidate.id }) else { return }
        do {
            let clean = try ProfileValidator.validate(
                candidate,
                among: preferences.profiles.profiles,
                editingID: candidate.id
            )
            preferences.profiles.profiles[index] = clean
            lastActionError = nil
        } catch {
            lastActionError = error.localizedDescription
        }
    }

    func removeProfile(_ profile: AgentProfile) {
        if profile.provider == .claude,
           ClaudeMonitorManager.status(profile: profile) != .notInstalled {
            do { _ = try ClaudeMonitorManager.restore(profile: profile) }
            catch {
                lastActionError = error.localizedDescription
                return
            }
        }
        preferences.profiles.profiles.removeAll { $0.id == profile.id }
        snapshots.removeValue(forKey: profile.id)
        preferences.normalize()
    }

    func toggleClaudeMonitor(_ profile: AgentProfile) {
        do {
            switch ClaudeMonitorManager.status(profile: profile) {
            case .installed:
                _ = try ClaudeMonitorManager.restore(profile: profile)
            case .notInstalled, .updateAvailable:
                guard let collector = AppResources.bundledCollector else {
                    throw ProviderError("claude_monitor_invalid", "The bundled Claude collector is unavailable.")
                }
                _ = try ClaudeMonitorManager.install(profile: profile, bundledCollector: collector)
            case .conflict:
                throw ProviderError("claude_monitor_conflict", "Claude Code statusLine changed independently. Resolve the conflict before continuing.")
            }
            lastActionError = nil
        } catch {
            lastActionError = error.localizedDescription
        }
    }

    func reloadThemes() {
        try? FileManager.default.createDirectory(
            at: AppResources.userThemes,
            withIntermediateDirectories: true,
            attributes: [.posixPermissions: 0o700]
        )
        themes = ThemeCatalog.load(builtInRoot: AppResources.themes, userRoot: AppResources.userThemes)
        if preferences.themeID != "classic" && !themes.contains(where: { $0.id == preferences.themeID }) {
            preferences.themeID = themes.first(where: { $0.id == "fallout-2" })?.id ?? "classic"
        }
    }

    func setLaunchAtLogin(_ enabled: Bool) {
        do {
            if enabled { try SMAppService.mainApp.register() }
            else { try SMAppService.mainApp.unregister() }
            objectWillChange.send()
            lastActionError = nil
        } catch {
            lastActionError = error.localizedDescription
        }
    }

    func openProvider(_ provider: Provider) {
        let value = provider == .claude ? "https://claude.ai/code" : "https://chatgpt.com/codex"
        if let url = URL(string: value) { NSWorkspace.shared.open(url) }
    }

    func openThemeFolder() {
        NSWorkspace.shared.open(AppResources.userThemes)
    }

    func showSettings() {
        NSApp.activate(ignoringOtherApps: true)
        NSApp.sendAction(Selector(("showSettingsWindow:")), to: nil, from: nil)
    }

    func quit() { NSApp.terminate(nil) }

    private func reloadLocalizer() {
        localizer = Localizer(language: preferences.language, localeRoot: AppResources.locales)
    }

    private func restartRefreshLoop() {
        refreshLoop?.cancel()
        let interval = max(60, preferences.refreshInterval)
        refreshLoop = Task { [weak self] in
            while !Task.isCancelled {
                try? await Task.sleep(nanoseconds: UInt64(interval) * 1_000_000_000)
                guard let self, !Task.isCancelled else { return }
                await self.refreshAll()
            }
        }
    }

    nonisolated private static func localizedError(
        _ error: ProviderError,
        using localizer: Localizer
    ) -> (message: String, details: String?) {
        let messageKey = "errors.\(error.code)"
        let localizedMessage = localizer.text(messageKey)
        let hintKey = "hints.\(error.code)"
        let localizedHint = localizer.text(hintKey)
        return (
            localizedMessage == messageKey ? error.message : localizedMessage,
            localizedHint == hintKey ? error.details : localizedHint
        )
    }
}
