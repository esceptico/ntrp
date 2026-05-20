import AppKit
import SwiftUI

struct SidebarView: View {
    @ObservedObject var store: NtrpStore
    @Binding var activeSurface: MainSurface
    @State private var searchOpen = false
    @State private var query = ""
    @State private var collapsedBuckets: Set<String> = []
    @State private var searchKeyMonitor: Any?
    @FocusState private var searchFocused: Bool

    var body: some View {
        if #available(macOS 26.0, *) {
            GlassEffectContainer(spacing: 8) {
                content
            }
        } else {
            content
        }
    }

    private var content: some View {
        VStack(alignment: .leading, spacing: 0) {
            Color.clear
                .frame(height: 22)

            topActions
                .padding(.top, 8)
                .padding(.horizontal, 10)

            sessionList
                .padding(.top, 12)

            Spacer(minLength: 16)

            SidebarNavButton(title: "Settings", icon: "gearshape", isActive: activeSurface == .settings) {
                activeSurface = .settings
            }
            .padding(.horizontal, 10)
            .padding(.bottom, 12)
        }
        .frame(maxWidth: .infinity, maxHeight: .infinity)
    }

    private var topActions: some View {
        VStack(alignment: .leading, spacing: 1) {
            SidebarNavButton(title: "New session", icon: "pencil", isActive: false) {
                activeSurface = .chat
                Task { await store.createSession() }
            }
            SidebarNavButton(title: "Automations", icon: "bolt", isActive: activeSurface == .automations) {
                activeSurface = .automations
            }
            SidebarNavButton(title: "Memory", icon: "brain", isActive: activeSurface == .memory) {
                activeSurface = .memory
            }
        }
    }

    private var sessionList: some View {
        VStack(spacing: 8) {
            if searchOpen || !query.isEmpty {
                HStack(spacing: 6) {
                    Image(systemName: "magnifyingglass")
                        .font(.system(size: 12))
                        .foregroundStyle(NtrpColors.faint)
                    TextField("Filter sessions", text: $query)
                        .textFieldStyle(.plain)
                        .font(.system(size: 13))
                        .foregroundStyle(NtrpColors.text)
                        .focused($searchFocused)
                        .onExitCommand(perform: dismissSearch)
                        .onChange(of: searchFocused) { _, focused in
                            if !focused && query.isEmpty {
                                closeSearch()
                            }
                        }
                    Button {
                        closeSearch()
                    } label: {
                        Image(systemName: "xmark")
                            .font(.system(size: 10, weight: .semibold))
                    }
                    .buttonStyle(.plain)
                    .foregroundStyle(NtrpColors.faint)
                }
                .padding(.horizontal, 7)
                .frame(height: 24)
                .background(NtrpColors.row)
                .clipShape(RoundedRectangle(cornerRadius: 6, style: .continuous))
                .padding(.horizontal, 10)
                .padding(.bottom, 4)
                .onAppear {
                    searchFocused = true
                }
            }

            ScrollView {
                LazyVStack(alignment: .leading, spacing: 12) {
                    if store.sessions.isEmpty {
                        Text(store.connectionLabel.contains("Connected") ? "No sessions yet." : "Connect to load sessions.")
                            .font(.system(size: 13))
                            .foregroundStyle(NtrpColors.faint)
                            .italic()
                            .padding(.horizontal, 12)
                            .padding(.top, 4)
                    } else if filteredSessions.isEmpty {
                        Text("No matches.")
                            .font(.system(size: 13))
                            .foregroundStyle(NtrpColors.faint)
                            .italic()
                            .padding(.horizontal, 12)
                            .padding(.top, 4)
                    } else {
                        ForEach(Array(sessionBuckets.enumerated()), id: \.element.title) { index, bucket in
                            SessionSection(
                                title: bucket.title,
                                sessions: bucket.sessions,
                                selectedID: store.selectedSessionID,
                                activeRunSessionIDs: store.activeRunSessionIDs,
                                unreadDoneSessionIDs: store.unreadDoneSessionIDs,
                                isCollapsed: collapsedBuckets.contains(bucket.title),
                                showsHeaderActions: index == 0 && !searchOpen,
                                toggleCollapsed: { toggleBucket(bucket.title) },
                                openSearch: { openSearch() },
                                toggleArchive: { activeSurface = .archive }
                            ) { id in
                                activeSurface = .chat
                                Task { await store.selectSession(id) }
                            } rename: { id, name in
                                Task { await store.renameSession(id, name: name) }
                            } compact: { id in
                                Task { await store.compactSession(id) }
                            } archive: { id in
                                Task { await store.archiveSession(id) }
                            }
                        }
                    }
                }
                .padding(.bottom, 12)
                .padding(.top, (searchOpen || !query.isEmpty) ? 0 : 12)
            }
            .scrollIndicators(.hidden)
        }
        .onAppear(perform: installSearchKeyMonitor)
        .onDisappear(perform: removeSearchKeyMonitor)
    }

    private var filteredSessions: [SessionListItem] {
        let needle = query.trimmingCharacters(in: .whitespacesAndNewlines).lowercased()
        guard !needle.isEmpty else { return store.sessions }
        return store.sessions.filter { ($0.name ?? "untitled").lowercased().contains(needle) }
    }

    private var sessionBuckets: [SessionBucket] {
        SessionBucket.bucket(filteredSessions)
    }

    private func toggleBucket(_ title: String) {
        if collapsedBuckets.contains(title) {
            collapsedBuckets.remove(title)
        } else {
            collapsedBuckets.insert(title)
        }
    }

    private func openSearch() {
        searchOpen = true
        searchFocused = true
    }

    private func closeSearch() {
        query = ""
        searchOpen = false
        searchFocused = false
    }

    private func dismissSearch() {
        if query.isEmpty {
            closeSearch()
        } else {
            query = ""
        }
    }

    private func installSearchKeyMonitor() {
        guard searchKeyMonitor == nil else { return }
        searchKeyMonitor = NSEvent.addLocalMonitorForEvents(matching: .keyDown) { event in
            let flags = event.modifierFlags.intersection([.command, .control, .option, .shift])
            guard flags == .command,
                  event.charactersIgnoringModifiers?.lowercased() == "f"
            else {
                return event
            }
            openSearch()
            return nil
        }
    }

    private func removeSearchKeyMonitor() {
        if let searchKeyMonitor {
            NSEvent.removeMonitor(searchKeyMonitor)
            self.searchKeyMonitor = nil
        }
    }
}

