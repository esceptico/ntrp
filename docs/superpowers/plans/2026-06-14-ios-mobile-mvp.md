# iOS Mobile MVP Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a native iOS app scaffold that can connect to the existing ntrp server, list sessions, open chat history, send messages, stream SSE events, approve/reject tools, and cancel runs.

**Architecture:** Put the app in `apps/ios/ntrp`. Keep pure networking/models/SSE code under `ntrp/Core` and expose it to a local Swift package for fast `swift test`; the Xcode iOS app target includes the same files through a filesystem-synchronized source group. The first UI is SwiftUI-native and standard-control-first, with no desktop relay or local tools.

**Tech Stack:** Swift 6/Xcode 26 project, SwiftUI, URLSession, Keychain Services, Swift Testing/XCTest via SwiftPM for core code.

**Explicit v1 non-goal:** no long-term context screens, endpoints, search, or editing.

---

### Task 1: Core package and tests

**Files:**
- Create: `apps/ios/ntrp/Package.swift`
- Create: `apps/ios/ntrp/ntrp/Core/NtrpModels.swift`
- Create: `apps/ios/ntrp/ntrp/Core/NtrpAPIClient.swift`
- Create: `apps/ios/ntrp/ntrp/Core/SSEParser.swift`
- Create: `apps/ios/ntrp/Tests/NtrpCoreTests/SSEParserTests.swift`
- Create: `apps/ios/ntrp/Tests/NtrpCoreTests/NtrpAPIClientTests.swift`

- [x] Write failing tests for SSE parsing and request construction.
- [x] Run `swift test --package-path apps/ios/ntrp` and verify failures.
- [x] Implement core models, API client, and parser.
- [x] Run `swift test --package-path apps/ios/ntrp` and verify pass.

### Task 2: iOS app target

**Files:**
- Create: `apps/ios/ntrp/ntrp.xcodeproj/project.pbxproj`
- Create: `apps/ios/ntrp/ntrp.xcodeproj/project.xcworkspace/contents.xcworkspacedata`
- Create: `apps/ios/ntrp/ntrp/App/NtrpMobileApp.swift`
- Create: `apps/ios/ntrp/ntrp/Assets.xcassets/...`
- Create: `apps/ios/ntrp/ntrp/Info.plist`

- [x] Create a minimal iOS app target using filesystem-synchronized sources.
- [x] Add app entrypoint and generated Info.plist settings.
- [x] Build with `xcodebuild -project apps/ios/ntrp/ntrp.xcodeproj -scheme ntrp -destination generic/platform=iOS -derivedDataPath apps/ios/ntrp/build CODE_SIGNING_ALLOWED=NO build`.

### Task 3: Store and UI

**Files:**
- Create: `apps/ios/ntrp/ntrp/Core/NtrpMobileStore.swift`
- Create: `apps/ios/ntrp/ntrp/Views/SettingsView.swift`
- Create: `apps/ios/ntrp/ntrp/Views/SessionListView.swift`
- Create: `apps/ios/ntrp/ntrp/Views/ChatView.swift`
- Create: `apps/ios/ntrp/ntrp/Views/ApprovalCard.swift`
- Create: `apps/ios/ntrp/ntrp/Support/KeychainConfigStore.swift`

- [x] Add a small observable store for config, sessions, history, send, stream, approve, cancel.
- [x] Add settings, session list, chat, and approval views.
- [x] Keep visuals standard SwiftUI first: `NavigationSplitView`/`NavigationStack`, `List`, `Form`, `ToolbarItem`, standard buttons, semantic tint only.
- [x] Rebuild the app.
