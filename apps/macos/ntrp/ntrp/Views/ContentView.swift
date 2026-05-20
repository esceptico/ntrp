import AppKit
import SwiftUI

struct ContentView: View {
    @ObservedObject var store: NtrpStore
    @ObservedObject var ui: NtrpUIState
    @State private var settingsTab: SettingsTab = .connection
    @State private var keyMonitor: Any?

    var body: some View {
        ZStack(alignment: .leading) {
            mainContent

            ZStack(alignment: .trailing) {
                sidebarContent
                    .frame(width: max(0, activeSidebarWidth - 16))
                    .frame(maxHeight: .infinity)
                    .background(NtrpColors.surfaceFill(0.72))
                    .overlay(RoundedRectangle(cornerRadius: 14, style: .continuous).stroke(NtrpColors.sidebarStroke, lineWidth: 1))
                    .clipShape(RoundedRectangle(cornerRadius: 14, style: .continuous))
                    .shadow(color: .black.opacity(0.34), radius: 22, x: 0, y: 14)
                    .ntrpGlass(cornerRadius: 14)
                    .padding(.vertical, 8)
                    .padding(.leading, 8)
                    .frame(width: activeSidebarWidth, alignment: .leading)
                    .frame(maxHeight: .infinity)

                if !ui.sidebarHidden {
                    SidebarResizeHandle(
                        width: ui.sidebarWidth,
                        setWidth: { width in
                            ui.setSidebarWidth(width)
                        },
                        finishWidth: { width in
                            ui.finishSidebarResize(width)
                        },
                        resetWidth: {
                            ui.resetSidebarWidth()
                        }
                    )
                }
            }
            .frame(width: activeSidebarWidth, alignment: .leading)
            .offset(x: sidebarOffset)
            .allowsHitTesting(sidebarIsVisible)
            .zIndex(30)

            Button {
                ui.toggleSidebar()
            } label: {
                Image(systemName: ui.sidebarHidden ? "sidebar.left" : "sidebar.leading")
                    .font(.system(size: 13, weight: .semibold))
                    .foregroundStyle(NtrpColors.muted)
                    .frame(width: 22, height: 22)
                    .contentShape(Rectangle())
            }
            .buttonStyle(.plain)
            .background(NtrpColors.row.opacity(0.0))
            .clipShape(RoundedRectangle(cornerRadius: 6, style: .continuous))
            .help(ui.sidebarHidden ? "Show sidebar" : "Hide sidebar")
            .padding(.top, 14)
            .padding(.leading, 84)
            .frame(maxWidth: .infinity, maxHeight: .infinity, alignment: .topLeading)
            .zIndex(35)

            if ui.activeSurface == .chat {
                AgentRightSidebarView(store: store, ui: ui)
                    .zIndex(40)
            }

            if ui.activeSurface == .settings || ui.activeSurface == .automations || ui.activeSurface == .memory || ui.activeSurface == .archive {
                activeSurfaceOverlay
                    .zIndex(45)
            }

            if let tool = ui.inspectingTool {
                toolOverlay(tool)
                    .zIndex(46)
            }

            if let approval = ui.reviewingApproval {
                approvalOverlay(approval)
                    .zIndex(47)
            }

            if let markdown = ui.viewingMarkdown {
                markdownOverlay(markdown)
                    .zIndex(48)
            }

            if let mermaid = ui.viewingMermaid {
                mermaidOverlay(mermaid)
                    .zIndex(49)
            }

            if let loop = ui.viewingLoop {
                loopOverlay(loop)
                    .zIndex(50)
            }

            if ui.paletteOpen {
                CommandPaletteView(store: store, ui: ui)
                    .transition(.paletteEntry)
                    .zIndex(51)
            }
        }
        .frame(maxWidth: .infinity, maxHeight: .infinity)
        .background(NtrpColors.canvas)
        .modifier(NtrpThemeBridge())
        .environmentObject(ui)
        .animation(.snappy(duration: 0.22), value: ui.sidebarHidden)
        .onAppear(perform: installKeyMonitor)
        .onDisappear(perform: removeKeyMonitor)
    }

    @ViewBuilder
    private var sidebarContent: some View {
        SidebarView(
            store: store,
            activeSurface: $ui.activeSurface
        )
    }

    @ViewBuilder
    private var mainContent: some View {
        ChatView(store: store, ui: ui, sidebarHidden: $ui.sidebarHidden)
            .padding(.leading, ui.sidebarHidden ? 0 : ui.sidebarWidth)
    }

