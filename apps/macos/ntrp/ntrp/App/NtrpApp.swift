import SwiftUI

@main
struct NtrpApp: App {
    @NSApplicationDelegateAdaptor(NtrpAppDelegate.self) private var appDelegate
    @StateObject private var store = NtrpStore()
    @StateObject private var ui = NtrpUIState()

    var body: some Scene {
        WindowGroup("ntrp") {
            ContentView(store: store, ui: ui)
                .frame(minWidth: 980, minHeight: 660)
                .background(WindowConfigurator().frame(width: 0, height: 0))
                .toolbar(removing: .title)
                .toolbarBackgroundVisibility(.hidden, for: .windowToolbar)
                .task {
                    await store.bootstrap()
                }
                .onAppear {
                    appDelegate.configure(store: store)
                }
        }
        .defaultSize(width: 1320, height: 880)
        .windowStyle(.hiddenTitleBar)
        .commands {
            CommandGroup(after: .newItem) {
                Button("New Session") {
                    Task { await store.createSession() }
                }
                .keyboardShortcut("n", modifiers: [.command])

                Button("Reload") {
                    Task { await store.reload() }
                }
                .keyboardShortcut("r", modifiers: [.command])

                Button("Toggle Sidebar") {
                    ui.toggleSidebar()
                }
                .keyboardShortcut("b", modifiers: [.command])

                Button("Settings") {
                    ui.openSettings()
                }
                .keyboardShortcut(",", modifiers: [.command])

                Button("Command Palette") {
                    ui.togglePalette()
                }
                .keyboardShortcut("k", modifiers: [.command])
            }
        }
    }
}
