import AppKit
import SwiftUI
import WebKit

struct ChatView: View {
    @ObservedObject var store: NtrpStore
    @ObservedObject var ui: NtrpUIState
    @Binding var sidebarHidden: Bool
    @State private var isNearBottom = true
    @State private var unreadCount = 0
    @State private var seenLastMessageID: String?
    @State private var bottomStackHeight: CGFloat = 96
    @State private var chatScrolled = false

    private let bottomAnchorID = "chat-bottom-anchor"

    var body: some View {
        ZStack(alignment: .bottom) {
            bottomFade
                .allowsHitTesting(false)
                .zIndex(1)

            ScrollViewReader { proxy in
                    GeometryReader { viewport in
                        ScrollView {
                            LazyVStack(alignment: .leading, spacing: 12) {
                                chatTopSentinel

                                if store.messages.isEmpty {
                                    EmptyChatState(connected: store.connectionLabel == "Connected")
                                        .frame(maxWidth: .infinity)
                                } else {
                                    ForEach(chatSegments) { segment in
                                        if let user = segment.user {
                                            TurnGroupRow(segment: segment, store: store, ui: ui)
                                                .id(user.id)
                                        } else {
                                            ForEach(segment.children) { message in
                                                MessageRow(message: message, store: store, ui: ui)
                                                    .id(message.id)
                                            }
                                        }
                                    }
                                }
                                CompactionIndicator(store: store)
                                bottomSentinel
                            }
                            .padding(.horizontal, 28)
                            .frame(maxWidth: 760, alignment: .leading)
                            .padding(.top, 100)
                            .padding(.bottom, bottomStackHeight + 40)
                            .frame(maxWidth: .infinity)
                        }
                        .blur(radius: store.pendingApprovals.isEmpty ? 0 : 0.6)
                        .saturation(store.pendingApprovals.isEmpty ? 1 : 0.96)
                        .coordinateSpace(name: "chat-scroll")
                        .scrollContentBackground(.hidden)
                        .mask(NtrpScrollTopMask(scrolled: chatScrolled))
                        .onPreferenceChange(ChatTopYPreferenceKey.self) { topY in
                            let next = topY < -0.5
                            if chatScrolled != next {
                                chatScrolled = next
                            }
                        }
                        .onPreferenceChange(ChatBottomYPreferenceKey.self) { bottomY in
                            updateNearBottom(bottomY: bottomY, viewportHeight: viewport.size.height)
                        }
                        .onChange(of: store.selectedSessionID) { _, _ in
                            isNearBottom = true
                            unreadCount = 0
                            seenLastMessageID = nil
                        }
                        .onChange(of: store.messages.count) { _, _ in
                            handleMessagesChanged(proxy: proxy)
                        }
                        .overlay(alignment: .bottom) {
                            if !isNearBottom && !store.messages.isEmpty {
                                JumpToBottomPill(unreadCount: unreadCount) {
                                    unreadCount = 0
                                    if let last = store.messages.last?.id {
                                        seenLastMessageID = last
                                    }
                                    withAnimation(.snappy(duration: 0.22)) {
                                        proxy.scrollTo(bottomAnchorID, anchor: .bottom)
                                    }
                                }
                                .padding(.bottom, bottomStackHeight + 12)
                                .transition(.opacity.combined(with: .scale(scale: 0.95)))
                            }
                        }
                    }
            }
            .zIndex(0)

            header
                .frame(height: 52)
                .padding(.leading, sidebarHidden ? 128 : 18)
                .padding(.trailing, 18)
                .frame(maxWidth: .infinity, maxHeight: .infinity, alignment: .top)
                .zIndex(2)

            VStack(spacing: 10) {
                ApprovalStrip(store: store, ui: ui)
                ComposerView(store: store, ui: ui)
                    .frame(maxWidth: 760)
            }
            .padding(.horizontal, 28)
            .padding(.bottom, 8)
            .zIndex(2)
            .background(
                GeometryReader { geometry in
                    Color.clear.preference(key: ChatBottomStackHeightKey.self, value: geometry.size.height)
                }
            )
        }
        .foregroundStyle(NtrpColors.text)
        .onPreferenceChange(ChatBottomStackHeightKey.self) { height in
            if height > 0, abs(height - bottomStackHeight) > 0.5 {
                bottomStackHeight = height
            }
        }
    }

    private var bottomFade: some View {
        LinearGradient(
            colors: [
                NtrpColors.canvas.opacity(0.0),
                NtrpColors.canvas.opacity(0.38),
                NtrpColors.canvas.opacity(0.82)
            ],
            startPoint: .top,
            endPoint: .bottom
        )
        .frame(height: bottomStackHeight + 24)
        .frame(maxWidth: .infinity, maxHeight: .infinity, alignment: .bottom)
    }

    private var chatTopSentinel: some View {
        GeometryReader { geometry in
            Color.clear.preference(
                key: ChatTopYPreferenceKey.self,
                value: geometry.frame(in: .named("chat-scroll")).minY
            )
        }
        .frame(height: 1)
        .padding(.bottom, -1)
    }

    private var bottomSentinel: some View {
        GeometryReader { geometry in
            Color.clear.preference(
                key: ChatBottomYPreferenceKey.self,
                value: geometry.frame(in: .named("chat-scroll")).maxY
            )
        }
        .frame(height: 1)
        .id(bottomAnchorID)
    }

    private func updateNearBottom(bottomY: CGFloat, viewportHeight: CGFloat) {
        let next = bottomY <= viewportHeight + 120
        if next != isNearBottom {
            isNearBottom = next
        }
        if next {
            seenLastMessageID = store.messages.last?.id
            if unreadCount != 0 {
                unreadCount = 0
            }
        }
    }

    private func handleMessagesChanged(proxy: ScrollViewProxy) {
        guard let last = store.messages.last?.id else {
            seenLastMessageID = nil
            unreadCount = 0
            return
        }

        if isNearBottom {
            seenLastMessageID = last
            unreadCount = 0
            withAnimation(.snappy(duration: 0.2)) {
                proxy.scrollTo(bottomAnchorID, anchor: .bottom)
            }
            return
        }

        guard let seenLastMessageID,
              let seenIndex = store.messages.firstIndex(where: { $0.id == seenLastMessageID })
        else {
            seenLastMessageID = last
            unreadCount = 0
            return
        }

        unreadCount = max(0, store.messages.count - 1 - seenIndex)
    }

    private var header: some View {
        HStack(spacing: 10) {
            HStack(alignment: .firstTextBaseline, spacing: 8) {
                Text(currentTitle)
                    .font(.system(size: 16, weight: .semibold))
                    .tracking(-0.16)
                    .foregroundStyle(NtrpColors.text)
                    .lineLimit(1)

                if currentSession?.sessionType == "channel" {
                    HStack(spacing: 4) {
                        Image(systemName: "dot.radiowaves.left.and.right")
                            .font(.system(size: 9, weight: .medium))
                        Text("channel")
                    }
                    .font(.system(size: 10, weight: .semibold))
                    .tracking(0.6)
                    .textCase(.uppercase)
                    .foregroundStyle(NtrpColors.muted)
                    .padding(.horizontal, 7)
                    .frame(height: 18)
                    .background(NtrpColors.row.opacity(0.45))
                    .clipShape(Capsule())

                    if let originLabel {
                        Text("from \(originLabel)")
                            .font(.system(size: 12))
                            .foregroundStyle(NtrpColors.faint)
                            .lineLimit(1)
                    }
                }
            }

            Spacer()
        }
        .frame(maxWidth: .infinity)
    }

    private var currentTitle: String {
        currentSession?.name ?? (store.selectedSessionID == nil ? "no session" : "untitled")
    }

    private var currentSession: SessionListItem? {
        guard let id = store.selectedSessionID else { return nil }
        return store.sessions.first(where: { $0.sessionID == id })
    }

    private var originLabel: String? {
        guard let id = currentSession?.originAutomationID, !id.isEmpty else { return nil }
        if let automation = store.runningAutomations.first(where: { $0.taskID == id }),
           !automation.name.isEmpty {
            return automation.name
        }
        return String(id.prefix(8))
    }

    private var chatSegments: [ChatSegment] {
        ChatSegment.build(from: store.messages)
    }
}

private struct ChatSegment: Identifiable {
    let id: String
    var user: TranscriptMessage?
    var children: [TranscriptMessage]

    static func build(from messages: [TranscriptMessage]) -> [ChatSegment] {
        var segments: [ChatSegment] = []
        var current: ChatSegment?

        for message in messages {
            if message.role == .user {
                if let current { segments.append(current) }
                current = ChatSegment(id: message.id, user: message, children: [])
                continue
            }

            if message.role == .status || message.role == .error {
                if let openSegment = current {
                    segments.append(openSegment)
                    current = nil
                }
                segments.append(ChatSegment(id: "notice-\(message.id)", user: nil, children: [message]))
                continue
            }

            if current == nil {
                current = ChatSegment(id: "preamble-\(message.id)", user: nil, children: [])
            }
            current?.children.append(message)
        }

        if let current { segments.append(current) }
        return segments
    }
}

private struct TurnLayout {
    let workMessages: [TranscriptMessage]
    let afterWorkMessages: [TranscriptMessage]
    let finalAssistantID: String?

    static func make(children: [TranscriptMessage], isDone: Bool) -> TurnLayout {
        let lastAssistantID = children.last(where: { $0.role == .assistant })?.id

        guard isDone else {
            return TurnLayout(workMessages: [], afterWorkMessages: children, finalAssistantID: lastAssistantID)
        }

        guard children.contains(where: { $0.role == .activity }) else {
            return TurnLayout(workMessages: [], afterWorkMessages: children, finalAssistantID: lastAssistantID)
        }

        guard children.last?.role == .assistant, let final = children.last else {
            return TurnLayout(workMessages: children, afterWorkMessages: [], finalAssistantID: nil)
        }

        return TurnLayout(
            workMessages: children.dropLast(),
            afterWorkMessages: [final],
            finalAssistantID: final.id
        )
    }
}

private struct ChatBottomYPreferenceKey: PreferenceKey {
    static var defaultValue: CGFloat = .greatestFiniteMagnitude

    static func reduce(value: inout CGFloat, nextValue: () -> CGFloat) {
        value = nextValue()
    }
}

private struct ChatTopYPreferenceKey: PreferenceKey {
    static var defaultValue: CGFloat = 0

    static func reduce(value: inout CGFloat, nextValue: () -> CGFloat) {
        value = nextValue()
    }
}

private struct ChatBottomStackHeightKey: PreferenceKey {
    static var defaultValue: CGFloat = 96

    static func reduce(value: inout CGFloat, nextValue: () -> CGFloat) {
        value = nextValue()
    }
}

private struct JumpToBottomPill: View {
    let unreadCount: Int
    let action: () -> Void

    var body: some View {
        Button(action: action) {
            HStack(spacing: unreadCount > 0 ? 6 : 0) {
                Image(systemName: "chevron.down")
                    .font(.system(size: 14, weight: .semibold))
                if unreadCount > 0 {
                    Text("\(unreadCount) new")
                        .font(.system(size: 13, weight: .medium))
                        .monospacedDigit()
                }
            }
            .foregroundStyle(unreadCount > 0 ? Color.black.opacity(0.88) : NtrpColors.muted)
            .frame(minWidth: unreadCount > 0 ? 0 : 32, minHeight: 32)
            .padding(.horizontal, unreadCount > 0 ? 11 : 0)
            .background(unreadCount > 0 ? NtrpColors.text : NtrpColors.sidebar.opacity(0.9))
            .overlay(
                Capsule()
                    .stroke(unreadCount > 0 ? Color.clear : NtrpColors.sidebarStroke, lineWidth: 1)
            )
            .clipShape(Capsule())
            .shadow(color: .black.opacity(0.24), radius: 14, x: 0, y: 8)
        }
        .buttonStyle(.plain)
        .help(unreadCount > 0 ? "\(unreadCount) new message\(unreadCount == 1 ? "" : "s") - jump to latest" : "Scroll to bottom")
    }
}

private struct EmptyChatState: View {
    let connected: Bool

    var body: some View {
        VStack(spacing: 20) {
            Image(systemName: "sparkles")
                .font(.system(size: 28, weight: .medium))
                .foregroundStyle(NtrpColors.accent)
                .frame(width: 48, height: 48)
                .background(NtrpColors.accent.opacity(0.14))
                .clipShape(RoundedRectangle(cornerRadius: 16, style: .continuous))

            VStack(spacing: 6) {
                Text(connected ? "What's on your mind?" : "Connect to get started")
                    .font(.system(size: 24, weight: .semibold))
                    .tracking(-0.43)
                    .foregroundStyle(NtrpColors.text)
                Text(connected ? "Send a message, or press ⌘K to search memory, agents, and tools." : "Open settings to point ntrp at your server.")
                    .font(.system(size: 16))
                    .foregroundStyle(NtrpColors.muted)
                    .multilineTextAlignment(.center)
                    .lineLimit(2)
            }
            .frame(maxWidth: 420)
        }
        .frame(maxWidth: .infinity)
        .padding(.top, 120)
        .multilineTextAlignment(.center)
    }
}

private struct TurnGroupRow: View {
    let segment: ChatSegment
    @ObservedObject var store: NtrpStore
    @ObservedObject var ui: NtrpUIState
    @State private var expanded = false

    private var isDone: Bool {
        segment.children.contains { $0.role == .assistant } && !store.isStreaming
    }

    private var layout: TurnLayout {
        TurnLayout.make(children: segment.children, isDone: isDone)
    }

    private var workMessages: [TranscriptMessage] {
        layout.workMessages
    }

    private var inlineMessages: [TranscriptMessage] {
        layout.afterWorkMessages
    }

    private var usesWorkBlock: Bool {
        !workMessages.isEmpty
    }

    private var showWork: Bool {
        !isDone || expanded
    }

    private var headerLabel: String {
        guard let duration = workDurationLabel else { return "Worked" }
        return "Worked for \(duration)"
    }

    private var workDurationLabel: String? {
        let dated = segment.children.compactMap { message -> Date? in
            guard let createdAt = message.createdAt else { return nil }
            return ISO8601DateFormatter.ntrp.date(from: createdAt) ?? ISO8601DateFormatter.ntrpFractional.date(from: createdAt)
        }
        guard let first = dated.first, let last = dated.last, last >= first else { return nil }
        return formatWorkDuration(last.timeIntervalSince(first))
    }

    var body: some View {
        VStack(alignment: .leading, spacing: 10) {
            if let user = segment.user {
                MessageRow(message: user, store: store, ui: ui)
            }

            if usesWorkBlock && isDone {
                workBlock
            }

            ForEach(inlineMessages) { message in
                MessageRow(
                    message: message,
                    store: store,
                    ui: ui,
                    showsAssistantActions: message.role != .assistant || (isDone && message.id == layout.finalAssistantID)
                )
            }

            if usesWorkBlock && !isDone {
                workBlock
            }
        }
        .frame(maxWidth: .infinity, alignment: .leading)
    }