    private var activeSidebarWidth: CGFloat {
        ui.sidebarWidth
    }

    private var sidebarOffset: CGFloat {
        return sidebarIsVisible ? 0 : -activeSidebarWidth
    }

    private var sidebarIsVisible: Bool {
        !ui.sidebarHidden
    }

    private var activeSurfaceOverlay: some View {
        GeometryReader { geometry in
            ZStack {
                NtrpModalScrim()
                    .ignoresSafeArea()
                    .onTapGesture {
                        ui.showChat()
                    }

                surfacePanel(size: geometry.size)
                    .transition(.modalPanelEntry)
            }
            .frame(maxWidth: .infinity, maxHeight: .infinity)
        }
        .transition(.opacity)
    }

    private func markdownOverlay(_ markdown: MarkdownViewState) -> some View {
        GeometryReader { geometry in
            ZStack {
                NtrpModalScrim()
                    .ignoresSafeArea()
                    .onTapGesture {
                        ui.viewingMarkdown = nil
                    }

                MarkdownViewerPanel(view: markdown) {
                    ui.viewingMarkdown = nil
                }
                .frame(
                    width: min(720, max(320, geometry.size.width - 80)),
                    height: min(640, max(360, geometry.size.height - 80))
                )
                .modalPanel()
                .transition(.modalPanelEntry)
            }
            .frame(maxWidth: .infinity, maxHeight: .infinity)
        }
        .transition(.opacity)
    }

    private func approvalOverlay(_ approval: PendingApproval) -> some View {
        GeometryReader { geometry in
            ZStack {
                NtrpModalScrim()
                    .ignoresSafeArea()
                    .onTapGesture {
                        ui.reviewingApproval = nil
                    }

                ApprovalReviewPanel(store: store, approval: approval) {
                    ui.reviewingApproval = nil
                }
                .frame(
                    width: min(720, max(320, geometry.size.width - 80)),
                    height: min(520, max(360, geometry.size.height - 80))
                )
                .modalPanel()
                .transition(.modalPanelEntry)
            }
            .frame(maxWidth: .infinity, maxHeight: .infinity)
        }
        .transition(.opacity)
    }

    private func mermaidOverlay(_ mermaid: MermaidViewState) -> some View {
        GeometryReader { geometry in
            ZStack {
                NtrpModalScrim()
                    .ignoresSafeArea()
                    .onTapGesture {
                        ui.viewingMermaid = nil
                    }

                MermaidDiagramPanel(code: mermaid.code, fullscreen: true) {
                    ui.viewingMermaid = nil
                }
                .padding(24)
                .frame(width: geometry.size.width, height: geometry.size.height)
                .transition(.opacity.combined(with: .scale(scale: 0.96)))
            }
            .frame(maxWidth: .infinity, maxHeight: .infinity)
        }
        .transition(.opacity)
    }

    private func loopOverlay(_ loop: LoopSummary) -> some View {
        GeometryReader { geometry in
            ZStack {
                NtrpModalScrim()
                    .ignoresSafeArea()
                    .onTapGesture {
                        ui.viewingLoop = nil
                    }

                LoopDetailPanel(loop: loop) {
                    ui.viewingLoop = nil
                }
                .frame(
                    width: min(560, max(320, geometry.size.width - 80)),
                    height: min(640, max(360, geometry.size.height - 80))
                )
                .modalPanel()
                .transition(.modalPanelEntry)
            }
            .frame(maxWidth: .infinity, maxHeight: .infinity)
        }
        .transition(.opacity)
    }

    private func toolOverlay(_ tool: TranscriptMessage) -> some View {
        let liveTool = store.messages.first(where: { $0.id == tool.id }) ?? tool
        return GeometryReader { geometry in
            ZStack {
                NtrpModalScrim()
                    .ignoresSafeArea()
                    .onTapGesture {
                        ui.inspectingTool = nil
                    }

                ToolDetailPanel(message: liveTool, messages: store.messages, openTool: { child in
                    ui.inspectingTool = child
                }) {
                    ui.inspectingTool = nil
                }
                .frame(width: min(720, max(320, geometry.size.width - 80)))
                .frame(maxHeight: max(360, geometry.size.height - 80))
                .modalPanel()
                .transition(.modalPanelEntry)
            }
            .frame(maxWidth: .infinity, maxHeight: .infinity)
        }
        .transition(.opacity)
    }

