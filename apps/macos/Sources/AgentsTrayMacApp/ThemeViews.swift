import AgentsTrayCore
import AppKit
import SwiftUI

struct ThemeContainerView: View {
    @ObservedObject var store: AppStore

    var body: some View {
        let theme = store.selectedTheme
        switch theme?.manifest.macDefinition.layout ?? .classic {
        case .classic:
            ClassicMenuView(store: store, theme: theme)
        case .pipboy2000:
            PipBoy2000View(store: store, theme: theme!)
        case .agentsAmp:
            AgentsAmpView(store: store, theme: theme!)
        }
    }
}

struct ThemeArtView: View {
    let theme: LoadedTheme?
    let status: LimitStatus
    let animate: Bool
    @Environment(\.accessibilityReduceMotion) private var reduceMotion
    @State private var frameIndex = 0

    private var frameURLs: [URL] {
        guard let theme else { return [] }
        let relative = theme.manifest.frameAnimation?.frames[status] ?? [theme.manifest.art[status]]
        return relative.map { theme.root.appendingPathComponent($0) }
    }

    var body: some View {
        Group {
            if let image = image(at: frameIndex) {
                Image(nsImage: image).resizable().scaledToFit()
            } else {
                Image(systemName: status.symbolName).resizable().scaledToFit().padding(24)
            }
        }
        .accessibilityLabel(status.rawValue.capitalized)
        .task(id: "\(theme?.id ?? "classic")-\(status.rawValue)-\(animate)-\(reduceMotion)") {
            let frames = frameURLs
            guard frames.count > 1 else { frameIndex = 0; return }
            frameIndex = frames.count - 1
            guard animate, !reduceMotion, let animation = theme?.manifest.frameAnimation else { return }
            for index in frames.indices {
                if Task.isCancelled { return }
                frameIndex = index
                try? await Task.sleep(nanoseconds: UInt64(animation.interval(for: status)) * 1_000_000)
            }
        }
    }

    private func image(at index: Int) -> NSImage? {
        let frames = frameURLs
        guard !frames.isEmpty else { return nil }
        return NSImage(contentsOf: frames[min(max(index, 0), frames.count - 1)])
    }
}

struct PipBoy2000View: View {
    @ObservedObject var store: AppStore
    let theme: LoadedTheme

    var body: some View {
        let palette = ThemePalette(theme.manifest.macDefinition.palette)
        ZStack {
            palette.background
            if let shell = NSImage(contentsOf: theme.root.appendingPathComponent("assets/ui/device-shell-v3.png")) {
                Image(nsImage: shell).resizable().scaledToFill()
            }
            HStack(alignment: .top, spacing: 26) {
                VStack(spacing: 12) {
                    Text("PIP-BOY 2000").font(.system(size: 13, weight: .black, design: .monospaced))
                    ThemeArtView(
                        theme: theme,
                        status: store.activeStatus ?? .worried,
                        animate: store.preferences.themeAnimation
                    )
                    .frame(width: 162, height: 162)
                    ProfilePicker(store: store).frame(width: 180)
                }
                .foregroundStyle(palette.text)
                .padding(.top, 26)

                VStack(alignment: .leading, spacing: 12) {
                    Text(store.panelText)
                        .font(.system(size: 24, weight: .bold, design: .monospaced))
                        .foregroundStyle(palette.primary)
                    if let profile = store.activeProfile {
                        ScrollView {
                            StatusDetailView(store: store, profile: profile)
                                .foregroundStyle(palette.text)
                        }
                    }
                    Spacer()
                    MenuActions(store: store).foregroundStyle(palette.primary)
                }
                .padding(18)
                .background(palette.surface.opacity(0.9))
                .clipShape(RoundedRectangle(cornerRadius: 8))
            }
            .padding(.horizontal, 34)
            .padding(.vertical, 32)
        }
        .frame(width: 680, height: 520)
        .font(.system(size: 12, design: .monospaced))
    }
}

private enum AgentsAmpMode: String {
    case normal
    case loading
    case error
}

struct AgentsAmpView: View {
    @ObservedObject var store: AppStore
    let theme: LoadedTheme
    @Environment(\.accessibilityReduceMotion) private var reduceMotion
    @State private var levels = Array(repeating: 2, count: 28)
    @State private var peaks = Array(repeating: 2, count: 28)

