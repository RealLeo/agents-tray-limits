import Foundation

public enum Provider: String, Codable, CaseIterable, Sendable {
    case codex
    case claude

    public var displayName: String {
        switch self {
        case .codex: return "Codex"
        case .claude: return "Claude Code"
        }
    }
}

public enum JSONValue: Codable, Equatable, Sendable {
    case object([String: JSONValue])
    case array([JSONValue])
    case string(String)
    case number(Double)
    case bool(Bool)
    case null

    public init(from decoder: Decoder) throws {
        let container = try decoder.singleValueContainer()
        if container.decodeNil() { self = .null }
        else if let value = try? container.decode(Bool.self) { self = .bool(value) }
        else if let value = try? container.decode(Double.self) { self = .number(value) }
        else if let value = try? container.decode(String.self) { self = .string(value) }
        else if let value = try? container.decode([String: JSONValue].self) { self = .object(value) }
        else if let value = try? container.decode([JSONValue].self) { self = .array(value) }
        else {
            throw DecodingError.dataCorruptedError(
                in: container,
                debugDescription: "Unsupported JSON value"
            )
        }
    }

    public func encode(to encoder: Encoder) throws {
        var container = encoder.singleValueContainer()
        switch self {
        case .object(let value): try container.encode(value)
        case .array(let value): try container.encode(value)
        case .string(let value): try container.encode(value)
        case .number(let value): try container.encode(value)
        case .bool(let value): try container.encode(value)
        case .null: try container.encodeNil()
        }
    }

    public var objectValue: [String: JSONValue]? {
        guard case .object(let value) = self else { return nil }
        return value
    }

    public var stringValue: String? {
        guard case .string(let value) = self else { return nil }
        return value
    }

    public var numberValue: Double? {
        guard case .number(let value) = self else { return nil }
        return value
    }
}

public struct LimitWindow: Codable, Equatable, Sendable {
    public var usedPercent: Double?
    public var windowDurationMins: Double?
    public var resetsAt: Double?

    public init(usedPercent: Double? = nil, windowDurationMins: Double? = nil, resetsAt: Double? = nil) {
        self.usedPercent = usedPercent
        self.windowDurationMins = windowDurationMins
        self.resetsAt = resetsAt
    }
}

public struct RateLimitBucket: Codable, Equatable, Sendable {
    public var limitId: String?
    public var limitName: String?
    public var primary: LimitWindow?
    public var secondary: LimitWindow?
    public var planType: String?
    public var rateLimitReachedType: String?

    public init(
        limitId: String? = nil,
        limitName: String? = nil,
        primary: LimitWindow? = nil,
        secondary: LimitWindow? = nil,
        planType: String? = nil,
        rateLimitReachedType: String? = nil
    ) {
        self.limitId = limitId
        self.limitName = limitName
        self.primary = primary
        self.secondary = secondary
        self.planType = planType
        self.rateLimitReachedType = rateLimitReachedType
    }
}

public struct RateLimitResult: Codable, Equatable, Sendable {
    public var rateLimits: RateLimitBucket?
    public var rateLimitsByLimitId: [String: RateLimitBucket]?
    public var rateLimitResetCredits: JSONValue?
    public var credits: JSONValue?

    public init(
        rateLimits: RateLimitBucket? = nil,
        rateLimitsByLimitId: [String: RateLimitBucket]? = nil,
        rateLimitResetCredits: JSONValue? = nil,
        credits: JSONValue? = nil
    ) {
        self.rateLimits = rateLimits
        self.rateLimitsByLimitId = rateLimitsByLimitId
        self.rateLimitResetCredits = rateLimitResetCredits
        self.credits = credits
    }
}

public struct UsageSnapshot: Codable, Equatable, Sendable, Identifiable {
    public var id: String { profileId }
    public var ok: Bool
    public var helperVersion: String?
    public var profileId: String
    public var provider: Provider
    public var source: String?
    public var fetchedAt: Int
    public var elapsedMs: Int?
    public var codexBinary: String?
    public var account: JSONValue?
    public var requiresOpenaiAuth: Bool?
    public var rateLimits: RateLimitResult?
    public var usage: JSONValue?
    public var usageError: JSONValue?
    public var claudeVersion: String?
    public var configDir: String?
    public var errorCode: String?
    public var message: String?
    public var details: String?

    public init(
        ok: Bool,
        helperVersion: String? = nil,
        profileId: String,
        provider: Provider,
        source: String? = nil,
        fetchedAt: Int = Int(Date().timeIntervalSince1970),
        elapsedMs: Int? = nil,
        codexBinary: String? = nil,
        account: JSONValue? = nil,
        requiresOpenaiAuth: Bool? = nil,
        rateLimits: RateLimitResult? = nil,
        usage: JSONValue? = nil,
        usageError: JSONValue? = nil,
        claudeVersion: String? = nil,
        configDir: String? = nil,
        errorCode: String? = nil,
        message: String? = nil,
        details: String? = nil
    ) {
        self.ok = ok
        self.helperVersion = helperVersion
        self.profileId = profileId
        self.provider = provider
        self.source = source
        self.fetchedAt = fetchedAt
        self.elapsedMs = elapsedMs
        self.codexBinary = codexBinary
        self.account = account
        self.requiresOpenaiAuth = requiresOpenaiAuth
        self.rateLimits = rateLimits
        self.usage = usage
        self.usageError = usageError
        self.claudeVersion = claudeVersion
        self.configDir = configDir
        self.errorCode = errorCode
        self.message = message
        self.details = details
    }

    public var primaryBucket: RateLimitBucket? {
        if let direct = rateLimits?.rateLimits { return direct }
        for id in ["codex", "claude"] {
            if let bucket = rateLimits?.rateLimitsByLimitId?[id] { return bucket }
        }
        return nil
    }

    public static func failure(
        profileId: String,
        provider: Provider,
        code: String,
        message: String,
        details: String? = nil
    ) -> UsageSnapshot {
        UsageSnapshot(
            ok: false,
            profileId: profileId,
            provider: provider,
            errorCode: code,
            message: message,
            details: details
        )
    }
}