    @ViewBuilder
    private func surfacePanel(size: CGSize) -> some View {
        let width = min(1000, max(320, size.width - 64))
        let height = min(740, max(420, size.height - 64))

        switch ui.activeSurface {
        case .settings:
            HStack(spacing: 0) {
                SettingsSidebarView(activeTab: $settingsTab)
                    .frame(width: 208)
                    .frame(maxHeight: .infinity)
                    .background(NtrpColors.surfaceFill(0.72))
                    .overlay(RoundedRectangle(cornerRadius: 10, style: .continuous).stroke(NtrpColors.sidebarStroke, lineWidth: 1))
                    .clipShape(RoundedRectangle(cornerRadius: 10, style: .continuous))
                    .ntrpGlass(cornerRadius: 10)
                    .padding(8)
                    .frame(width: 224)

                SettingsView(store: store, activeTab: $settingsTab) {
                    ui.showChat()
                }
                .frame(maxWidth: .infinity, maxHeight: .infinity, alignment: .topLeading)
            }
            .frame(width: width, height: height)
            .modalPanel()
        case .automations:
            SurfaceOverlay(store: store, title: "Automations", paths: ["/automations", "/loops"]) {
                ui.showChat()
            }
            .frame(width: width, height: height)
            .modalPanel()
        case .memory:
            SurfaceOverlay(store: store, title: "Memory", paths: ["/memory/stats", "/memory/audit"]) {
                ui.showChat()
            }
            .frame(width: width, height: height)
            .modalPanel()
        case .archive:
            NtrpArchivePanel(store: store) {
                ui.showChat()
            }
            .frame(width: min(720, max(320, size.width - 80)), height: min(560, max(360, size.height - 80)))
            .modalPanel()
        case .chat:
            EmptyView()
        }
    }

    private var currentTitle: String {
        guard let id = store.selectedSessionID else { return "ntrp" }
        return store.sessions.first(where: { $0.sessionID == id })?.name ?? "untitled"
    }

    private func installKeyMonitor() {
        guard keyMonitor == nil else { return }
        keyMonitor = NSEvent.addLocalMonitorForEvents(matching: .keyDown) { event in
            if event.keyCode == 53, ui.viewingMarkdown != nil {
                ui.viewingMarkdown = nil
                return nil
            }
            if event.keyCode == 53, ui.viewingMermaid != nil {
                ui.viewingMermaid = nil
                return nil
            }
            if event.keyCode == 53, ui.viewingLoop != nil {
                ui.viewingLoop = nil
                return nil
            }
            if event.keyCode == 53, ui.reviewingApproval != nil {
                ui.reviewingApproval = nil
                return nil
            }
            if event.keyCode == 53, ui.inspectingTool != nil {
                ui.inspectingTool = nil
                return nil
            }
            if event.keyCode == 53, ui.activeSurface != .chat, !ui.paletteOpen {
                ui.showChat()
                return nil
            }
            guard shouldFocusComposer(for: event) else { return event }
            ui.focusComposer(seed: event.characters)
            return nil
        }
    }

    private func removeKeyMonitor() {
        if let keyMonitor {
            NSEvent.removeMonitor(keyMonitor)
            self.keyMonitor = nil
        }
    }

    private func shouldFocusComposer(for event: NSEvent) -> Bool {
        guard ui.activeSurface == .chat, !ui.paletteOpen, ui.inspectingTool == nil, ui.reviewingApproval == nil, ui.viewingMarkdown == nil, ui.viewingMermaid == nil, ui.viewingLoop == nil else { return false }
        guard event.modifierFlags.intersection([.command, .control, .option]).isEmpty else { return false }
        guard let text = event.characters, text.count == 1, text.isPrintableKeySeed else { return false }
        if let responder = NSApp.keyWindow?.firstResponder, responder.isTextEntryResponder {
            return false
        }
        return true
    }
}

private struct MarkdownViewerPanel: View {
    let view: MarkdownViewState
    let close: () -> Void

