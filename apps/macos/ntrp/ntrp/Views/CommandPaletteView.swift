import AppKit
import SwiftUI

struct CommandPaletteView: View {
    @ObservedObject var store: NtrpStore
    @ObservedObject var ui: NtrpUIState
    @State private var query = ""
    @State private var index = 0
    @State private var mode: PaletteMode = .root
    @State private var listScrolled = false
    @FocusState private var focused: Bool

    var body: some View {
        GeometryReader { geometry in
            ZStack(alignment: .top) {
                NtrpModalScrim()
                    .ignoresSafeArea()
                    .onTapGesture { ui.closePalette() }

                VStack(spacing: 0) {
                    paletteInput

                    ScrollViewReader { proxy in
                        ScrollView {
                            VStack(spacing: 0) {
                                GeometryReader { geometry in
                                    Color.clear.preference(
                                        key: PaletteScrollTopPreferenceKey.self,
                                        value: geometry.frame(in: .named("palette-scroll")).minY
                                    )
                                }
                                .frame(height: 1)
                                .padding(.bottom, -1)

                                if entries.isEmpty {
                                    Text("Nothing matches.")
                                        .font(.system(size: 14))
                                        .italic()
                                        .foregroundStyle(NtrpColors.faint)
                                        .frame(maxWidth: .infinity, minHeight: 120)
                                } else {
                                    LazyVStack(alignment: .leading, spacing: 0) {
                                        ForEach(groupedEntries, id: \.title) { group in
                                            VStack(alignment: .leading, spacing: 0) {
                                                Text(sectionLabel(group.title).uppercased())
                                                    .font(.system(size: 10, weight: .medium))
                                                    .tracking(1.0)
                                                    .foregroundStyle(NtrpColors.faint)
                                                    .padding(.horizontal, 16)
                                                    .padding(.top, 12)
                                                    .padding(.bottom, 4)
                                                VStack(spacing: 0) {
                                                    ForEach(group.entries, id: \.paletteID) { entry in
                                                        let isSelected = selectedID == entry.paletteID
                                                        PaletteRow(entry: entry, selected: isSelected)
                                                            .id(entry.paletteID)
                                                            .onHover { hovering in
                                                                if hovering, let next = entries.firstIndex(where: { $0.paletteID == entry.paletteID }) {
                                                                    index = next
                                                                }
                                                            }
                                                            .onTapGesture { run(entry) }
                                                    }
                                                }
                                                .padding(.horizontal, 6)
                                            }
                                        }
                                        .padding(.bottom, 8)
                                    }
                                }
                            }
                        }
                        .coordinateSpace(name: "palette-scroll")
                        .mask(NtrpScrollTopMask(scrolled: listScrolled))
                        .onPreferenceChange(PaletteScrollTopPreferenceKey.self) { top in
                            let next = top < -0.5
                            if listScrolled != next {
                                listScrolled = next
                            }
                        }
                        .onChange(of: selectedID) { _, id in
                            guard let id else { return }
                            withAnimation(.snappy(duration: 0.12)) {
                                proxy.scrollTo(id, anchor: .center)
                            }
                        }
                    }
                }
                .frame(width: min(660, max(320, geometry.size.width - 80)))
                .frame(maxHeight: geometry.size.height * 0.62)
                .background(NtrpColors.surfaceFill(0.48))
                .overlay(RoundedRectangle(cornerRadius: 14, style: .continuous).stroke(NtrpColors.sidebarStroke, lineWidth: 1))
                .clipShape(RoundedRectangle(cornerRadius: 14, style: .continuous))
                .shadow(color: .black.opacity(0.45), radius: 30, x: 0, y: 20)
                .ntrpGlass(cornerRadius: 14)
                .padding(.top, geometry.size.height * 0.14)
            }
        }
        .onAppear { focused = true }
        .onChange(of: query) { _, _ in index = 0 }
        .onChange(of: mode) { _, _ in
            query = ""
            index = 0
        }
        .onKeyPress(.downArrow) {
            guard !entries.isEmpty else { return .ignored }
            index = min(entries.count - 1, index + 1)
            return .handled
        }
        .onKeyPress(.upArrow) {
            guard !entries.isEmpty else { return .ignored }
            index = max(0, index - 1)
            return .handled
        }
        .onKeyPress(.escape) {
            if mode != .root {
                popMode()
                return .handled
            }
            ui.closePalette()
            return .handled
        }
        .onKeyPress(.delete) {
            guard query.isEmpty, mode != .root else { return .ignored }
            popMode()
            return .handled
        }
    }

