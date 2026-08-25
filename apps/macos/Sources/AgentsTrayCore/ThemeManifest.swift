@preconcurrency import Foundation

public struct ThemeStatusPaths: Codable, Equatable, Sendable {
    public var good: String
    public var worried: String
    public var critical: String
    public var dead: String

    public subscript(status: LimitStatus) -> String {
        switch status {
        case .good: return good
        case .worried: return worried
        case .critical: return critical
        case .dead: return dead
        }
    }

    public var all: [String] { [good, worried, critical, dead] }
}

public struct ThemeAnimationStep: Codable, Equatable, Sendable {
    public var x: Double?
    public var y: Double?
    public var opacity: Double?
    public var scale: Double?
}

public struct ThemeAnimation: Codable, Equatable, Sendable {
    public var intervalMs: Int
    public var steps: [ThemeAnimationStep]
}

public struct ThemeFrameLists: Codable, Equatable, Sendable {
    public var good: [String]
    public var worried: [String]
    public var critical: [String]
    public var dead: [String]

    public subscript(status: LimitStatus) -> [String] {
        switch status {
        case .good: return good
        case .worried: return worried
        case .critical: return critical
        case .dead: return dead
        }
    }

    public var all: [String] { good + worried + critical + dead }
}

public struct ThemeFrameAnimation: Codable, Equatable, Sendable {
    public var intervalMs: Int
    public var intervalMsByStatus: [String: Int]?
    public var playback: String
    public var frames: ThemeFrameLists

    public func interval(for status: LimitStatus) -> Int {
        intervalMsByStatus?[status.rawValue] ?? intervalMs
    }
}

public enum MacThemeLayout: String, Codable, CaseIterable, Sendable {
    case classic
    case pipboy2000 = "pipboy-2000"
}

public struct MacThemeTypography: Codable, Equatable, Sendable {
    public var family: String?
    public var scale: Double?
}

public struct MacThemeDefinition: Codable, Equatable, Sendable {
    public var layout: MacThemeLayout
    public var palette: [String: String]?
    public var typography: MacThemeTypography?
}

public struct GnomeThemeDefinition: Codable, Equatable, Sendable {
    public var stylesheet: String?
    public var layout: String?
}

public struct ThemePlatforms: Codable, Equatable, Sendable {
    public var gnome: GnomeThemeDefinition?
    public var macos: MacThemeDefinition?
}

public struct ThemeManifest: Codable, Equatable, Identifiable, Sendable {
    public var version: Int
    public var id: String
    public var name: String
    public var description: String?
    public var stylesheet: String?
    public var layout: String?
    public var art: ThemeStatusPaths
    public var panelArt: ThemeStatusPaths?
    public var animation: ThemeAnimation?
    public var frameAnimation: ThemeFrameAnimation?
    public var platforms: ThemePlatforms?

    public var macDefinition: MacThemeDefinition {
        if version == 2, let macos = platforms?.macos { return macos }
        return MacThemeDefinition(
            layout: .classic,
            palette: nil,
            typography: MacThemeTypography(family: "system", scale: 1)
        )
    }
}

public struct LoadedTheme: Identifiable, Equatable, Sendable {
    public var id: String { manifest.id }
    public var manifest: ThemeManifest
    public var root: URL
    public var isUserTheme: Bool
}

public enum ThemeValidationError: Error, LocalizedError, Sendable {
    case invalid(String)
    public var errorDescription: String? {
        if case .invalid(let message) = self { return message }
        return nil
    }
}

public enum ThemeValidator {
    private static let idPattern = try! NSRegularExpression(pattern: "^[a-z0-9_-]+$")
    private static let colorPattern = try! NSRegularExpression(pattern: "^#[0-9A-Fa-f]{6}([0-9A-Fa-f]{2})?$")
    private static let paletteKeys = Set([
        "background", "surface", "primary", "secondary",
        "text", "muted", "warning", "critical",
    ])