    private var palette: ThemePalette { ThemePalette(theme.manifest.macDefinition.palette) }
    private var snapshot: UsageSnapshot? { store.activeSnapshot }
    private var mode: AgentsAmpMode {
        guard let snapshot else { return .loading }
        return snapshot.ok ? .normal : .error
    }
    private var status: LimitStatus { store.activeStatus ?? (mode == .error ? .dead : .worried) }
    private var remaining: Int? {
        guard let snapshot else { return nil }
        return UsageFormatting.displayPercent(UsageFormatting.remaining(snapshot))
    }
    private var statusColor: Color {
        switch status {
        case .good: return palette.primary
        case .worried: return palette.warning
        case .critical: return palette.critical
        case .dead: return palette.muted
        }
    }

    var body: some View {
        ZStack {
            palette.background
            if let shell = NSImage(
                contentsOf: theme.root.appendingPathComponent("assets/ui/chrome-shell-v2.png")
            ) {
                Image(nsImage: shell)
                    .resizable()
                    .interpolation(.none)
                    .frame(width: 680, height: 520)
            }
            VStack(spacing: 4) {
                playerPanel.frame(height: 160)
                equalizerPanel.frame(height: 138)
                playlistPanel.frame(height: 214)
            }
        }
        .frame(width: 680, height: 520)
        .foregroundStyle(palette.text)
        .font(.system(size: 10, weight: .medium, design: .monospaced))
        .task(id: "\(mode.rawValue)-\(status.rawValue)-\(store.preferences.themeAnimation)-\(reduceMotion)") {
            resetEqualizer()
            guard mode == .normal, store.preferences.themeAnimation, !reduceMotion else { return }
            while !Task.isCancelled {
                do {
                    try await Task.sleep(nanoseconds: 120_000_000)
                } catch {
                    return
                }
                guard !Task.isCancelled else { return }
                advanceEqualizer()
            }
        }
    }

    private var playerPanel: some View {
        AgentsAmpModule(title: store.localizer.text("agentsAmp.player"), palette: palette) {
            VStack(spacing: 8) {
                HStack(spacing: 8) {
                    VStack(alignment: .leading, spacing: 7) {
                        AgentsAmpLED(label: "PWR", color: palette.primary)
                        AgentsAmpLED(label: "NET", color: palette.primary)
                        AgentsAmpLED(label: "LMT", color: palette.warning)
                    }
                    .frame(width: 54, alignment: .leading)
                    .accessibilityHidden(true)

                    ZStack {
                        Color.clear
                        HStack(spacing: 0) {
                            VStack(alignment: .leading, spacing: 3) {
                                Text(accountLine)
                                    .font(.system(size: 13, weight: .black, design: .monospaced))
                                    .lineLimit(1)
                                Text(providerLine)
                                    .font(.system(size: 9, weight: .bold, design: .monospaced))
                                    .foregroundStyle(palette.secondary)
                                    .lineLimit(1)
                                Spacer(minLength: 0)
                                Text(statusText)
                                    .font(.system(size: 21, weight: .black, design: .monospaced))
                                    .lineLimit(1)
                            }
                            .frame(maxWidth: .infinity, alignment: .leading)
                            Rectangle()
                                .fill(Color(hex: "#35404B"))
                                .frame(width: 2, height: 70)
                            VStack(spacing: 3) {
                                Text(store.localizer.text("agentsAmp.remaining"))
                                    .font(.system(size: 9, weight: .bold, design: .monospaced))
                                HStack(alignment: .bottom, spacing: 4) {
                                    AgentsAmpSevenSegmentNumber(
                                        text: remaining.map(String.init) ?? "—",
                                        color: statusColor,
                                        digitWidth: 22,
                                        digitHeight: 44
                                    )
                                    Text("%")
                                        .font(.system(size: 24, weight: .black, design: .monospaced))
                                        .padding(.bottom, 2)
                                }
                            }
                            .frame(width: 138)
                        }
                        .padding(.horizontal, 12)
                        .padding(.vertical, 8)
                        .foregroundStyle(statusColor)
                    }
                    .frame(maxWidth: .infinity, minHeight: 86, maxHeight: 86)

                    VStack(spacing: 12) {
                        HStack(spacing: 7) {
                            AgentsAmpDecorativeKey("EQ", palette: palette)
                            AgentsAmpDecorativeKey("PL", palette: palette)
                        }
                        HStack(spacing: 6) {
                            ZStack(alignment: .leading) {
                                Rectangle().fill(Color.black).frame(height: 5)
                                Rectangle()
                                    .fill(LinearGradient(
                                        colors: [palette.primary, palette.warning],
                                        startPoint: .leading,
                                        endPoint: .trailing
                                    ))
                                    .frame(width: 58, height: 3)
                                Rectangle()
                                    .fill(Color(hex: "#DCE0E8"))
                                    .frame(width: 9, height: 15)
                                    .offset(x: 55)
                            }
                            Text("◖))")
                                .font(.system(size: 10, weight: .black, design: .monospaced))
                        }
                    }
                    .frame(width: 120)
                    .accessibilityHidden(true)
                    .allowsHitTesting(false)
                }
                HStack(spacing: 8) {
                    ForEach(["◀◀", "▶", "▮▮", "■", "▶▶", "▲", "SHUF", "REP"], id: \.self) { label in
                        AgentsAmpDecorativeKey(label, palette: palette)
                            .frame(maxWidth: .infinity)
                    }
                }
                .accessibilityHidden(true)
                .allowsHitTesting(false)
            }
            .padding(.horizontal, 14)
            .padding(.bottom, 7)
        }
    }