    private var workBlock: some View {
        VStack(alignment: .leading, spacing: 0) {
            if isDone {
                Button {
                    withAnimation(.snappy(duration: 0.18)) {
                        expanded.toggle()
                    }
                } label: {
                    HStack(spacing: 6) {
                        Text(headerLabel)
                        Image(systemName: "chevron.down")
                            .font(.system(size: 9, weight: .semibold))
                            .rotationEffect(.degrees(expanded ? 180 : 0))
                    }
                    .font(.system(size: 16))
                    .foregroundStyle(NtrpColors.muted)
                }
                .buttonStyle(.plain)
            }

            if showWork {
                VStack(alignment: .leading, spacing: 4) {
                    if isDone {
                        Rectangle()
                            .fill(NtrpColors.sidebarStroke)
                            .frame(height: 1)
                            .padding(.top, 8)
                    }

                    WorkMessageList(messages: workMessages, done: isDone, store: store, ui: ui)
                }
                .transition(.opacity.combined(with: .move(edge: .top)))
            }
        }
    }
}

private struct WorkMessageList: View {
    let messages: [TranscriptMessage]
    let done: Bool
    @ObservedObject var store: NtrpStore
    @ObservedObject var ui: NtrpUIState

    var body: some View {
        VStack(alignment: .leading, spacing: 14) {
            ForEach(workItems) { item in
                switch item.kind {
                case .activity(let messages):
                    ActivityTraceView(messages: messages, done: done, ui: ui)
                case .message(let message):
                    MessageRow(message: message, store: store, ui: ui, showsAssistantActions: false)
                }
            }
        }
    }

    private var workItems: [WorkItem] {
        var items: [WorkItem] = []
        var activityGroup: [TranscriptMessage] = []

        func flushActivityGroup() {
            guard !activityGroup.isEmpty else { return }
            let id = "activity-\(activityGroup.first?.id ?? UUID().uuidString)"
            items.append(WorkItem(id: id, kind: .activity(activityGroup)))
            activityGroup.removeAll()
        }

        for message in messages {
            if message.role == .activity {
                activityGroup.append(message)
            } else {
                flushActivityGroup()
                items.append(WorkItem(id: message.id, kind: .message(message)))
            }
        }
        flushActivityGroup()
        return items
    }
}

private struct WorkItem: Identifiable {
    enum Kind {
        case message(TranscriptMessage)
        case activity([TranscriptMessage])
    }

    let id: String
    let kind: Kind
}

private func formatWorkDuration(_ seconds: TimeInterval) -> String {
    if seconds < 1 { return "less than a second" }
    let total = Int(seconds.rounded())
    if total < 60 { return "\(total)s" }
    let minutes = total / 60
    let remSeconds = total % 60
    if minutes < 60 {
        return remSeconds == 0 ? "\(minutes)m" : "\(minutes)m \(remSeconds)s"
    }
    let hours = minutes / 60
    let remMinutes = minutes % 60
    return remMinutes == 0 ? "\(hours)h" : "\(hours)h \(remMinutes)m"
}

private struct ActivityTraceView: View {
    let messages: [TranscriptMessage]
    let done: Bool
    @ObservedObject var ui: NtrpUIState

    private var visibleMessages: [TranscriptMessage] {
        done ? staticTree(messages) : rollingTree(messages, max: 3)
    }

    var body: some View {
        VStack(alignment: .leading, spacing: 3) {
            HStack(spacing: 8) {
                Image(systemName: "terminal")
                    .font(.system(size: 16, weight: .medium))
                Text(done ? "Called" : "Calling")
                    .padding(.trailing, 4)
                Text("\(messages.count) \(messages.count == 1 ? "tool" : "tools")")
                if !done {
                    NtrpSpinner(size: 10, lineWidth: 1.3)
                        .frame(width: 14, height: 14)
                }
            }
            .font(.system(size: 14))
            .foregroundStyle(NtrpColors.faint)

            VStack(alignment: .leading, spacing: 0) {
                ForEach(visibleMessages) { message in
                    ActivityTraceRow(message: message) {
                        ui.inspectingTool = message
                    }
                        .frame(height: 20)
                }
            }
            .padding(.leading, 12)
        }
        .font(.system(size: 14))
        .foregroundStyle(NtrpColors.muted)
    }

    private func staticTree(_ messages: [TranscriptMessage]) -> [TranscriptMessage] {
        let childrenByParent = Dictionary(grouping: messages.filter { $0.parentToolID != nil }) { message in
            message.parentToolID ?? ""
        }
        var output: [TranscriptMessage] = []
        var seen = Set<String>()

        func visit(_ message: TranscriptMessage) {
            guard !seen.contains(message.id) else { return }
            seen.insert(message.id)
            output.append(message)
            for child in childrenByParent[message.id] ?? [] {
                visit(child)
            }
        }

        for message in messages where (message.toolDepth ?? 0) == 0 {
            visit(message)
        }
        for message in messages where !seen.contains(message.id) {
            visit(message)
        }
        return output
    }

    private func rollingTree(_ messages: [TranscriptMessage], max: Int) -> [TranscriptMessage] {
        let childrenByParent = Dictionary(grouping: messages.filter { $0.parentToolID != nil }) { message in
            message.parentToolID ?? ""
        }
        var output: [TranscriptMessage] = []
        var seen = Set<String>()

        func include(_ message: TranscriptMessage) {
            guard !seen.contains(message.id) else { return }
            seen.insert(message.id)
            output.append(message)
            guard message.toolResult == nil else { return }
            for child in (childrenByParent[message.id] ?? []).suffix(max) {
                include(child)
            }
        }

        let topLevel = messages.filter { ($0.toolDepth ?? 0) == 0 }
        for message in topLevel.suffix(max) {
            include(message)
        }
        return output.isEmpty ? Array(messages.suffix(max)) : output
    }
}

private struct ActivityTraceRow: View {
    let message: TranscriptMessage
    let open: () -> Void

    var body: some View {
        Button(action: open) {
            HStack(alignment: .firstTextBaseline, spacing: 6) {
                if isAgent {
                    Image(systemName: "brain")
                        .font(.system(size: 11, weight: .medium))
                        .foregroundStyle(NtrpColors.accent)
                        .frame(width: 18, height: 18)
                        .background(NtrpColors.accent.opacity(0.14))
                        .clipShape(RoundedRectangle(cornerRadius: 6, style: .continuous))
                }

                Text(target)
                    .font(.system(size: 14, design: .monospaced))
                    .foregroundStyle(rowColor)
                    .lineLimit(1)
                if let durationLabel {
                    Text(durationLabel)
                        .font(.system(size: 12, design: .monospaced))
                        .foregroundStyle(NtrpColors.faint)
                        .lineLimit(1)
                }
                if let usageLabel, message.toolResult != nil {
                    Text(usageLabel)
                        .font(.system(size: 12, design: .monospaced))
                        .foregroundStyle(NtrpColors.faint)
                        .lineLimit(1)
                }
            }
            .frame(maxWidth: .infinity, alignment: .leading)
            .padding(.leading, CGFloat(min(message.toolDepth ?? 0, 4)) * 16)
        }
        .buttonStyle(.plain)
        .help("Open tool details")
    }

    private var target: String {
        if !message.content.isEmpty {
            return message.content
        }
        if let detail = message.detail, detail.hasPrefix("Called ") {
            return String(detail.dropFirst("Called ".count))
        }
        return "tool"
    }

    private var isAgent: Bool {
        message.toolSemanticKind == "agent" || target.lowercased().contains("agent") || target.lowercased().contains("subagent")
    }

    private var rowColor: Color {
        if message.toolResultIsError { return Color(red: 0.83, green: 0.33, blue: 0.24) }
        return message.toolResult == nil ? NtrpColors.muted : NtrpColors.faint
    }

    private var durationLabel: String? {
        guard let duration = message.toolDurationMS, duration > 0 else { return nil }
        if duration < 1000 { return "\(Int(duration.rounded()))ms" }
        return String(format: "%.1fs", duration / 1000)
    }

    private var usageLabel: String? {
        guard isAgent else { return nil }
        let tokens = message.toolUsageTotal ?? 0
        let cost = message.toolCost
        guard tokens > 0 || (cost ?? 0) > 0 else { return nil }
        let tokenLabel: String
        if tokens < 1000 {
            tokenLabel = "\(tokens)"
        } else if tokens < 10_000 {
            tokenLabel = String(format: "%.1fk", Double(tokens) / 1000)
        } else {
            tokenLabel = "\(Int((Double(tokens) / 1000).rounded()))k"
        }
        guard let cost, cost > 0 else {
            return "· \(tokenLabel)"
        }
        let costLabel = cost < 0.01 ? String(format: "$%.4f", cost) : String(format: "$%.3f", cost)
        return "· \(tokenLabel) · \(costLabel)"
    }
}

private struct CompactionIndicator: View {
    @ObservedObject var store: NtrpStore
    @State private var visibleCompaction: LastCompaction?
    @State private var hideTask: Task<Void, Never>?

    var body: some View {
        Group {
            if store.compacting {
                HStack(spacing: 8) {
                    NtrpSpinner(size: 11, lineWidth: 1.4)
                    Text("Compacting conversation...")
                        .font(.system(size: 14, weight: .medium))
                        .foregroundStyle(NtrpColors.muted)
                }
                .padding(.vertical, 4)
            } else if let compaction = visibleCompaction {
                HStack(spacing: 8) {
                    Image(systemName: "sparkles")
                        .font(.system(size: 12, weight: .medium))
                        .foregroundStyle(NtrpColors.faint)
                    Text("Conversation compacted (\(compaction.before) -> \(compaction.after) messages)")
                        .font(.system(size: 14))
                        .foregroundStyle(NtrpColors.faint)
                }
                .padding(.vertical, 4)
            }
        }
        .animation(.snappy(duration: 0.18), value: store.compacting)
        .animation(.snappy(duration: 0.18), value: visibleCompaction)
        .onChange(of: store.lastCompaction) { _, compaction in
            guard let compaction else { return }
            visibleCompaction = compaction
            hideTask?.cancel()
            hideTask = Task {
                try? await Task.sleep(for: .milliseconds(4500))
                await MainActor.run {
                    if visibleCompaction == compaction {
                        visibleCompaction = nil
                    }
                }
            }
        }
        .onDisappear {
            hideTask?.cancel()
        }
    }
}

private struct MessageRow: View {
    let message: TranscriptMessage
    @ObservedObject var store: NtrpStore
    @ObservedObject var ui: NtrpUIState
    var showsAssistantActions = true
    @State private var reasoningExpanded = false
    @State private var hovered = false
    @AppStorage("ntrp.showReasoningInChat") private var showReasoning = true

    @ViewBuilder
    var body: some View {
        content
    }

    @ViewBuilder
    private var content: some View {
        switch message.role {
        case .user:
            userMessage
        case .assistant:
            if !showsAssistantActions && message.content.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty {
                EmptyView()
            } else {
                assistantMessage
            }
        case .reasoning, .activity:
            if message.role == .reasoning && !showReasoning {
                EmptyView()
            } else {
                activityMessage
            }
        case .approval:
            activityMessage
        case .status:
            statusMessage
        case .error:
            errorMessage
        }
    }

    private var userMessage: some View {
        let match = skillMatch
        let goal = goalMatch
        let visibleContent = goal ?? match?.rest ?? message.content
        let showBubble = !visibleContent.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty
        return HStack {
            Spacer(minLength: 0)
            VStack(alignment: .trailing, spacing: 6) {
                if !message.images.isEmpty {
                    HStack(spacing: 6) {
                        ForEach(message.images) { image in
                            if let preview = image.preview {
                                Image(nsImage: preview)
                                    .resizable()
                                    .scaledToFill()
                                    .frame(maxWidth: 220, maxHeight: 180)
                                    .clipShape(RoundedRectangle(cornerRadius: 8, style: .continuous))
                                    .overlay(RoundedRectangle(cornerRadius: 8, style: .continuous).stroke(NtrpColors.sidebarStroke, lineWidth: 1))
                            }
                        }
                    }
                    .frame(maxWidth: 570, alignment: .trailing)
                }

                if showBubble {
                    Text(visibleContent)
                        .font(.system(size: 16))
                        .lineSpacing(3)
                        .frame(maxWidth: 570, alignment: .leading)
                        .padding(.horizontal, 14)
                        .padding(.vertical, 8)
                        .background(NtrpColors.surfaceFill(0.35))
                        .clipShape(RoundedRectangle(cornerRadius: 18, style: .continuous))
                        .ntrpGlass(cornerRadius: 18)
                        .textSelection(.enabled)
                }

                if goal != nil {
                    GoalChip()
                } else if let skill = match?.skill {
                    SkillChip(skill: skill) {
                        Task {
                            if let view = await store.markdownForSkill(skill) {
                                ui.viewingMarkdown = view
                            }
                        }
                    }
                }

                detail
                MessageActions(message: message, store: store, role: .user, visible: hovered)
            }
            .frame(maxWidth: 570, alignment: .trailing)
        }
        .onHover { hovered = $0 }
    }

    private var assistantMessage: some View {
        VStack(alignment: .leading, spacing: 7) {
            MarkdownText(message.content.isEmpty ? " " : message.content)
                .font(.system(size: 16))
                .lineSpacing(4)
                .textSelection(.enabled)
            detail
            if showsAssistantActions {
                MessageActions(message: message, store: store, role: .assistant, visible: hovered)
            }
        }
        .frame(maxWidth: .infinity, alignment: .leading)
        .onHover { hovered = $0 }
    }

    @ViewBuilder
    private var activityMessage: some View {
        if message.role == .reasoning {
            reasoningMessage
        } else {
            toolMessage
        }
    }

    private var reasoningMessage: some View {
        VStack(alignment: .leading, spacing: 6) {
            Button {
                withAnimation(.snappy(duration: 0.16)) {
                    reasoningExpanded.toggle()
                }
            } label: {
                HStack(spacing: 6) {
                    Image(systemName: "brain")
                        .font(.system(size: 12, weight: .medium))
                    Text("Reasoning")
                        .font(.system(size: 12, weight: .medium))
                    Image(systemName: "chevron.down")
                        .font(.system(size: 9, weight: .semibold))
                        .rotationEffect(.degrees(reasoningExpanded ? 180 : 0))
                }
                .foregroundStyle(NtrpColors.muted)
            }
            .buttonStyle(.plain)

            if reasoningExpanded && !message.content.isEmpty {
                MarkdownText(message.content)
                    .font(.system(size: 12))
                    .italic()
                    .foregroundStyle(NtrpColors.muted)
                    .lineSpacing(3)
                    .padding(.leading, 12)
                    .overlay(alignment: .leading) {
                        Rectangle()
                            .fill(NtrpColors.sidebarStroke)
                            .frame(width: 2)
                    }
                    .textSelection(.enabled)
                    .transition(.opacity.combined(with: .move(edge: .top)))
            }
        }
    }

    private var toolMessage: some View {
        Button {
            ui.inspectingTool = message
        } label: {
            VStack(alignment: .leading, spacing: 5) {
                HStack(alignment: .firstTextBaseline, spacing: 8) {
                    Text("↗")
                        .font(.system(size: 12, design: .monospaced))
                        .foregroundStyle(NtrpColors.faint)
                    Image(systemName: icon)
                        .font(.system(size: 12, weight: .medium))
                        .foregroundStyle(NtrpColors.muted)
                    Text(activityTitle)
                        .font(.system(size: 12, weight: .medium, design: .monospaced))
                        .foregroundStyle(NtrpColors.text.opacity(0.78))
                        .lineLimit(1)
                    if let subtitle = activitySubtitle {
                        Text(subtitle)
                            .font(.system(size: 12, design: .monospaced))
                            .foregroundStyle(NtrpColors.faint)
                            .lineLimit(1)
                    }
                }

                if let detail = message.detail,
                   !detail.isEmpty,
                   !detail.hasPrefix("Called ") {
                    Text(detail)
                        .font(.system(size: 14, design: .monospaced))
                        .foregroundStyle(NtrpColors.muted)
                        .lineSpacing(2)
                        .lineLimit(4)
                        .frame(maxHeight: 80, alignment: .topLeading)
                        .clipped()
                        .padding(.top, 3)
                        .padding(.leading, 18)
                        .textSelection(.enabled)
                }
            }
            .contentShape(Rectangle())
        }
        .buttonStyle(.plain)
        .help("Open tool details")
    }

