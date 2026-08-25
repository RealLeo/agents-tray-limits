import AgentsTrayCore
import Foundation

struct AppPreferences: Codable, Equatable {
    var profiles: ProfileDocument = .defaultDocument
    var activeProfileID = "default-codex"
    var refreshInterval = 300
    var panelDisplay: PanelDisplay = .remaining
    var codexBinary = ""
    var showIcon = true
    var showTokens = true
    var showAllBuckets = true
    var themeID = "fallout-2"
    var themeAnimation = true
    var language: SupportedLanguage = .system

    var activeProfile: AgentProfile? {
        profiles.profiles.first(where: { $0.id == activeProfileID }) ?? profiles.profiles.first
    }

    mutating func normalize() {
        let encoded = try? JSONEncoder().encode(profiles)
        profiles = ProfileValidator.normalizedDocument(from: encoded)
        if !profiles.profiles.contains(where: { $0.id == activeProfileID }) {
            activeProfileID = profiles.profiles.first?.id ?? ""
        }
        refreshInterval = [60, 300, 900, 1800, 3600].contains(refreshInterval)
            ? refreshInterval : 300
        if themeID.isEmpty { themeID = "fallout-2" }
    }
}

enum PreferencesPersistence {
    private static let key = "preferences-v1"

    static func load() -> AppPreferences {
        guard let data = UserDefaults.standard.data(forKey: key),
              var value = try? JSONDecoder().decode(AppPreferences.self, from: data) else {
            return AppPreferences()
        }
        value.normalize()
        return value
    }

    static func save(_ value: AppPreferences) {
        guard let data = try? JSONEncoder().encode(value) else { return }
        UserDefaults.standard.set(data, forKey: key)
    }
}

enum AppResources {
    static var root: URL? {
        if let bundle = Bundle.main.resourceURL,
           FileManager.default.fileExists(atPath: bundle.appendingPathComponent("locales").path) {
            return bundle
        }
        var candidate = URL(fileURLWithPath: FileManager.default.currentDirectoryPath)
        for _ in 0..<5 {
            let shared = candidate.appendingPathComponent("shared")
            if FileManager.default.fileExists(atPath: shared.appendingPathComponent("locales").path) {
                return shared
            }
            candidate.deleteLastPathComponent()
        }
        return nil
    }

    static var locales: URL? { root?.appendingPathComponent("locales", isDirectory: true) }
    static var themes: URL? { root?.appendingPathComponent("themes", isDirectory: true) }

    static var userThemes: URL {
        let support = FileManager.default.urls(for: .applicationSupportDirectory, in: .userDomainMask).first ??
            FileManager.default.homeDirectoryForCurrentUser.appendingPathComponent("Library/Application Support")
        return support.appendingPathComponent("Agents Tray Limits/themes", isDirectory: true)
    }

    static var bundledCollector: URL? {
        let bundled = Bundle.main.bundleURL.appendingPathComponent("Contents/Helpers/AgentsTrayCollector")
        if FileManager.default.isExecutableFile(atPath: bundled.path) { return bundled }
        if let explicit = ProcessInfo.processInfo.environment["AGENTS_TRAY_COLLECTOR_PATH"],
           FileManager.default.isExecutableFile(atPath: explicit) {
            return URL(fileURLWithPath: explicit)
        }
        return nil
    }
}