    private var equalizerPanel: some View {
        AgentsAmpModule(title: store.localizer.text("agentsAmp.equalizer"), palette: palette) {
            HStack(spacing: 8) {
                VStack(spacing: 2) {
                    HStack(alignment: .bottom, spacing: 4) {
                        ForEach(0..<28, id: \.self) { index in
                            VStack(spacing: 2) {
                                ForEach((1...12).reversed(), id: \.self) { level in
                                    Rectangle()
                                        .fill(equalizerCellColor(band: index, level: level))
                                        .frame(width: 6, height: 4)
                                }
                            }
                        }
                    }
                    HStack(spacing: 0) {
                        ForEach(["31", "62", "125", "250", "500", "1K", "2K", "4K", "8K", "16K"], id: \.self) { label in
                            Text(label)
                                .font(.system(size: 6, weight: .bold, design: .monospaced))
                                .frame(maxWidth: .infinity)
                        }
                    }
                    .foregroundStyle(palette.secondary)
                }
                .padding(.horizontal, 7)
                .padding(.vertical, 5)
                .frame(width: 296, height: 96)
                .background(Color.clear)
                .accessibilityLabel(store.localizer.text("agentsAmp.equalizer"))

                HStack(spacing: 1) {
                    VStack(spacing: 6) {
                        ForEach(["+12", "+6", "0", "-6", "-12"], id: \.self) { label in
                            Text(label)
                        }
                    }
                    .font(.system(size: 6, weight: .bold, design: .monospaced))
                    .foregroundStyle(palette.secondary)
                    ForEach(["PRE", "60", "170", "310", "600", "1K", "3K", "6K", "12K", "16K"], id: \.self) { label in
                        AgentsAmpSlider(label: label, palette: palette)
                    }
                }
                .frame(maxWidth: .infinity)
                .accessibilityHidden(true)
                .allowsHitTesting(false)

                VStack(spacing: 3) {
                    Text(store.localizer.text("agentsAmp.resetTime"))
                        .font(.system(size: 8, weight: .bold, design: .monospaced))
                        .foregroundStyle(palette.secondary)
                    ForEach(Array(resetCounters.enumerated()), id: \.offset) { _, counter in
                        HStack(spacing: 3) {
                            AgentsAmpSevenSegmentNumber(
                                text: counter.value.map(String.init) ?? "—",
                                color: statusColor,
                                digitWidth: 10,
                                digitHeight: 23
                            )
                            Text(counter.unit)
                                .font(.system(size: 6, weight: .black, design: .monospaced))
                                .foregroundStyle(statusColor)
                                .lineLimit(1)
                        }
                        .frame(maxWidth: .infinity, alignment: .leading)
                        .padding(.horizontal, 4)
                        .padding(.vertical, 2)
                        .background(Color(hex: "#020806"))
                    }
                }
                .frame(width: 82, height: 96)
                .background(Color.clear)
            }
            .padding(.horizontal, 14)
            .padding(.bottom, 7)
        }
    }

