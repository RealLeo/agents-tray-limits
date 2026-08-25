import XCTest
@testable import AgentsTrayCore

final class CoreTests: XCTestCase {
    private var repositoryRoot: URL {
        var url = URL(fileURLWithPath: #filePath)
        for _ in 0..<5 { url.deleteLastPathComponent() }
        return url
    }

    private func temporaryDirectory() throws -> URL {
        let root = FileManager.default.temporaryDirectory
            .appendingPathComponent("agents-tray-tests-\(UUID().uuidString)")
        try FileManager.default.createDirectory(at: root, withIntermediateDirectories: true)
        return root
    }

    private func executable(_ source: String, named name: String, in root: URL) throws -> URL {
        let url = root.appendingPathComponent(name)
        try Data(source.utf8).write(to: url)
        try FileManager.default.setAttributes([.posixPermissions: 0o700], ofItemAtPath: url.path)
        return url
    }

    private func providerError(script: String, timeout: TimeInterval = 5) async throws -> ProviderError {
        let root = try temporaryDirectory()
        defer { try? FileManager.default.removeItem(at: root) }
        let binary = try executable(script, named: "codex", in: root)
        let profile = AgentProfile(id: "fixture", provider: .codex, label: "Fixture")
        do {
            _ = try await CodexProvider().fetch(profile: profile, explicitBinary: binary.path, timeout: timeout)
            XCTFail("provider unexpectedly succeeded")
            return ProviderError("unexpected_success", "provider unexpectedly succeeded")
        } catch let error as ProviderError {
            return error
        }
    }

    func testSharedFixturesDecode() throws {
        let fixtures = repositoryRoot.appendingPathComponent("shared/fixtures")
        for name in [
            "codex-multi-bucket.json",
            "codex-optional-usage.json",
            "claude-success.json",
            "error-unsupported-auth.json",
            "error-codex-too-old.json",
            "error-process-exit.json",
            "error-timeout.json",
        ] {
            let snapshot = try JSONDecoder().decode(
                UsageSnapshot.self,
                from: Data(contentsOf: fixtures.appendingPathComponent(name))
            )
            XCTAssertFalse(snapshot.profileId.isEmpty, name)
        }
        let codex = try JSONDecoder().decode(
            UsageSnapshot.self,
            from: Data(contentsOf: fixtures.appendingPathComponent("codex-multi-bucket.json"))
        )
        XCTAssertEqual(codex.primaryBucket?.limitId, "codex")
        XCTAssertEqual(UsageFormatting.remaining(codex), 65)
    }

    func testCodexAppServerSuccessAndOptionalUsage() async throws {
        let root = try temporaryDirectory()
        defer { try? FileManager.default.removeItem(at: root) }
        let script = #"""
        #!/bin/sh
        printf '%s\n' '{"id":1,"result":{}}'
        printf '%s\n' '{"id":2,"result":{"account":{"type":"chatgpt","planType":"plus"},"requiresOpenaiAuth":true}}'
        printf '%s\n' '{"id":3,"result":{"rateLimits":{"limitId":"codex","primary":{"usedPercent":25,"windowDurationMins":300,"resetsAt":2000000000}},"rateLimitsByLimitId":{"codex":{"limitId":"codex","primary":{"usedPercent":25,"windowDurationMins":300,"resetsAt":2000000000}},"spark":{"limitId":"spark","primary":{"usedPercent":10}}}}}'
        printf '%s\n' '{"id":4,"error":{"code":-32601,"message":"Method not found"}}'
        cat >/dev/null
        """#
        let binary = try executable(script, named: "codex", in: root)
        let profile = AgentProfile(id: "work", provider: .codex, label: "Work")
        let snapshot = try await CodexProvider().fetch(profile: profile, explicitBinary: binary.path)
        XCTAssertEqual(snapshot.primaryBucket?.primary?.usedPercent, 25)
        XCTAssertEqual(snapshot.rateLimits?.rateLimitsByLimitId?["spark"]?.primary?.usedPercent, 10)
        XCTAssertNil(snapshot.usage)
        XCTAssertNotNil(snapshot.usageError)
        XCTAssertEqual(snapshot.requiresOpenaiAuth, true)
    }

    func testCodexAppServerProtocolErrors() async throws {
        let unsupported = try await providerError(script: #"""
        #!/bin/sh
        printf '%s\n' '{"id":1,"result":{}}'
        printf '%s\n' '{"id":2,"result":{"account":{"type":"apiKey"}}}'
        cat >/dev/null
        """#)
        XCTAssertEqual(unsupported.code, "unsupported_auth")

        let oldCLI = try await providerError(script: #"""
        #!/bin/sh
        printf '%s\n' '{"id":1,"result":{}}'
        printf '%s\n' '{"id":2,"result":{"account":{"type":"chatgpt"}}}'
        printf '%s\n' '{"id":3,"error":{"code":-32601,"message":"Method not found"}}'
        cat >/dev/null
        """#)
        XCTAssertEqual(oldCLI.code, "codex_too_old")

        let stopped = try await providerError(script: #"""
        #!/bin/sh
        printf '%s\n' '{"id":1,"result":{}}'
        exit 9
        """#)
        XCTAssertEqual(stopped.code, "app_server_stopped")
    }

    func testCodexAppServerTimeout() async throws {
        let error = try await providerError(script: #"""
        #!/bin/sh
        exec sleep 10
        """#, timeout: 2)
        XCTAssertEqual(error.code, "timeout")
    }

    func testCodexAppServerCancellationStopsProcess() async throws {
        let root = try temporaryDirectory()
        defer { try? FileManager.default.removeItem(at: root) }
        let binary = try executable("#!/bin/sh\nexec sleep 10\n", named: "codex", in: root)
        let profile = AgentProfile(id: "cancelled", provider: .codex, label: "Cancelled")
        let task = Task {
            try await CodexProvider().fetch(profile: profile, explicitBinary: binary.path, timeout: 30)
        }
        try await Task.sleep(nanoseconds: 100_000_000)
        task.cancel()
        do {
            _ = try await task.value
            XCTFail("cancelled provider unexpectedly succeeded")
        } catch is CancellationError {
            // Expected.
        }
    }

    func testProfileValidationAndNormalization() throws {
        let profile = try ProfileValidator.validate(
            AgentProfile(id: "work-1", provider: .codex, label: " Work ", configDir: "~/.codex-work"),
            among: []
        )
        XCTAssertEqual(profile.label, "Work")
        XCTAssertThrowsError(try ProfileValidator.validate(
            AgentProfile(id: "other", provider: .claude, label: "work"),
            among: [profile]
        ))
        XCTAssertThrowsError(try ProfileValidator.validate(
            AgentProfile(id: "bad id", provider: .codex, label: "Bad"),
            among: []
        ))
    }

    func testStatusBoundariesAndPanelFormatting() throws {
        XCTAssertEqual(UsageFormatting.status(forRemaining: 0.49), .dead)
        XCTAssertEqual(UsageFormatting.status(forRemaining: 0.5), .critical)
        XCTAssertEqual(UsageFormatting.status(forRemaining: 20.49), .critical)
        XCTAssertEqual(UsageFormatting.status(forRemaining: 20.5), .worried)
        XCTAssertEqual(UsageFormatting.status(forRemaining: 50.5), .good)

        let localizer = Localizer(
            language: .en,
            localeRoot: repositoryRoot.appendingPathComponent("shared/locales")
        )
        let now = 2_000_000_000.0
        let bucket = RateLimitBucket(
            limitId: "codex",
            primary: LimitWindow(usedPercent: 34, windowDurationMins: 10080, resetsAt: now + 4 * 86400 + 22 * 3600)
        )
        let snapshot = UsageSnapshot(
            ok: true,
            profileId: "default-codex",
            provider: .codex,
            rateLimits: RateLimitResult(rateLimits: bucket)
        )
        XCTAssertEqual(
            UsageFormatting.panelText(snapshot, display: .remaining, now: now, localizer: localizer),
            "66% · reset 4d 22h"
        )
        XCTAssertEqual(
            UsageFormatting.panelText(snapshot, display: .used, now: now, localizer: localizer),
            "34% · reset 4d 22h"
        )
    }

    func testEverySharedLocaleResolvesCoreStrings() {
        let root = repositoryRoot.appendingPathComponent("shared/locales")
        for language in SupportedLanguage.allCases where language != .system {
            let localizer = Localizer(language: language, localeRoot: root)
            XCTAssertNotEqual(localizer.text("actions.refresh"), "actions.refresh", language.rawValue)
            XCTAssertNotEqual(localizer.text("profiles.error"), "profiles.error", language.rawValue)
            XCTAssertFalse(localizer.plural("time.minute", count: 2).contains("{count}"), language.rawValue)
        }
    }

    func testBuiltInThemeV2Validation() throws {
        let root = repositoryRoot.appendingPathComponent("shared/themes")
        for id in ["fallout-2", "fallout-3"] {
            let directory = root.appendingPathComponent(id)
            let manifest = try JSONDecoder().decode(
                ThemeManifest.self,
                from: Data(contentsOf: directory.appendingPathComponent("theme.json"))
            )
            XCTAssertEqual(manifest.version, 2)
            XCTAssertNoThrow(try ThemeValidator.validate(manifest, at: directory))
        }
    }

    func testThemeV1FallsBackToClassicAndRejectsSymlinks() throws {
        let root = try temporaryDirectory().appendingPathComponent("legacy-theme")
        try FileManager.default.createDirectory(at: root, withIntermediateDirectories: true)
        defer { try? FileManager.default.removeItem(at: root.deletingLastPathComponent()) }
        for name in ["good.png", "worried.png", "critical.png", "dead.png"] {
            try Data("fixture".utf8).write(to: root.appendingPathComponent(name))
        }
        var manifest = try JSONDecoder().decode(
            ThemeManifest.self,
            from: Data(contentsOf: repositoryRoot.appendingPathComponent("shared/themes/fallout-3/theme.json"))
        )
        manifest.version = 1
        manifest.id = "legacy-theme"
        manifest.platforms = nil
        manifest.stylesheet = nil
        manifest.frameAnimation = nil
        manifest.animation = nil
        manifest.panelArt = nil
        manifest.art = ThemeStatusPaths(
            good: "good.png",
            worried: "worried.png",
            critical: "critical.png",
            dead: "dead.png"
        )
        XCTAssertEqual(manifest.macDefinition.layout, .classic)
        XCTAssertNoThrow(try ThemeValidator.validate(manifest, at: root))

        try FileManager.default.removeItem(at: root.appendingPathComponent("good.png"))
        try FileManager.default.createSymbolicLink(
            at: root.appendingPathComponent("good.png"),
            withDestinationURL: root.appendingPathComponent("worried.png")
        )
        XCTAssertThrowsError(try ThemeValidator.validate(manifest, at: root))
        XCTAssertFalse(ThemeValidator.safeRelativePath("../outside.png"))
    }

    func testClaudeMonitorInstallConflictAndRestore() throws {
        let root = try temporaryDirectory()
        defer { try? FileManager.default.removeItem(at: root) }
        let collector = root.appendingPathComponent("collector")
        try Data("collector".utf8).write(to: collector)
        try FileManager.default.setAttributes([.posixPermissions: 0o700], ofItemAtPath: collector.path)
        let profile = AgentProfile(id: "test-\(UUID().uuidString)", provider: .claude, label: "Claude", configDir: root.path)
        let original: [String: JSONValue] = [
            "statusLine": .object(["type": .string("command"), "command": .string("previous")])
        ]
        let encoder = JSONEncoder()
        try encoder.encode(original).write(to: root.appendingPathComponent("settings.json"), options: .atomic)

        XCTAssertEqual(try ClaudeMonitorManager.install(profile: profile, bundledCollector: collector), .installed)
        XCTAssertEqual(ClaudeMonitorManager.status(profile: profile), .installed)

        let paths = ClaudeMonitorPaths(profile: profile)
        var outdatedBackup = try JSONDecoder().decode(
            [String: JSONValue].self,
            from: Data(contentsOf: paths.backup)
        )
        outdatedBackup["collectorVersion"] = .number(0)
        try encoder.encode(outdatedBackup).write(to: paths.backup, options: .atomic)
        XCTAssertEqual(ClaudeMonitorManager.status(profile: profile), .updateAvailable)
        XCTAssertEqual(try ClaudeMonitorManager.install(profile: profile, bundledCollector: collector), .installed)

        var changed = original
        changed["statusLine"] = .object(["type": .string("command"), "command": .string("independent")])
        try encoder.encode(changed).write(to: root.appendingPathComponent("settings.json"), options: .atomic)
        XCTAssertThrowsError(try ClaudeMonitorManager.restore(profile: profile))

        let backup = try JSONDecoder().decode(
            [String: JSONValue].self,
            from: Data(contentsOf: paths.backup)
        )
        var installedSettings = original
        installedSettings["statusLine"] = backup["installedStatusLine"]
        try encoder.encode(installedSettings).write(to: root.appendingPathComponent("settings.json"), options: .atomic)
        XCTAssertEqual(try ClaudeMonitorManager.restore(profile: profile), .notInstalled)
        let restored = try JSONDecoder().decode(
            [String: JSONValue].self,
            from: Data(contentsOf: root.appendingPathComponent("settings.json"))
        )
        XCTAssertEqual(restored, original)
    }

    func testClaudeProviderRejectsStaleCache() async throws {
        let profile = AgentProfile(
            id: "stale-\(UUID().uuidString)",
            provider: .claude,
            label: "Stale"
        )
        let cache = ClaudeProvider.cacheURL(profileID: profile.id)
        try FileManager.default.createDirectory(at: cache.deletingLastPathComponent(), withIntermediateDirectories: true)
        defer { try? FileManager.default.removeItem(at: cache) }
        let expired = """
        {"version":"2.1","rate_limits":{"five_hour":{"used_percentage":10,"resets_at":1}},"fetchedAt":1}
        """
        try Data(expired.utf8).write(to: cache, options: .atomic)
        do {
            _ = try await ClaudeProvider().fetch(profile: profile, now: 2)
            XCTFail("stale Claude cache unexpectedly succeeded")
        } catch let error as ProviderError {
            XCTAssertEqual(error.code, "claude_limits_stale")
        }
    }

    func testClaudeCollectorDelegatesStreamsAndExitCode() throws {
        var search = URL(fileURLWithPath: CommandLine.arguments[0]).deletingLastPathComponent()
        var builtCollector: URL?
        for _ in 0..<7 {
            let candidate = search.appendingPathComponent("AgentsTrayCollector")
            if FileManager.default.isExecutableFile(atPath: candidate.path) {
                builtCollector = candidate
                break
            }
            search.deleteLastPathComponent()
        }
        let sourceCollector = try XCTUnwrap(builtCollector, "AgentsTrayCollector product was not built")
        let root = try temporaryDirectory()
        defer { try? FileManager.default.removeItem(at: root) }
        let collector = root.appendingPathComponent("statusline")
        try FileManager.default.copyItem(at: sourceCollector, to: collector)
        try FileManager.default.setAttributes([.posixPermissions: 0o700], ofItemAtPath: collector.path)
        let delegate = try executable(#"""
        #!/bin/sh
        input="$(cat)"
        printf 'delegated:%s' "$input"
        printf 'delegated-error' >&2
        exit 7
        """#, named: "delegate", in: root)
        let cache = root.appendingPathComponent("cache/claude.json")
        let configuration = ClaudeCollectorConfiguration(
            profileId: "collector-test",
            cachePath: cache.path,
            originalCommand: "'\(delegate.path)'"
        )
        try JSONEncoder().encode(configuration)
            .write(to: root.appendingPathComponent("collector-config.json"), options: .atomic)

        let process = Process()
        let input = Pipe(), output = Pipe(), errors = Pipe()
        process.executableURL = collector
        process.standardInput = input
        process.standardOutput = output
        process.standardError = errors
        try process.run()
        let raw = Data(#"{"version":"2.1","rate_limits":{"five_hour":{"used_percentage":12,"resets_at":2000000000}}}"#.utf8)
        try input.fileHandleForWriting.write(contentsOf: raw)
        try input.fileHandleForWriting.close()
        process.waitUntilExit()

        XCTAssertEqual(process.terminationStatus, 7)
        XCTAssertEqual(String(data: output.fileHandleForReading.readDataToEndOfFile(), encoding: .utf8), "delegated:" + String(data: raw, encoding: .utf8)!)
        XCTAssertEqual(String(data: errors.fileHandleForReading.readDataToEndOfFile(), encoding: .utf8), "delegated-error")
        let payload = try XCTUnwrap(try JSONSerialization.jsonObject(with: Data(contentsOf: cache)) as? [String: Any])
        let limits = try XCTUnwrap(payload["rate_limits"] as? [String: Any])
        let fiveHour = try XCTUnwrap(limits["five_hour"] as? [String: Any])
        XCTAssertEqual((fiveHour["used_percentage"] as? NSNumber)?.doubleValue, 12)
        XCTAssertNil(limits["seven_day"])
    }
}