    private var paletteInput: some View {
        HStack(spacing: 6) {
            Image(systemName: "magnifyingglass")
                .font(.system(size: 15, weight: .medium))
                .foregroundStyle(NtrpColors.faint)
                .frame(width: 18, height: 18)

            if mode != .root {
                Button {
                    popMode()
                } label: {
                    HStack(spacing: 5) {
                        Text(mode.crumbLabel)
                            .font(.system(size: 12))
                            .foregroundStyle(NtrpColors.text)
                            .lineLimit(1)
                        Image(systemName: "chevron.right")
                            .font(.system(size: 9, weight: .semibold))
                            .foregroundStyle(NtrpColors.faint)
                    }
                    .padding(.horizontal, 8)
                    .frame(height: 24)
                    .background(NtrpColors.row.opacity(0.55))
                    .clipShape(RoundedRectangle(cornerRadius: 6, style: .continuous))
                }
                .buttonStyle(.plain)
            }

            TextField(mode.placeholder, text: $query)
                .textFieldStyle(.plain)
                .font(.system(size: 16))
                .foregroundStyle(NtrpColors.text)
                .focused($focused)
                .onSubmit(runSelected)
        }
        .padding(.horizontal, 16)
        .padding(.top, 12)
        .padding(.bottom, 10)
    }

    private var selectedID: String? {
        guard entries.indices.contains(index) else { return nil }
        return entries[index].paletteID
    }

    private var entries: [PaletteEntry] {
        let needle = query.trimmingCharacters(in: .whitespacesAndNewlines).lowercased()
        let all = modeEntries
        if needle.isEmpty, mode == .root {
            let actions = all.filter { $0.section != "session" }
            let sessions = Array(all.filter { $0.section == "session" }.prefix(6))
            return sortedForVisualOrder(actions + sessions)
        }
        if needle.isEmpty {
            return sortedForVisualOrder(all)
        }
        let tokens = needle.split(whereSeparator: \.isWhitespace).map(String.init)
        return sortedForVisualOrder(all.filter { entry in
            let haystack = entry.search.lowercased()
            return tokens.allSatisfy { haystack.contains($0) }
        })
    }

    private var groupedEntries: [PaletteGroup] {
        mode.sections.compactMap { section in
            let sectionEntries = entries.filter { $0.section == section }
            guard !sectionEntries.isEmpty else { return nil }
            return PaletteGroup(title: section, entries: sectionEntries)
        }
    }

    private var modeEntries: [PaletteEntry] {
        switch mode {
        case .root:
            rootEntries
        case .modelProviders:
            modelProviderEntries
        case .models(let provider):
            modelEntries(provider: provider)
        case .archived:
            archivedEntries
        case .theme:
            themeEntries
        case .palette:
            paletteEntries
        }
    }

