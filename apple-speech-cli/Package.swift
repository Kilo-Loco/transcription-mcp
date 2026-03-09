// swift-tools-version: 6.2

import PackageDescription

let package = Package(
    name: "apple-speech-cli",
    platforms: [.macOS(.v26)],
    targets: [
        .executableTarget(
            name: "SpeechCLI",
            path: "Sources/SpeechCLI"
        ),
    ]
)
