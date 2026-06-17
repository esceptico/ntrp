import SwiftUI

@main
struct NtrpMobileApp: App {
    @StateObject private var store = NtrpMobileStore()
    @AppStorage("ntrp.appearance") private var appearance: AppAppearance = .system

    var body: some Scene {
        WindowGroup {
            RootView(store: store)
                .tint(Theme.accent)
                .preferredColorScheme(appearance.colorScheme)
                .task {
                    await store.bootstrap()
                }
        }
    }
}
