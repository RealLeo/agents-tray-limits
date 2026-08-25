import AgentsTrayCore
import Foundation

private func writeError(_ message: String) {
    FileHandle.standardError.write(Data((message + "\n").utf8))
}

private func cleanWindow(_ value: Any?) -> [String: Any]? {
    guard let object = value as? [String: Any],
          let used = (object["used_percentage"] as? NSNumber)?.doubleValue,
          let reset = (object["resets_at"] as? NSNumber)?.doubleValue,
          (0...100).contains(used), reset > 0 else { return nil }
    return ["used_percentage": used, "resets_at": reset]
}

private func updateCache(raw: Data, configuration: ClaudeCollectorConfiguration) throws {
    guard let source = try JSONSerialization.jsonObject(with: raw) as? [String: Any] else { return }
    var cleaned: [String: Any] = [:]
    if let rateLimits = source["rate_limits"] as? [String: Any] {
        for key in ["five_hour", "seven_day"] {
            if let window = cleanWindow(rateLimits[key]) { cleaned[key] = window }
        }
    }
    let payload: [String: Any] = [
        "version": source["version"] as? String ?? NSNull(),
        "rate_limits": cleaned,
        "fetchedAt": Int(Date().timeIntervalSince1970),
    ]
    let destination = URL(fileURLWithPath: configuration.cachePath)
    try FileManager.default.createDirectory(
        at: destination.deletingLastPathComponent(),
        withIntermediateDirectories: true,
        attributes: [.posixPermissions: 0o700]
    )
    let data = try JSONSerialization.data(withJSONObject: payload, options: [.prettyPrinted, .sortedKeys])
    try data.write(to: destination, options: .atomic)
    try FileManager.default.setAttributes([.posixPermissions: 0o600], ofItemAtPath: destination.path)
}

private func delegate(raw: Data, command: String) throws -> Int32 {
    guard !command.isEmpty else { return 0 }
    let process = Process()
    let input = Pipe(), output = Pipe(), errors = Pipe()
    process.executableURL = URL(fileURLWithPath: "/bin/sh")
    process.arguments = ["-c", command]
    process.standardInput = input
    process.standardOutput = output
    process.standardError = errors
    try process.run()

    var outputData = Data(), errorData = Data()
    let group = DispatchGroup()
    group.enter()
    DispatchQueue.global(qos: .utility).async {
        outputData = output.fileHandleForReading.readDataToEndOfFile()
        group.leave()
    }
    group.enter()
    DispatchQueue.global(qos: .utility).async {
        errorData = errors.fileHandleForReading.readDataToEndOfFile()
        group.leave()
    }
    input.fileHandleForWriting.write(raw)
    try input.fileHandleForWriting.close()
    process.waitUntilExit()
    group.wait()
    FileHandle.standardOutput.write(outputData)
    FileHandle.standardError.write(errorData)
    return process.terminationStatus
}

let executable = URL(fileURLWithPath: CommandLine.arguments[0]).standardizedFileURL
let configurationURL = executable.deletingLastPathComponent()
    .appendingPathComponent("collector-config.json")

do {
    let configuration = try JSONDecoder().decode(
        ClaudeCollectorConfiguration.self,
        from: Data(contentsOf: configurationURL)
    )
    let raw = FileHandle.standardInput.readDataToEndOfFile()
    do { try updateCache(raw: raw, configuration: configuration) }
    catch { writeError("Agents Tray Limits cache update failed: \(error.localizedDescription)") }
    exit(try delegate(raw: raw, command: configuration.originalCommand))
} catch {
    writeError("Agents Tray Limits collector failed: \(error.localizedDescription)")
    exit(2)
}
