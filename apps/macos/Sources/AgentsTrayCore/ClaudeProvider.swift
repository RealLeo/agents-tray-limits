@preconcurrency import Foundation
#if canImport(Darwin)
import Darwin
#else
import Glibc
#endif

public struct ClaudeCollectorConfiguration: Codable, Equatable, Sendable {
    public var version: Int
    public var profileId: String
    public var cachePath: String
    public var originalCommand: String

    public init(version: Int = 1, profileId: String, cachePath: String, originalCommand: String) {
        self.version = version
        self.profileId = profileId
        self.cachePath = cachePath
        self.originalCommand = originalCommand
    }
}

private struct ClaudeMonitorBackup: Codable, Equatable {
    var version: Int
    var profileId: String
    var originalPresent: Bool
    var originalStatusLine: JSONValue?
    var installedStatusLine: JSONValue
    var collectorVersion: Int
}

public enum ClaudeMonitorState: String, Sendable {
    case notInstalled = "not_installed"
    case installed
    case updateAvailable = "update_available"
    case conflict
}

public struct ClaudeMonitorPaths: Sendable {
    public let settings: URL
    public let managedDirectory: URL
    public let collector: URL
    public let collectorConfiguration: URL
    public let backup: URL
    public let lock: URL
    public let cache: URL

    public init(profile: AgentProfile) {
        let root = profile.expandedConfigDirectory
        managedDirectory = root.appendingPathComponent("agents-tray-limits", isDirectory: true)
        settings = root.appendingPathComponent("settings.json")
        collector = managedDirectory.appendingPathComponent("statusline")
        collectorConfiguration = managedDirectory.appendingPathComponent("collector-config.json")
        backup = managedDirectory.appendingPathComponent("statusline-backup.json")
        lock = managedDirectory.appendingPathComponent("statusline.lock")
        cache = ClaudeProvider.cacheURL(profileID: profile.id)
    }
}

private final class FileLock {
    private let descriptor: Int32

    init(url: URL) throws {
        try FileManager.default.createDirectory(
            at: url.deletingLastPathComponent(),
            withIntermediateDirectories: true,
            attributes: [.posixPermissions: 0o700]
        )
        descriptor = url.path.withCString { open($0, O_CREAT | O_RDWR, mode_t(0o600)) }
        guard descriptor >= 0, flock(descriptor, LOCK_EX) == 0 else {
            if descriptor >= 0 { close(descriptor) }
            throw ProviderError("claude_monitor_invalid", "Could not lock Claude monitor files.")
        }
        _ = fchmod(descriptor, mode_t(0o600))
    }

    deinit {
        _ = flock(descriptor, LOCK_UN)
        close(descriptor)
    }
}

public enum ClaudeMonitorManager {
    public static let collectorVersion = 1

    public static func status(profile: AgentProfile) -> ClaudeMonitorState {
        let paths = ClaudeMonitorPaths(profile: profile)
        guard let settings = try? readObject(paths.settings) else {
            return FileManager.default.fileExists(atPath: paths.backup.path) ? .conflict : .notInstalled
        }
        guard let backup = try? decode(ClaudeMonitorBackup.self, from: paths.backup) else {
            return FileManager.default.fileExists(atPath: paths.collector.path) ? .conflict : .notInstalled
        }
        guard backup.profileId == profile.id,
              settings["statusLine"] == backup.installedStatusLine else { return .conflict }
        guard FileManager.default.isExecutableFile(atPath: paths.collector.path),
              FileManager.default.fileExists(atPath: paths.collectorConfiguration.path) else { return .conflict }
        return backup.collectorVersion == collectorVersion ? .installed : .updateAvailable
    }