    var body: some View {
        VStack(alignment: .leading, spacing: 0) {
            HStack(alignment: .firstTextBaseline, spacing: 10) {
                VStack(alignment: .leading, spacing: 2) {
                    Text(view.title)
                        .font(.system(size: 18, weight: .semibold))
                        .foregroundStyle(NtrpColors.text)
                        .lineLimit(1)
                    if let subtitle = view.subtitle, !subtitle.isEmpty {
                        Text(subtitle)
                            .font(.system(size: 12, design: .monospaced))
                            .foregroundStyle(NtrpColors.faint)
                            .lineLimit(1)
                            .truncationMode(.middle)
                    }
                }
                Spacer()
                if let path = view.sourcePath, !path.isEmpty {
                    Button {
                        NSWorkspace.shared.open(URL(fileURLWithPath: path))
                    } label: {
                        Image(systemName: "arrow.up.right.square")
                            .font(.system(size: 13, weight: .medium))
                            .frame(width: 26, height: 26)
                    }
                    .buttonStyle(.plain)
                    .foregroundStyle(NtrpColors.muted)
                    .help("Open in default app")
                }
                Button {
                    close()
                } label: {
                    Image(systemName: "xmark")
                        .font(.system(size: 13, weight: .semibold))
                        .frame(width: 26, height: 26)
                }
                .buttonStyle(.plain)
                .foregroundStyle(NtrpColors.muted)
            }
            .padding(.horizontal, 18)
            .padding(.top, 16)
            .padding(.bottom, 12)

            ScrollView {
                MarkdownText(view.content)
                    .font(.system(size: 15))
                    .lineSpacing(4)
                    .textSelection(.enabled)
                    .frame(maxWidth: .infinity, alignment: .leading)
                    .padding(18)
            }
            .scrollIndicators(.hidden)
        }
    }
}

private struct LoopDetailPanel: View {
    let loop: LoopSummary
    let close: () -> Void

    var body: some View {
        VStack(alignment: .leading, spacing: 0) {
            HStack(spacing: 8) {
                Image(systemName: "arrow.triangle.2.circlepath")
                    .font(.system(size: 13, weight: .medium))
                    .foregroundStyle(NtrpColors.muted)
                Text("Loop")
                    .font(.system(size: 14, weight: .semibold))
                    .foregroundStyle(NtrpColors.text)
                Spacer()
                Text("Every \(loop.every) · next in \(countdownText)")
                    .font(.system(size: 12))
                    .foregroundStyle(NtrpColors.faint)
                    .lineLimit(1)
                Button {
                    close()
                } label: {
                    Image(systemName: "xmark")
                        .font(.system(size: 12, weight: .semibold))
                        .frame(width: 24, height: 24)
                }
                .buttonStyle(.plain)
                .foregroundStyle(NtrpColors.faint)
            }
            .padding(.horizontal, 16)
            .padding(.vertical, 12)
            .overlay(Rectangle().fill(NtrpColors.sidebarStroke).frame(height: 1), alignment: .bottom)

            ScrollView {
                MarkdownText(loop.prompt ?? "")
                    .font(.system(size: 14))
                    .lineSpacing(4)
                    .textSelection(.enabled)
                    .frame(maxWidth: .infinity, alignment: .leading)
                    .padding(16)
            }
            .scrollIndicators(.hidden)

            HStack(spacing: 12) {
                if let maxIterations = loop.maxIterations {
                    Text("iter \(loop.iterationCount)/\(maxIterations)")
                } else if loop.iterationCount > 0 {
                    Text("iter \(loop.iterationCount)")
                }
                if let maxAgeDays = loop.maxAgeDays {
                    Text("expires after \(maxAgeDays)d")
                }
                if let stopWhen = loop.stopWhen, !stopWhen.isEmpty {
                    Text("stops when: \(stopWhen)")
                        .lineLimit(1)
                }
                Spacer()
                Text(loop.id)
                    .font(.system(size: 11, design: .monospaced))
                    .lineLimit(1)
            }
            .font(.system(size: 12))
            .foregroundStyle(NtrpColors.faint)
            .padding(.horizontal, 16)
            .padding(.vertical, 10)
            .overlay(Rectangle().fill(NtrpColors.sidebarStroke).frame(height: 1), alignment: .top)
        }
    }

    private var countdownText: String {
        guard let nextRunAt = loop.nextRunAt, let date = loopDate(from: nextRunAt) else {
            return loop.every
        }
        let seconds = max(0, Int(date.timeIntervalSinceNow))
        if seconds < 60 { return "\(seconds)s" }
        let minutes = seconds / 60
        if minutes < 60 { return "\(minutes)m" }
        let hours = minutes / 60
        if hours < 24 { return "\(hours)h" }
        return "\(hours / 24)d"
    }

