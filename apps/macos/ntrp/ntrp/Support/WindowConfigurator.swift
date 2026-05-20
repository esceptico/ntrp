import AppKit
import SwiftUI

struct WindowConfigurator: NSViewRepresentable {
    func makeNSView(context: Context) -> NSView {
        let view = NSView(frame: .zero)
        DispatchQueue.main.async {
            configure(view.window)
        }
        return view
    }

    func updateNSView(_ nsView: NSView, context: Context) {
        DispatchQueue.main.async {
            configure(nsView.window)
        }
    }

    private func configure(_ window: NSWindow?) {
        guard let window else { return }
        window.title = "ntrp"
        window.minSize = NSSize(width: 980, height: 660)
        window.titleVisibility = .hidden
        window.titlebarAppearsTransparent = true
        window.styleMask.insert(.fullSizeContentView)
        window.backgroundColor = windowBackgroundColor()
        window.isMovableByWindowBackground = true

        if window.frame.width < 1000 || window.frame.height < 700 {
            window.setContentSize(NSSize(width: 1320, height: 880))
            window.center()
        }

        positionTrafficLights(in: window)
    }

    private func positionTrafficLights(in window: NSWindow) {
        guard
            let close = window.standardWindowButton(.closeButton),
            let minimize = window.standardWindowButton(.miniaturizeButton),
            let zoom = window.standardWindowButton(.zoomButton),
            let superview = close.superview
        else {
            return
        }

        let topInset: CGFloat = 18
        let leftInset: CGFloat = 18
        let spacing: CGFloat = 20
        let y = superview.bounds.height - topInset - close.frame.height
        close.setFrameOrigin(NSPoint(x: leftInset, y: y))
        minimize.setFrameOrigin(NSPoint(x: leftInset + spacing, y: y))
        zoom.setFrameOrigin(NSPoint(x: leftInset + spacing * 2, y: y))
    }

    private func windowBackgroundColor() -> NSColor {
        let theme = UserDefaults.standard.string(forKey: "ntrp.theme") ?? "system"
        let dark: Bool
        switch theme {
        case "light":
            dark = false
        case "dark":
            dark = true
        default:
            dark = NSApp.effectiveAppearance.bestMatch(from: [.darkAqua, .aqua]) == .darkAqua
        }

        if dark {
            return NSColor(red: 16 / 255, green: 15 / 255, blue: 15 / 255, alpha: 1)
        }
        return NSColor(red: 236 / 255, green: 233 / 255, blue: 224 / 255, alpha: 1)
    }
}
