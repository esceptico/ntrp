import AppKit
import Carbon
import Combine
import SwiftUI

final class NtrpAppDelegate: NSObject, NSApplicationDelegate {
    private weak var store: NtrpStore?
    private var controller: QuickCaptureController?

    func configure(store: NtrpStore) {
        self.store = store
        if controller == nil {
            controller = QuickCaptureController { [weak self] message in
                await self?.submitQuickCapture(message)
            }
        }
        controller?.registerDefaultShortcut()
    }

    func applicationWillTerminate(_ notification: Notification) {
        controller?.unregisterShortcut()
    }

    @MainActor
    private func submitQuickCapture(_ message: String) async {
        guard let store else { return }
        await store.createSession()
        await store.send(message)
        NSApp.activate(ignoringOtherApps: true)
    }
}

private final class QuickCaptureController {
    private static let shortcutKey = "ntrp.quickCaptureShortcut"
    private static let defaultShortcut = "CommandOrControl+Shift+Space"
    private let onSubmit: (String) async -> Void
    private let state = QuickCaptureState()
    private var panel: QuickCapturePanel?
    private var hotKeyRef: EventHotKeyRef?
    private var eventHandler: EventHandlerRef?
    private var defaultsObserver: NSObjectProtocol?
    private var currentShortcut: String?

    init(onSubmit: @escaping (String) async -> Void) {
        self.onSubmit = onSubmit
        defaultsObserver = NotificationCenter.default.addObserver(
            forName: UserDefaults.didChangeNotification,
            object: nil,
            queue: .main
        ) { [weak self] _ in
            self?.registerDefaultShortcut()
        }
    }

    deinit {
        if let defaultsObserver {
            NotificationCenter.default.removeObserver(defaultsObserver)
        }
        unregisterShortcut()
    }

    func registerDefaultShortcut() {
        let shortcut = UserDefaults.standard.string(forKey: Self.shortcutKey) ?? Self.defaultShortcut
        guard shortcut != currentShortcut else { return }
        currentShortcut = shortcut
        unregisterShortcut()
        guard let parsed = Self.parseShortcut(shortcut) else { return }

        var eventSpec = EventTypeSpec(
            eventClass: OSType(kEventClassKeyboard),
            eventKind: UInt32(kEventHotKeyPressed)
        )

        let selfPointer = UnsafeMutableRawPointer(Unmanaged.passUnretained(self).toOpaque())
        InstallEventHandler(
            GetApplicationEventTarget(),
            { _, _, userData in
                guard let userData else { return noErr }
                let controller = Unmanaged<QuickCaptureController>
                    .fromOpaque(userData)
                    .takeUnretainedValue()
                DispatchQueue.main.async {
                    controller.show()
                }
                return noErr
            },
            1,
            &eventSpec,
            selfPointer,
            &eventHandler
        )

        let hotKeyID = EventHotKeyID(signature: QuickCaptureController.signature, id: 1)
        RegisterEventHotKey(
            parsed.keyCode,
            parsed.modifiers,
            hotKeyID,
            GetApplicationEventTarget(),
            0,
            &hotKeyRef
        )
    }

    func unregisterShortcut() {
        if let hotKeyRef {
            UnregisterEventHotKey(hotKeyRef)
            self.hotKeyRef = nil
        }
        if let eventHandler {
            RemoveEventHandler(eventHandler)
            self.eventHandler = nil
        }
    }

    @MainActor
    private func show() {
        let panel = panel ?? makePanel()
        self.panel = panel

        if let screen = NSScreen.main ?? NSScreen.screens.first {
            let frame = screen.visibleFrame
            let width: CGFloat = min(680, frame.width - 48)
            let height: CGFloat = 64
            panel.setFrame(
                NSRect(
                    x: frame.midX - width / 2,
                    y: frame.maxY - height - 96,
                    width: width,
                    height: height
                ),
                display: true
            )
        }

        NSApp.activate(ignoringOtherApps: true)
        panel.makeKeyAndOrderFront(nil)
        state.present()
    }