    private var rootEntries: [PaletteEntry] {
        var result: [PaletteEntry] = [
            PaletteEntry(id: "suggested:new-session", section: "suggested", label: "New session", icon: "pencil", shortcut: "⌘N", search: "new session create chat") {
                Task { await store.createSession() }
            },
            PaletteEntry(id: "suggested:toggle-sidebar", section: "suggested", label: ui.sidebarHidden ? "Show sidebar" : "Hide sidebar", icon: "sidebar.left", shortcut: "⌘B", search: "sidebar panel toggle hide show") {
                ui.toggleSidebar()
            },
            PaletteEntry(id: "suggested:compact", section: "suggested", label: "Compact context", icon: "sparkles", search: "compact context summarize") {
                Task { await store.compactSelectedSession() }
            },
            PaletteEntry(id: "suggested:auto-approve", section: "suggested", label: store.skipApprovals ? "Disable Auto-approve" : "Enable Auto-approve", icon: store.skipApprovals ? "shield.slash" : "checkmark.shield", hint: store.skipApprovals ? "currently on" : "", search: "auto approve approval toggle") {
                Task { await store.toggleAutoApprovals(!store.skipApprovals) }
            },
            PaletteEntry(id: "open:memory", section: "open", label: "Memory", icon: "brain", search: "memory facts observations patterns") {
                ui.activeSurface = .memory
            },
            PaletteEntry(id: "open:automations", section: "open", label: "Automations", icon: "bolt", search: "automations cron scheduled") {
                ui.activeSurface = .automations
            },
            PaletteEntry(id: "open:archive", section: "open", label: "Archived sessions", icon: "archivebox", search: "archive archived sessions") {
                ui.activeSurface = .archive
            },
            PaletteEntry(id: "open:settings", section: "open", label: "Settings", icon: "gearshape", shortcut: "⌘,", search: "settings preferences config mcp models") {
                ui.openSettings()
            },
            PaletteEntry(id: "system:reload", section: "system", label: "Reload window", icon: "arrow.clockwise", shortcut: "⌘R", search: "reload refresh restart window") {
                Task { await store.reload() }
            },
            PaletteEntry(id: "system:quit", section: "system", label: "Quit ntrp", icon: "power", shortcut: "⌘Q", search: "quit exit close app") {
                NSApp.terminate(nil)
            },
            PaletteEntry(id: "appearance:theme", section: "appearance", label: "Theme", icon: "circle.lefthalf.filled", hint: currentThemeLabel, search: "theme light dark system mode", next: .theme),
            PaletteEntry(id: "appearance:palette", section: "appearance", label: "Color palette", icon: "paintpalette", hint: currentPaletteLabel, search: "palette color warm graphite raycast notion", next: .palette)
        ]

        if !modelGroups.isEmpty {
            result.insert(
                PaletteEntry(id: "open:switch-model", section: "open", label: "Switch model", icon: "cpu", hint: shortModel(store.serverConfig?.chatModel), search: "model provider openrouter openai anthropic gemini", next: .modelProviders),
                at: 8
            )
        }

        if let sessionID = store.selectedSessionID {
            let currentName = store.sessions.first(where: { $0.sessionID == sessionID })?.name?.trimmingCharacters(in: .whitespacesAndNewlines).nilIfEmpty ?? "untitled"
            result.insert(
                PaletteEntry(id: "suggested:rename-current", section: "suggested", label: "Rename current session", icon: "pencil", hint: currentName, search: "rename session title") {
                    if let next = promptString(title: "Rename session", message: "Name", value: currentName), !next.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty {
                        Task { await store.renameSelectedSession(next) }
                    }
                },
                at: 4
            )
            result.insert(
                PaletteEntry(id: "suggested:clear-current", section: "suggested", label: "Clear session messages", icon: "eraser", search: "clear reset wipe messages") {
                    if confirm(title: "Clear all messages?", message: "This cannot be undone.") {
                        Task { await store.clearSelectedSession() }
                    }
                },
                at: 5
            )
            if let assistantID = lastAssistantID {
                result.insert(
                    PaletteEntry(id: "suggested:branch-last", section: "suggested", label: "Branch from last assistant message", icon: "arrow.triangle.branch", search: "branch fork split") {
                        Task { await store.branchAtMessage(assistantID) }
                    },
                    at: 6
                )
            }
            result.insert(
                PaletteEntry(id: "suggested:archive-session", section: "suggested", label: "Archive current session", icon: "archivebox", search: "archive current session") {
                    if confirm(title: "Archive this session?", message: "You can restore it later.") {
                        Task { await store.archiveSelectedSession() }
                    }
                },
                at: min(7, result.count)
            )
            result.insert(
                PaletteEntry(id: "suggested:copy-session-id", section: "suggested", label: "Copy session ID", icon: "doc.on.doc", hint: sessionID.prefix(8).description, search: "copy session id identifier") {
                    if let id = store.selectedSessionID {
                        NSPasteboard.general.clearContents()
                        NSPasteboard.general.setString(id, forType: .string)
                    }
                },
                at: min(8, result.count)
            )
        }

        if store.isStreaming {
            result.insert(
                PaletteEntry(id: "suggested:stop-run", section: "suggested", label: "Stop current run", icon: "stop.fill", shortcut: "Esc", search: "stop cancel halt run") {
                    Task { await store.stopCurrentRun() }
                },
                at: 0
            )
        }

        for session in store.sessions where session.sessionID != store.selectedSessionID {
            result.append(
                PaletteEntry(id: "session:\(session.sessionID)", section: "session", label: session.name?.trimmingCharacters(in: .whitespacesAndNewlines).nilIfEmpty ?? "untitled", icon: "message", hint: shortRelative(paletteSessionActivityDate(session)), search: "session \(session.name ?? "")") {
                    Task { await store.selectSession(session.sessionID) }
                }
            )
        }

        return result
    }