    private var errorMessage: some View {
        Text(message.content)
            .font(.system(size: 16))
            .lineSpacing(3)
            .foregroundStyle(Color(red: 0.83, green: 0.33, blue: 0.24))
            .padding(.horizontal, 14)
            .padding(.vertical, 10)
            .background(Color(red: 0.72, green: 0.27, blue: 0.17).opacity(0.12))
            .overlay(
                RoundedRectangle(cornerRadius: 10, style: .continuous)
                    .stroke(Color(red: 0.72, green: 0.27, blue: 0.17).opacity(0.18), lineWidth: 1)
            )
            .clipShape(RoundedRectangle(cornerRadius: 10, style: .continuous))
            .textSelection(.enabled)
    }

    private var statusMessage: some View {
        HStack {
            Spacer(minLength: 0)
            Text(statusText)
                .font(.system(size: 14, design: .monospaced))
                .foregroundStyle(NtrpColors.muted)
                .lineLimit(3)
                .padding(.horizontal, 10)
                .padding(.vertical, 4)
                .background(NtrpColors.row)
                .clipShape(Capsule())
                .textSelection(.enabled)
            Spacer(minLength: 0)
        }
    }

    private var statusText: String {
        guard let detail = message.detail, !detail.isEmpty else { return message.content }
        return "\(detail) · \(message.content)"
    }

    @ViewBuilder
    private var detail: some View {
        if let detail = message.detail, !detail.isEmpty {
            HStack(spacing: 8) {
                Text(detail)
                    .font(.system(size: 12))
                    .foregroundStyle(NtrpColors.faint)
                    .lineLimit(4)
                if store.queuedMessageIDs.contains(message.id) {
                    Button("Cancel") {
                        Task { await store.cancelQueuedMessage(message.id) }
                    }
                    .font(.system(size: 12))
                    .buttonStyle(.plain)
                    .foregroundStyle(NtrpColors.muted)
                }
            }
        }
    }

    private var label: String {
        switch message.role {
        case .reasoning: "Reasoning"
        case .activity: "Called"
        case .approval: "Approval"
        case .status: "Status"
        default: ""
            }
    }

    private var activityTitle: String {
        guard message.role == .activity else { return label }
        if !message.content.isEmpty {
            return message.content
        }
        if let toolName = message.toolName, !toolName.isEmpty { return toolName }
        return label
    }

    private var activitySubtitle: String? {
        guard message.role == .activity else { return nil }
        if let detail = message.detail, detail.hasPrefix("Called ") {
            return String(detail.dropFirst("Called ".count))
        }
        return message.toolName
    }

    private var icon: String {
        switch message.role {
        case .reasoning: "brain"
        case .approval: "shield"
        default: "terminal"
        }
    }