private struct SessionBucket {
    let title: String
    let sessions: [SessionListItem]

    static func bucket(_ sessions: [SessionListItem]) -> [SessionBucket] {
        let calendar = Calendar.current
        let today = calendar.startOfDay(for: Date())
        let yesterday = calendar.date(byAdding: .day, value: -1, to: today) ?? today
        let sevenDaysAgo = calendar.date(byAdding: .day, value: -6, to: today) ?? today
        let thirtyDaysAgo = calendar.date(byAdding: .day, value: -29, to: today) ?? today
        var todayItems: [SessionListItem] = []
        var yesterdayItems: [SessionListItem] = []
        var weekItems: [SessionListItem] = []
        var monthItems: [SessionListItem] = []
        var olderItems: [SessionListItem] = []

        for session in sessions {
            let date = sessionActivityDate(session) ?? .distantPast
            if date >= today {
                todayItems.append(session)
            } else if date >= yesterday {
                yesterdayItems.append(session)
            } else if date >= sevenDaysAgo {
                weekItems.append(session)
            } else if date >= thirtyDaysAgo {
                monthItems.append(session)
            } else {
                olderItems.append(session)
            }
        }

        return [
            SessionBucket(title: "Today", sessions: todayItems),
            SessionBucket(title: "Yesterday", sessions: yesterdayItems),
            SessionBucket(title: "Previous 7 days", sessions: weekItems),
            SessionBucket(title: "Previous 30 days", sessions: monthItems),
            SessionBucket(title: "Older", sessions: olderItems)
        ].filter { !$0.sessions.isEmpty }
    }
}

private struct SessionSection: View {
    let title: String
    let sessions: [SessionListItem]
    let selectedID: String?
    let activeRunSessionIDs: Set<String>
    let unreadDoneSessionIDs: Set<String>
    let isCollapsed: Bool
    let showsHeaderActions: Bool
    let toggleCollapsed: () -> Void
    let openSearch: () -> Void
    let toggleArchive: () -> Void
    let select: (String) -> Void
    let rename: (String, String) -> Void
    let compact: (String) -> Void
    let archive: (String) -> Void

    var body: some View {
        if !sessions.isEmpty {
            VStack(alignment: .leading, spacing: 0) {
                HStack(spacing: 4) {
                    Button(action: toggleCollapsed) {
                        HStack(spacing: 4) {
                            Image(systemName: "chevron.down")
                                .font(.system(size: 10, weight: .semibold))
                                .rotationEffect(.degrees(isCollapsed ? -90 : 0))
                            Text(title.uppercased())
                                .font(.system(size: 11.5, weight: .medium))
                                .tracking(0.9)
                            Spacer(minLength: 0)
                        }
                        .contentShape(Rectangle())
                    }
                    .buttonStyle(.plain)
                    if showsHeaderActions {
                        HStack(spacing: 1) {
                            SidebarHeaderActionButton(icon: "magnifyingglass", action: openSearch)
                            SidebarHeaderActionButton(icon: "archivebox", action: toggleArchive)
                        }
                    }
                }
                .foregroundStyle(NtrpColors.faint)
                .padding(.leading, 18)
                .padding(.trailing, 18)
                .padding(.top, 6)
                .padding(.bottom, 4)

                if !isCollapsed {
                    ForEach(sessions) { session in
                        SessionRow(
                            session: session,
                            isSelected: selectedID == session.sessionID,
                            isStreaming: activeRunSessionIDs.contains(session.sessionID),
                            isUnread: unreadDoneSessionIDs.contains(session.sessionID),
                            select: select,
                            rename: rename,
                            compact: compact,
                            archive: archive
                        )
                    }
                }
            }
            .animation(.snappy(duration: 0.18), value: isCollapsed)
        }
    }
}

