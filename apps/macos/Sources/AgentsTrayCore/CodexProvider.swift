import Foundation
#if canImport(Darwin)
import Darwin
#else
import Glibc
#endif

public struct ProviderError: Error, LocalizedError, Sendable {
    public var code: String
    public var message: String
    public var details: String?

    public init(_ code: String, _ message: String, details: String? = nil) {
        self.code = code
        self.message = message
        self.details = details
    }

    public var errorDescription: String? { message }
}

public enum CodexLocator {
    public static func find(explicit: String? = nil, environment: [String: String] = ProcessInfo.processInfo.environment) throws -> String {
        if let explicit = explicit?.trimmingCharacters(in: .whitespacesAndNewlines), !explicit.isEmpty {
            let expanded = NSString(string: explicit).expandingTildeInPath
            if expanded.contains("/") {
                guard FileManager.default.isExecutableFile(atPath: expanded) else {
                    throw ProviderError("codex_not_found", "Codex CLI was not found at the configured path.", details: expanded)
                }
                return URL(fileURLWithPath: expanded).standardizedFileURL.path
            }
            if let match = findInPath(expanded, path: environment["PATH"]) { return match }
            throw ProviderError("codex_not_found", "Codex CLI was not found at the configured path.", details: expanded)
        }

        if let match = findInPath("codex", path: environment["PATH"]) { return match }
        let home = FileManager.default.homeDirectoryForCurrentUser.path
        var candidates = [
            "\(home)/.local/bin/codex",
            "\(home)/.cargo/bin/codex",
            "\(home)/.volta/bin/codex",
            "\(home)/.bun/bin/codex",
            "\(home)/.npm-global/bin/codex",
            "\(home)/.local/share/pnpm/codex",
            "\(home)/.asdf/shims/codex",
            "\(home)/.local/share/mise/shims/codex",
            "/opt/homebrew/bin/codex",
            "/usr/local/bin/codex",
            "/usr/bin/codex",
        ]

        let nvmRoot = URL(fileURLWithPath: home).appendingPathComponent(".nvm/versions/node")
        if let versions = try? FileManager.default.contentsOfDirectory(
            at: nvmRoot,
            includingPropertiesForKeys: [.contentModificationDateKey],
            options: [.skipsHiddenFiles]
        ) {
            let nvm = versions.map { $0.appendingPathComponent("bin/codex") }
                .filter { FileManager.default.isExecutableFile(atPath: $0.path) }
                .sorted {
                    let left = (try? $0.resourceValues(forKeys: [.contentModificationDateKey]).contentModificationDate) ?? .distantPast
                    let right = (try? $1.resourceValues(forKeys: [.contentModificationDateKey]).contentModificationDate) ?? .distantPast
                    return left > right
                }
                .map(\.path)
            candidates.insert(contentsOf: nvm, at: 0)
        }
        if let match = candidates.first(where: FileManager.default.isExecutableFile(atPath:)) {
            return URL(fileURLWithPath: match).standardizedFileURL.path
        }
        throw ProviderError(
            "codex_not_found",
            "Codex CLI was not found. Install Codex and sign in with ChatGPT once."
        )
    }

    private static func findInPath(_ executable: String, path: String?) -> String? {
        for directory in (path ?? "").split(separator: ":") {
            let candidate = URL(fileURLWithPath: String(directory)).appendingPathComponent(executable).path
            if FileManager.default.isExecutableFile(atPath: candidate) {
                return URL(fileURLWithPath: candidate).standardizedFileURL.path
            }
        }
        return nil
    }
}

private final class AppServerSession: @unchecked Sendable {
    private let process = Process()
    private let input = Pipe()
    private let output = Pipe()
    private let errors = Pipe()
    private let lock = NSLock()
    private var buffer = Data()
    private var stderr = Data()
    private var stopped = false

