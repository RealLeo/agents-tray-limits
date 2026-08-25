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
        case .pipboy3000:
            PipBoy3000View(store: store, theme: theme!)
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

struct PipBoy3000View: View {
    @ObservedObject var store: AppStore
    let theme: LoadedTheme

    var body: some View {
        let palette = ThemePalette(theme.manifest.macDefinition.palette)
        VStack(alignment: .leading, spacing: 12) {
            HStack {
                Text("PIP-BOY 3000").font(.system(size: 16, weight: .black, design: .monospaced))
                Spacer()
                ProfilePicker(store: store).frame(width: 180)
            }
            Divider().overlay(palette.primary)
            HStack(alignment: .top, spacing: 18) {
                ThemeArtView(
                    theme: theme,
                    status: store.activeStatus ?? .worried,
                    animate: store.preferences.themeAnimation
                )
                .frame(width: 170, height: 170)
                if let profile = store.activeProfile {
                    ScrollView { StatusDetailView(store: store, profile: profile) }
                }
            }
            Divider().overlay(palette.primary)
            MenuActions(store: store)
        }
        .padding(18)
        .frame(width: 540, height: 390)
        .background(palette.background)
        .foregroundStyle(palette.text)
        .tint(palette.primary)
        .font(.system(size: 12, design: .monospaced))
        .shadow(color: palette.primary.opacity(0.25), radius: 8)
    }
}

private struct ThemePalette {
    let background: Color
    let surface: Color
    let primary: Color
    let text: Color

    init(_ values: [String: String]?) {
        background = Color(hex: values?["background"] ?? "#101510")
        surface = Color(hex: values?["surface"] ?? "#182018")
        primary = Color(hex: values?["primary"] ?? "#56E36B")
        text = Color(hex: values?["text"] ?? "#DDF6DD")
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