    private var playlistPanel: some View {
        AgentsAmpModule(title: store.localizer.text("agentsAmp.playlist"), palette: palette) {
            VStack(spacing: 7) {
                ScrollView {
                    LazyVStack(alignment: .leading, spacing: 2) {
                        profileRows
                        if let snapshot {
                            if snapshot.ok {
                                limitRows(snapshot)
                            } else {
                                Text(snapshot.message ?? store.localizer.text("agentsAmp.offline"))
                                    .foregroundStyle(palette.critical)
                            }
                        } else {
                            Text(store.localizer.text("agentsAmp.loading"))
                                .foregroundStyle(palette.secondary)
                        }
                    }
                    .padding(.horizontal, 7)
                    .padding(.vertical, 4)
                    .frame(maxWidth: .infinity, alignment: .leading)
                }
                .frame(height: 141)
                .background(Color.clear)

                HStack(spacing: 4) {
                    AgentsAmpActionButton(
                        store.localizer.text("agentsAmp.refresh"), assetKey: "refresh",
                        systemImage: "arrow.clockwise", width: 140, theme: theme, palette: palette
                    ) {
                        Task { await store.refreshAll() }
                    }
                    .disabled(!store.refreshing.isEmpty)
                    AgentsAmpActionButton(
                        store.localizer.text("agentsAmp.profile"), assetKey: "profile",
                        systemImage: "arrow.up.right.square", width: 124, theme: theme,
                        palette: palette
                    ) {
                        if let provider = store.activeProfile?.provider { store.openProvider(provider) }
                    }
                    AgentsAmpActionButton(
                        store.localizer.text("agentsAmp.settings"), assetKey: "settings",
                        systemImage: "gearshape", width: 210, theme: theme, palette: palette
                    ) {
                        store.showSettings()
                    }
                    AgentsAmpActionButton(
                        store.localizer.text("agentsAmp.close"), assetKey: "close",
                        systemImage: "xmark", width: 162, theme: theme, palette: palette
                    ) {
                        store.closeMenu()
                    }
                }
                .frame(height: 31)
            }
            .padding(.horizontal, 14)
            .padding(.bottom, 8)
        }
    }

    @ViewBuilder private var profileRows: some View {
        Text(store.localizer.text("profiles.section").uppercased())
            .font(.system(size: 8, weight: .black, design: .monospaced))
            .foregroundStyle(palette.secondary)
            .frame(maxWidth: .infinity, alignment: .leading)
            .overlay(alignment: .bottom) { Rectangle().fill(Color(hex: "#35405D")).frame(height: 1) }
        ForEach(store.preferences.profiles.profiles) { profile in
            Button {
                store.selectProfile(profile.id)
            } label: {
                HStack(spacing: 5) {
                    Text(profile.id == store.preferences.activeProfileID ? "●" : "○")
                        .foregroundStyle(palette.warning)
                    Text("\(profile.provider.displayName) · \(profile.label)")
                        .lineLimit(1)
                    Spacer()
                    Text(profileSummary(profile))
                        .monospacedDigit()
                        .lineLimit(1)
                }
                .foregroundStyle(profile.id == store.preferences.activeProfileID ? statusColor : palette.primary)
                .font(.system(size: 9, weight: .bold, design: .monospaced))
                .padding(.horizontal, 3)
                .padding(.vertical, 1)
                .background(profile.id == store.preferences.activeProfileID ? Color(hex: "#18213A") : .clear)
                .overlay(Rectangle().stroke(
                    profile.id == store.preferences.activeProfileID ? palette.muted : .clear,
                    lineWidth: 1
                ))
                .contentShape(Rectangle())
            }
            .buttonStyle(.plain)
            .accessibilityLabel(store.localizer.text("profiles.select", ["profile": profile.label]))
        }
    }

