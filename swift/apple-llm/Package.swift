// swift-tools-version: 6.2
import PackageDescription

let package = Package(
    name: "apple-llm",
    platforms: [.macOS(.v26)],
    targets: [
        .executableTarget(name: "apple-llm", path: "Sources/AppleLLM"),
    ]
)
