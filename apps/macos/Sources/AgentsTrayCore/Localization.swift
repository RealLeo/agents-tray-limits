import Foundation

public enum SupportedLanguage: String, CaseIterable, Codable, Sendable {
    case system
    case en
    case ru
    case de
    case fr
    case zhCN = "zh-CN"

    public static func resolve(_ selected: SupportedLanguage, preferred: [String] = Locale.preferredLanguages) -> SupportedLanguage {
        guard selected == .system else { return selected }
        for candidate in preferred {
            let normalized = candidate.replacingOccurrences(of: "_", with: "-").lowercased()
            if normalized.hasPrefix("zh") { return .zhCN }
            if let match = allCases.first(where: { $0 != .system && normalized.hasPrefix($0.rawValue.lowercased()) }) {
                return match
            }
        }
        return .en
    }
}

public struct Localizer: Sendable {
    public let language: SupportedLanguage
    private let catalog: [String: JSONValue]
    private let english: [String: JSONValue]

    public init(language: SupportedLanguage, localeRoot: URL?) {
        self.language = SupportedLanguage.resolve(language)
        func load(_ value: SupportedLanguage) -> [String: JSONValue] {
            guard let localeRoot,
                  let data = try? Data(contentsOf: localeRoot.appendingPathComponent("\(value.rawValue).json")),
                  let decoded = try? JSONDecoder().decode([String: JSONValue].self, from: data) else {
                return [:]
            }
            return decoded
        }
        let fallback = load(.en)
        self.english = fallback
        self.catalog = self.language == .en ? fallback : load(self.language)
    }

    public func text(_ key: String, _ parameters: [String: String] = [:]) -> String {
        let template = catalog[key]?.stringValue ?? english[key]?.stringValue ?? key
        return parameters.reduce(template) { result, pair in
            result.replacingOccurrences(of: "{\(pair.key)}", with: pair.value)
        }
    }

    public func plural(_ key: String, count: Int) -> String {
        let category: String
        switch language {
        case .ru:
            let mod10 = count % 10, mod100 = count % 100
            category = mod10 == 1 && mod100 != 11 ? "one" :
                (2...4).contains(mod10) && !(12...14).contains(mod100) ? "few" : "many"
        case .fr: category = count == 0 || count == 1 ? "one" : "other"
        case .zhCN: category = "other"
        default: category = count == 1 ? "one" : "other"
        }
        let values = catalog[key]?.objectValue ?? english[key]?.objectValue ?? [:]
        let template = values[category]?.stringValue ?? values["other"]?.stringValue ?? key
        return template.replacingOccurrences(of: "{count}", with: String(count))
    }
}