    private var modelProviderEntries: [PaletteEntry] {
        modelGroups.map { group in
            let provider = group.string("provider") ?? "models"
            let count = modelIDs(in: group).count
            return PaletteEntry(
                id: "provider:\(provider)",
                section: "provider",
                label: prettyProvider(provider),
                icon: providerIcon(provider),
                hint: count == 1 ? "1 model" : "\(count) models",
                search: "provider \(provider)",
                next: .models(provider)
            )
        }
    }

    private func modelEntries(provider: String) -> [PaletteEntry] {
        guard let group = modelGroups.first(where: { ($0.string("provider") ?? "models") == provider }) else { return [] }
        let current = store.serverConfig?.chatModel
        return modelIDs(in: group).map { model in
            PaletteEntry(
                id: "model:\(provider):\(model)",
                section: "model",
                label: stripProviderPrefix(model, provider: provider),
                icon: model == current ? "checkmark" : "cpu",
                hint: model == current ? "current" : "",
                search: "model \(provider) \(model)"
            ) {
                Task { await store.patchServerConfig(["chat_model": .string(model)]) }
            }
        }
    }

    private var archivedEntries: [PaletteEntry] {
        if store.archivedSessions.isEmpty {
            return [
                PaletteEntry(id: "archive:empty", section: "archive", label: "No archived sessions", icon: "archivebox", hint: "", search: "empty archive") {}
            ]
        }
        return store.archivedSessions.map { session in
            PaletteEntry(
                id: "archive:\(session.sessionID)",
                section: "archive",
                label: session.name?.trimmingCharacters(in: .whitespacesAndNewlines).nilIfEmpty ?? "untitled",
                icon: "archivebox",
                hint: shortRelative(paletteSessionActivityDate(session)),
                search: "archive archived session \(session.name ?? "")"
            ) {
                ui.activeSurface = .chat
                Task { await store.restoreArchivedSession(session.sessionID) }
            }
        }
    }

    private var themeEntries: [PaletteEntry] {
        [
            PaletteEntry(id: "theme:system", section: "theme", label: "System", icon: "display", hint: currentDefault("ntrp.theme", equals: "system", fallback: "system"), search: "theme system") {
                UserDefaults.standard.set("system", forKey: "ntrp.theme")
            },
            PaletteEntry(id: "theme:light", section: "theme", label: "Light", icon: "sun.max", hint: currentDefault("ntrp.theme", equals: "light", fallback: "system"), search: "theme light") {
                UserDefaults.standard.set("light", forKey: "ntrp.theme")
            },
            PaletteEntry(id: "theme:dark", section: "theme", label: "Dark", icon: "moon", hint: currentDefault("ntrp.theme", equals: "dark", fallback: "system"), search: "theme dark") {
                UserDefaults.standard.set("dark", forKey: "ntrp.theme")
            }
        ]
    }

    private var paletteEntries: [PaletteEntry] {
        [
            ("warm", "Warm"),
            ("graphite", "Graphite"),
            ("raycast", "Raycast"),
            ("notion", "Notion")
        ].map { id, label in
            PaletteEntry(id: "palette:\(id)", section: "palette", label: label, icon: "circle.fill", hint: currentDefault("ntrp.palette", equals: id, fallback: "graphite"), search: "palette color \(id) \(label)") {
                UserDefaults.standard.set(id, forKey: "ntrp.palette")
            }
        }
    }

    private var modelGroups: [[String: JSONValue]] {
        guard let source = store.serverModels?.value(for: "groups")?.arrayValue, !source.isEmpty else {
            let models = store.serverModels?.value(for: "models")?.arrayValue ?? []
            guard !models.isEmpty else { return [] }
            return [["provider": .string("all"), "models": .array(models)]]
        }
        return source.compactMap(\.objectValue)
    }

    private func modelIDs(in group: [String: JSONValue]) -> [String] {
        group.array("models").compactMap { value in
            if let id = value.stringValue { return id }
            return value.objectValue?.string("id")
        }
    }