    init(binary: String, configDirectory: String) throws {
        process.executableURL = URL(fileURLWithPath: binary)
        var arguments: [String] = []
        var environment = ProcessInfo.processInfo.environment
        let launcherDirectory = URL(fileURLWithPath: binary).deletingLastPathComponent().path
        let existing = (environment["PATH"] ?? "").split(separator: ":").map(String.init)
        environment["PATH"] = ([launcherDirectory] + existing.filter { $0 != launcherDirectory }).joined(separator: ":")
        if !configDirectory.isEmpty {
            let expanded = NSString(string: configDirectory).expandingTildeInPath
            environment["CODEX_HOME"] = expanded
            arguments += ["-c", "cli_auth_credentials_store=\"file\""]
        } else {
            environment.removeValue(forKey: "CODEX_HOME")
        }
        arguments.append("app-server")
        process.arguments = arguments
        process.environment = environment
        process.currentDirectoryURL = FileManager.default.homeDirectoryForCurrentUser
        process.standardInput = input
        process.standardOutput = output
        process.standardError = errors
#if canImport(Darwin)
        _ = fcntl(input.fileHandleForWriting.fileDescriptor, F_SETNOSIGPIPE, 1)
#else
        _ = signal(SIGPIPE, SIG_IGN)
#endif
        do {
            try process.run()
        } catch {
            throw ProviderError("app_server_start_failed", "Failed to start Codex App Server.", details: error.localizedDescription)
        }
    }

    deinit { stop() }

    func stop() {
        lock.lock()
        if stopped {
            lock.unlock()
            return
        }
        stopped = true
        lock.unlock()
        try? input.fileHandleForWriting.close()
        if process.isRunning {
            let identifier = process.processIdentifier
            process.terminate()
            if process.isRunning { _ = kill(identifier, SIGKILL) }
        }
    }

    func collect(profile: AgentProfile, binary: String) throws -> UsageSnapshot {
        let started = Date()
        try send(method: "initialize", id: 1, params: [
            "clientInfo": [
                "name": "agents_tray_limits_macos",
                "title": "Agents Tray Limits for macOS",
                "version": "1.0.0",
            ],
        ])
        let initialize = try response(id: 1)
        try result(of: initialize, method: "initialize")
        try send(method: "initialized", params: [:])
        try send(method: "account/read", id: 2, params: ["refreshToken": false])
        let accountResult = try result(of: response(id: 2), method: "account/read")
        guard let account = accountResult["account"], !(account is NSNull) else {
            throw ProviderError("not_logged_in", "Codex CLI has no active session. Sign in with ChatGPT first.")
        }
        let accountObject = account as? [String: Any]
        let accountType = accountObject?["type"] as? String
        if ["apiKey", "amazonBedrock"].contains(accountType) {
            throw ProviderError(
                "unsupported_auth",
                "Subscription limits require Codex sign-in with ChatGPT, not an API key or Bedrock.",
                details: "account.type=\(accountType ?? "unknown")"
            )
        }

        try send(method: "account/rateLimits/read", id: 3)
        try send(method: "account/usage/read", id: 4)
        let rateObject = try result(of: response(id: 3), method: "account/rateLimits/read")
        let rateData = try JSONSerialization.data(withJSONObject: rateObject)
        let rateLimits: RateLimitResult
        do {
            rateLimits = try JSONDecoder().decode(RateLimitResult.self, from: rateData)
        } catch {
            throw ProviderError("no_rate_limits", "Codex did not return any available ChatGPT limits.", details: error.localizedDescription)
        }

        var usage: JSONValue?
        var usageError: JSONValue?
        do {
            let usageObject = try result(of: response(id: 4), method: "account/usage/read", optional: true)
            usage = try jsonValue(usageObject)
        } catch let error as ProviderError {
            usageError = .object(["code": .string(error.code), "message": .string(error.message)])
        }

        return UsageSnapshot(
            ok: true,
            helperVersion: "1.0.0",
            profileId: profile.id,
            provider: .codex,
            source: "codex-app-server",
            elapsedMs: Int(Date().timeIntervalSince(started) * 1000),
            codexBinary: binary,
            account: try jsonValue(account),
            requiresOpenaiAuth: accountResult["requiresOpenaiAuth"] as? Bool,
            rateLimits: rateLimits,
            usage: usage,
            usageError: usageError
        )
    }