    private func loopDate(from value: String) -> Date? {
        if let date = ISO8601DateFormatter.ntrp.date(from: value) {
            return date
        }
        return ISO8601DateFormatter.ntrpFractional.date(from: value)
    }
}

private extension String {
    var isPrintableKeySeed: Bool {
        unicodeScalars.allSatisfy { scalar in
            scalar.value >= 32 && scalar.value != 127
        }
    }
}

private extension NSResponder {
    var isTextEntryResponder: Bool {
        self is NSTextView || self is NSTextField || self is NSSearchField
    }
}

private extension View {
    func modalPanel() -> some View {
        self
            .background(NtrpColors.surfaceFill(0.52))
            .overlay(
                RoundedRectangle(cornerRadius: 14, style: .continuous)
                    .stroke(NtrpColors.sidebarStroke, lineWidth: 1)
            )
            .clipShape(RoundedRectangle(cornerRadius: 14, style: .continuous))
            .shadow(color: .black.opacity(0.44), radius: 30, x: 0, y: 18)
            .ntrpGlass(cornerRadius: 14)
    }
}

private extension AnyTransition {
    static var modalPanelEntry: AnyTransition {
        .asymmetric(
            insertion: .opacity.combined(with: .scale(scale: 0.95)).combined(with: .offset(y: 6)),
            removal: .opacity.combined(with: .scale(scale: 0.95)).combined(with: .offset(y: 6))
        )
    }

    static var paletteEntry: AnyTransition {
        .asymmetric(
            insertion: .opacity.combined(with: .scale(scale: 0.96, anchor: .top)).combined(with: .offset(y: -6)),
            removal: .opacity.combined(with: .scale(scale: 0.96, anchor: .top)).combined(with: .offset(y: -6))
        )
    }
}

struct NtrpArchivePanel: View {
    @ObservedObject var store: NtrpStore
    let close: () -> Void
    @State private var query = ""
    @State private var busyID: String?
    @State private var archiveScrolled = false

    private var filtered: [SessionListItem] {
        let needle = query.trimmingCharacters(in: .whitespacesAndNewlines).lowercased()
        guard !needle.isEmpty else { return store.archivedSessions }
        return store.archivedSessions.filter { ($0.name ?? "untitled").lowercased().contains(needle) }
    }

    var body: some View {
        VStack(spacing: 0) {
            HStack(spacing: 12) {
                HStack(alignment: .firstTextBaseline, spacing: 10) {
                    Text("Archive")
                        .font(.system(size: 18, weight: .semibold))
                        .foregroundStyle(NtrpColors.text)
                    if !store.archivedSessions.isEmpty {
                        Text("\(store.archivedSessions.count) \(store.archivedSessions.count == 1 ? "session" : "sessions")")
                            .font(.system(size: 12))
                            .foregroundStyle(NtrpColors.faint)
                    }
                }

                Spacer()

                HStack(spacing: 6) {
                    Image(systemName: "magnifyingglass")
                        .font(.system(size: 12))
                        .foregroundStyle(NtrpColors.faint)
                    TextField("Filter...", text: $query)
                        .textFieldStyle(.plain)
                        .font(.system(size: 13))
                        .foregroundStyle(NtrpColors.text)
                }
                .padding(.horizontal, 9)
                .frame(width: 200, height: 28)
                .background(NtrpColors.row.opacity(0.36))
                .overlay(RoundedRectangle(cornerRadius: 7, style: .continuous).stroke(NtrpColors.sidebarStroke, lineWidth: 1))
                .clipShape(RoundedRectangle(cornerRadius: 7, style: .continuous))

                Button {
                    close()
                } label: {
                    Image(systemName: "xmark")
                        .font(.system(size: 13, weight: .semibold))
                        .frame(width: 26, height: 26)
                }
                .buttonStyle(.plain)
                .foregroundStyle(NtrpColors.muted)
            }
            .padding(.horizontal, 18)
            .padding(.top, 16)
            .padding(.bottom, 12)

            ScrollView {
                VStack(spacing: 0) {
                    GeometryReader { geometry in
                        Color.clear.preference(
                            key: ArchiveScrollTopPreferenceKey.self,
                            value: geometry.frame(in: .named("archive-scroll")).minY
                        )
                    }
                    .frame(height: 1)
                    .padding(.bottom, -1)

                    LazyVStack(alignment: .leading, spacing: 1) {
                        if store.archivedSessions.isEmpty {
                            ArchiveEmptyText("Nothing here. Archived sessions will show up in this view.")
                        } else if filtered.isEmpty {
                            ArchiveEmptyText("No matches.")
                        } else {
                            ForEach(filtered) { session in
                                ArchiveRow(
                                    session: session,
                                    busy: busyID == session.sessionID,
                                    restore: {
                                        await run(session.sessionID) {
                                            await store.restoreArchivedSession(session.sessionID)
                                            close()
                                        }
                                    },
                                    delete: {
                                        guard confirmDelete(session) else { return }
                                        await run(session.sessionID) {
                                            await store.deleteArchivedSession(session.sessionID)
                                        }
                                    }
                                )
                            }
                        }
                    }
                    .padding(.horizontal, 12)
                    .padding(.vertical, 12)
                }
            }
            .scrollIndicators(.hidden)
            .coordinateSpace(name: "archive-scroll")
            .mask(NtrpScrollTopMask(scrolled: archiveScrolled))
            .onPreferenceChange(ArchiveScrollTopPreferenceKey.self) { top in
                let next = top < -0.5
                if archiveScrolled != next {
                    archiveScrolled = next
                }
            }
        }
        .task {
            await store.refreshArchivedSessions()
        }
    }

