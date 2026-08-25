import Foundation

public struct AgentProfile: Codable, Equatable, Identifiable, Sendable {
    public var id: String
    public var provider: Provider
    public var label: String
    public var configDir: String

    public init(id: String, provider: Provider, label: String, configDir: String = "") {
        self.id = id
        self.provider = provider
        self.label = label
        self.configDir = configDir
    }

    public var expandedConfigDirectory: URL {
        if configDir.isEmpty {
            return FileManager.default.homeDirectoryForCurrentUser
                .appendingPathComponent(provider == .claude ? ".claude" : ".codex", isDirectory: true)
        }
        return URL(fileURLWithPath: NSString(string: configDir).expandingTildeInPath, isDirectory: true)
    }
}

public struct ProfileDocument: Codable, Equatable, Sendable {
    public static let version = 1
    public var version: Int
    public var profiles: [AgentProfile]

    public init(version: Int = ProfileDocument.version, profiles: [AgentProfile]) {
        self.version = version
        self.profiles = profiles
    }

    public static var defaultDocument: ProfileDocument {
        ProfileDocument(profiles: [
            AgentProfile(id: "default-codex", provider: .codex, label: "Codex")
        ])
    }
}

public enum ProfileValidationError: String, Error, LocalizedError, Sendable {
    case invalid
    case duplicateLabel = "duplicate_label"
    case duplicateLocation = "duplicate_location"

    public var errorDescription: String? { rawValue }
}

public enum ProfileValidator {
    private static let idPattern = try! NSRegularExpression(pattern: "^[A-Za-z0-9._-]{1,128}$")

    public static func validate(
        _ candidate: AgentProfile,
        among profiles: [AgentProfile],
        editingID: String? = nil
    ) throws -> AgentProfile {
        let id = candidate.id.trimmingCharacters(in: .whitespacesAndNewlines)
        let label = candidate.label.trimmingCharacters(in: .whitespacesAndNewlines)
        let configDir = candidate.configDir.trimmingCharacters(in: .whitespacesAndNewlines)
        let idRange = NSRange(id.startIndex..<id.endIndex, in: id)
        let hasControls = { (value: String) in
            value.unicodeScalars.contains { CharacterSet.controlCharacters.contains($0) }
        }
        guard idPattern.firstMatch(in: id, range: idRange) != nil,
              !label.isEmpty, !hasControls(label), !hasControls(configDir),
              configDir.isEmpty || configDir.hasPrefix("/") || configDir.hasPrefix("~/") else {
            throw ProfileValidationError.invalid
        }

        let others = profiles.filter { $0.id != editingID }
        guard !others.contains(where: { $0.label.caseInsensitiveCompare(label) == .orderedSame }) else {
            throw ProfileValidationError.duplicateLabel
        }
        guard !others.contains(where: { $0.provider == candidate.provider && $0.configDir == configDir }) else {
            throw ProfileValidationError.duplicateLocation
        }
        return AgentProfile(id: id, provider: candidate.provider, label: label, configDir: configDir)
    }

    public static func normalizedDocument(from data: Data?, createDefault: Bool = true) -> ProfileDocument {
        guard let data,
              let decoded = try? JSONDecoder().decode(ProfileDocument.self, from: data),
              decoded.version == ProfileDocument.version else {
            return createDefault ? .defaultDocument : ProfileDocument(profiles: [])
        }

        var accepted: [AgentProfile] = []
        for profile in decoded.profiles {
            guard let clean = try? validate(profile, among: accepted) else { continue }
            if accepted.contains(where: { $0.id == clean.id }) { continue }
            accepted.append(clean)
        }
        if accepted.isEmpty && createDefault { return .defaultDocument }
        return ProfileDocument(profiles: accepted)
    }
}

public enum LoginCommand {
    private static func shellQuote(_ value: String) -> String {
        "'" + value.replacingOccurrences(of: "'", with: "'\"'\"'") + "'"
    }

    private static func directory(_ value: String) -> String {
        guard !value.isEmpty else { return "" }
        if value.hasPrefix("~/") {
            return "\"$HOME\"/" + shellQuote(String(value.dropFirst(2)))
        }
        return shellQuote(value)
    }

    public static func forProfile(_ profile: AgentProfile, codexBinary: String = "codex") -> String {
        let config = directory(profile.configDir)
        if profile.provider == .claude {
            return config.isEmpty ? "claude" : "CLAUDE_CONFIG_DIR=\(config) claude"
        }
        let binary = codexBinary == "codex" ? codexBinary : shellQuote(codexBinary)
        if config.isEmpty { return "\(binary) login" }
        return "CODEX_HOME=\(config) \(binary) -c 'cli_auth_credentials_store=\"file\"' login"
    }
}
