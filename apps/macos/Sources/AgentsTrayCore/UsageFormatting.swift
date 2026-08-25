import Foundation

public enum LimitStatus: String, CaseIterable, Sendable {
    case good
    case worried
    case critical
    case dead
}

public enum PanelDisplay: String, Codable, CaseIterable, Sendable {
    case remaining
    case used
}

public enum UsageFormatting {
    public static func clamp(_ value: Double?) -> Double? {
        guard let value, value.isFinite else { return nil }
        return min(100, max(0, value))
    }

    public static func displayPercent(_ value: Double?) -> Int? {
        guard let value = clamp(value) else { return nil }
        return Int(value.rounded(.toNearestOrAwayFromZero))
    }

    public static func remaining(_ snapshot: UsageSnapshot) -> Double? {
        guard let used = clamp(snapshot.primaryBucket?.primary?.usedPercent) else { return nil }
        return 100 - used
    }

    public static func status(forRemaining value: Double?) -> LimitStatus? {
        guard let value = displayPercent(value) else { return nil }
        if value == 0 { return .dead }
        if value <= 20 { return .critical }
        if value <= 50 { return .worried }
        return .good
    }

    public static func resetText(
        timestamp: Double?,
        now: Double = Date().timeIntervalSince1970,
        localizer: Localizer
    ) -> String {
        guard let timestamp, timestamp > 0 else { return localizer.text("panel.resetUnknown") }
        guard timestamp > now else { return localizer.text("panel.resetNow") }
        let totalMinutes = max(1, Int(ceil((timestamp - now) / 60)))
        let days = totalMinutes / 1440
        let hours = (totalMinutes % 1440) / 60
        let minutes = totalMinutes % 60
        if days > 0 {
            let day = localizer.plural("time.dayShort", count: days)
            return hours > 0 ? "\(day) \(localizer.plural("time.hourShort", count: hours))" : day
        }
        if hours > 0 {
            let hour = localizer.plural("time.hourShort", count: hours)
            return minutes > 0 ? "\(hour) \(localizer.plural("time.minuteShort", count: minutes))" : hour
        }
        return localizer.plural("time.minuteShort", count: minutes)
    }

    public static func panelText(
        _ snapshot: UsageSnapshot,
        display: PanelDisplay,
        now: Double = Date().timeIntervalSince1970,
        localizer: Localizer
    ) -> String? {
        guard let primary = snapshot.primaryBucket?.primary,
              let used = clamp(primary.usedPercent),
              let roundedRemaining = displayPercent(100 - used) else { return nil }
        let value = display == .used ? 100 - roundedRemaining : roundedRemaining
        return localizer.text("panel.value", [
            "value": String(value),
            "reset": resetText(timestamp: primary.resetsAt, now: now, localizer: localizer),
        ])
    }
}
