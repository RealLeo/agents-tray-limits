import SwiftUI

@main
struct AgentsTrayLimitsApp: App {
    @StateObject private var store = AppStore()

    var body: some Scene {
        MenuBarExtra {
            MenuContentView(store: store)
        } label: {
            HStack(spacing: 4) {
                Text(store.panelText)
                if store.preferences.showIcon {
                    if let panelImage = store.panelImage {
                        Image(nsImage: panelImage)
                            .resizable()
                            .scaledToFit()
                            .frame(width: 18, height: 18)
                    } else {
                        Image(systemName: store.activeStatus?.symbolName ?? "gauge.with.dots.needle.50percent")
                    }
                }
            }
            .accessibilityLabel(accessibilityLabel)
        }
        .menuBarExtraStyle(.window)

        Settings {
            SettingsView(store: store)
        }
    }

    private var accessibilityLabel: String {
        guard let profile = store.activeProfile else { return store.panelText }
        return store.localizer.text("app.accessibleProfileValue", [
            "profile": profile.label,
            "value": store.panelText,
        ])
    }
}

extension LimitStatus {
    var symbolName: String {
        switch self {
        case .good: return "gauge.with.dots.needle.33percent"
        case .worried: return "gauge.with.dots.needle.67percent"
        case .critical: return "exclamationmark.triangle.fill"
        case .dead: return "xmark.octagon.fill"
        }
    }
}