    @MainActor
    private func makePanel() -> QuickCapturePanel {
        let panel = QuickCapturePanel(
            contentRect: NSRect(x: 0, y: 0, width: 680, height: 64),
            styleMask: [.borderless, .fullSizeContentView],
            backing: .buffered,
            defer: false
        )
        panel.isReleasedWhenClosed = false
        panel.isOpaque = false
        panel.backgroundColor = .clear
        panel.hasShadow = false
        panel.level = .floating
        panel.collectionBehavior = [.canJoinAllSpaces, .fullScreenAuxiliary]
        panel.contentViewController = NSHostingController(
            rootView: QuickCaptureView(
                state: state,
                submit: { [weak self, weak panel] message in
                    panel?.orderOut(nil)
                    Task { await self?.onSubmit(message) }
                },
                close: { [weak panel] in
                    panel?.orderOut(nil)
                }
            )
        )
        return panel
    }

    private static let signature: OSType = {
        let chars = Array("NTRP".utf8)
        return chars.reduce(0) { ($0 << 8) + OSType($1) }
    }()

    private static func parseShortcut(_ shortcut: String) -> (keyCode: UInt32, modifiers: UInt32)? {
        let parts = shortcut
            .split(separator: "+")
            .map { $0.trimmingCharacters(in: .whitespacesAndNewlines).lowercased() }
        guard !parts.isEmpty else { return nil }

        var modifiers: UInt32 = 0
        var keyCode: UInt32?
        for part in parts {
            switch part {
            case "command", "cmd", "meta", "commandorcontrol":
                modifiers |= UInt32(cmdKey)
            case "shift":
                modifiers |= UInt32(shiftKey)
            case "option", "alt":
                modifiers |= UInt32(optionKey)
            case "control", "ctrl":
                modifiers |= UInt32(controlKey)
            case "space":
                keyCode = UInt32(kVK_Space)
            default:
                if part.count == 1, let scalar = part.unicodeScalars.first {
                    keyCode = Self.letterKeyCode(for: scalar)
                }
            }
        }

        guard let keyCode, modifiers != 0 else { return nil }
        return (keyCode, modifiers)
    }

    private static func letterKeyCode(for scalar: UnicodeScalar) -> UInt32? {
        switch scalar {
        case "a": return UInt32(kVK_ANSI_A)
        case "b": return UInt32(kVK_ANSI_B)
        case "c": return UInt32(kVK_ANSI_C)
        case "d": return UInt32(kVK_ANSI_D)
        case "e": return UInt32(kVK_ANSI_E)
        case "f": return UInt32(kVK_ANSI_F)
        case "g": return UInt32(kVK_ANSI_G)
        case "h": return UInt32(kVK_ANSI_H)
        case "i": return UInt32(kVK_ANSI_I)
        case "j": return UInt32(kVK_ANSI_J)
        case "k": return UInt32(kVK_ANSI_K)
        case "l": return UInt32(kVK_ANSI_L)
        case "m": return UInt32(kVK_ANSI_M)
        case "n": return UInt32(kVK_ANSI_N)
        case "o": return UInt32(kVK_ANSI_O)
        case "p": return UInt32(kVK_ANSI_P)
        case "q": return UInt32(kVK_ANSI_Q)
        case "r": return UInt32(kVK_ANSI_R)
        case "s": return UInt32(kVK_ANSI_S)
        case "t": return UInt32(kVK_ANSI_T)
        case "u": return UInt32(kVK_ANSI_U)
        case "v": return UInt32(kVK_ANSI_V)
        case "w": return UInt32(kVK_ANSI_W)
        case "x": return UInt32(kVK_ANSI_X)
        case "y": return UInt32(kVK_ANSI_Y)
        case "z": return UInt32(kVK_ANSI_Z)
        default: return nil
        }
    }
}

private final class QuickCapturePanel: NSPanel {
    override var canBecomeKey: Bool { true }
    override var canBecomeMain: Bool { true }
}

private final class QuickCaptureState: ObservableObject {
    @Published var summonID = UUID()

    func present() {
        summonID = UUID()
    }
}