    private func run(_ id: String, action: @escaping () async -> Void) async {
        guard busyID == nil else { return }
        busyID = id
        await action()
        busyID = nil
    }

    private func confirmDelete(_ session: SessionListItem) -> Bool {
        let alert = NSAlert()
        alert.messageText = "Permanently delete this session?"
        alert.informativeText = "This cannot be undone."
        alert.addButton(withTitle: "Delete")
        alert.addButton(withTitle: "Cancel")
        alert.alertStyle = .warning
        return alert.runModal() == .alertFirstButtonReturn
    }
}

private struct ArchiveScrollTopPreferenceKey: PreferenceKey {
    static var defaultValue: CGFloat = 0

    static func reduce(value: inout CGFloat, nextValue: () -> CGFloat) {
        value = nextValue()
    }
}

private struct ArchiveRow: View {
    let session: SessionListItem
    let busy: Bool
    let restore: () async -> Void
    let delete: () async -> Void
    @State private var hovering = false

    var body: some View {
        HStack(spacing: 12) {
            VStack(alignment: .leading, spacing: 3) {
                Text(sessionTitle)
                    .font(.system(size: 15, weight: .medium))
                    .foregroundStyle(NtrpColors.text)
                    .lineLimit(1)
                Text("archived \(shortRelative(session.archivedAt ?? session.lastActivity)) ago · \(session.messageCount) \(session.messageCount == 1 ? "msg" : "msgs")")
                    .font(.system(size: 11))
                    .foregroundStyle(NtrpColors.faint)
                    .lineLimit(1)
            }
            Spacer()
            HStack(spacing: 4) {
                archiveAction("arrow.uturn.backward", label: "Restore", disabled: busy) {
                    Task { await restore() }
                }
                archiveAction("trash", label: "Delete", disabled: busy, danger: true) {
                    Task { await delete() }
                }
            }
            .opacity((hovering || busy) ? 1 : 0)
        }
        .padding(.horizontal, 10)
        .frame(height: 48)
        .background((hovering || busy) ? NtrpColors.row.opacity(0.46) : Color.clear)
        .clipShape(RoundedRectangle(cornerRadius: 9, style: .continuous))
        .onHover { hovering = $0 }
    }

    private func archiveAction(_ icon: String, label: String, disabled: Bool, danger: Bool = false, action: @escaping () -> Void) -> some View {
        Button(action: action) {
            HStack(spacing: 5) {
                Image(systemName: icon)
                    .font(.system(size: 11, weight: .medium))
                Text(label)
                    .font(.system(size: 12, weight: .medium))
            }
            .foregroundStyle(danger ? Color.red.opacity(0.86) : NtrpColors.muted)
            .padding(.horizontal, 8)
            .frame(height: 25)
            .background(NtrpColors.row.opacity(0.34))
            .clipShape(RoundedRectangle(cornerRadius: 6, style: .continuous))
        }
        .buttonStyle(.plain)
        .disabled(disabled)
    }

