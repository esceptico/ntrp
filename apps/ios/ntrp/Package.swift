// swift-tools-version: 6.0

import PackageDescription

let package = Package(
    name: "NtrpMobile",
    platforms: [.iOS(.v18), .macOS(.v15)],
    products: [
        .library(name: "NtrpCore", targets: ["NtrpCore"])
    ],
    targets: [
        .target(
            name: "NtrpCore",
            path: "ntrp/Core"
        ),
        .testTarget(
            name: "NtrpCoreTests",
            dependencies: ["NtrpCore"],
            path: "Tests/NtrpCoreTests"
        )
    ]
)
