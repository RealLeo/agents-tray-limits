// swift-tools-version: 5.9
import PackageDescription

var products: [Product] = [
    .library(name: "AgentsTrayCore", targets: ["AgentsTrayCore"]),
    .executable(name: "AgentsTrayCollector", targets: ["AgentsTrayCollector"]),
]
var targets: [Target] = [
    .target(name: "AgentsTrayCore"),
    .executableTarget(name: "AgentsTrayCollector", dependencies: ["AgentsTrayCore"]),
    .testTarget(name: "AgentsTrayCoreTests", dependencies: ["AgentsTrayCore"]),
]

#if os(macOS)
products.append(.executable(name: "AgentsTrayMacApp", targets: ["AgentsTrayMacApp"]))
targets.append(.executableTarget(name: "AgentsTrayMacApp", dependencies: ["AgentsTrayCore"]))
#endif

let package = Package(
    name: "AgentsTrayLimits",
    platforms: [.macOS(.v13)],
    products: products,
    targets: targets
)