    private var sessionTitle: String {
        let name = session.name?.trimmingCharacters(in: .whitespacesAndNewlines) ?? ""
        return name.isEmpty ? "untitled" : name
    }
}

private struct ArchiveEmptyText: View {
    let text: String

    init(_ text: String) {
        self.text = text
    }

    var body: some View {
        Text(text)
            .font(.system(size: 15))
            .italic()
            .foregroundStyle(NtrpColors.faint)
            .frame(maxWidth: .infinity, minHeight: 200)
    }
}

private struct AgentRightSidebarView: View {
    @ObservedObject var store: NtrpStore
    @ObservedObject var ui: NtrpUIState

    private var activeCount: Int {
        activeBackgroundTasks.count + store.runningAutomations.count
    }

    private var activeBackgroundTasks: [BackgroundTaskSummary] {
        store.backgroundTasks.filter { task in
            let status = task.status ?? "running"
            return status == "running" || status == "cancel_requested"
        }
    }

    var body: some View {
        GeometryReader { geometry in
            ZStack(alignment: .topTrailing) {
                Button {
                    ui.toggleRightSidebar()
                } label: {
                    HStack(spacing: 5) {
                        if ui.rightSidebarCollapsed, activeCount > 0 {
                            StatusDot(pulse: true)
                            Text("\(activeCount)")
                                .font(.system(size: 12, weight: .medium, design: .monospaced))
                                .foregroundStyle(NtrpColors.faint)
                        }
                        Image(systemName: "sidebar.right")
                            .font(.system(size: 15, weight: .medium))
                    }
                    .foregroundStyle(NtrpColors.muted)
                    .frame(minWidth: 22, minHeight: 22)
                    .padding(.horizontal, ui.rightSidebarCollapsed && activeCount > 0 ? 4 : 0)
                    .contentShape(Rectangle())
                }
                .buttonStyle(.plain)
                .background(NtrpColors.row.opacity(0.0))
                .clipShape(RoundedRectangle(cornerRadius: 6, style: .continuous))
                .padding(.top, 14)
                .padding(.trailing, 14)
                .zIndex(2)

                rightPanel
                    .frame(maxHeight: max(120, geometry.size.height - 120), alignment: .top)
                    .offset(x: ui.rightSidebarCollapsed ? 272 : 0)
                    .allowsHitTesting(!ui.rightSidebarCollapsed)
                    .padding(.top, 8)
                    .padding(.trailing, 8)
                    .zIndex(1)
            }
            .frame(maxWidth: .infinity, maxHeight: .infinity, alignment: .topTrailing)
        }
        .animation(.snappy(duration: 0.22), value: ui.rightSidebarCollapsed)
        .task(id: store.selectedSessionID) {
            while !Task.isCancelled {
                await store.refreshActivePanel()
                try? await Task.sleep(for: .seconds(5))
            }
        }
    }

    private var rightPanel: some View {
        VStack(alignment: .leading, spacing: 0) {
            HStack {
                Text(activeCount > 0 ? "ACTIVE · \(activeCount)" : "ACTIVE")
                    .font(.system(size: 11, weight: .semibold))
                    .tracking(1.1)
                    .foregroundStyle(NtrpColors.faint)
                Spacer()
            }
            .frame(height: 34)
            .padding(.horizontal, 12)

            ScrollView {
                VStack(alignment: .leading, spacing: 0) {
                    ForEach(activeBackgroundTasks) { task in
                        ActiveRow(
                            title: task.command.isEmpty ? task.taskID : task.command,
                            detail: task.detail ?? String(task.taskID.prefix(12)),
                            elapsed: store.backgroundTaskElapsed(task),
                            status: task.status ?? "running"
                        ) {
                            Task { await store.cancelBackgroundTask(task.taskID) }
                        }
                    }

                    ForEach(store.runningAutomations) { automation in
                        ActiveRow(
                            title: automation.name.isEmpty ? automation.taskID : automation.name,
                            detail: automation.status ?? "",
                            elapsed: shortRelative(automation.runningSince),
                            status: "running"
                        )
                    }

                    if activeCount == 0 {
                        Text("No active agents or automations.")
                            .font(.system(size: 12))
                            .lineSpacing(3)
                            .foregroundStyle(NtrpColors.faint)
                            .multilineTextAlignment(.center)
                            .frame(maxWidth: .infinity, minHeight: 120)
                    }
                }
                .padding(.horizontal, 12)
                .padding(.top, 4)
                .padding(.bottom, 12)
            }
            .scrollIndicators(.hidden)
        }
        .frame(width: 256)
        .background(NtrpColors.surfaceFill(0.72))
        .overlay(
            RoundedRectangle(cornerRadius: 14, style: .continuous)
                .stroke(NtrpColors.sidebarStroke, lineWidth: 1)
        )
        .clipShape(RoundedRectangle(cornerRadius: 14, style: .continuous))
        .shadow(color: .black.opacity(0.34), radius: 22, x: 0, y: 14)
        .ntrpGlass(cornerRadius: 14)
    }
}