    private func send(method: String, id: Int? = nil, params: [String: Any]? = nil) throws {
        var message: [String: Any] = ["method": method]
        if let id { message["id"] = id }
        if let params { message["params"] = params }
        var data = try JSONSerialization.data(withJSONObject: message)
        data.append(0x0A)
        do {
            try input.fileHandleForWriting.write(contentsOf: data)
        } catch {
            throw ProviderError("app_server_stopped", "Codex App Server stopped before replying.", details: error.localizedDescription)
        }
    }

    private func response(id: Int) throws -> [String: Any] {
        while true {
            let line = try readLine()
            guard let object = try? JSONSerialization.jsonObject(with: line) as? [String: Any] else { continue }
            if let responseID = object["id"] as? NSNumber, responseID.intValue == id { return object }
        }
    }

    private func readLine() throws -> Data {
        while true {
            if let newline = buffer.firstIndex(of: 0x0A) {
                let line = buffer.prefix(upTo: newline)
                buffer.removeSubrange(...newline)
                return Data(line)
            }
            let chunk = output.fileHandleForReading.availableData
            guard !chunk.isEmpty else {
                if let errorData = try? errors.fileHandleForReading.readToEnd() { stderr.append(errorData) }
                let details = String(data: stderr, encoding: .utf8)?.trimmingCharacters(in: .whitespacesAndNewlines)
                throw ProviderError("app_server_stopped", "Codex App Server stopped before replying.", details: details)
            }
            buffer.append(chunk)
        }
    }

    @discardableResult
    private func result(
        of response: [String: Any],
        method: String,
        optional: Bool = false
    ) throws -> [String: Any] {
        if let error = response["error"] as? [String: Any] {
            let message = String(describing: error["message"] ?? "Unknown app-server error")
            let code = (error["code"] as? NSNumber)?.intValue
            if optional { throw ProviderError("optional_method_unavailable", message) }
            if code == -32601 || message.localizedCaseInsensitiveContains("not found") {
                throw ProviderError("codex_too_old", "This Codex CLI version cannot read usage limits. Update Codex and try again.", details: message)
            }
            throw ProviderError("app_server_error", "Codex did not return data for \(method).", details: message)
        }
        guard let value = response["result"] as? [String: Any] else {
            throw ProviderError("protocol_error", "Codex returned an unexpected data format for \(method).")
        }
        return value
    }

    private func jsonValue(_ object: Any) throws -> JSONValue {
        let data = try JSONSerialization.data(withJSONObject: object, options: [.fragmentsAllowed])
        return try JSONDecoder().decode(JSONValue.self, from: data)
    }
}

private enum CodexFetchOutcome: Sendable {
    case success(UsageSnapshot)
    case failure(ProviderError)
    case timeout
    case cancelled
}

public actor CodexProvider {
    public init() {}

    public func fetch(profile: AgentProfile, explicitBinary: String? = nil, timeout: TimeInterval = 15) async throws -> UsageSnapshot {
        guard profile.provider == .codex else {
            throw ProviderError("invalid_profile", "The selected profile is not a Codex profile.")
        }
        let binary = try CodexLocator.find(explicit: explicitBinary)
        let session = try AppServerSession(binary: binary, configDirectory: profile.configDir)
        let bounded = min(60, max(2, timeout))
        return try await withTaskCancellationHandler(operation: {
            let outcome = await withTaskGroup(of: CodexFetchOutcome.self) { group in
                group.addTask {
                    do { return .success(try session.collect(profile: profile, binary: binary)) }
                    catch let error as ProviderError { return .failure(error) }
                    catch { return .failure(ProviderError("internal_error", error.localizedDescription)) }
                }
                group.addTask {
                    do {
                        try await Task.sleep(nanoseconds: UInt64(bounded * 1_000_000_000))
                        return .timeout
                    } catch {
                        return .cancelled
                    }
                }
                let first = await group.next() ?? .failure(
                    ProviderError("internal_error", "Codex provider did not produce a result.")
                )
                session.stop()
                group.cancelAll()
                return first
            }
            session.stop()
            if Task.isCancelled { throw CancellationError() }
            switch outcome {
            case .success(let snapshot): return snapshot
            case .failure(let error): throw error
            case .timeout: throw ProviderError("timeout", "Codex App Server did not reply in time.")
            case .cancelled: throw CancellationError()
            }
        }, onCancel: {
            session.stop()
        })
    }
}