    @ViewBuilder private func limitRows(_ snapshot: UsageSnapshot) -> some View {
        Text(store.localizer.text("menu.limits").uppercased())
            .font(.system(size: 8, weight: .black, design: .monospaced))
            .foregroundStyle(palette.secondary)
            .frame(maxWidth: .infinity, alignment: .leading)
            .overlay(alignment: .bottom) { Rectangle().fill(Color(hex: "#35405D")).frame(height: 1) }
        HStack(spacing: 4) {
            Text(store.localizer.text("agentsAmp.columnWindow")).frame(width: 192, alignment: .leading)
            Text(store.localizer.text("agentsAmp.columnReset")).frame(width: 220, alignment: .leading)
            Text(store.localizer.text("agentsAmp.columnScale")).frame(width: 120, alignment: .leading)
            Text(store.localizer.text(store.preferences.panelDisplay == .used
                ? "agentsAmp.usedShort"
                : "agentsAmp.remainingShort"))
                .frame(maxWidth: .infinity, alignment: .trailing)
        }
        .font(.system(size: 7, weight: .black, design: .monospaced))
        .foregroundStyle(palette.secondary)
        .textCase(.uppercase)
        ForEach(Array(buckets(snapshot).enumerated()), id: \.offset) { _, entry in
            let (name, bucket) = entry
            if let primary = bucket.primary {
                AgentsAmpLimitRow(
                    bucket: name,
                    title: store.localizer.text("menu.primary"),
                    window: primary,
                    display: store.preferences.panelDisplay,
                    palette: palette,
                    localizer: store.localizer
                )
            }
            if let secondary = bucket.secondary {
                AgentsAmpLimitRow(
                    bucket: name,
                    title: store.localizer.text("menu.secondary"),
                    window: secondary,
                    display: store.preferences.panelDisplay,
                    palette: palette,
                    localizer: store.localizer
                )
            }
        }
        if store.preferences.showTokens,
           let summary = snapshot.usage?.objectValue?["summary"]?.objectValue {
            Text(store.localizer.text("menu.activity").uppercased())
                .font(.system(size: 8, weight: .black, design: .monospaced))
                .foregroundStyle(palette.secondary)
                .padding(.top, 2)
                .frame(maxWidth: .infinity, alignment: .leading)
                .overlay(alignment: .bottom) { Rectangle().fill(Color(hex: "#35405D")).frame(height: 1) }
            ForEach(summary.keys.sorted(), id: \.self) { key in
                HStack {
                    Text(key.replacingOccurrences(of: "([a-z])([A-Z])", with: "$1 $2", options: .regularExpression).uppercased())
                    Spacer()
                    Text(formatJSON(summary[key])).monospacedDigit()
                }
                .foregroundStyle(palette.primary)
                .font(.system(size: 8, weight: .bold, design: .monospaced))
                .padding(.horizontal, 3)
            }
        }
    }

    private var accountLine: String {
        guard let profile = store.activeProfile else { return "—" }
        let account = snapshot?.account?.objectValue
        let plan = account?["planType"]?.stringValue ?? account?["plan_type"]?.stringValue
        return [profile.label, plan ?? profile.provider.displayName]
            .compactMap { value in
                guard let value, !value.isEmpty else { return nil }
                return value
            }
            .joined(separator: " · ")
    }

    private var providerLine: String {
        store.activeProfile?.provider.displayName ?? "—"
    }

    private var statusText: String {
        switch mode {
        case .loading: return store.localizer.text("agentsAmp.loading")
        case .error: return store.localizer.text("agentsAmp.offline")
        case .normal: return store.localizer.text("status.\(status.rawValue)")
        }
    }

    private var resetCounters: [AgentsAmpResetPart] {
        guard let timestamp = snapshot?.primaryBucket?.primary?.resetsAt else {
            return [AgentsAmpResetPart(value: nil, unit: "—"), AgentsAmpResetPart(value: nil, unit: "")]
        }
        let totalMinutes = max(
            0,
            Int(ceil((timestamp - Date().timeIntervalSince1970) / 60))
        )
        let days = totalMinutes / 1440
        let hours = (totalMinutes % 1440) / 60
        let minutes = totalMinutes % 60
        if days > 0 {
            return [
                AgentsAmpResetPart(value: days, unit: resetUnit("time.day", days)),
                AgentsAmpResetPart(value: hours, unit: resetUnit("time.hour", hours)),
            ]
        }
        if hours > 0 {
            return [
                AgentsAmpResetPart(value: hours, unit: resetUnit("time.hour", hours)),
                AgentsAmpResetPart(value: minutes, unit: resetUnit("time.minute", minutes)),
            ]
        }
        return [
            AgentsAmpResetPart(value: minutes, unit: resetUnit("time.minute", minutes)),
            AgentsAmpResetPart(value: nil, unit: ""),
        ]
    }

    private func resetUnit(_ key: String, _ value: Int) -> String {
        store.localizer.plural(key, count: value)
            .replacingOccurrences(of: String(value), with: "")
            .trimmingCharacters(in: .whitespacesAndNewlines)
            .uppercased()
    }