private struct SidebarHeaderActionButton: View {
    let icon: String
    let action: () -> Void

    @State private var hovering = false

    var body: some View {
        Button(action: action) {
            Image(systemName: icon)
                .font(.system(size: 13, weight: .medium))
                .foregroundStyle(hovering ? NtrpColors.text : NtrpColors.faint)
                .frame(width: 26, height: 22)
                .background(hovering ? NtrpColors.row.opacity(0.7) : Color.clear)
                .clipShape(RoundedRectangle(cornerRadius: 5, style: .continuous))
        }
        .buttonStyle(.plain)
        .onHover { hovering = $0 }
    }
}

private struct SidebarNavButton: View {
    let title: String
    let icon: String
    let isActive: Bool
    let action: () -> Void
    @State private var hovering = false

    var body: some View {
        Button(action: action) {
            HStack(spacing: 8) {
                Image(systemName: icon)
                    .font(.system(size: 16, weight: .medium))
                    .frame(width: 16, height: 16)
                Text(title)
                    .font(.system(size: 16, weight: .medium))
                    .tracking(-0.08)
                    .lineLimit(1)
                Spacer(minLength: 0)
            }
            .foregroundStyle(isActive || hovering ? NtrpColors.text : NtrpColors.muted)
            .padding(.horizontal, 8)
            .frame(height: 32)
            .background(isActive ? NtrpColors.rowActive : Color.clear)
            .overlay(
                RoundedRectangle(cornerRadius: 8, style: .continuous)
                    .stroke(isActive ? NtrpColors.rowActiveStroke : Color.clear, lineWidth: 1)
            )
            .clipShape(RoundedRectangle(cornerRadius: 8, style: .continuous))
            .contentShape(Rectangle())
        }
        .buttonStyle(.plain)
        .onHover { hovering = $0 }
    }
}

private struct SessionRow: View {
    let session: SessionListItem
    let isSelected: Bool
    let isStreaming: Bool
    let isUnread: Bool
    let select: (String) -> Void
    let rename: (String, String) -> Void
    let compact: (String) -> Void
    let archive: (String) -> Void

    @State private var isHovering = false
    @State private var isRenaming = false
    @State private var draft = ""
    @FocusState private var renameFocused: Bool

    var body: some View {
        rowContent
            .padding(.horizontal, 8)
            .frame(height: 32)
            .background(rowBackground)
            .overlay(
                RoundedRectangle(cornerRadius: 8, style: .continuous)
                    .stroke(rowStroke, lineWidth: 1)
            )
            .clipShape(RoundedRectangle(cornerRadius: 8, style: .continuous))
            .shadow(color: .black.opacity(isRenaming ? 0.10 : 0), radius: isRenaming ? 5 : 0, x: 0, y: isRenaming ? 2 : 0)
            .contentShape(Rectangle())
            .onTapGesture {
                if !isRenaming {
                    select(session.sessionID)
                }
            }
            .onTapGesture(count: 2) {
                startRename()
            }
            .onHover { isHovering = $0 }
            .contextMenu {
                Button {
                    startRename()
                } label: {
                    Label("Rename", systemImage: "pencil")
                }
                Button {
                    compact(session.sessionID)
                } label: {
                    Label("Compact context", systemImage: "sparkles")
                }
                Button {
                    archive(session.sessionID)
                } label: {
                    Label("Archive", systemImage: "archivebox")
                }
            }
    }

    private var rowBackground: Color {
        if isRenaming { return NtrpColors.row.opacity(0.72) }
        return isSelected ? NtrpColors.rowActive : Color.clear
    }

    private var rowStroke: Color {
        if isRenaming { return NtrpColors.sidebarStroke.opacity(0.55) }
        return isSelected ? NtrpColors.rowActiveStroke : Color.clear
    }