private struct QuickCaptureView: View {
    @ObservedObject var state: QuickCaptureState
    let submit: (String) -> Void
    let close: () -> Void
    @State private var text = ""
    @State private var visible = false
    @State private var exitReason: ExitReason?
    @State private var pendingSubmit: String?
    @FocusState private var focused: Bool

    private var canSubmit: Bool {
        !text.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty
    }

    var body: some View {
        ZStack {
            if visible {
                card
                    .transition(.quickCaptureTransition(exitReason: exitReason))
            }
        }
        .animation(.interpolatingSpring(stiffness: 520, damping: 36).speed(1.1), value: visible)
        .padding(6)
        .onChange(of: state.summonID) { _, _ in
            present()
        }
        .onAppear(perform: present)
        .onKeyPress(.escape) {
            dismiss(.close)
            return .handled
        }
    }

    private var card: some View {
        HStack(spacing: 10) {
            Image(systemName: "sparkles")
                .font(.system(size: 16, weight: .medium))
                .foregroundStyle(NtrpColors.accent)
                .frame(width: 20, height: 20)

            TextField("What can I help you with today?", text: $text)
                .textFieldStyle(.plain)
                .font(.system(size: 15, weight: .regular))
                .foregroundStyle(NtrpColors.text)
                .focused($focused)
                .onSubmit(send)

            Button(action: send) {
                Image(systemName: "arrow.up")
                    .font(.system(size: 13, weight: .bold))
                    .foregroundStyle(canSubmit ? Color.black.opacity(0.86) : NtrpColors.faint)
                    .frame(width: 24, height: 24)
                    .background(canSubmit ? NtrpColors.text : Color.clear)
                    .clipShape(RoundedRectangle(cornerRadius: 6, style: .continuous))
            }
            .buttonStyle(.plain)
            .scaleEffect(canSubmit ? 1 : 0.98)
            .disabled(!canSubmit)
        }
        .padding(.horizontal, 14)
        .frame(maxWidth: .infinity, maxHeight: .infinity)
        .background(NtrpColors.sidebar)
        .overlay(
            RoundedRectangle(cornerRadius: 12, style: .continuous)
                .stroke(focused ? NtrpColors.accent.opacity(0.30) : NtrpColors.text.opacity(0.10), lineWidth: focused ? 1 : 0.5)
        )
        .clipShape(RoundedRectangle(cornerRadius: 12, style: .continuous))
        .shadow(color: .black.opacity(focused ? 0.36 : 0.32), radius: 28, x: 0, y: 14)
        .shadow(color: .black.opacity(0.18), radius: 8, x: 0, y: 2)
    }

    private func present() {
        text = ""
        exitReason = nil
        pendingSubmit = nil
        visible = false
        Task { @MainActor in
            try? await Task.sleep(for: .milliseconds(1))
            visible = true
            focused = true
        }
    }

    private func send() {
        let trimmed = text.trimmingCharacters(in: .whitespacesAndNewlines)
        guard !trimmed.isEmpty else { return }
        pendingSubmit = trimmed
        dismiss(.submit)
    }

    private func dismiss(_ reason: ExitReason) {
        guard visible else { return }
        exitReason = reason
        visible = false
        let delay = reason == .submit ? 140 : 110
        Task { @MainActor in
            try? await Task.sleep(for: .milliseconds(delay))
            switch reason {
            case .submit:
                if let pendingSubmit {
                    submit(pendingSubmit)
                }
            case .close:
                close()
            }
            text = ""
            pendingSubmit = nil
            exitReason = nil
        }
    }
}

private enum ExitReason {
    case submit
    case close
}

private extension AnyTransition {
    static func quickCaptureTransition(exitReason: ExitReason?) -> AnyTransition {
        let insertion = AnyTransition
            .opacity
            .combined(with: .scale(scale: 0.96))
            .combined(with: .offset(y: -16))

        let removal: AnyTransition
        if exitReason == .submit {
            removal = .opacity
                .combined(with: .scale(scale: 0.97))
                .combined(with: .offset(y: -10))
        } else {
            removal = .opacity
                .combined(with: .scale(scale: 0.96))
        }

        return .asymmetric(insertion: insertion, removal: removal)
    }
}