    private func equalizerCellColor(band: Int, level: Int) -> Color {
        if mode == .error {
            return level <= levels[band] ? palette.muted : Color(hex: "#151923")
        }
        if level == peaks[band] { return palette.warning }
        if level <= levels[band] { return statusColor }
        return Color(hex: "#0B2C10")
    }

    private func profileSummary(_ profile: AgentProfile) -> String {
        if store.refreshing.contains(profile.id), store.snapshots[profile.id] == nil {
            return store.localizer.text("profiles.refreshing")
        }
        guard let snapshot = store.snapshots[profile.id] else {
            return store.localizer.text("profiles.pending")
        }
        guard snapshot.ok else { return store.localizer.text("profiles.error") }
        guard let value = UsageFormatting.displayPercent(UsageFormatting.remaining(snapshot)) else { return "—" }
        return store.localizer.text("profiles.remaining", ["value": String(value)])
    }

    private func buckets(_ snapshot: UsageSnapshot) -> [(String, RateLimitBucket)] {
        if store.preferences.showAllBuckets,
           let byID = snapshot.rateLimits?.rateLimitsByLimitId, !byID.isEmpty {
            return byID.sorted { $0.key.localizedCaseInsensitiveCompare($1.key) == .orderedAscending }
                .map { ($0.value.limitName ?? $0.key, $0.value) }
        }
        if let bucket = snapshot.primaryBucket {
            return [(bucket.limitName ?? bucket.limitId ?? snapshot.provider.displayName, bucket)]
        }
        return []
    }

    private func formatJSON(_ value: JSONValue?) -> String {
        switch value {
        case .number(let number): return number.formatted(.number.precision(.fractionLength(0)))
        case .string(let string): return string
        default: return "—"
        }
    }

    private func resetEqualizer() {
        if mode == .error {
            levels = Array(repeating: 1, count: 28)
        } else {
            levels = (0..<28).map { 2 + ($0 * 5 % 4) }
        }
        peaks = levels
    }

    private func advanceEqualizer() {
        var nextLevels = levels
        var nextPeaks = peaks
        for index in 0..<28 {
            let target = 1 + Int(((Double.random(in: 0..<1) + Double.random(in: 0..<1)) / 2) * 12)
            let current = levels[index]
            let level = target > current ? min(target, current + 3) : max(target, current - 2)
            nextLevels[index] = min(12, max(1, level))
            nextPeaks[index] = level >= peaks[index] ? level : max(level, peaks[index] - 1)
        }
        levels = nextLevels
        peaks = nextPeaks
    }
}

private struct AgentsAmpResetPart {
    let value: Int?
    let unit: String
}

private struct AgentsAmpModule<Content: View>: View {
    let title: String
    let palette: ThemePalette
    let content: Content

    init(title: String, palette: ThemePalette, @ViewBuilder content: () -> Content) {
        self.title = title
        self.palette = palette
        self.content = content()
    }

    var body: some View {
        ZStack(alignment: .top) {
            Color.clear
            content.padding(.top, 22)
            Text(title)
                .font(.system(size: 9, weight: .black, design: .monospaced))
                .foregroundStyle(palette.text)
                .lineLimit(1)
                .fixedSize(horizontal: true, vertical: false)
            .padding(.top, 3)
            .accessibilityHidden(true)
        }
        .clipped()
    }
}

private struct AgentsAmpLED: View {
    let label: String
    let color: Color

    var body: some View {
        HStack(spacing: 6) {
            Circle().fill(color).frame(width: 8, height: 8).shadow(color: color, radius: 2)
            Text(label).font(.system(size: 8, weight: .bold, design: .monospaced))
        }
    }
}

private struct AgentsAmpSevenSegmentNumber: View {
    let text: String
    let color: Color
    let digitWidth: CGFloat
    let digitHeight: CGFloat

    var body: some View {
        HStack(spacing: 4) {
            ForEach(Array(text.enumerated()), id: \.offset) { _, character in
                AgentsAmpSevenSegmentDigit(
                    character: character,
                    color: color,
                    width: digitWidth,
                    height: digitHeight
                )
            }
        }
        .fixedSize()
        .accessibilityLabel(text)
    }
}

private struct AgentsAmpSevenSegmentDigit: View {
    let character: Character
    let color: Color
    let width: CGFloat
    let height: CGFloat