private struct ActiveRow: View {
    let title: String
    let detail: String
    var elapsed: String
    var status: String
    var cancel: (() -> Void)?
    @State private var hovering = false

    var body: some View {
        VStack(alignment: .leading, spacing: 2) {
            HStack(alignment: .center, spacing: 8) {
                StatusDot(color: dotColor, pulse: isRunning)
                Text(title)
                    .font(.system(size: 14, weight: .regular))
                    .tracking(-0.06)
                    .foregroundStyle(NtrpColors.text.opacity(0.82))
                    .lineLimit(1)
                Spacer(minLength: 6)
                if !elapsed.isEmpty {
                    Text(elapsed)
                        .font(.system(size: 12))
                        .monospacedDigit()
                        .foregroundStyle(NtrpColors.faint)
                        .lineLimit(1)
                }
                if let cancel, isRunning {
                    Button(action: cancel) {
                        Image(systemName: "xmark")
                            .font(.system(size: 9, weight: .bold))
                            .foregroundStyle(NtrpColors.faint)
                            .frame(width: 16, height: 16)
                    }
                    .buttonStyle(.plain)
                    .opacity(hovering ? 1 : 0)
                }
            }

            if !detail.isEmpty {
                Text(detail)
                    .font(.system(size: 12))
                    .foregroundStyle(NtrpColors.faint)
                    .lineLimit(1)
                    .padding(.leading, 14)
            }
        }
        .padding(.vertical, 4)
        .frame(maxWidth: .infinity, alignment: .leading)
        .onHover { hovering = $0 }
    }

    private var isRunning: Bool {
        status == "running"
    }

    private var dotColor: Color {
        switch status {
        case "completed":
            Color.green
        case "failed":
            Color.red
        case "cancelled", "interrupted", "cancel_request":
            NtrpColors.faint
        default:
            NtrpColors.accent
        }
    }
}

private struct StatusDot: View {
    var color: Color = NtrpColors.accent
    var pulse = false

    var body: some View {
        Circle()
            .fill(color)
            .frame(width: 6, height: 6)
            .shadow(color: color.opacity(pulse ? 0.75 : 0.25), radius: pulse ? 5 : 2)
    }
}

private let contentDateFormatter = ISO8601DateFormatter()

private func shortRelative(_ dateString: String?) -> String {
    guard let dateString, let date = contentDateFormatter.date(from: dateString) else { return "" }
    return shortElapsed(since: date)
}

func shortElapsed(since date: Date) -> String {
    let seconds = max(0, Int(Date().timeIntervalSince(date)))
    if seconds < 60 { return "\(seconds)s" }
    let minutes = seconds / 60
    if minutes < 60 { return "\(minutes)m" }
    let hours = minutes / 60
    if hours < 48 { return "\(hours)h" }
    return "\(hours / 24)d"
}

enum MainSurface {
    case chat
    case settings
    case automations
    case memory
    case archive
}

private struct SidebarResizeHandle: View {
    let width: CGFloat
    let setWidth: (CGFloat) -> Void
    let finishWidth: (CGFloat) -> Void
    let resetWidth: () -> Void
    @State private var startWidth: CGFloat?
    @State private var liveWidth: CGFloat?

    var body: some View {
        Rectangle()
            .fill(Color.clear)
            .frame(width: 8)
            .contentShape(Rectangle())
            .onTapGesture(count: 2) {
                resetWidth()
            }
            .gesture(
                DragGesture(minimumDistance: 0)
                    .onChanged { value in
                        let base = startWidth ?? width
                        startWidth = base
                        let next = base + value.translation.width
                        liveWidth = next
                        setWidth(next)
                    }
                    .onEnded { _ in
                        finishWidth(liveWidth ?? width)
                        startWidth = nil
                        liveWidth = nil
                    }
            )
    }
}