    private var currentThemeLabel: String {
        switch UserDefaults.standard.string(forKey: "ntrp.theme") ?? "system" {
        case "light": "Light"
        case "dark": "Dark"
        default: "System"
        }
    }

    private var currentPaletteLabel: String {
        switch UserDefaults.standard.string(forKey: "ntrp.palette") ?? "graphite" {
        case "warm": "Warm"
        case "raycast": "Raycast"
        case "notion": "Notion"
        default: "Graphite"
        }
    }

    private var lastAssistantID: String? {
        store.messages.reversed().first { $0.role == .assistant }?.id
    }

    private func runSelected() {
        guard entries.indices.contains(index) else { return }
        run(entries[index])
    }

    private func run(_ entry: PaletteEntry) {
        if let next = entry.next {
            mode = next
            return
        }
        ui.closePalette()
        entry.run?()
    }

    private func popMode() {
        switch mode {
        case .models:
            mode = .modelProviders
        default:
            mode = .root
        }
    }

    private func sortedForVisualOrder<S: Sequence>(_ source: S) -> [PaletteEntry] where S.Element == PaletteEntry {
        let sectionRank = Dictionary(uniqueKeysWithValues: mode.sections.enumerated().map { ($1, $0) })
        return source.enumerated()
            .sorted { left, right in
                let leftRank = sectionRank[left.element.section] ?? mode.sections.count
                let rightRank = sectionRank[right.element.section] ?? mode.sections.count
                return leftRank == rightRank ? left.offset < right.offset : leftRank < rightRank
            }
            .map(\.element)
    }
}

private enum PaletteMode: Equatable {
    case root
    case modelProviders
    case models(String)
    case archived
    case theme
    case palette

    var placeholder: String {
        switch self {
        case .root: "Search commands, sessions, memory..."
        case .modelProviders: "Filter providers..."
        case .models(let provider): "Filter \(prettyProvider(provider)) models..."
        case .archived: "Search archived sessions..."
        case .theme: "Choose theme..."
        case .palette: "Choose palette..."
        }
    }

    var crumbLabel: String {
        switch self {
        case .root: ""
        case .modelProviders: "Switch model"
        case .models(let provider): prettyProvider(provider)
        case .archived: "Archived sessions"
        case .theme: "Theme"
        case .palette: "Color palette"
        }
    }

    var sections: [String] {
        switch self {
        case .root: ["suggested", "open", "appearance", "session", "system"]
        case .modelProviders: ["provider"]
        case .models: ["model"]
        case .archived: ["archive"]
        case .theme: ["theme"]
        case .palette: ["palette"]
        }
    }
}

private struct PaletteGroup {
    let title: String
    let entries: [PaletteEntry]
}

private struct PaletteScrollTopPreferenceKey: PreferenceKey {
    static var defaultValue: CGFloat = 0

    static func reduce(value: inout CGFloat, nextValue: () -> CGFloat) {
        value = nextValue()
    }
}

private struct PaletteEntry: Identifiable {
    let paletteID: String
    let section: String
    let label: String
    let icon: String
    var shortcut = ""
    var hint = ""
    var search = ""
    var next: PaletteMode?
    let run: (() -> Void)?

    var id: String { paletteID }

    init(
        id: String,
        section: String,
        label: String,
        icon: String,
        shortcut: String = "",
        hint: String = "",
        search: String = "",
        next: PaletteMode? = nil,
        run: (() -> Void)? = nil
    ) {
        self.paletteID = id
        self.section = section
        self.label = label
        self.icon = icon
        self.shortcut = shortcut
        self.hint = hint
        self.search = search
        self.next = next
        self.run = run
    }
}

private struct PaletteRow: View {
    let entry: PaletteEntry
    let selected: Bool

