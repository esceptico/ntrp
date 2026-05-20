import Combine
import Foundation
import SwiftUI

final class NtrpUIState: ObservableObject {
    static let sidebarMinWidth: CGFloat = 200
    static let sidebarMaxWidth: CGFloat = 380
    static let sidebarDefaultWidth: CGFloat = 272
    static let sidebarDoubleClickWidth: CGFloat = 244
    private static let sidebarSnapPoints: [CGFloat] = [220, 244, 280, 320]
    private static let sidebarSnapThreshold: CGFloat = 12

    @Published var activeSurface: MainSurface = .chat
    @Published var sidebarHidden = false
    @Published var rightSidebarCollapsed = true
    @Published var paletteOpen = false
    @Published var inspectingTool: TranscriptMessage?
    @Published var reviewingApproval: PendingApproval?
    @Published var viewingMarkdown: MarkdownViewState?
    @Published var viewingMermaid: MermaidViewState?
    @Published var viewingLoop: LoopSummary?
    @Published var composerFocusRequest = 0
    var composerSeed: String?
    @Published var sidebarWidth: CGFloat

    private let sidebarWidthKey = "ntrp.sidebarWidth"

    init() {
        let stored = UserDefaults.standard.double(forKey: sidebarWidthKey)
        sidebarWidth = stored > 0 ? Self.clampSidebarWidth(CGFloat(stored)) : Self.sidebarDefaultWidth
    }

    func openSettings() {
        activeSurface = .settings
    }

    func showChat() {
        activeSurface = .chat
    }

    func toggleSidebar() {
        sidebarHidden.toggle()
    }

    func toggleRightSidebar() {
        rightSidebarCollapsed.toggle()
    }

    func openPalette() {
        paletteOpen = true
    }

    func closePalette() {
        paletteOpen = false
    }

    func togglePalette() {
        paletteOpen.toggle()
    }

    func focusComposer(seed: String? = nil) {
        composerSeed = seed
        composerFocusRequest += 1
    }

    func setSidebarWidth(_ width: CGFloat) {
        let clamped = Self.clampSidebarWidth(width)
        sidebarWidth = clamped
    }

    func finishSidebarResize(_ width: CGFloat) {
        let snapped = Self.snappedSidebarWidth(width)
        sidebarWidth = snapped
        UserDefaults.standard.set(Double(snapped), forKey: sidebarWidthKey)
    }

    private static func clampSidebarWidth(_ width: CGFloat) -> CGFloat {
        min(max(width, sidebarMinWidth), sidebarMaxWidth)
    }

    private static func snappedSidebarWidth(_ width: CGFloat) -> CGFloat {
        let clamped = clampSidebarWidth(width)
        guard let nearest = sidebarSnapPoints.min(by: { abs($0 - clamped) < abs($1 - clamped) }) else {
            return clamped
        }
        return abs(nearest - clamped) <= sidebarSnapThreshold ? nearest : clamped
    }

    func resetSidebarWidth() {
        let clamped = Self.sidebarDoubleClickWidth
        sidebarWidth = clamped
        UserDefaults.standard.set(Double(clamped), forKey: sidebarWidthKey)
    }
}