    public static func install(profile: AgentProfile, bundledCollector: URL) throws -> ClaudeMonitorState {
        guard profile.provider == .claude else {
            throw ProviderError("invalid_profile", "The selected profile is not a Claude profile.")
        }
        let paths = ClaudeMonitorPaths(profile: profile)
        try FileManager.default.createDirectory(
            at: paths.managedDirectory,
            withIntermediateDirectories: true,
            attributes: [.posixPermissions: 0o700]
        )
        _ = try FileLock(url: paths.lock)
        var settings = try readObject(paths.settings)
        let current = settings["statusLine"]
        let originalPresent: Bool
        let original: JSONValue?
        var backup: ClaudeMonitorBackup

        if FileManager.default.fileExists(atPath: paths.backup.path) {
            backup = try decode(ClaudeMonitorBackup.self, from: paths.backup)
            guard backup.profileId == profile.id, current == backup.installedStatusLine else {
                throw ProviderError("claude_monitor_conflict", "Claude Code statusLine changed after monitoring was installed.")
            }
            originalPresent = backup.originalPresent
            original = backup.originalStatusLine
        } else {
            guard !FileManager.default.fileExists(atPath: paths.collector.path) else {
                throw ProviderError("claude_monitor_conflict", "Claude monitor files exist without a restorable backup.")
            }
            originalPresent = current != nil
            original = current
            let installed = installedStatusLine(paths.collector, original: original)
            backup = ClaudeMonitorBackup(
                version: 1,
                profileId: profile.id,
                originalPresent: originalPresent,
                originalStatusLine: original,
                installedStatusLine: installed,
                collectorVersion: collectorVersion
            )
        }

        guard FileManager.default.isExecutableFile(atPath: bundledCollector.path) else {
            throw ProviderError("claude_monitor_invalid", "The bundled Claude collector is missing or not executable.")
        }
        let originalCommand = original?.objectValue?["command"]?.stringValue ?? ""
        let configuration = ClaudeCollectorConfiguration(
            profileId: profile.id,
            cachePath: paths.cache.path,
            originalCommand: originalCommand
        )

        try atomicCopy(from: bundledCollector, to: paths.collector, mode: 0o700)
        try atomicWrite(try JSONEncoder.pretty.encode(configuration), to: paths.collectorConfiguration, mode: 0o600)
        backup.collectorVersion = collectorVersion
        backup.installedStatusLine = installedStatusLine(paths.collector, original: original)
        try atomicWrite(try JSONEncoder.pretty.encode(backup), to: paths.backup, mode: 0o600)
        settings["statusLine"] = backup.installedStatusLine
        try atomicWrite(try JSONEncoder.pretty.encode(settings), to: paths.settings, mode: 0o600)
        return .installed
    }

    public static func restore(profile: AgentProfile) throws -> ClaudeMonitorState {
        let paths = ClaudeMonitorPaths(profile: profile)
        guard FileManager.default.fileExists(atPath: paths.backup.path) else {
            if FileManager.default.fileExists(atPath: paths.collector.path) {
                throw ProviderError("claude_monitor_conflict", "Claude monitor files exist without a restorable backup.")
            }
            return .notInstalled
        }
        _ = try FileLock(url: paths.lock)
        let backup = try decode(ClaudeMonitorBackup.self, from: paths.backup)
        var settings = try readObject(paths.settings)
        guard backup.profileId == profile.id, settings["statusLine"] == backup.installedStatusLine else {
            throw ProviderError("claude_monitor_conflict", "Claude Code statusLine changed independently; it was not overwritten.")
        }
        if backup.originalPresent, let original = backup.originalStatusLine {
            settings["statusLine"] = original
        } else {
            settings.removeValue(forKey: "statusLine")
        }
        try atomicWrite(try JSONEncoder.pretty.encode(settings), to: paths.settings, mode: 0o600)
        for url in [paths.backup, paths.collector, paths.collectorConfiguration, paths.cache] {
            try? FileManager.default.removeItem(at: url)
        }
        try? FileManager.default.removeItem(at: paths.lock)
        try? FileManager.default.removeItem(at: paths.managedDirectory)
        return .notInstalled
    }

    private static func installedStatusLine(_ collector: URL, original: JSONValue?) -> JSONValue {
        var object = original?.objectValue ?? [:]
        object["type"] = .string("command")
        object["command"] = .string(shellQuote(collector.path))
        return .object(object)
    }

    private static func shellQuote(_ value: String) -> String {
        "'" + value.replacingOccurrences(of: "'", with: "'\"'\"'") + "'"
    }

    private static func readObject(_ url: URL) throws -> [String: JSONValue] {
        guard FileManager.default.fileExists(atPath: url.path) else { return [:] }
        do { return try decode([String: JSONValue].self, from: url) }
        catch {
            throw ProviderError("claude_settings_invalid", "Claude Code settings.json is not valid JSON.", details: error.localizedDescription)
        }
    }