    public static func safeRelativePath(_ value: String) -> Bool {
        guard !value.isEmpty, !value.hasPrefix("/"), !value.hasPrefix("~"), !value.contains("\\") else {
            return false
        }
        return value.split(separator: "/", omittingEmptySubsequences: false).allSatisfy {
            !$0.isEmpty && $0 != "." && $0 != ".."
        }
    }

    public static func validate(_ manifest: ThemeManifest, at root: URL) throws {
        let idRange = NSRange(manifest.id.startIndex..<manifest.id.endIndex, in: manifest.id)
        guard [1, 2].contains(manifest.version),
              idPattern.firstMatch(in: manifest.id, range: idRange) != nil,
              manifest.id != "classic", root.lastPathComponent == manifest.id,
              !manifest.name.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty else {
            throw ThemeValidationError.invalid("invalid theme identity")
        }
        guard !(manifest.animation != nil && manifest.frameAnimation != nil) else {
            throw ThemeValidationError.invalid("animation forms are mutually exclusive")
        }
        if let animation = manifest.animation {
            guard (50...5000).contains(animation.intervalMs), (1...10).contains(animation.steps.count) else {
                throw ThemeValidationError.invalid("animation is outside safe bounds")
            }
        }
        if let animation = manifest.frameAnimation {
            guard (20...5000).contains(animation.intervalMs), animation.playback == "once" else {
                throw ThemeValidationError.invalid("invalid frame animation")
            }
            for frames in LimitStatus.allCases.map({ animation.frames[$0] }) {
                guard (1...32).contains(frames.count) else {
                    throw ThemeValidationError.invalid("frame count is outside 1...32")
                }
            }
        }
        if let macos = manifest.platforms?.macos {
            for (key, color) in macos.palette ?? [:] {
                let range = NSRange(color.startIndex..<color.endIndex, in: color)
                guard paletteKeys.contains(key), colorPattern.firstMatch(in: color, range: range) != nil else {
                    throw ThemeValidationError.invalid("invalid macOS palette token")
                }
            }
            let scale = macos.typography?.scale ?? 1
            guard (0.75...1.5).contains(scale),
                  [nil, "system", "monospaced"].contains(macos.typography?.family) else {
                throw ThemeValidationError.invalid("invalid macOS typography")
            }
        }

        var paths = manifest.art.all + (manifest.panelArt?.all ?? [])
        paths += manifest.frameAnimation?.frames.all ?? []
        for relative in paths {
            guard safeRelativePath(relative) else {
                throw ThemeValidationError.invalid("unsafe theme path: \(relative)")
            }
            let file = root.appendingPathComponent(relative)
            let values = try file.resourceValues(forKeys: [.isRegularFileKey, .isSymbolicLinkKey])
            guard values.isRegularFile == true, values.isSymbolicLink != true else {
                throw ThemeValidationError.invalid("theme asset must be a regular non-symlink file")
            }
        }
    }
}

public enum ThemeCatalog {
    public static func load(builtInRoot: URL?, userRoot: URL?) -> [LoadedTheme] {
        var themes: [String: LoadedTheme] = [:]
        for (root, isUser) in [(builtInRoot, false), (userRoot, true)] {
            guard let root,
                  let directories = try? FileManager.default.contentsOfDirectory(
                    at: root,
                    includingPropertiesForKeys: [.isDirectoryKey, .isSymbolicLinkKey],
                    options: [.skipsHiddenFiles]
                  ) else { continue }
            for directory in directories {
                let values = try? directory.resourceValues(forKeys: [.isDirectoryKey, .isSymbolicLinkKey])
                guard values?.isDirectory == true, values?.isSymbolicLink != true,
                      let data = try? Data(contentsOf: directory.appendingPathComponent("theme.json")),
                      let manifest = try? JSONDecoder().decode(ThemeManifest.self, from: data),
                      (try? ThemeValidator.validate(manifest, at: directory)) != nil else { continue }
                themes[manifest.id] = LoadedTheme(manifest: manifest, root: directory, isUserTheme: isUser)
            }
        }
        return themes.values.sorted { $0.manifest.name.localizedCaseInsensitiveCompare($1.manifest.name) == .orderedAscending }
    }
}