    private var enabled: Set<Character> {
        let map: [Character: String] = [
            "0": "abcdef", "1": "bc", "2": "abdeg", "3": "abcdg", "4": "bcfg",
            "5": "acdfg", "6": "acdefg", "7": "abc", "8": "abcdefg", "9": "abcdfg",
            "—": "g", "-": "g",
        ]
        return Set(map[character] ?? "")
    }

    var body: some View {
        let thickness = max(3, width / 6)
        let verticalHeight = (height - thickness * 3) / 2
        ZStack(alignment: .topLeading) {
            segment("a").frame(width: width - thickness * 2, height: thickness)
                .offset(x: thickness)
            segment("b").frame(width: thickness, height: verticalHeight)
                .offset(x: width - thickness, y: thickness)
            segment("c").frame(width: thickness, height: verticalHeight)
                .offset(x: width - thickness, y: thickness * 2 + verticalHeight)
            segment("d").frame(width: width - thickness * 2, height: thickness)
                .offset(x: thickness, y: height - thickness)
            segment("e").frame(width: thickness, height: verticalHeight)
                .offset(y: thickness * 2 + verticalHeight)
            segment("f").frame(width: thickness, height: verticalHeight)
                .offset(y: thickness)
            segment("g").frame(width: width - thickness * 2, height: thickness)
                .offset(x: thickness, y: thickness + verticalHeight)
        }
        .frame(width: width, height: height)
    }

    private func segment(_ name: Character) -> some View {
        Rectangle()
            .fill(enabled.contains(name) ? color : Color(hex: "#09240B"))
            .shadow(color: enabled.contains(name) ? color.opacity(0.7) : .clear, radius: 2)
    }
}

private struct AgentsAmpDecorativeKey: View {
    let label: String
    let palette: ThemePalette

    init(_ label: String, palette: ThemePalette) {
        self.label = label
        self.palette = palette
    }

    var body: some View {
        Text(label)
            .font(.system(size: 9, weight: .black, design: .monospaced))
            .foregroundStyle(palette.text)
            .frame(minWidth: 36, minHeight: 25)
            .background(Color.clear)
    }
}

private struct AgentsAmpSlider: View {
    let label: String
    let palette: ThemePalette

    var body: some View {
        VStack(spacing: 3) {
            Color.clear.frame(width: 13, height: 58)
            Text(label)
                .font(.system(size: 7, weight: .bold, design: .monospaced))
                .foregroundStyle(palette.secondary)
        }
        .frame(maxWidth: .infinity)
    }
}

private struct AgentsAmpLimitRow: View {
    let bucket: String
    let title: String
    let window: LimitWindow
    let display: PanelDisplay
    let palette: ThemePalette
    let localizer: Localizer

    var body: some View {
        let used = UsageFormatting.clamp(window.usedPercent) ?? 0
        let remaining = 100 - used
        let value = display == .used ? used : remaining
        HStack(spacing: 4) {
            VStack(alignment: .leading, spacing: 0) {
                Text("\(bucket) · \(title)")
                    .font(.system(size: 8, weight: .black, design: .monospaced))
                    .lineLimit(1)
                Text(duration)
                    .font(.system(size: 7, weight: .bold, design: .monospaced))
                    .foregroundStyle(palette.secondary)
            }
            .frame(width: 192, alignment: .leading)
            Text(UsageFormatting.resetText(timestamp: window.resetsAt, localizer: localizer))
                .font(.system(size: 7, weight: .medium, design: .monospaced))
                .foregroundStyle(palette.secondary)
                .lineLimit(1)
                .frame(width: 220, alignment: .leading)
            GeometryReader { geometry in
                ZStack(alignment: .leading) {
                    Rectangle().fill(Color(hex: "#020604"))
                        .overlay(Rectangle().stroke(Color(hex: "#35405A"), lineWidth: 1))
                    Rectangle().fill(progressColor(used)).frame(
                        width: geometry.size.width * CGFloat(value / 100)
                    )
                }
            }
            .frame(width: 120, height: 6)
            Text("\(Int(value.rounded()))%")
                .font(.system(size: 9, weight: .black, design: .monospaced))
                .monospacedDigit()
                .foregroundStyle(progressColor(used))
                .frame(maxWidth: .infinity, alignment: .trailing)
        }
        .foregroundStyle(palette.primary)
        .padding(.horizontal, 3)
        .padding(.vertical, 2)
        .overlay(alignment: .bottom) { Rectangle().fill(Color(hex: "#17223C")).frame(height: 1) }
    }