    private var skillMatch: (skill: JSONValue, rest: String)? {
        let skills = store.skills
        if message.content.hasPrefix("/") {
            let body = String(message.content.dropFirst())
            let parts = body.split(separator: " ", maxSplits: 1, omittingEmptySubsequences: false)
            guard let name = parts.first.map(String.init),
                  let skill = skills.first(where: { skillName($0) == name })
            else { return nil }
            let rest = parts.count > 1 ? String(parts[1]).trimmingCharacters(in: .whitespacesAndNewlines) : ""
            return (skill, rest)
        }

        if message.content.hasPrefix("<skill"),
           let nameRange = message.content.range(of: #"name="([^"]+)""#, options: .regularExpression),
           let closeRange = message.content.range(of: "</skill>") {
            let nameToken = String(message.content[nameRange])
                .replacingOccurrences(of: #"name=""#, with: "")
                .replacingOccurrences(of: #"""#, with: "")
            guard let skill = skills.first(where: { skillName($0) == nameToken }) else { return nil }
            var rest = String(message.content[closeRange.upperBound...])
                .trimmingCharacters(in: .whitespacesAndNewlines)
            if rest.hasPrefix("User request:") {
                rest = String(rest.dropFirst("User request:".count)).trimmingCharacters(in: .whitespacesAndNewlines)
            }
            return (skill, rest)
        }

        return nil
    }

    private var goalMatch: String? {
        guard message.content.hasPrefix("/goal") else { return nil }
        let rest = String(message.content.dropFirst("/goal".count)).trimmingCharacters(in: .whitespacesAndNewlines)
        return rest.isEmpty ? nil : rest
    }
}

struct ToolDetailPanel: View {
    let message: TranscriptMessage
    var messages: [TranscriptMessage] = []
    var openTool: ((TranscriptMessage) -> Void)?
    let close: () -> Void
    @State private var scrolled = false

    private var input: String {
        prettyPrintJSON(message.toolArguments) ?? message.toolArguments ?? ""
    }

    private var output: String {
        prettyPrintJSON(message.toolResult) ?? message.toolResult ?? message.detail ?? ""
    }

    var body: some View {
        VStack(alignment: .leading, spacing: 0) {
            HStack(alignment: .top, spacing: 14) {
                HStack(alignment: .center, spacing: 10) {
                    if isAgent {
                        Image(systemName: "cpu")
                            .font(.system(size: 12, weight: .medium))
                            .foregroundStyle(NtrpColors.accent)
                            .frame(width: 22, height: 22)
                            .background(NtrpColors.accent.opacity(0.14))
                            .clipShape(RoundedRectangle(cornerRadius: 6, style: .continuous))
                    }
                    VStack(alignment: .leading, spacing: 2) {
                        Text(toolTitle)
                            .font(.system(size: 18, weight: .semibold))
                            .tracking(-0.216)
                            .foregroundStyle(NtrpColors.text)
                            .lineLimit(1)
                        if let target {
                            Text(target)
                                .font(.system(size: 12, design: .monospaced))
                                .foregroundStyle(NtrpColors.faint)
                                .lineLimit(1)
                                .truncationMode(.middle)
                        }
                    }
                }
                Spacer()
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
            .padding(.horizontal, 20)
            .padding(.top, 18)
            .padding(.bottom, 12)

            ScrollView {
                VStack(spacing: 0) {
                    ModalScrollSentinel(space: "tool-detail-scroll")
                    VStack(alignment: .leading, spacing: 16) {
                        if message.toolSemanticKind == "agent" {
                            ToolAgentBody(message: message, descendants: childActivity, openTool: openTool)
                        } else {
                            ToolDetailSection(title: "Input", bodyText: input, empty: "No input arguments.")
                            ToolDetailSection(
                                title: "Output",
                                bodyText: output,
                                empty: message.toolResult == nil ? "Waiting for result…" : "Empty result.",
                                isError: message.toolResultIsError
                            )
                            let directChildren = childActivity.filter { $0.parentToolID == message.id }
                            if !directChildren.isEmpty {
                                ToolActivitySection(title: "Child runs", items: directChildren, showStats: false, openTool: openTool)
                            }
                        }
                    }
                    .padding(.horizontal, 20)
                    .padding(.vertical, 16)
                }
            }
            .scrollIndicators(.hidden)
            .coordinateSpace(name: "tool-detail-scroll")
            .mask(NtrpScrollTopMask(scrolled: scrolled))
            .onPreferenceChange(ModalScrollTopPreferenceKey.self) { top in
                let next = top < -0.5
                if scrolled != next {
                    scrolled = next
                }
            }
        }
    }

    private var toolTitle: String {
        let raw = message.toolName ?? message.content
        guard isAgent else { return raw }
        let stripped = raw.lowercased().hasSuffix("_agent") ? String(raw.dropLast("_agent".count)) : raw
        guard let first = stripped.first else { return raw.isEmpty ? "Agent" : raw }
        return first.uppercased() + stripped.dropFirst()
    }

    private var target: String? {
        guard !isAgent else { return nil }
        guard message.content != toolTitle, !message.content.isEmpty else { return nil }
        return message.content
    }

    private var isAgent: Bool {
        message.toolSemanticKind == "agent"
    }

    private var childActivity: [TranscriptMessage] {
        let childrenByParent = Dictionary(grouping: messages.filter { $0.parentToolID != nil }) { item in
            item.parentToolID ?? ""
        }
        var output: [TranscriptMessage] = []
        var seen = Set<String>()

        func visit(_ item: TranscriptMessage) {
            guard !seen.contains(item.id) else { return }
            seen.insert(item.id)
            output.append(item)
            for child in childrenByParent[item.id] ?? [] {
                visit(child)
            }
        }

        for child in childrenByParent[message.id] ?? [] {
            visit(child)
        }
        return output
    }

    private func prettyPrintJSON(_ raw: String?) -> String? {
        guard let raw,
              let data = raw.data(using: .utf8),
              let object = try? JSONSerialization.jsonObject(with: data),
              JSONSerialization.isValidJSONObject(object),
              let prettyData = try? JSONSerialization.data(withJSONObject: object, options: [.prettyPrinted]),
              let pretty = String(data: prettyData, encoding: .utf8)
        else {
            return nil
        }
        return pretty
    }
}

private struct ToolActivitySection: View {
    var title = "Activity"
    let items: [TranscriptMessage]
    var showStats = true
    var openTool: ((TranscriptMessage) -> Void)?

    var body: some View {
        VStack(alignment: .leading, spacing: 8) {
            HStack(spacing: 8) {
                Text(title)
                    .font(.system(size: 11, weight: .semibold))
                    .tracking(0.88)
                    .foregroundStyle(NtrpColors.faint)
                    .textCase(.uppercase)
                if showStats {
                    Text(statsLabel)
                        .font(.system(size: 11))
                        .foregroundStyle(NtrpColors.faint)
                }
                Spacer(minLength: 0)
            }

            VStack(alignment: .leading, spacing: 7) {
                ForEach(items) { item in
                    Button {
                        openTool?(item)
                    } label: {
                        HStack(spacing: 7) {
                            let agent = item.toolSemanticKind == "agent"
                            Image(systemName: agent ? "cpu" : "arrow.right")
                                .font(.system(size: 11, weight: .medium))
                                .foregroundStyle(item.toolResultIsError ? Color(red: 0.83, green: 0.33, blue: 0.24) : (agent ? NtrpColors.accent : NtrpColors.faint))
                                .frame(width: 16)
                            Text(primaryLabel(item))
                                .font(.system(size: 12, weight: agent ? .medium : .regular, design: agent ? .default : .monospaced))
                                .foregroundStyle(item.toolResultIsError ? Color(red: 0.83, green: 0.33, blue: 0.24) : NtrpColors.muted)
                                .lineLimit(1)
                                .fixedSize(horizontal: true, vertical: false)
                            if let detail = detailLabel(item) {
                                Text(detail)
                                    .font(.system(size: 11, design: agent ? .default : .monospaced))
                                    .foregroundStyle(NtrpColors.faint)
                                    .lineLimit(1)
                                    .truncationMode(.middle)
                            }
                            Spacer(minLength: 0)
                            if let label = statusLabel(item) {
                                Text(label)
                                    .font(.system(size: 11, design: .monospaced))
                                    .foregroundStyle(NtrpColors.faint)
                            }
                        }
                        .padding(.leading, CGFloat(min(item.toolDepth ?? 0, 4)) * 14)
                        .contentShape(Rectangle())
                    }
                    .buttonStyle(.plain)
                    .disabled(openTool == nil)
                }
            }
            .padding(10)
            .background(NtrpColors.row.opacity(0.28))
            .overlay(RoundedRectangle(cornerRadius: 9, style: .continuous).stroke(NtrpColors.sidebarStroke, lineWidth: 1))
            .clipShape(RoundedRectangle(cornerRadius: 9, style: .continuous))
        }
    }

    private func statusLabel(_ item: TranscriptMessage) -> String? {
        if item.toolResult == nil { return "running" }
        if item.toolResultIsError { return "failed" }
        guard let duration = item.toolDurationMS, duration > 0 else { return nil }
        if duration < 1000 { return "\(Int(duration.rounded()))ms" }
        return String(format: "%.1fs", duration / 1000)
    }

    private var statsLabel: String {
        let agents = items.filter { $0.toolSemanticKind == "agent" }.count
        let calls = "\(items.count) \(items.count == 1 ? "call" : "calls")"
        guard agents > 0 else { return calls }
        return "\(calls) · \(agents) sub-agent\(agents == 1 ? "" : "s")"
    }

    private func primaryLabel(_ item: TranscriptMessage) -> String {
        let raw = item.toolName ?? item.content
        guard item.toolSemanticKind == "agent" else {
            return raw.isEmpty ? "tool" : raw
        }
        let stripped = raw.lowercased().hasSuffix("_agent") ? String(raw.dropLast("_agent".count)) : raw
        guard let first = stripped.first else { return raw.isEmpty ? "Agent" : raw }
        return first.uppercased() + stripped.dropFirst()
    }

    private func detailLabel(_ item: TranscriptMessage) -> String? {
        if item.toolSemanticKind == "agent" {
            return extractTask(item.toolArguments) ?? nonEmpty(item.content)
        }
        return item.content == item.toolName ? nil : nonEmpty(item.content)
    }

    private func extractTask(_ raw: String?) -> String? {
        guard let raw,
              let data = raw.data(using: .utf8),
              let object = try? JSONSerialization.jsonObject(with: data) as? [String: Any],
              let task = object["task"] as? String,
              !task.isEmpty
        else {
            return nil
        }
        return task
    }

    private func nonEmpty(_ value: String?) -> String? {
        guard let value, !value.isEmpty else { return nil }
        return value
    }
}

private struct ToolAgentBody: View {
    let message: TranscriptMessage
    let descendants: [TranscriptMessage]
    var openTool: ((TranscriptMessage) -> Void)?
    @State private var copied = false

    private var task: String {
        extractTask(message.toolArguments) ?? nonEmpty(message.content) ?? "(no task provided)"
    }

    private var result: String {
        message.toolResult ?? message.detail ?? ""
    }

    var body: some View {
        VStack(alignment: .leading, spacing: 16) {
            HStack(spacing: 8) {
                sectionHeader("Task")
                Spacer()
                if let usageSummary {
                    Text(usageSummary)
                        .font(.system(size: 12, design: .monospaced))
                        .foregroundStyle(NtrpColors.faint)
                        .lineLimit(1)
                }
            }
            Text(task)
                .font(.system(size: 15))
                .lineSpacing(3)
                .foregroundStyle(NtrpColors.text)
                .frame(maxWidth: .infinity, alignment: .leading)

            HStack(spacing: 8) {
                sectionHeader("Result")
                Spacer()
                if !result.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty {
                    Button {
                        copy()
                    } label: {
                        HStack(spacing: 4) {
                            Image(systemName: copied ? "checkmark" : "doc.on.doc")
                                .font(.system(size: 11, weight: .medium))
                            Text(copied ? "Copied" : "Copy")
                                .font(.system(size: 11, weight: .medium))
                        }
                        .padding(.horizontal, 6)
                        .frame(height: 24)
                        .background(copied ? NtrpColors.accent.opacity(0.14) : Color.clear)
                        .clipShape(RoundedRectangle(cornerRadius: 6, style: .continuous))
                    }
                    .buttonStyle(.plain)
                    .foregroundStyle(copied ? NtrpColors.accent : NtrpColors.faint)
                }
            }

            if message.toolResult == nil {
                placeholder("Working…")
            } else if result.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty {
                placeholder("Empty result.")
            } else {
                ScrollView {
                    MarkdownText(result)
                        .padding(12)
                }
                .frame(maxHeight: 360)
                .background(NtrpColors.row.opacity(0.34))
                .overlay(RoundedRectangle(cornerRadius: 10, style: .continuous).stroke(NtrpColors.sidebarStroke, lineWidth: 1))
                .clipShape(RoundedRectangle(cornerRadius: 10, style: .continuous))
                .scrollIndicators(.visible)
            }

            if !descendants.isEmpty {
                ToolActivitySection(items: descendants, openTool: openTool)
            }
        }
    }

    private func sectionHeader(_ title: String) -> some View {
        Text(title.uppercased())
            .font(.system(size: 10, weight: .medium))
            .tracking(0.8)
            .foregroundStyle(NtrpColors.faint)
    }

    private var usageSummary: String? {
        guard let tokens = message.toolUsageTotal, tokens > 0 else { return nil }
        let tokenLabel: String
        if tokens < 1000 {
            tokenLabel = "\(tokens)"
        } else if tokens < 10_000 {
            tokenLabel = String(format: "%.1fk", Double(tokens) / 1000)
        } else {
            tokenLabel = "\(Int((Double(tokens) / 1000).rounded()))k"
        }
        guard let cost = message.toolCost, cost > 0 else {
            return "\(tokenLabel) tokens"
        }
        let costLabel = cost < 0.01 ? String(format: "$%.4f", cost) : String(format: "$%.3f", cost)
        return "\(tokenLabel) tokens · \(costLabel)"
    }

    private func placeholder(_ text: String) -> some View {
        Text(text)
            .font(.system(size: 14))
            .italic()
            .foregroundStyle(NtrpColors.faint)
            .frame(maxWidth: .infinity, alignment: .leading)
            .padding(.horizontal, 12)
            .padding(.vertical, 10)
            .background(NtrpColors.row.opacity(0.34))
            .clipShape(RoundedRectangle(cornerRadius: 10, style: .continuous))
    }

    private func copy() {
        NSPasteboard.general.clearContents()
        NSPasteboard.general.setString(result, forType: .string)
        copied = true
        Task {
            try? await Task.sleep(for: .milliseconds(900))
            await MainActor.run { copied = false }
        }
    }

    private func extractTask(_ raw: String?) -> String? {
        guard let raw,
              let data = raw.data(using: .utf8),
              let object = try? JSONSerialization.jsonObject(with: data) as? [String: Any],
              let task = object["task"] as? String,
              !task.isEmpty
        else {
            return nil
        }
        return task
    }

    private func nonEmpty(_ value: String?) -> String? {
        guard let value, !value.isEmpty else { return nil }
        return value
    }
}

private struct ToolDetailSection: View {
    let title: String
    let bodyText: String
    let empty: String
    var isError = false
    @State private var copied = false

    var body: some View {
        VStack(alignment: .leading, spacing: 7) {
            HStack(spacing: 8) {
                Text(title.uppercased())
                    .font(.system(size: 10, weight: .medium))
                    .tracking(0.8)
                    .foregroundStyle(isError ? Color.red.opacity(0.8) : NtrpColors.faint)
                Spacer()
                if !bodyText.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty {
                    Button {
                        copy()
                    } label: {
                        HStack(spacing: 4) {
                            Image(systemName: copied ? "checkmark" : "doc.on.doc")
                                .font(.system(size: 11, weight: .medium))
                            Text(copied ? "Copied" : "Copy")
                                .font(.system(size: 11, weight: .medium))
                        }
                        .padding(.horizontal, 6)
                        .frame(height: 24)
                        .background(copied ? NtrpColors.accent.opacity(0.14) : Color.clear)
                        .clipShape(RoundedRectangle(cornerRadius: 6, style: .continuous))
                    }
                    .buttonStyle(.plain)
                    .foregroundStyle(copied ? NtrpColors.accent : NtrpColors.faint)
                }
            }

            if bodyText.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty {
                Text(empty)
                    .font(.system(size: 14))
                    .italic()
                    .foregroundStyle(NtrpColors.faint)
                    .frame(maxWidth: .infinity, alignment: .leading)
                    .padding(.horizontal, 12)
                    .padding(.vertical, 10)
                    .background(NtrpColors.row.opacity(0.34))
                    .clipShape(RoundedRectangle(cornerRadius: 10, style: .continuous))
            } else {
                ScrollView {
                    Text(bodyText)
                        .font(.system(size: 12.25, design: .monospaced))
                        .foregroundStyle(isError ? Color.red.opacity(0.86) : NtrpColors.muted)
                        .lineSpacing(4)
                        .textSelection(.enabled)
                        .frame(maxWidth: .infinity, alignment: .leading)
                        .padding(12)
                }
                .frame(maxHeight: 360)
                .background(NtrpColors.row.opacity(0.34))
                .overlay(RoundedRectangle(cornerRadius: 10, style: .continuous).stroke(NtrpColors.sidebarStroke, lineWidth: 1))
                .clipShape(RoundedRectangle(cornerRadius: 10, style: .continuous))
                .scrollIndicators(.visible)
            }
        }
    }

    private func copy() {
        NSPasteboard.general.clearContents()
        NSPasteboard.general.setString(bodyText, forType: .string)
        copied = true
        Task {
            try? await Task.sleep(for: .milliseconds(900))
            await MainActor.run { copied = false }
        }
    }
}

struct MarkdownText: View {
    let content: String
    private let blocks: [MarkdownBlock]

    init(_ content: String) {
        self.content = content
        self.blocks = MarkdownBlock.parse(content)
    }

    var body: some View {
        VStack(alignment: .leading, spacing: 8) {
            ForEach(Array(blocks.enumerated()), id: \.offset) { _, block in
                MarkdownBlockView(block: block)
            }
        }
        .frame(maxWidth: .infinity, alignment: .leading)
    }
}

private struct MarkdownBlockView: View {
    let block: MarkdownBlock
    @EnvironmentObject private var ui: NtrpUIState

    var body: some View {
        switch block {
        case .paragraph(let text):
            InlineMarkdownView(text: text)
                .frame(maxWidth: .infinity, alignment: .leading)
        case .heading(let level, let text):
            InlineMarkdownView(text: text, size: headingSize(level), weight: .semibold)
                .frame(maxWidth: .infinity, alignment: .leading)
                .padding(.top, level == 1 ? 4 : 2)
        case .unorderedList(let items):
            VStack(alignment: .leading, spacing: 5) {
                ForEach(Array(items.enumerated()), id: \.offset) { _, item in
                    if let task = taskListItem(item) {
                        HStack(alignment: .firstTextBaseline, spacing: 8) {
                            Image(systemName: task.checked ? "checkmark.square" : "square")
                                .font(.system(size: 13, weight: .medium))
                                .foregroundStyle(task.checked ? NtrpColors.accent : NtrpColors.faint)
                                .frame(width: 14)
                            InlineMarkdownView(text: task.text)
                                .frame(maxWidth: .infinity, alignment: .leading)
                        }
                    } else {
                        HStack(alignment: .firstTextBaseline, spacing: 8) {
                            Text("•")
                                .foregroundStyle(NtrpColors.faint)
                            InlineMarkdownView(text: item)
                                .frame(maxWidth: .infinity, alignment: .leading)
                        }
                    }
                }
            }
        case .orderedList(let items):
            VStack(alignment: .leading, spacing: 5) {
                ForEach(Array(items.enumerated()), id: \.offset) { index, item in
                    HStack(alignment: .firstTextBaseline, spacing: 8) {
                        Text("\(index + 1).")
                            .font(.system(.body, design: .monospaced))
                            .foregroundStyle(NtrpColors.faint)
                        InlineMarkdownView(text: item)
                            .frame(maxWidth: .infinity, alignment: .leading)
                    }
                }
            }
        case .quote(let text):
            InlineMarkdownView(text: text, color: NtrpColors.muted)
                .frame(maxWidth: .infinity, alignment: .leading)
                .padding(.leading, 12)
                .overlay(alignment: .leading) {
                    Rectangle()
                        .fill(NtrpColors.sidebarStroke)
                        .frame(width: 2)
                }
        case .code(let language, let code):
            MarkdownCodeBlock(language: language, code: code)
        case .table(let rows):
            MarkdownTableBlock(rows: rows)
        case .mermaid(let code):
            MermaidDiagramBlock(code: code) {
                ui.viewingMermaid = MermaidViewState(code: code)
            }
        case .math(let source):
            MathBlockView(source: source)
        }
    }

    private func headingSize(_ level: Int) -> CGFloat {
        switch level {
        case 1: 22
        case 2: 19
        default: 17
        }
    }

    private func taskListItem(_ value: String) -> (checked: Bool, text: String)? {
        let trimmed = value.trimmingCharacters(in: .whitespaces)
        guard trimmed.count >= 4, trimmed.hasPrefix("[") else { return nil }
        let marker = trimmed.prefix(3).lowercased()
        guard marker == "[ ]" || marker == "[x]" else { return nil }
        let rest = trimmed.dropFirst(3)
        guard rest.first == " " else { return nil }
        return (marker == "[x]", String(rest.dropFirst()))
    }
}

private enum ChatInlineMath {
    struct Segment {
        let text: String
        let isMath: Bool
    }

    static func segments(_ value: String) -> [Segment] {
        var segments: [Segment] = []
        var cursor = value.startIndex
        var textStart = cursor

        while cursor < value.endIndex {
            guard value[cursor] == "$", !isEscapedDollar(value, at: cursor) else {
                cursor = value.index(after: cursor)
                continue
            }
            let next = value.index(after: cursor)
            if next < value.endIndex, value[next] == "$" {
                cursor = value.index(after: next)
                continue
            }

            var close = next
            var found: String.Index?
            while close < value.endIndex {
                if value[close] == "$", !isEscapedDollar(value, at: close) {
                    found = close
                    break
                }
                close = value.index(after: close)
            }

            guard let end = found else {
                cursor = next
                continue
            }

            let math = String(value[next..<end]).trimmingCharacters(in: .whitespacesAndNewlines)
            guard !math.isEmpty else {
                cursor = value.index(after: end)
                continue
            }

            if textStart < cursor {
                segments.append(Segment(text: String(value[textStart..<cursor]), isMath: false))
            }
            segments.append(Segment(text: math, isMath: true))
            cursor = value.index(after: end)
            textStart = cursor
        }

        if textStart < value.endIndex {
            segments.append(Segment(text: String(value[textStart..<value.endIndex]), isMath: false))
        }
        return segments.isEmpty ? [Segment(text: value, isMath: false)] : segments
    }

    static func html(_ value: String) -> String {
        segments(value).map { segment in
            if segment.isMath {
                return "<span data-math data-source=\"\(escape(segment.text))\"></span>"
            }
            return basicInlineMarkdownHTML(segment.text)
        }.joined()
    }

    static func escape(_ value: String) -> String {
        value
            .replacingOccurrences(of: "&", with: "&amp;")
            .replacingOccurrences(of: "<", with: "&lt;")
            .replacingOccurrences(of: ">", with: "&gt;")
            .replacingOccurrences(of: "\"", with: "&quot;")
    }

    static func loadAssets() -> (js: String, css: String)? {
        let path = URL(fileURLWithPath: #filePath)
        var cursor = path
        for _ in 0..<10 {
            let base = cursor.appendingPathComponent("apps/desktop/node_modules/katex/dist")
            let scriptURL = base.appendingPathComponent("katex.min.js")
            let cssURL = base.appendingPathComponent("katex.min.css")
            if
                let js = try? String(contentsOf: scriptURL, encoding: .utf8),
                let css = try? String(contentsOf: cssURL, encoding: .utf8),
                !js.isEmpty,
                !css.isEmpty
            {
                return (js, css)
            }
            cursor.deleteLastPathComponent()
        }
        return nil
    }

    private static func isEscapedDollar(_ value: String, at index: String.Index) -> Bool {
        guard index > value.startIndex else { return false }
        var cursor = value.index(before: index)
        var slashCount = 0
        while true {
            if value[cursor] != "\\" { break }
            slashCount += 1
            if cursor == value.startIndex { break }
            cursor = value.index(before: cursor)
        }
        return slashCount % 2 == 1
    }
}

private struct InlineMarkdownView: View {
    let text: String
    var size: CGFloat = 14
    var weight: Font.Weight = .regular
    var design: Font.Design = .default
    var color: Color = NtrpColors.text
    @State private var webHeight: CGFloat = 24

    var body: some View {
        if ChatInlineMath.segments(text).contains(where: { $0.isMath }) {
            InlineKatexWebView(source: text, fontSize: size, height: $webHeight)
                .frame(height: max(webHeight, size * 1.65))
                .frame(maxWidth: .infinity, alignment: .leading)
        } else {
            Text(markdownInline(text))
                .font(.system(size: size, weight: weight, design: design))
                .foregroundStyle(color)
        }
    }
}

private struct InlineKatexWebView: NSViewRepresentable {
    let source: String
    let fontSize: CGFloat
    @Binding var height: CGFloat

    func makeNSView(context: Context) -> WKWebView {
        let config = WKWebViewConfiguration()
        let view = WKWebView(frame: .zero, configuration: config)
        view.setValue(false, forKey: "drawsBackground")
        view.navigationDelegate = context.coordinator
        context.coordinator.lastSource = source
        view.loadHTMLString(html, baseURL: nil)
        return view
    }

    func updateNSView(_ view: WKWebView, context: Context) {
        guard context.coordinator.lastSource != source else { return }
        context.coordinator.lastSource = source
        view.loadHTMLString(html, baseURL: nil)
    }

    func makeCoordinator() -> Coordinator {
        Coordinator(height: $height)
    }

    final class Coordinator: NSObject, WKNavigationDelegate {
        var lastSource: String?
        var height: Binding<CGFloat>

        init(height: Binding<CGFloat>) {
            self.height = height
        }

        func webView(_ webView: WKWebView, didFinish navigation: WKNavigation!) {
            webView.evaluateJavaScript("Math.ceil(document.documentElement.scrollHeight)") { value, _ in
                guard let number = value as? NSNumber else { return }
                let next = CGFloat(truncating: number)
                DispatchQueue.main.async {
                    self.height.wrappedValue = max(22, next)
                }
            }
        }
    }

    private var html: String {
        guard let assets = ChatInlineMath.loadAssets() else {
            return fallbackHTML
        }
        return """
        <!doctype html>
        <html>
        <head>
          <meta charset="utf-8">
          <style>
            \(assets.css)
            html, body { margin: 0; padding: 0; background: transparent; color: #d9d9d6; overflow: hidden; }
            body { font: \(fontSize)px -apple-system, BlinkMacSystemFont, sans-serif; line-height: 1.55; }
            #content { overflow-wrap: anywhere; }
            .katex { color: #d9d9d6; font-size: 1em; }
            code { font-family: ui-monospace, SFMono-Regular, Menlo, monospace; background: rgba(255,255,255,0.08); border-radius: 4px; padding: 1px 4px; }
            strong { font-weight: 650; }
            em { font-style: italic; }
          </style>
        </head>
        <body>
          <div id="content">\(ChatInlineMath.html(source))</div>
          <script>\(assets.js)</script>
          <script>
            document.querySelectorAll("[data-math]").forEach((node) => {
              try {
                katex.render(node.getAttribute("data-source") || "", node, {
                  displayMode: false,
                  throwOnError: false,
                  trust: false,
                  strict: "ignore"
                });
              } catch (error) {
                node.textContent = node.getAttribute("data-source") || "";
              }
            });
          </script>
        </body>
        </html>
        """
    }

    private var fallbackHTML: String {
        """
        <!doctype html>
        <html><body style="margin:0;background:transparent;color:#d9d9d6;font:\(fontSize)px -apple-system,BlinkMacSystemFont,sans-serif;line-height:1.55;">\(htmlEscaped(source))</body></html>
        """
    }
}

private struct MarkdownCodeBlock: View {
    let language: String
    let code: String
    @State private var copied = false

    var body: some View {
        VStack(alignment: .leading, spacing: 0) {
            HStack(spacing: 8) {
                Text(language)
                    .font(.system(size: 10, weight: .medium))
                    .tracking(0.8)
                    .foregroundStyle(NtrpColors.faint)
                Spacer()
                Button {
                    copy()
                } label: {
                    Image(systemName: copied ? "checkmark" : "doc.on.doc")
                        .font(.system(size: 12, weight: .medium))
                        .frame(width: 22, height: 22)
                }
                .buttonStyle(.plain)
                .foregroundStyle(copied ? Color.green : NtrpColors.faint)
                .help(copied ? "Copied" : "Copy code")
            }
            .padding(.horizontal, 10)
            .frame(height: 30)
            .background(NtrpColors.surfaceFill(0.36))

            ScrollView(.horizontal, showsIndicators: false) {
                Text(highlightedCode(code.isEmpty ? " " : code, language: language))
                    .font(.system(size: 13, design: .monospaced))
                    .textSelection(.enabled)
                    .padding(12)
                    .frame(maxWidth: .infinity, alignment: .leading)
            }
        }
        .background(NtrpColors.row.opacity(0.32))
        .overlay {
            RoundedRectangle(cornerRadius: 9, style: .continuous)
                .stroke(NtrpColors.sidebarStroke, lineWidth: 1)
        }
        .overlay(alignment: .topLeading) {
            MarkdownCodeTick()
                .padding(5)
        }
        .overlay(alignment: .topTrailing) {
            MarkdownCodeTick()
                .rotationEffect(.degrees(90))
                .padding(5)
        }
        .clipShape(RoundedRectangle(cornerRadius: 9, style: .continuous))
    }

    private func copy() {
        NSPasteboard.general.clearContents()
        NSPasteboard.general.setString(code, forType: .string)
        copied = true
        Task {
            try? await Task.sleep(for: .milliseconds(900))
            await MainActor.run { copied = false }
        }
    }
}

private struct MermaidDiagramBlock: View {
    let code: String
    let openFullscreen: () -> Void

    var body: some View {
        MermaidDiagramPanel(code: code, fullscreen: false, onToggleFullscreen: openFullscreen)
    }
}

struct MermaidDiagramPanel: View {
    let code: String
    let fullscreen: Bool
    let onToggleFullscreen: () -> Void
    @State private var copied = false
    @State private var zoom: CGFloat = 1
    @State private var fitRequest = 0

    var body: some View {
        VStack(alignment: .leading, spacing: 0) {
            HStack(spacing: 8) {
                Text("Diagram")
                    .font(.system(size: 10, weight: .medium))
                    .tracking(0.8)
                    .foregroundStyle(NtrpColors.faint)
                Spacer()
                MermaidToolbarButton(systemName: "minus", label: "Zoom out", disabled: zoom <= 0.12) {
                    zoom = max(0.1, zoom / 1.2)
                }
                Text("\(Int((zoom * 100).rounded()))%")
                    .font(.system(size: 11, weight: .medium, design: .monospaced))
                    .foregroundStyle(NtrpColors.muted)
                    .frame(width: 42)
                MermaidToolbarButton(systemName: "plus", label: "Zoom in", disabled: zoom >= 4.95) {
                    zoom = min(5, zoom * 1.2)
                }
                MermaidToolbarButton(systemName: "arrow.counterclockwise", label: "Fit to view") {
                    fitRequest += 1
                }
                Rectangle()
                    .fill(NtrpColors.sidebarStroke)
                    .frame(width: 1, height: 14)
                    .padding(.horizontal, 3)
                MermaidToolbarButton(systemName: fullscreen ? "arrow.down.right.and.arrow.up.left" : "arrow.up.left.and.arrow.down.right", label: fullscreen ? "Exit fullscreen" : "Fullscreen") {
                    onToggleFullscreen()
                }
                MermaidToolbarButton(systemName: copied ? "checkmark" : "doc.on.doc", label: copied ? "Copied" : "Copy source", active: copied) {
                    copy()
                }
            }
            .padding(.horizontal, 10)
            .frame(height: 30)
            .background(NtrpColors.surfaceFill(0.36))

            MermaidWebView(code: code, zoom: zoom, fullscreen: fullscreen, fitRequest: fitRequest)
                .frame(minHeight: fullscreen ? 0 : 220, idealHeight: fullscreen ? nil : 300, maxHeight: fullscreen ? .infinity : 360)
                .background(NtrpColors.row.opacity(0.28))
        }
        .background(NtrpColors.row.opacity(0.32))
        .overlay {
            RoundedRectangle(cornerRadius: 9, style: .continuous)
                .stroke(NtrpColors.sidebarStroke, lineWidth: 1)
        }
        .overlay(alignment: .topLeading) {
            MarkdownCodeTick()
                .padding(5)
        }
        .overlay(alignment: .topTrailing) {
            MarkdownCodeTick()
                .rotationEffect(.degrees(90))
                .padding(5)
        }
        .clipShape(RoundedRectangle(cornerRadius: fullscreen ? 16 : 9, style: .continuous))
        .onExitCommand {
            if fullscreen {
                onToggleFullscreen()
            }
        }
    }

    private func copy() {
        NSPasteboard.general.clearContents()
        NSPasteboard.general.setString(code, forType: .string)
        copied = true
        Task {
            try? await Task.sleep(for: .milliseconds(900))
            await MainActor.run { copied = false }
        }
    }
}

private struct MermaidToolbarButton: View {
    let systemName: String
    let label: String
    var active = false
    var disabled = false
    let action: () -> Void

    var body: some View {
        Button(action: action) {
            Image(systemName: systemName)
                .font(.system(size: 11, weight: .semibold))
                .frame(width: 24, height: 24)
        }
        .buttonStyle(.plain)
        .foregroundStyle(active ? Color.green : NtrpColors.faint)
        .opacity(disabled ? 0.35 : 1)
        .disabled(disabled)
        .help(label)
    }
}

private struct MathBlockView: View {
    let source: String
    @State private var copied = false

    var body: some View {
        VStack(alignment: .leading, spacing: 0) {
            HStack(spacing: 8) {
                Text("Math")
                    .font(.system(size: 10, weight: .medium))
                    .tracking(0.8)
                    .foregroundStyle(NtrpColors.faint)
                Spacer()
                MermaidToolbarButton(systemName: copied ? "checkmark" : "doc.on.doc", label: copied ? "Copied" : "Copy source", active: copied) {
                    copy()
                }
            }
            .padding(.horizontal, 10)
            .frame(height: 30)
            .background(NtrpColors.surfaceFill(0.36))

            KatexWebView(source: source)
                .frame(minHeight: 72, idealHeight: 116, maxHeight: 220)
                .background(NtrpColors.row.opacity(0.28))
        }
        .background(NtrpColors.row.opacity(0.32))
        .overlay {
            RoundedRectangle(cornerRadius: 9, style: .continuous)
                .stroke(NtrpColors.sidebarStroke, lineWidth: 1)
        }
        .overlay(alignment: .topLeading) {
            MarkdownCodeTick()
                .padding(5)
        }
        .overlay(alignment: .topTrailing) {
            MarkdownCodeTick()
                .rotationEffect(.degrees(90))
                .padding(5)
        }
        .clipShape(RoundedRectangle(cornerRadius: 9, style: .continuous))
    }

    private func copy() {
        NSPasteboard.general.clearContents()
        NSPasteboard.general.setString(source, forType: .string)
        copied = true
        Task {
            try? await Task.sleep(for: .milliseconds(900))
            await MainActor.run { copied = false }
        }
    }
}

private struct MermaidWebView: NSViewRepresentable {
    let code: String
    let zoom: CGFloat
    let fullscreen: Bool
    let fitRequest: Int

    func makeNSView(context: Context) -> WKWebView {
        let config = WKWebViewConfiguration()
        let view = WKWebView(frame: .zero, configuration: config)
        view.setValue(false, forKey: "drawsBackground")
        view.navigationDelegate = context.coordinator
        context.coordinator.lastCode = code
        context.coordinator.lastFitRequest = fitRequest
        view.loadHTMLString(html, baseURL: nil)
        return view
    }

    func updateNSView(_ view: WKWebView, context: Context) {
        if context.coordinator.lastCode != code {
            context.coordinator.lastCode = code
            context.coordinator.lastFitRequest = fitRequest
            view.loadHTMLString(html, baseURL: nil)
        } else if context.coordinator.lastFitRequest != fitRequest {
            context.coordinator.lastFitRequest = fitRequest
            view.evaluateJavaScript("window.ntrpFitToView && window.ntrpFitToView()")
        } else {
            view.evaluateJavaScript("window.ntrpSetZoom && window.ntrpSetZoom(\(Double(zoom)))")
        }
    }

    func makeCoordinator() -> Coordinator {
        Coordinator()
    }

    final class Coordinator: NSObject, WKNavigationDelegate {
        var lastCode: String?
        var lastFitRequest: Int?
    }

    private var html: String {
        guard let mermaidScript = loadMermaidScript() else {
            return fallbackHTML
        }
        let codeLiteral = javascriptStringLiteral(code)
        let theme = NtrpColors.isDarkMode ? "dark" : "default"
        return """
        <!doctype html>
        <html>
        <head>
          <meta charset="utf-8">
          <style>
            html, body { margin: 0; min-height: 100%; background: transparent; color: #d9d9d6; font: 13px -apple-system, BlinkMacSystemFont, sans-serif; overflow: auto; }
            body { display: grid; place-items: center; padding: 14px; box-sizing: border-box; user-select: none; }
            #diagram { max-width: 100%; transform-origin: 0 0; transition: transform 80ms ease-out; cursor: grab; }
            body.dragging #diagram { cursor: grabbing; transition: none; }
            #diagram svg { max-width: 100%; height: auto; display: block; }
            #error { white-space: pre-wrap; color: #d28b8b; font-family: ui-monospace, SFMono-Regular, Menlo, monospace; }
          </style>
        </head>
        <body>
          <div id="diagram"></div>
          <script>\(mermaidScript)</script>
          <script>
            const source = \(codeLiteral);
            const fullscreen = \(fullscreen ? "true" : "false");
            const view = { zoom: \(Double(zoom)), x: 0, y: 0 };
            const apply = () => {
              const el = document.getElementById("diagram");
              if (el) el.style.transform = `translate3d(${view.x}px, ${view.y}px, 0) scale(${view.zoom})`;
            };
            const clampZoom = (zoom) => Math.max(0.1, Math.min(5, zoom));
            const zoomTowards = (requestedZoom, x, y) => {
              const next = clampZoom(requestedZoom);
              const ratio = next / view.zoom;
              view.x = x - (x - view.x) * ratio;
              view.y = y - (y - view.y) * ratio;
              view.zoom = next;
              apply();
            };
            window.ntrpSetZoom = (zoom) => {
              const rect = document.body.getBoundingClientRect();
              zoomTowards(zoom, rect.width / 2, rect.height / 2);
            };
            window.ntrpFitToView = () => {
              const svg = document.querySelector("#diagram svg");
              const rect = document.body.getBoundingClientRect();
              if (!svg || rect.width <= 0 || rect.height <= 0) return;
              const box = svg.getBBox ? svg.getBBox() : { width: svg.clientWidth || 1, height: svg.clientHeight || 1 };
              const margin = 28;
              const fit = Math.max(0.1, Math.min(5, Math.min((rect.width - margin) / Math.max(1, box.width), (rect.height - margin) / Math.max(1, box.height))));
              view.zoom = fit;
              view.x = (rect.width - Math.max(1, box.width) * fit) / 2;
              view.y = (rect.height - Math.max(1, box.height) * fit) / 2;
              apply();
            };
            window.addEventListener("wheel", (event) => {
              if (!fullscreen && !(event.metaKey || event.ctrlKey)) return;
              event.preventDefault();
              const rect = document.body.getBoundingClientRect();
              const factor = event.deltaY > 0 ? 0.9 : 1.1;
              zoomTowards(view.zoom * factor, event.clientX - rect.left, event.clientY - rect.top);
            }, { passive: false });
            let drag = null;
            document.addEventListener("mousedown", (event) => {
              if (event.button !== 0) return;
              drag = { x: event.clientX, y: event.clientY, startX: view.x, startY: view.y };
              document.body.classList.add("dragging");
            });
            document.addEventListener("mousemove", (event) => {
              if (!drag) return;
              view.x = drag.startX + event.clientX - drag.x;
              view.y = drag.startY + event.clientY - drag.y;
              apply();
            });
            document.addEventListener("mouseup", () => {
              drag = null;
              document.body.classList.remove("dragging");
            });
            mermaid.initialize({ startOnLoad: false, securityLevel: "strict", theme: "\(theme)" });
            mermaid.render("ntrp-mermaid", source)
              .then(({ svg }) => { document.getElementById("diagram").innerHTML = svg; window.ntrpFitToView(); })
              .catch((error) => { document.getElementById("diagram").innerHTML = "<pre id='error'></pre>"; document.getElementById("error").textContent = String(error && error.message ? error.message : error); });
          </script>
        </body>
        </html>
        """
    }

    private var fallbackHTML: String {
        """
        <!doctype html>
        <html>
        <body style="margin:0;padding:14px;background:transparent;color:#d9d9d6;font:12px ui-monospace,SFMono-Regular,Menlo,monospace;white-space:pre-wrap;">
        \(htmlEscaped(code))
        </body>
        </html>
        """
    }

    private func loadMermaidScript() -> String? {
        let path = URL(fileURLWithPath: #filePath)
        var cursor = path
        for _ in 0..<10 {
            let candidate = cursor
                .appendingPathComponent("apps/desktop/node_modules/mermaid/dist/mermaid.min.js")
            if let script = try? String(contentsOf: candidate, encoding: .utf8), !script.isEmpty {
                return script
            }
            cursor.deleteLastPathComponent()
        }
        return nil
    }
}

private struct KatexWebView: NSViewRepresentable {
    let source: String

    func makeNSView(context: Context) -> WKWebView {
        let config = WKWebViewConfiguration()
        let view = WKWebView(frame: .zero, configuration: config)
        view.setValue(false, forKey: "drawsBackground")
        view.navigationDelegate = context.coordinator
        context.coordinator.lastSource = source
        view.loadHTMLString(html, baseURL: nil)
        return view
    }

    func updateNSView(_ view: WKWebView, context: Context) {
        guard context.coordinator.lastSource != source else { return }
        context.coordinator.lastSource = source
        view.loadHTMLString(html, baseURL: nil)
    }

    func makeCoordinator() -> Coordinator {
        Coordinator()
    }

    final class Coordinator: NSObject, WKNavigationDelegate {
        var lastSource: String?
    }

    private var html: String {
        guard let assets = loadKatexAssets() else {
            return fallbackHTML
        }
        let sourceLiteral = javascriptStringLiteral(source)
        return """
        <!doctype html>
        <html>
        <head>
          <meta charset="utf-8">
          <style>
            \(assets.css)
            html, body { margin: 0; min-height: 100%; background: transparent; color: #d9d9d6; font: 14px -apple-system, BlinkMacSystemFont, sans-serif; overflow: auto; }
            body { display: grid; place-items: center; padding: 16px; box-sizing: border-box; }
            #math { max-width: 100%; overflow-x: auto; overflow-y: hidden; }
            .katex { color: #d9d9d6; font-size: 1.12em; }
            #error { white-space: pre-wrap; color: #d28b8b; font-family: ui-monospace, SFMono-Regular, Menlo, monospace; }
          </style>
        </head>
        <body>
          <div id="math"></div>
          <script>\(assets.js)</script>
          <script>
            const source = \(sourceLiteral);
            try {
              katex.render(source, document.getElementById("math"), {
                displayMode: true,
                throwOnError: false,
                trust: false,
                strict: "ignore"
              });
            } catch (error) {
              document.getElementById("math").innerHTML = "<pre id='error'></pre>";
              document.getElementById("error").textContent = String(error && error.message ? error.message : error);
            }
          </script>
        </body>
        </html>
        """
    }

    private var fallbackHTML: String {
        """
        <!doctype html>
        <html>
        <body style="margin:0;padding:14px;background:transparent;color:#d9d9d6;font:12px ui-monospace,SFMono-Regular,Menlo,monospace;white-space:pre-wrap;">
        \(ChatInlineMath.escape(source))
        </body>
        </html>
        """
    }

    private func loadKatexAssets() -> (js: String, css: String)? {
        let path = URL(fileURLWithPath: #filePath)
        var cursor = path
        for _ in 0..<10 {
            let base = cursor.appendingPathComponent("apps/desktop/node_modules/katex/dist")
            let scriptURL = base.appendingPathComponent("katex.min.js")
            let cssURL = base.appendingPathComponent("katex.min.css")
            if
                let js = try? String(contentsOf: scriptURL, encoding: .utf8),
                let css = try? String(contentsOf: cssURL, encoding: .utf8),
                !js.isEmpty,
                !css.isEmpty
            {
                return (js, css)
            }
            cursor.deleteLastPathComponent()
        }
        return nil
    }
}

private func highlightedCode(_ code: String, language: String) -> AttributedString {
    let normalizedLanguage = language.lowercased()
    switch normalizedLanguage {
    case "json":
        return highlightJSON(code)
    case "python", "py":
        return highlightCodeLike(code, keywords: pythonKeywords, commentPrefix: "#")
    case "javascript", "js", "jsx", "typescript", "ts", "tsx":
        return highlightCodeLike(code, keywords: jsKeywords, commentPrefix: "//")
    case "bash", "sh", "shell", "zsh":
        return highlightCodeLike(code, keywords: shellKeywords, commentPrefix: "#")
    default:
        var output = AttributedString(code)
        output.foregroundColor = NtrpColors.text
        return output
    }
}

private let jsKeywords: Set<String> = [
    "async", "await", "break", "case", "catch", "class", "const", "continue",
    "default", "do", "else", "export", "extends", "false", "finally", "for",
    "from", "function", "if", "import", "in", "instanceof", "interface", "let",
    "new", "null", "return", "switch", "throw", "true", "try", "type", "undefined",
    "var", "while", "yield"
]

private let pythonKeywords: Set<String> = [
    "and", "as", "assert", "async", "await", "break", "class", "continue",
    "def", "del", "elif", "else", "except", "False", "finally", "for",
    "from", "global", "if", "import", "in", "is", "lambda", "None", "nonlocal",
    "not", "or", "pass", "raise", "return", "True", "try", "while", "with", "yield"
]

private let shellKeywords: Set<String> = [
    "case", "do", "done", "elif", "else", "esac", "fi", "for", "function",
    "if", "in", "select", "then", "until", "while"
]

private func highlightJSON(_ code: String) -> AttributedString {
    var output = AttributedString()
    var index = code.startIndex
    while index < code.endIndex {
        let char = code[index]
        if char == "\"" {
            let token = consumeQuotedString(code, from: index)
            var piece = AttributedString(String(code[index..<token.end]))
            piece.foregroundColor = token.isKey ? NtrpColors.accent : Color(red: 0.73, green: 0.84, blue: 0.64)
            output += piece
            index = token.end
        } else if char.isNumber || char == "-" {
            let end = consumeNumber(code, from: index)
            var piece = AttributedString(String(code[index..<end]))
            piece.foregroundColor = Color(red: 0.72, green: 0.68, blue: 0.96)
            output += piece
            index = end
        } else if let literal = consumeLiteral(code, from: index, literals: ["true", "false", "null"]) {
            var piece = AttributedString(literal.value)
            piece.foregroundColor = Color(red: 0.88, green: 0.60, blue: 0.72)
            output += piece
            index = literal.end
        } else {
            var piece = AttributedString(String(char))
            piece.foregroundColor = punctuationColor(char)
            output += piece
            index = code.index(after: index)
        }
    }
    return output
}

private func highlightCodeLike(_ code: String, keywords: Set<String>, commentPrefix: String) -> AttributedString {
    var output = AttributedString()
    var index = code.startIndex
    while index < code.endIndex {
        if code[index...].hasPrefix(commentPrefix) {
            let end = code[index...].firstIndex(of: "\n") ?? code.endIndex
            var piece = AttributedString(String(code[index..<end]))
            piece.foregroundColor = NtrpColors.faint
            output += piece
            index = end
        } else if code[index] == "\"" || code[index] == "'" {
            let end = consumeStringLiteral(code, from: index, quote: code[index])
            var piece = AttributedString(String(code[index..<end]))
            piece.foregroundColor = Color(red: 0.73, green: 0.84, blue: 0.64)
            output += piece
            index = end
        } else if code[index].isNumber {
            let end = consumeNumber(code, from: index)
            var piece = AttributedString(String(code[index..<end]))
            piece.foregroundColor = Color(red: 0.72, green: 0.68, blue: 0.96)
            output += piece
            index = end
        } else if isIdentifierStart(code[index]) {
            let end = consumeIdentifier(code, from: index)
            let word = String(code[index..<end])
            var piece = AttributedString(word)
            piece.foregroundColor = keywords.contains(word) ? NtrpColors.accent : NtrpColors.text
            output += piece
            index = end
        } else {
            var piece = AttributedString(String(code[index]))
            piece.foregroundColor = punctuationColor(code[index])
            output += piece
            index = code.index(after: index)
        }
    }
    return output
}

private func consumeQuotedString(_ code: String, from start: String.Index) -> (end: String.Index, isKey: Bool) {
    let end = consumeStringLiteral(code, from: start, quote: "\"")
    var cursor = end
    while cursor < code.endIndex, code[cursor].isWhitespace {
        cursor = code.index(after: cursor)
    }
    return (end, cursor < code.endIndex && code[cursor] == ":")
}

private func consumeStringLiteral(_ code: String, from start: String.Index, quote: Character) -> String.Index {
    var index = code.index(after: start)
    var escaped = false
    while index < code.endIndex {
        let char = code[index]
        if escaped {
            escaped = false
        } else if char == "\\" {
            escaped = true
        } else if char == quote {
            return code.index(after: index)
        }
        index = code.index(after: index)
    }
    return code.endIndex
}

private func consumeNumber(_ code: String, from start: String.Index) -> String.Index {
    var index = start
    while index < code.endIndex {
        let char = code[index]
        guard char.isNumber || char == "." || char == "-" || char == "+" || char == "e" || char == "E" else { break }
        index = code.index(after: index)
    }
    return index
}

private func consumeLiteral(_ code: String, from start: String.Index, literals: [String]) -> (value: String, end: String.Index)? {
    for literal in literals where code[start...].hasPrefix(literal) {
        let end = code.index(start, offsetBy: literal.count)
        return (literal, end)
    }
    return nil
}

private func consumeIdentifier(_ code: String, from start: String.Index) -> String.Index {
    var index = start
    while index < code.endIndex, isIdentifierPart(code[index]) {
        index = code.index(after: index)
    }
    return index
}

private func isIdentifierStart(_ char: Character) -> Bool {
    char == "_" || char.isLetter
}

private func isIdentifierPart(_ char: Character) -> Bool {
    char == "_" || char.isLetter || char.isNumber
}

private func punctuationColor(_ char: Character) -> Color {
    char.isWhitespace ? NtrpColors.text : NtrpColors.muted
}

private func javascriptStringLiteral(_ value: String) -> String {
    var output = "\""
    for scalar in value.unicodeScalars {
        switch scalar {
        case "\"":
            output += "\\\""
        case "\\":
            output += "\\\\"
        case "\n":
            output += "\\n"
        case "\r":
            output += "\\r"
        case "\t":
            output += "\\t"
        case "\u{2028}":
            output += "\\u2028"
        case "\u{2029}":
            output += "\\u2029"
        default:
            output.unicodeScalars.append(scalar)
        }
    }
    output += "\""
    return output
}

private func htmlEscaped(_ value: String) -> String {
    value
        .replacingOccurrences(of: "&", with: "&amp;")
        .replacingOccurrences(of: "<", with: "&lt;")
        .replacingOccurrences(of: ">", with: "&gt;")
        .replacingOccurrences(of: "\"", with: "&quot;")
}

private struct InlineMathSegment {
    let text: String
    let isMath: Bool
}

private func inlineMathSegments(_ value: String) -> [InlineMathSegment] {
    var segments: [InlineMathSegment] = []
    var cursor = value.startIndex
    var textStart = cursor

    while cursor < value.endIndex {
        guard value[cursor] == "$", !isEscapedDollar(value, at: cursor) else {
            cursor = value.index(after: cursor)
            continue
        }
        let next = value.index(after: cursor)
        if next < value.endIndex, value[next] == "$" {
            cursor = value.index(after: next)
            continue
        }

        var close = next
        var found: String.Index?
        while close < value.endIndex {
            if value[close] == "$", !isEscapedDollar(value, at: close) {
                found = close
                break
            }
            close = value.index(after: close)
        }

        guard let end = found else {
            cursor = next
            continue
        }

        let math = String(value[next..<end]).trimmingCharacters(in: .whitespacesAndNewlines)
        guard !math.isEmpty else {
            cursor = value.index(after: end)
            continue
        }

        if textStart < cursor {
            segments.append(InlineMathSegment(text: String(value[textStart..<cursor]), isMath: false))
        }
        segments.append(InlineMathSegment(text: math, isMath: true))
        cursor = value.index(after: end)
        textStart = cursor
    }

    if textStart < value.endIndex {
        segments.append(InlineMathSegment(text: String(value[textStart..<value.endIndex]), isMath: false))
    }
    return segments.isEmpty ? [InlineMathSegment(text: value, isMath: false)] : segments
}

private func isEscapedDollar(_ value: String, at index: String.Index) -> Bool {
    guard index > value.startIndex else { return false }
    var cursor = value.index(before: index)
    var slashCount = 0
    while true {
        if value[cursor] != "\\" { break }
        slashCount += 1
        if cursor == value.startIndex { break }
        cursor = value.index(before: cursor)
    }
    return slashCount % 2 == 1
}

private func inlineMathHTML(_ value: String) -> String {
    inlineMathSegments(value).map { segment in
        if segment.isMath {
            return "<span data-math data-source=\"\(htmlEscaped(segment.text))\"></span>"
        }
        return basicInlineMarkdownHTML(segment.text)
    }.joined()
}

private func basicInlineMarkdownHTML(_ value: String) -> String {
    var output = ""
    var cursor = value.startIndex
    while cursor < value.endIndex {
        if value[cursor] == "`", let end = value[value.index(after: cursor)...].firstIndex(of: "`") {
            let codeStart = value.index(after: cursor)
            output += "<code>\(htmlEscaped(String(value[codeStart..<end])))</code>"
            cursor = value.index(after: end)
            continue
        }
        if value[cursor...].hasPrefix("**"), let end = value[value.index(cursor, offsetBy: 2)...].range(of: "**")?.lowerBound {
            let strongStart = value.index(cursor, offsetBy: 2)
            output += "<strong>\(htmlEscaped(String(value[strongStart..<end])))</strong>"
            cursor = value.index(end, offsetBy: 2)
            continue
        }
        output += htmlEscaped(String(value[cursor]))
        cursor = value.index(after: cursor)
    }
    return output.replacingOccurrences(of: "\n", with: "<br>")
}

private func loadKatexAssets() -> (js: String, css: String)? {
    let path = URL(fileURLWithPath: #filePath)
    var cursor = path
    for _ in 0..<10 {
        let base = cursor.appendingPathComponent("apps/desktop/node_modules/katex/dist")
        let scriptURL = base.appendingPathComponent("katex.min.js")
        let cssURL = base.appendingPathComponent("katex.min.css")
        if
            let js = try? String(contentsOf: scriptURL, encoding: .utf8),
            let css = try? String(contentsOf: cssURL, encoding: .utf8),
            !js.isEmpty,
            !css.isEmpty
        {
            return (js, css)
        }
        cursor.deleteLastPathComponent()
    }
    return nil
}

private struct MarkdownCodeTick: View {
    var body: some View {
        Path { path in
            path.move(to: CGPoint(x: 0, y: 7))
            path.addLine(to: CGPoint(x: 0, y: 0))
            path.addLine(to: CGPoint(x: 7, y: 0))
        }
        .stroke(NtrpColors.sidebarStroke.opacity(0.9), lineWidth: 1)
        .frame(width: 7, height: 7)
    }
}

private struct MarkdownTableBlock: View {
    let rows: [[String]]

    var body: some View {
        ScrollView(.horizontal, showsIndicators: false) {
            Grid(horizontalSpacing: 0, verticalSpacing: 0) {
                ForEach(rows.indices, id: \.self) { rowIndex in
                    GridRow {
                        ForEach(rows[rowIndex].indices, id: \.self) { columnIndex in
                            InlineMarkdownView(text: rows[rowIndex][columnIndex], size: 13, weight: rowIndex == 0 ? .semibold : .regular)
                                .lineLimit(nil)
                                .padding(.horizontal, 9)
                                .padding(.vertical, 7)
                                .frame(minWidth: 88, maxWidth: 220, alignment: .leading)
                                .background(rowIndex == 0 ? NtrpColors.row.opacity(0.42) : Color.clear)
                                .border(NtrpColors.sidebarStroke, width: 0.5)
                        }
                    }
                }
            }
            .padding(0.5)
        }
        .clipShape(RoundedRectangle(cornerRadius: 8, style: .continuous))
    }
}

private enum MarkdownBlock {
    case paragraph(String)
    case heading(Int, String)
    case unorderedList([String])
    case orderedList([String])
    case quote(String)
    case code(language: String, String)
    case mermaid(String)
    case math(String)
    case table([[String]])

    static func parse(_ content: String) -> [MarkdownBlock] {
        let normalized = content.replacingOccurrences(of: "\r\n", with: "\n")
        let lines = normalized.split(separator: "\n", omittingEmptySubsequences: false).map(String.init)
        guard !lines.isEmpty else { return [.paragraph(" ")] }

        var blocks: [MarkdownBlock] = []
        var index = 0

        while index < lines.count {
            let line = lines[index]
            if line.trimmingCharacters(in: .whitespaces).isEmpty {
                index += 1
                continue
            }

            if let fence = fenceStart(line) {
                var codeLines: [String] = []
                index += 1
                while index < lines.count, !lines[index].hasPrefix(fence.marker) {
                    codeLines.append(lines[index])
                    index += 1
                }
                if index < lines.count { index += 1 }
                let code = codeLines.joined(separator: "\n")
                if fence.language.lowercased() == "mermaid", !code.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty {
                    blocks.append(.mermaid(code))
                } else {
                    blocks.append(.code(language: fence.language, code))
                }
                continue
            }

            if let math = mathBlock(lines, at: index) {
                blocks.append(.math(math.source))
                index = math.nextIndex
                continue
            }

            if let heading = headingStart(line) {
                blocks.append(.heading(heading.level, heading.text))
                index += 1
                continue
            }

            if isQuote(line) {
                var quoteLines: [String] = []
                while index < lines.count, isQuote(lines[index]) {
                    quoteLines.append(stripQuote(lines[index]))
                    index += 1
                }
                blocks.append(.quote(quoteLines.joined(separator: "\n")))
                continue
            }

            if let item = unorderedItem(line) {
                var items = [item]
                index += 1
                while index < lines.count, let next = unorderedItem(lines[index]) {
                    items.append(next)
                    index += 1
                }
                blocks.append(.unorderedList(items))
                continue
            }

            if let item = orderedItem(line) {
                var items = [item]
                index += 1
                while index < lines.count, let next = orderedItem(lines[index]) {
                    items.append(next)
                    index += 1
                }
                blocks.append(.orderedList(items))
                continue
            }

            if isTableStart(lines, at: index) {
                var tableLines: [String] = []
                while index < lines.count, lines[index].contains("|"), !lines[index].trimmingCharacters(in: .whitespaces).isEmpty {
                    tableLines.append(lines[index])
                    index += 1
                }
                blocks.append(.table(parseTable(tableLines)))
                continue
            }

            var paragraphLines = [line]
            index += 1
            while index < lines.count, shouldContinueParagraph(lines, at: index) {
                paragraphLines.append(lines[index])
                index += 1
            }
            blocks.append(.paragraph(paragraphLines.joined(separator: "\n")))
        }

        return blocks.isEmpty ? [.paragraph(" ")] : blocks
    }

    private static func shouldContinueParagraph(_ lines: [String], at index: Int) -> Bool {
        let line = lines[index]
        guard !line.trimmingCharacters(in: .whitespaces).isEmpty else { return false }
        if fenceStart(line) != nil || headingStart(line) != nil || isQuote(line) { return false }
        if mathBlock(lines, at: index) != nil { return false }
        if unorderedItem(line) != nil || orderedItem(line) != nil { return false }
        if isTableStart(lines, at: index) { return false }
        return true
    }

    private static func fenceStart(_ line: String) -> (marker: String, language: String)? {
        let trimmed = line.trimmingCharacters(in: .whitespaces)
        guard trimmed.hasPrefix("```") || trimmed.hasPrefix("~~~") else { return nil }
        let marker = String(trimmed.prefix(3))
        let language = trimmed.dropFirst(3).trimmingCharacters(in: .whitespacesAndNewlines)
        return (marker, language)
    }

    private static func headingStart(_ line: String) -> (level: Int, text: String)? {
        let trimmed = line.trimmingCharacters(in: .whitespaces)
        let hashes = trimmed.prefix { $0 == "#" }.count
        guard (1...3).contains(hashes), trimmed.dropFirst(hashes).first == " " else { return nil }
        return (hashes, String(trimmed.dropFirst(hashes + 1)))
    }

    private static func mathBlock(_ lines: [String], at index: Int) -> (source: String, nextIndex: Int)? {
        let line = lines[index]
        let trimmed = line.trimmingCharacters(in: .whitespaces)
        guard trimmed.hasPrefix("$$") else { return nil }

        let afterOpening = String(trimmed.dropFirst(2))
        if afterOpening.hasSuffix("$$"), afterOpening.count >= 2 {
            let source = String(afterOpening.dropLast(2)).trimmingCharacters(in: .whitespacesAndNewlines)
            guard !source.isEmpty else { return nil }
            return (source, index + 1)
        }

        var mathLines: [String] = []
        if !afterOpening.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty {
            mathLines.append(afterOpening)
        }

        var cursor = index + 1
        while cursor < lines.count {
            let current = lines[cursor]
            let currentTrimmed = current.trimmingCharacters(in: .whitespaces)
            if currentTrimmed == "$$" {
                let source = mathLines.joined(separator: "\n").trimmingCharacters(in: .whitespacesAndNewlines)
                guard !source.isEmpty else { return nil }
                return (source, cursor + 1)
            }
            mathLines.append(current)
            cursor += 1
        }

        return nil
    }

    private static func isQuote(_ line: String) -> Bool {
        line.trimmingCharacters(in: .whitespaces).hasPrefix(">")
    }

    private static func stripQuote(_ line: String) -> String {
        let trimmed = line.trimmingCharacters(in: .whitespaces)
        return String(trimmed.dropFirst()).trimmingCharacters(in: .whitespaces)
    }

    private static func unorderedItem(_ line: String) -> String? {
        let trimmed = line.trimmingCharacters(in: .whitespaces)
        guard trimmed.count > 2 else { return nil }
        let marker = trimmed.first
        guard marker == "-" || marker == "*" || marker == "+", trimmed.dropFirst().first == " " else { return nil }
        return String(trimmed.dropFirst(2))
    }

    private static func orderedItem(_ line: String) -> String? {
        let trimmed = line.trimmingCharacters(in: .whitespaces)
        guard let markerIndex = trimmed.firstIndex(where: { $0 == "." || $0 == ")" }) else { return nil }
        let number = trimmed[..<markerIndex]
        guard !number.isEmpty, number.allSatisfy(\.isNumber) else { return nil }
        let after = trimmed.index(after: markerIndex)
        guard after < trimmed.endIndex, trimmed[after] == " " else { return nil }
        return String(trimmed[trimmed.index(after: after)...])
    }

    private static func isTableStart(_ lines: [String], at index: Int) -> Bool {
        guard index + 1 < lines.count else { return false }
        guard lines[index].contains("|") else { return false }
        let separator = lines[index + 1].trimmingCharacters(in: .whitespaces)
        guard separator.contains("|"), separator.contains("-") else { return false }
        return separator.allSatisfy { char in
            char == "|" || char == "-" || char == ":" || char == " "
        }
    }

    private static func parseTable(_ lines: [String]) -> [[String]] {
        lines.enumerated().compactMap { index, line in
            if index == 1 { return nil }
            let trimmed = line.trimmingCharacters(in: .whitespaces)
            let inner = trimmed.trimmingCharacters(in: CharacterSet(charactersIn: "|"))
            return inner
                .split(separator: "|", omittingEmptySubsequences: false)
                .map { $0.trimmingCharacters(in: .whitespacesAndNewlines) }
        }
    }
}

private func markdownInline(_ text: String) -> AttributedString {
    (try? AttributedString(markdown: text, options: AttributedString.MarkdownParsingOptions(interpretedSyntax: .inlineOnlyPreservingWhitespace))) ?? AttributedString(text)
}

private struct SkillChip: View {
    let skill: JSONValue
    let open: () -> Void

    var body: some View {
        Button(action: open) {
            HStack(spacing: 6) {
                Image(systemName: "sparkles")
                    .font(.system(size: 11, weight: .medium))
                    .foregroundStyle(NtrpColors.accent)
                Text(skillName(skill).replacingOccurrences(of: "-", with: " "))
                    .font(.system(size: 12, weight: .medium))
                    .foregroundStyle(NtrpColors.muted)
                    .lineLimit(1)
            }
            .padding(.horizontal, 8)
            .frame(height: 25)
            .background(NtrpColors.row.opacity(0.36))
            .overlay(
                RoundedRectangle(cornerRadius: 7, style: .continuous)
                    .stroke(NtrpColors.sidebarStroke.opacity(0.7), lineWidth: 1)
            )
            .clipShape(RoundedRectangle(cornerRadius: 7, style: .continuous))
        }
        .buttonStyle(.plain)
        .help("Open skill source")
    }
}

private struct GoalChip: View {
    var body: some View {
        HStack(spacing: 6) {
            Image(systemName: "target")
                .font(.system(size: 11, weight: .medium))
            Text("Goal")
                .font(.system(size: 12, weight: .medium))
        }
        .foregroundStyle(NtrpColors.accent)
        .padding(.horizontal, 8)
        .frame(height: 25)
        .background(NtrpColors.accent.opacity(0.14))
        .overlay(
            RoundedRectangle(cornerRadius: 7, style: .continuous)
                .stroke(NtrpColors.accent.opacity(0.18), lineWidth: 1)
        )
        .clipShape(RoundedRectangle(cornerRadius: 7, style: .continuous))
    }
}

private func skillName(_ value: JSONValue) -> String {
    value.objectValue?.string("name") ?? value.objectValue?.string("id") ?? value.display
}

private struct MessageActions: View {
    enum Role {
        case user
        case assistant
    }

    let message: TranscriptMessage
    @ObservedObject var store: NtrpStore
    let role: Role
    let visible: Bool
    @State private var copied = false
    @State private var branching = false
    @State private var copyHovered = false
    @State private var branchHovered = false
    @State private var editHovered = false

    var body: some View {
        let timeLabel = messageTimeLabel(message.createdAt)
        HStack(spacing: 6) {
            if role == .user, let timeLabel {
                Text(timeLabel)
                    .font(.system(size: 12))
                    .tracking(-0.08)
                    .foregroundStyle(NtrpColors.faint)
                    .padding(.trailing, 2)
            }

            Button {
                copy()
            } label: {
                Image(systemName: copied ? "checkmark" : "doc.on.doc")
                    .font(.system(size: 12, weight: .medium))
                    .frame(width: 24, height: 24)
                    .contentShape(Rectangle())
            }
            .buttonStyle(.plain)
            .foregroundStyle(copied ? Color.green : (copyHovered ? NtrpColors.text : NtrpColors.faint))
            .background(copyHovered && !copied ? NtrpColors.row.opacity(0.8) : Color.clear)
            .clipShape(RoundedRectangle(cornerRadius: 6, style: .continuous))
            .onHover { copyHovered = $0 }
            .help("Copy")

            if role == .assistant {
                Button {
                    guard !branching else { return }
                    branching = true
                    Task {
                        await store.branchAtMessage(message.id)
                        branching = false
                    }
                } label: {
                    Image(systemName: "arrow.triangle.branch")
                        .font(.system(size: 12, weight: .medium))
                        .frame(width: 24, height: 24)
                        .contentShape(Rectangle())
                }
                .buttonStyle(.plain)
                .foregroundStyle(branchHovered ? NtrpColors.text : NtrpColors.faint)
                .background(branchHovered ? NtrpColors.row.opacity(0.8) : Color.clear)
                .clipShape(RoundedRectangle(cornerRadius: 6, style: .continuous))
                .disabled(branching)
                .onHover { branchHovered = $0 }
                .help("Branch from this message")
            }

            if role == .user {
                Button {
                    store.editMessage(message)
                } label: {
                    Image(systemName: "pencil")
                        .font(.system(size: 12, weight: .medium))
                        .frame(width: 24, height: 24)
                        .contentShape(Rectangle())
                }
                .buttonStyle(.plain)
                .foregroundStyle(editHovered ? NtrpColors.text : NtrpColors.faint)
                .background(editHovered ? NtrpColors.row.opacity(0.8) : Color.clear)
                .clipShape(RoundedRectangle(cornerRadius: 6, style: .continuous))
                .onHover { editHovered = $0 }
                .help("Edit and resend")
            }

            if role == .assistant, let timeLabel {
                Text(timeLabel)
                    .font(.system(size: 12))
                    .tracking(-0.08)
                    .foregroundStyle(NtrpColors.faint)
                    .padding(.leading, 2)
            }
        }
        .frame(height: 24)
        .opacity(visible || copied ? 1 : 0)
        .frame(maxWidth: .infinity, alignment: role == .user ? .trailing : .leading)
        .animation(.easeInOut(duration: 0.15), value: visible)
        .animation(.easeInOut(duration: 0.15), value: copied)
    }

    private func copy() {
        NSPasteboard.general.clearContents()
        NSPasteboard.general.setString(message.content, forType: .string)
        copied = true
        Task {
            try? await Task.sleep(for: .milliseconds(1200))
            copied = false
        }
    }
}

private func messageTimeLabel(_ iso: String?) -> String? {
    guard let iso,
          let date = ISO8601DateFormatter.ntrp.date(from: iso) ?? ISO8601DateFormatter.ntrpFractional.date(from: iso)
    else { return nil }

    let formatter = DateFormatter()
    if Calendar.current.isDateInToday(date) {
        formatter.dateFormat = "h:mm a"
    } else {
        formatter.dateFormat = "MMM d · h:mm a"
    }
    return formatter.string(from: date)
}

private struct ApprovalStrip: View {
    @ObservedObject var store: NtrpStore
    @ObservedObject var ui: NtrpUIState
    @State private var keyMonitor: Any?

    var body: some View {
        if !store.pendingApprovals.isEmpty, ui.reviewingApproval == nil {
            ZStack(alignment: .top) {
                ForEach(Array(store.pendingApprovals.prefix(2).enumerated()).reversed(), id: \.element.id) { index, approval in
                    ApprovalCard(
                        store: store,
                        approval: approval,
                        totalPending: store.pendingApprovals.count,
                        isFront: index == 0,
                        review: {
                            ui.reviewingApproval = approval
                        }
                    )
                    .scaleEffect(index == 0 ? 1 : 0.965)
                    .offset(y: index == 0 ? 0 : -6)
                    .opacity(index == 0 ? 1 : 0.5)
                    .allowsHitTesting(index == 0)
                    .zIndex(Double(2 - index))
                }
            }
            .frame(maxWidth: 760)
            .padding(.top, store.pendingApprovals.count > 1 ? 14 : 0)
            .onAppear(perform: installKeyMonitor)
            .onDisappear(perform: removeKeyMonitor)
        } else {
            Color.clear
                .frame(width: 0, height: 0)
                .onDisappear(perform: removeKeyMonitor)
        }
    }

    private func installKeyMonitor() {
        guard keyMonitor == nil else { return }
        keyMonitor = NSEvent.addLocalMonitorForEvents(matching: .keyDown) { event in
            guard event.keyCode == 36,
                  event.modifierFlags.intersection([.command, .control]).isEmpty == false,
                  event.modifierFlags.intersection([.option, .shift]).isEmpty,
                  ui.reviewingApproval == nil,
                  let approval = store.pendingApprovals.first
            else {
                return event
            }
            Task { await store.resolveApproval(approval, approved: true) }
            return nil
        }
    }

    private func removeKeyMonitor() {
        if let keyMonitor {
            NSEvent.removeMonitor(keyMonitor)
            self.keyMonitor = nil
        }
    }
}

private struct ApprovalCard: View {
    @ObservedObject var store: NtrpStore
    let approval: PendingApproval
    let totalPending: Int
    let isFront: Bool
    let review: () -> Void

    private var showBulk: Bool {
        isFront && totalPending > 1
    }

    private var previewLine: String? {
        if structuredPreview != nil { return nil }
        return approvalSnippet(approval.preview ?? approval.diff)
    }

    private var structuredPreview: StructuredApprovalPreview? {
        guard let preview = approval.preview else { return nil }
        return StructuredApprovalPreview.parse(preview)
    }

    var body: some View {
        VStack(spacing: 0) {
            HStack(alignment: .firstTextBaseline, spacing: 4) {
                if structuredPreview != nil {
                    Text("Approve action")
                        .font(.system(size: 16, weight: .medium))
                        .tracking(-0.08)
                        .foregroundStyle(NtrpColors.text)
                } else {
                    Text("Approve")
                        .font(.system(size: 16, weight: .medium))
                        .tracking(-0.08)
                        .foregroundStyle(NtrpColors.text)
                    Text(approval.name)
                        .font(.system(size: 16, weight: .medium, design: .monospaced))
                        .foregroundStyle(NtrpColors.text)
                        .lineLimit(1)
                    Text("?")
                        .font(.system(size: 16, weight: .medium))
                        .foregroundStyle(NtrpColors.text)
                }
                Spacer(minLength: 12)
                if showBulk {
                    Text("1 of \(totalPending)")
                        .font(.system(size: 12))
                        .monospacedDigit()
                        .foregroundStyle(NtrpColors.faint)
                }
            }
            .padding(.horizontal, 16)
            .padding(.top, 12)
            .padding(.bottom, approvalBodyBottomPadding)

            if let structured = structuredPreview {
                VStack(alignment: .leading, spacing: 10) {
                    Text(approval.name)
                        .font(.system(size: 12, design: .monospaced))
                        .foregroundStyle(NtrpColors.faint)
                    VStack(alignment: .leading, spacing: 4) {
                        ForEach(structured.fields) { field in
                            approvalField(field.key, value: field.value)
                        }
                    }
                    if let body = structured.body, !body.text.isEmpty {
                        VStack(alignment: .leading, spacing: 4) {
                            Text(body.label.uppercased())
                                .font(.system(size: 12, weight: .medium))
                                .tracking(0.72)
                                .foregroundStyle(NtrpColors.faint)
                            Text(body.text)
                                .font(.system(size: 12, design: .monospaced))
                                .foregroundStyle(NtrpColors.muted)
                                .lineLimit(6)
                                .padding(8)
                                .frame(maxWidth: .infinity, alignment: .leading)
                                .background(NtrpColors.canvas.opacity(0.30))
                                .overlay(RoundedRectangle(cornerRadius: 6, style: .continuous).stroke(NtrpColors.sidebarStroke.opacity(0.7), lineWidth: 1))
                                .clipShape(RoundedRectangle(cornerRadius: 6, style: .continuous))
                        }
                    }
                }
                .padding(.horizontal, 16)
                .padding(.bottom, 12)
            } else if approval.path != nil || previewLine != nil {
                VStack(alignment: .leading, spacing: 4) {
                    if let path = approval.path {
                        approvalField("Target", value: path)
                    }
                    if let previewLine {
                        approvalField("Content", value: previewLine)
                    }
                }
                .padding(.horizontal, 16)
                .padding(.bottom, 12)
            }

            HStack(spacing: 8) {
                if hasReviewable {
                    approvalButton("Review", action: review)
                }
                Spacer(minLength: 0)
                if showBulk {
                    approvalButton("Reject all") {
                        Task { await store.resolveAllApprovals(approved: false) }
                    }
                    approvalButton("Approve all", bordered: true) {
                        Task { await store.resolveAllApprovals(approved: true) }
                    }
                    Rectangle()
                        .fill(NtrpColors.sidebarStroke.opacity(0.8))
                        .frame(width: 1, height: 20)
                        .padding(.horizontal, 2)
                }
                approvalButton("Reject", bordered: true) {
                    Task { await store.resolveApproval(approval, approved: false) }
                }
                Button {
                    Task { await store.resolveApproval(approval, approved: true) }
                } label: {
                    HStack(spacing: 6) {
                        Text("Approve")
                        Text("⌘↩")
                            .font(.system(size: 10, weight: .medium, design: .monospaced))
                            .opacity(0.72)
                    }
                    .font(.system(size: 13, weight: .medium))
                    .foregroundStyle(Color.black.opacity(0.86))
                    .padding(.horizontal, 11)
                    .frame(height: 28)
                    .background(NtrpColors.text)
                    .clipShape(RoundedRectangle(cornerRadius: 7, style: .continuous))
                }
                .buttonStyle(.plain)
                .keyboardShortcut(.return, modifiers: [.command])
            }
            .padding(.horizontal, 12)
            .padding(.vertical, 8)
            .background(NtrpColors.row.opacity(0.35))
        }
        .background(NtrpColors.surfaceFill(0.72))
        .clipShape(RoundedRectangle(cornerRadius: 14, style: .continuous))
        .shadow(color: .black.opacity(0.32), radius: 16, x: 0, y: 10)
        .ntrpGlass(cornerRadius: 14, interactive: true)
    }

    private var approvalBodyBottomPadding: CGFloat {
        if structuredPreview != nil || approval.path != nil || previewLine != nil {
            return 8
        }
        return 12
    }

    private var hasReviewable: Bool {
        if approval.diff != nil { return true }
        if let body = structuredPreview?.body, body.text.count > 480 { return true }
        return false
    }

    private func approvalField(_ label: String, value: String) -> some View {
        HStack(alignment: .firstTextBaseline, spacing: 20) {
            Text(label)
                .font(.system(size: 13))
                .foregroundStyle(NtrpColors.faint)
                .fixedSize(horizontal: true, vertical: false)
            Text(value)
                .font(.system(size: 13, design: .monospaced))
                .foregroundStyle(NtrpColors.muted)
                .lineLimit(1)
                .truncationMode(.middle)
        }
    }

    private func approvalButton(_ label: String, bordered: Bool = false, action: @escaping () -> Void) -> some View {
        Button(action: action) {
            Text(label)
                .font(.system(size: 13))
                .foregroundStyle(NtrpColors.muted)
                .padding(.horizontal, bordered ? 12 : 10)
                .frame(height: 28)
                .background(bordered ? NtrpColors.row.opacity(0.45) : Color.clear)
                .overlay {
                    if bordered {
                        RoundedRectangle(cornerRadius: 7, style: .continuous)
                            .stroke(NtrpColors.sidebarStroke, lineWidth: 1)
                    }
                }
                .clipShape(RoundedRectangle(cornerRadius: 7, style: .continuous))
        }
        .buttonStyle(.plain)
    }
}

private struct StructuredApprovalPreview {
    struct Field: Identifiable {
        let id = UUID()
        let key: String
        let value: String
    }

    struct Body {
        let label: String
        let text: String
    }

    let fields: [Field]
    let body: Body?

    static func parse(_ text: String) -> StructuredApprovalPreview? {
        guard !text.isEmpty else { return nil }
        let lines = text.components(separatedBy: "\n")
        var fields: [Field] = []
        var cursor = 0

        while cursor < lines.count {
            let line = lines[cursor]
            if line.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty { break }
            guard let match = line.firstMatch(of: /^([A-Z][A-Za-z _-]{0,30}):\s*(.*)$/) else { break }
            fields.append(Field(key: String(match.1).trimmingCharacters(in: .whitespacesAndNewlines), value: String(match.2).trimmingCharacters(in: .whitespacesAndNewlines)))
            cursor += 1
        }

        guard !fields.isEmpty else { return nil }

        while cursor < lines.count && lines[cursor].trimmingCharacters(in: .whitespacesAndNewlines).isEmpty {
            cursor += 1
        }

        var body: Body?
        if cursor < lines.count {
            let line = lines[cursor]
            if let labelMatch = line.firstMatch(of: /^([A-Z][A-Za-z _-]{0,30}):\s*$/), cursor + 1 < lines.count {
                body = Body(label: String(labelMatch.1), text: lines[(cursor + 1)...].joined(separator: "\n").trimmingCharacters(in: .whitespacesAndNewlines))
            } else {
                body = Body(label: "Detail", text: lines[cursor...].joined(separator: "\n").trimmingCharacters(in: .whitespacesAndNewlines))
            }
        }

        return StructuredApprovalPreview(fields: fields, body: body)
    }
}

struct ApprovalReviewPanel: View {
    @ObservedObject var store: NtrpStore
    let approval: PendingApproval
    let close: () -> Void
    @State private var scrolled = false

    private var content: String {
        approval.diff ?? approval.preview ?? approval.path ?? ""
    }

    var body: some View {
        VStack(alignment: .leading, spacing: 0) {
            HStack(alignment: .firstTextBaseline, spacing: 8) {
                Text(approval.name)
                    .font(.system(size: 17, weight: .medium, design: .monospaced))
                    .foregroundStyle(NtrpColors.text)
                    .lineLimit(1)
                if let path = approval.path {
                    Text(path)
                        .font(.system(size: 13, weight: .regular, design: .monospaced))
                        .foregroundStyle(NtrpColors.faint)
                        .lineLimit(1)
                        .truncationMode(.middle)
                }
                Spacer()
                Button {
                    close()
                } label: {
                    Image(systemName: "xmark")
                        .font(.system(size: 13, weight: .medium))
                        .foregroundStyle(NtrpColors.muted)
                        .frame(width: 26, height: 26)
                }
                .buttonStyle(.plain)
            }
            .padding(.horizontal, 18)
            .padding(.top, 16)
            .padding(.bottom, 10)

            ScrollView {
                VStack(spacing: 0) {
                    ModalScrollSentinel(space: "approval-review-scroll")
                    if let diff = approval.diff, !diff.isEmpty {
                        VStack(alignment: .leading, spacing: 0) {
                            ForEach(Array(diff.components(separatedBy: "\n").enumerated()), id: \.offset) { _, line in
                                Text(line.isEmpty ? " " : line)
                                    .font(.system(size: 12, design: .monospaced))
                                    .foregroundStyle(diffLineStyle(line).foreground)
                                    .padding(.horizontal, 8)
                                    .frame(maxWidth: .infinity, minHeight: 18, alignment: .leading)
                                    .background(diffLineStyle(line).background)
                                    .textSelection(.enabled)
                            }
                        }
                        .frame(maxWidth: .infinity, alignment: .leading)
                    } else if let preview = approval.preview, !preview.isEmpty {
                        Text(preview)
                            .font(.system(size: 14, design: .monospaced))
                            .lineSpacing(3)
                            .foregroundStyle(NtrpColors.text.opacity(0.82))
                            .textSelection(.enabled)
                            .frame(maxWidth: .infinity, alignment: .leading)
                            .padding(.horizontal, 20)
                            .padding(.vertical, 16)
                    } else {
                        Text("No diff or preview available.")
                            .font(.system(size: 14))
                            .italic()
                            .foregroundStyle(NtrpColors.faint)
                            .frame(maxWidth: .infinity, alignment: .leading)
                            .padding(.horizontal, 20)
                            .padding(.vertical, 24)
                    }
                }
            }
            .coordinateSpace(name: "approval-review-scroll")
            .mask(NtrpScrollTopMask(scrolled: scrolled))
            .onPreferenceChange(ModalScrollTopPreferenceKey.self) { top in
                let next = top < -0.5
                if scrolled != next {
                    scrolled = next
                }
            }

            HStack(spacing: 8) {
                Text(String(approval.id.prefix(8)))
                    .font(.system(size: 12, design: .monospaced))
                    .foregroundStyle(NtrpColors.faint)
                Spacer()
                Button {
                    Task {
                        await store.resolveApproval(approval, approved: false)
                        close()
                    }
                } label: {
                    HStack(spacing: 6) {
                        Image(systemName: "xmark")
                            .font(.system(size: 11, weight: .semibold))
                        Text("Reject")
                    }
                    .font(.system(size: 13, weight: .medium))
                    .foregroundStyle(NtrpColors.muted)
                    .padding(.horizontal, 12)
                    .frame(height: 32)
                    .background(NtrpColors.surfaceFill(0.55))
                    .overlay(
                        RoundedRectangle(cornerRadius: 7, style: .continuous)
                            .stroke(NtrpColors.sidebarStroke, lineWidth: 1)
                    )
                    .clipShape(RoundedRectangle(cornerRadius: 7, style: .continuous))
                }
                .buttonStyle(.plain)
                Button {
                    Task {
                        await store.resolveApproval(approval, approved: true)
                        close()
                    }
                } label: {
                    HStack(spacing: 6) {
                        Image(systemName: "checkmark")
                            .font(.system(size: 11, weight: .bold))
                        Text("Approve")
                    }
                    .font(.system(size: 13, weight: .medium))
                    .foregroundStyle(Color.black.opacity(0.86))
                    .padding(.horizontal, 16)
                    .frame(height: 32)
                    .background(NtrpColors.text)
                    .clipShape(RoundedRectangle(cornerRadius: 7, style: .continuous))
                }
                .buttonStyle(.plain)
                .keyboardShortcut(.return, modifiers: [.command])
            }
            .padding(.horizontal, 20)
            .padding(.vertical, 12)
            .background(NtrpColors.row.opacity(0.40))
        }
    }

    private func diffLineStyle(_ line: String) -> (foreground: Color, background: Color) {
        if line.hasPrefix("+++") || line.hasPrefix("---") || line.hasPrefix("@@") {
            return (NtrpColors.accent, .clear)
        }
        if line.hasPrefix("+") {
            return (
                NtrpColors.isDarkMode ? Color(red: 0.69, green: 0.77, blue: 0.39) : Color(red: 0.18, green: 0.40, blue: 0.13),
                (NtrpColors.isDarkMode ? Color(red: 0.53, green: 0.60, blue: 0.22) : Color(red: 0.31, green: 0.54, blue: 0.23)).opacity(NtrpColors.isDarkMode ? 0.16 : 0.10)
            )
        }
        if line.hasPrefix("-") {
            return (
                NtrpColors.isDarkMode ? Color(red: 0.90, green: 0.50, blue: 0.46) : Color(red: 0.54, green: 0.20, blue: 0.13),
                (NtrpColors.isDarkMode ? Color(red: 0.82, green: 0.30, blue: 0.25) : Color(red: 0.72, green: 0.27, blue: 0.17)).opacity(NtrpColors.isDarkMode ? 0.16 : 0.10)
            )
        }
        return (NtrpColors.text.opacity(0.82), .clear)
    }
}

private struct ModalScrollSentinel: View {
    let space: String

    var body: some View {
        GeometryReader { geometry in
            Color.clear.preference(
                key: ModalScrollTopPreferenceKey.self,
                value: geometry.frame(in: .named(space)).minY
            )
        }
        .frame(height: 1)
        .padding(.bottom, -1)
    }
}

private struct ModalScrollTopPreferenceKey: PreferenceKey {
    static var defaultValue: CGFloat = 0

    static func reduce(value: inout CGFloat, nextValue: () -> CGFloat) {
        value = nextValue()
    }
}

private func approvalSnippet(_ text: String?, maxLength: Int = 160) -> String? {
    guard let text else { return nil }
    for rawLine in text.split(separator: "\n", omittingEmptySubsequences: false) {
        let line = rawLine.trimmingCharacters(in: .whitespacesAndNewlines)
        if line.isEmpty || line.hasPrefix("---") || line.hasPrefix("+++") || line.hasPrefix("@@") {
            continue
        }
        if line.count <= maxLength { return line }
        return String(line.prefix(maxLength)).trimmingCharacters(in: .whitespacesAndNewlines) + "..."
    }
    return nil
}