    var body: some View {
        HStack(spacing: 10) {
            Image(systemName: entry.icon)
                .font(.system(size: 14, weight: .medium))
                .foregroundStyle(selected ? NtrpColors.accent : NtrpColors.muted)
                .frame(width: 20, height: 20)
                .background(selected ? NtrpColors.accent.opacity(0.14) : Color.clear)
                .clipShape(RoundedRectangle(cornerRadius: 6, style: .continuous))
            Text(entry.label)
                .font(.system(size: 16, weight: .regular))
                .foregroundStyle(NtrpColors.text)
                .lineLimit(1)
            Spacer(minLength: 8)
            if !entry.hint.isEmpty {
                Text(entry.hint)
                    .font(.system(size: 12))
                    .foregroundStyle(NtrpColors.faint)
                    .lineLimit(1)
            }
            if !entry.shortcut.isEmpty {
                Text(entry.shortcut)
                    .font(.system(size: 12, weight: .medium, design: .monospaced))
                    .foregroundStyle(NtrpColors.faint)
            }
            if entry.next != nil {
                Image(systemName: "chevron.right")
                    .font(.system(size: 10, weight: .semibold))
                    .foregroundStyle(NtrpColors.faint)
            }
        }
        .padding(.horizontal, 10)
        .padding(.vertical, 6)
        .background(selected ? NtrpColors.rowActive : Color.clear)
        .overlay(
            RoundedRectangle(cornerRadius: 8, style: .continuous)
                .stroke(selected ? NtrpColors.rowActiveStroke : Color.clear, lineWidth: 1)
        )
        .clipShape(RoundedRectangle(cornerRadius: 8, style: .continuous))
        .contentShape(Rectangle())
    }
}

private func shortRelative(_ date: Date?) -> String {
    guard let date else { return "" }
    let seconds = max(0, Int(Date().timeIntervalSince(date)))
    if seconds < 60 { return "\(seconds)s" }
    let minutes = seconds / 60
    if minutes < 60 { return "\(minutes)m" }
    let hours = minutes / 60
    if hours < 48 { return "\(hours)h" }
    return "\(hours / 24)d"
}

private let paletteDateFormatter = ISO8601DateFormatter()

private func paletteSessionActivityDate(_ session: SessionListItem) -> Date? {
    paletteDateFormatter.date(from: session.lastActivity)
        ?? paletteDateFormatter.date(from: session.startedAt)
}

private func currentDefault(_ key: String, equals value: String, fallback: String) -> String {
    (UserDefaults.standard.string(forKey: key) ?? fallback) == value ? "current" : ""
}

private func shortModel(_ model: String?) -> String {
    guard let model, !model.isEmpty else { return "" }
    return model
        .replacingOccurrences(of: "openai/", with: "")
        .replacingOccurrences(of: "anthropic/", with: "")
        .replacingOccurrences(of: "google/", with: "")
}

private func providerIcon(_ provider: String) -> String {
    switch provider.lowercased() {
    case "openai":
        return "sparkles"
    case "anthropic":
        return "text.bubble"
    case "gemini", "google":
        return "diamond"
    case "openrouter":
        return "arrow.triangle.swap"
    default:
        return "cpu"
    }
}

private func prettyProvider(_ provider: String) -> String {
    if provider.isEmpty { return "Unknown" }
    if provider == "openai" { return "OpenAI" }
    return provider.prefix(1).uppercased() + provider.dropFirst()
}

private func stripProviderPrefix(_ model: String, provider: String) -> String {
    let prefix = "\(provider)/"
    return model.hasPrefix(prefix) ? String(model.dropFirst(prefix.count)) : model
}

private func sectionLabel(_ section: String) -> String {
    switch section {
    case "suggested": "Suggested"
    case "open": "Navigation"
    case "appearance": "Appearance"
    case "session": "Sessions"
    case "system": "System"
    case "provider": "Providers"
    case "model": "Models"
    default: section
    }
}

private func confirm(title: String, message: String) -> Bool {
    let alert = NSAlert()
    alert.messageText = title
    alert.informativeText = message
    alert.addButton(withTitle: "Confirm")
    alert.addButton(withTitle: "Cancel")
    return alert.runModal() == .alertFirstButtonReturn
}

private func promptString(title: String, message: String, value: String) -> String? {
    let alert = NSAlert()
    alert.messageText = title
    alert.informativeText = message
    let field = NSTextField(string: value)
    field.frame = NSRect(x: 0, y: 0, width: 260, height: 24)
    alert.accessoryView = field
    alert.addButton(withTitle: "Save")
    alert.addButton(withTitle: "Cancel")
    return alert.runModal() == .alertFirstButtonReturn ? field.stringValue : nil
}

private extension String {
    var nilIfEmpty: String? {
        isEmpty ? nil : self
    }
}