    private var duration: String {
        let minutes = max(0, Int((window.windowDurationMins ?? 0).rounded()))
        if minutes > 0, minutes % 1440 == 0 { return localizer.plural("time.day", count: minutes / 1440) }
        if minutes > 0, minutes % 60 == 0 { return localizer.plural("time.hour", count: minutes / 60) }
        return localizer.plural("time.minute", count: minutes)
    }

    private func progressColor(_ used: Double) -> Color {
        if used >= 90 { return palette.critical }
        if used >= 70 { return palette.warning }
        return palette.primary
    }
}

private struct AgentsAmpActionButton: View {
    let title: String
    let assetKey: String
    let systemImage: String
    let width: CGFloat
    let theme: LoadedTheme
    let palette: ThemePalette
    let action: () -> Void
    @State private var hovered = false
    @FocusState private var focused: Bool

    init(
        _ title: String, assetKey: String, systemImage: String, width: CGFloat,
        theme: LoadedTheme, palette: ThemePalette, action: @escaping () -> Void
    ) {
        self.title = title
        self.assetKey = assetKey
        self.systemImage = systemImage
        self.width = width
        self.theme = theme
        self.palette = palette
        self.action = action
    }

    var body: some View {
        Button(action: action) {
            Label(title, systemImage: systemImage)
                .font(.system(size: 8, weight: .black, design: .monospaced))
                .lineLimit(1)
                .frame(maxWidth: .infinity, maxHeight: .infinity)
        }
        .buttonStyle(AgentsAmpRasterButtonStyle(
            assetKey: assetKey, width: width, theme: theme
        ))
        .frame(width: width, height: 31)
        .focused($focused)
        .foregroundStyle(palette.text)
        .overlay(Rectangle().stroke(
            hovered || focused ? palette.warning : .clear, lineWidth: 1
        ))
        .onHover { hovered = $0 }
    }
}

private struct AgentsAmpRasterButtonStyle: ButtonStyle {
    let assetKey: String
    let width: CGFloat
    let theme: LoadedTheme
    @Environment(\.isEnabled) private var isEnabled

    func makeBody(configuration: Configuration) -> some View {
        let state = configuration.isPressed ? "pressed" : "idle"
        let path = theme.root.appendingPathComponent(
            "assets/ui/button-\(assetKey)-\(state)-v1.png"
        )
        return ZStack {
            if let image = NSImage(contentsOf: path) {
                Image(nsImage: image)
                    .resizable()
                    .interpolation(.none)
                    .frame(width: width, height: 31)
            } else {
                Color(hex: "#10142A")
            }
            configuration.label
                .offset(y: configuration.isPressed ? 1 : 0)
        }
        .frame(width: width, height: 31)
        .contentShape(Rectangle())
        .opacity(isEnabled ? 1 : 0.42)
    }
}

private struct ThemePalette {
    let background: Color
    let surface: Color
    let primary: Color
    let secondary: Color
    let text: Color
    let muted: Color
    let warning: Color
    let critical: Color

    init(_ values: [String: String]?) {
        background = Color(hex: values?["background"] ?? "#101510")
        surface = Color(hex: values?["surface"] ?? "#182018")
        primary = Color(hex: values?["primary"] ?? "#56E36B")
        secondary = Color(hex: values?["secondary"] ?? "#70D7FF")
        text = Color(hex: values?["text"] ?? "#DDF6DD")
        muted = Color(hex: values?["muted"] ?? "#8992AA")
        warning = Color(hex: values?["warning"] ?? "#F2D15C")
        critical = Color(hex: values?["critical"] ?? "#FF4D6D")
    }
}

private extension Color {
    init(hex: String) {
        let value = hex.trimmingCharacters(in: CharacterSet(charactersIn: "#"))
        var number: UInt64 = 0
        Scanner(string: value).scanHexInt64(&number)
        let hasAlpha = value.count == 8
        let red = Double((number >> (hasAlpha ? 24 : 16)) & 0xFF) / 255
        let green = Double((number >> (hasAlpha ? 16 : 8)) & 0xFF) / 255
        let blue = Double((number >> (hasAlpha ? 8 : 0)) & 0xFF) / 255
        let alpha = hasAlpha ? Double(number & 0xFF) / 255 : 1
        self.init(.sRGB, red: red, green: green, blue: blue, opacity: alpha)
    }
}