    @ViewBuilder
    private var rowContent: some View {
        HStack(spacing: 8) {
            stateSlot

            if isRenaming {
                TextField("", text: $draft)
                    .textFieldStyle(.plain)
                    .font(.system(size: 16, weight: .medium))
                    .tracking(-0.08)
                    .foregroundStyle(NtrpColors.text)
                    .focused($renameFocused)
                    .onSubmit(commitRename)
                    .onExitCommand(perform: cancelRename)
                    .onAppear { renameFocused = true }
                    .onChange(of: renameFocused) { _, focused in
                        if !focused && isRenaming {
                            commitRename()
                        }
                    }
            } else {
                Text(sessionTitle)
                    .font(.system(size: 16, weight: .medium))
                    .tracking(-0.08)
                    .foregroundStyle(isSelected || isHovering ? NtrpColors.text : NtrpColors.muted)
                    .lineLimit(1)
            }

            Spacer(minLength: 8)

            ZStack(alignment: .trailing) {
                Text(shortAge)
                    .font(.system(size: 12, weight: .regular))
                    .monospacedDigit()
                    .foregroundStyle(NtrpColors.faint)
                    .opacity(isHovering && !isRenaming ? 0 : 1)

                HStack(spacing: 2) {
                    rowAction("pencil", label: "Rename", action: startRename)
                    rowAction("archivebox", label: "Archive") {
                        archive(session.sessionID)
                    }
                }
                .opacity(isHovering && !isRenaming ? 1 : 0)
            }
            .frame(width: 56, height: 22)
        }
    }

    private var stateSlot: some View {
        ZStack {
            if isStreaming {
                BreathingStatusDot()
            } else if isUnread {
                Circle()
                    .fill(NtrpColors.accent)
                    .frame(width: 5, height: 5)
            } else if session.sessionType == "channel" {
                Image(systemName: "dot.radiowaves.left.and.right")
                    .font(.system(size: 12, weight: .medium))
                    .foregroundStyle(NtrpColors.faint)
            }
        }
        .frame(width: 16, height: 16)
    }

    private func rowAction(_ icon: String, label: String, action: @escaping () -> Void) -> some View {
        Button(action: action) {
                Image(systemName: icon)
                .font(.system(size: 13, weight: .medium))
                .foregroundStyle(NtrpColors.muted)
                .frame(width: 26, height: 22)
                .contentShape(Rectangle())
        }
        .buttonStyle(.plain)
        .background(NtrpColors.row.opacity(0.0))
        .clipShape(RoundedRectangle(cornerRadius: 5, style: .continuous))
        .help(label)
    }

    private var sessionTitle: String {
        session.name?.isEmpty == false ? session.name! : "untitled"
    }

    private var shortAge: String {
        let date = sessionActivityDate(session)
        guard let date else { return "" }
        let seconds = max(0, Int(Date().timeIntervalSince(date)))
        if seconds < 60 { return "now" }
        let minutes = seconds / 60
        if minutes < 60 { return "\(minutes)m" }
        let hours = minutes / 60
        if hours < 48 { return "\(hours)h" }
        let days = hours / 24
        if days < 60 { return "\(days)d" }
        let months = days / 30
        return "\(months)mo"
    }

    private func startRename() {
        draft = sessionTitle
        isRenaming = true
    }

    private func cancelRename() {
        isRenaming = false
        draft = ""
    }

    private func commitRename() {
        let trimmed = draft.trimmingCharacters(in: .whitespacesAndNewlines)
        cancelRename()
        guard !trimmed.isEmpty, trimmed != sessionTitle else { return }
        rename(session.sessionID, trimmed)
    }

}

private struct BreathingStatusDot: View {
    var body: some View {
        TimelineView(.animation) { context in
            let progress = context.date.timeIntervalSinceReferenceDate.truncatingRemainder(dividingBy: 2.0) / 2.0
            let wave = (1 - cos(progress * .pi * 2)) / 2
            let radius = 3 + wave * 9
            let opacity = 0.85 + wave * 0.15

            Circle()
                .fill(NtrpColors.accent)
                .frame(width: 6, height: 6)
                .opacity(opacity)
                .shadow(color: NtrpColors.accent.opacity(0.85), radius: radius)
                .allowsHitTesting(false)
        }
    }
}

private func sessionActivityDate(_ session: SessionListItem) -> Date? {
    sessionDate(from: session.lastActivity) ?? sessionDate(from: session.startedAt)
}

private func sessionDate(from value: String) -> Date? {
    if let date = ISO8601DateFormatter.ntrp.date(from: value) {
        return date
    }
    return ISO8601DateFormatter.ntrpFractional.date(from: value)
}

extension ISO8601DateFormatter {
    static let ntrp: ISO8601DateFormatter = {
        let formatter = ISO8601DateFormatter()
        formatter.formatOptions = [.withInternetDateTime]
        return formatter
    }()

    static let ntrpFractional: ISO8601DateFormatter = {
        let formatter = ISO8601DateFormatter()
        formatter.formatOptions = [.withInternetDateTime, .withFractionalSeconds]
        return formatter
    }()
}