    private static func decode<T: Decodable>(_ type: T.Type, from url: URL) throws -> T {
        try JSONDecoder().decode(type, from: Data(contentsOf: url))
    }

    private static func atomicCopy(from source: URL, to destination: URL, mode: Int) throws {
        let data = try Data(contentsOf: source)
        try atomicWrite(data, to: destination, mode: mode)
    }

    private static func atomicWrite(_ data: Data, to destination: URL, mode: Int) throws {
        try FileManager.default.createDirectory(
            at: destination.deletingLastPathComponent(),
            withIntermediateDirectories: true,
            attributes: [.posixPermissions: 0o700]
        )
        try data.write(to: destination, options: .atomic)
        try FileManager.default.setAttributes([.posixPermissions: mode], ofItemAtPath: destination.path)
    }
}

private struct ClaudeCacheWindow: Codable {
    var used_percentage: Double
    var resets_at: Double
}

private struct ClaudeCacheRateLimits: Codable {
    var five_hour: ClaudeCacheWindow?
    var seven_day: ClaudeCacheWindow?
}

private struct ClaudeCache: Codable {
    var version: String?
    var rate_limits: ClaudeCacheRateLimits
    var fetchedAt: Int
}

public actor ClaudeProvider {
    public init() {}

    public static func cacheURL(profileID: String) -> URL {
        let caches = FileManager.default.urls(for: .cachesDirectory, in: .userDomainMask).first ??
            FileManager.default.homeDirectoryForCurrentUser.appendingPathComponent("Library/Caches")
        return caches
            .appendingPathComponent("Agents Tray Limits/claude", isDirectory: true)
            .appendingPathComponent("\(profileID).json")
    }

    public func fetch(profile: AgentProfile, now: Double = Date().timeIntervalSince1970) throws -> UsageSnapshot {
        guard profile.provider == .claude else {
            throw ProviderError("invalid_profile", "The selected profile is not a Claude profile.")
        }
        let url = Self.cacheURL(profileID: profile.id)
        guard FileManager.default.fileExists(atPath: url.path) else {
            throw ProviderError("claude_cache_missing", "Claude limits are not available yet. Enable the collector and use Claude Code once.")
        }
        let cache: ClaudeCache
        do { cache = try JSONDecoder().decode(ClaudeCache.self, from: Data(contentsOf: url)) }
        catch {
            throw ProviderError("claude_cache_invalid", "Claude limit cache is not valid.", details: error.localizedDescription)
        }
        guard let primary = cache.rate_limits.five_hour,
              (0...100).contains(primary.used_percentage), primary.resets_at > 0 else {
            throw ProviderError("claude_limits_unavailable", "Claude Code has not supplied usable rate limits yet.")
        }
        guard primary.resets_at > now else {
            throw ProviderError("claude_limits_stale", "Claude limits have expired. Use Claude Code once to refresh them.")
        }
        let secondary = cache.rate_limits.seven_day.map {
            LimitWindow(usedPercent: $0.used_percentage, windowDurationMins: 10080, resetsAt: $0.resets_at)
        }
        let bucket = RateLimitBucket(
            limitId: "claude",
            primary: LimitWindow(usedPercent: primary.used_percentage, windowDurationMins: 300, resetsAt: primary.resets_at),
            secondary: secondary
        )
        return UsageSnapshot(
            ok: true,
            helperVersion: "1.0.0",
            profileId: profile.id,
            provider: .claude,
            source: "claude-statusline",
            fetchedAt: cache.fetchedAt,
            account: .object(["type": .string("claude")]),
            rateLimits: RateLimitResult(rateLimits: bucket, rateLimitsByLimitId: ["claude": bucket]),
            usage: .null,
            claudeVersion: cache.version,
            configDir: profile.expandedConfigDirectory.path
        )
    }
}

private extension JSONEncoder {
    static var pretty: JSONEncoder {
        let encoder = JSONEncoder()
        encoder.outputFormatting = [.prettyPrinted, .sortedKeys, .withoutEscapingSlashes]
        return encoder
    }
}
