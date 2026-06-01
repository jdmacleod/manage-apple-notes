// swift-tools-version: 6.2
import PackageDescription

let package = Package(
    name: "apple-llm",
    platforms: [.macOS(.v26)],
    targets: [
        // Pure-logic library — no FoundationModels dependency; imported by tests.
        .target(
            name: "AppleLLMCore",
            path: "Sources/AppleLLMCore"
        ),
        // Thin entry point: reads stdin, calls FoundationModels, writes stdout.
        .executableTarget(
            name: "apple-llm",
            dependencies: ["AppleLLMCore"],
            path: "Sources/AppleLLM"
        ),
        .testTarget(
            name: "AppleLLMTests",
            dependencies: ["AppleLLMCore"],
            path: "Tests/AppleLLMTests"
        ),
    ]
)
