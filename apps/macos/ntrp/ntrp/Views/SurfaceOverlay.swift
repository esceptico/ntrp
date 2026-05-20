import SwiftUI

struct SurfaceOverlay: View {
    @ObservedObject var store: NtrpStore
    let title: String
    let paths: [String]
    var onClose: (() -> Void)?

    @Environment(\.dismiss) private var dismiss
    @StateObject private var surface = SurfaceStore()
    @State private var automationTab: AutomationTab = .active
    @State private var automationEditor: AutomationEditorSeed?
    @State private var memoryTab: MemoryTab = .search
    @State private var recallQuery = ""
    @State private var recallResult: JSONValue?
    @State private var showPromptContext = false
    @State private var pruneResult: JSONValue?
    @State private var sentQuery = ""
    @State private var selectedSentID: String?
    @State private var factQuery = ""
    @State private var selectedFactID: String?
    @State private var patternQuery = ""
    @State private var selectedPatternID: String?

    var body: some View {
        ZStack {
            VStack(spacing: 0) {
                header
                    .padding(.horizontal, 22)
                    .padding(.top, 18)
                    .padding(.bottom, 12)

                if title == "Automations" {
                    automationTabs
                    automationBody
                } else if title == "Memory" {
                memoryTabs
                    memoryBody
                } else {
                    fallbackBody
                }
            }

            if let automationEditor {
                AutomationEditorOverlay(
                    seed: automationEditor,
                    save: saveAutomation,
                    close: { self.automationEditor = nil }
                )
                .id(automationEditor.id)
                .zIndex(20)
            }
        }
        .frame(maxWidth: .infinity, maxHeight: .infinity)
        .background(NtrpColors.canvas)
        .foregroundStyle(NtrpColors.text)
        .task {
            await surface.reload(config: store.config, sessionID: store.selectedSessionID)
            if title == "Memory" {
                await surface.loadMemoryAccess(config: store.config)
                selectedSentID = surface.memoryAccessEvents.first?.objectValue?["id"]?.display
            }
        }
    }

    private var header: some View {
        HStack(spacing: 12) {
            Text(title)
                .font(.system(size: 20, weight: .semibold))
            Spacer()
            if title == "Automations" {
                Button {
                    automationEditor = .create(nil)
                } label: {
                    Label("New", systemImage: "plus")
                        .font(.system(size: 13, weight: .medium))
                        .foregroundStyle(Color.black.opacity(0.86))
                        .padding(.horizontal, 10)
                        .frame(height: 28)
                        .background(NtrpColors.text)
                        .clipShape(RoundedRectangle(cornerRadius: 7, style: .continuous))
                }
                .buttonStyle(.plain)
            }
            Button {
                if let onClose {
                    onClose()
                } else {
                    dismiss()
                }
            } label: {
                Image(systemName: "xmark")
                    .font(.system(size: 13, weight: .semibold))
                    .foregroundStyle(NtrpColors.muted)
                    .frame(width: 28, height: 28)
            }
            .buttonStyle(.plain)
        }
    }

    private var automationTabs: some View {
        HStack(spacing: 20) {
            ForEach(AutomationTab.allCases) { tab in
                tabButton(
                    title: tab.title,
                    count: tab == .templates ? nil : automationCount(for: tab),
                    active: automationTab == tab
                ) {
                    automationTab = tab
                }
            }
            Spacer()
        }
        .padding(.horizontal, 22)
        .padding(.bottom, 8)
    }

    private var automationBody: some View {
        ScrollView {
            switch automationTab {
            case .active:
                automationGrid(items: automationGroups.user, emptyTitle: "No automations yet.", emptyDetail: "Start from a template, or write a prompt and a schedule from scratch.")
            case .channels:
                automationGrid(items: automationGroups.channels, emptyTitle: "No channels yet.", emptyDetail: "Channels are post-mode loops that emit to a dedicated session each tick.")
            case .internal:
                automationGrid(items: automationGroups.internalItems, emptyTitle: "No internal automations.", emptyDetail: "Internal memory maintenance tasks will appear here when available.")
            case .templates:
                templatesGrid
            }
        }
        .padding(.horizontal, 22)
        .padding(.vertical, 14)
    }

    private func automationGrid(items: [JSONValue], emptyTitle: String, emptyDetail: String) -> some View {
        Group {
            if surface.isLoading && items.isEmpty {
                Text("Loading...")
                    .font(.system(size: 14))
                    .foregroundStyle(NtrpColors.faint)
                    .frame(maxWidth: .infinity, alignment: .leading)
            } else if items.isEmpty {
                if automationTab == .active {
                    automationEmptyState(title: emptyTitle, detail: emptyDetail)
                } else {
                    emptyState(title: emptyTitle, detail: emptyDetail)
                }
            } else {
                LazyVGrid(columns: [GridItem(.adaptive(minimum: 280), spacing: 10)], spacing: 10) {
                    ForEach(items) { item in
                        AutomationCard(
                            item: item,
                            edit: {
                                if item.objectValue?.bool("builtin") != true {
                                    automationEditor = .edit(item)
                                }
                            },
                            run: { taskID in
                                Task {
                                    await surface.runAutomation(config: store.config, taskID: taskID)
                                    await surface.reload(config: store.config, sessionID: store.selectedSessionID)
                                }
                            },
                            toggle: { taskID in
                                Task {
                                    await surface.toggleAutomation(config: store.config, taskID: taskID)
                                    await surface.reload(config: store.config, sessionID: store.selectedSessionID)
                                }
                            },
                            delete: { taskID in
                                Task {
                                    await surface.deleteAutomation(config: store.config, taskID: taskID)
                                    await surface.reload(config: store.config, sessionID: store.selectedSessionID)
                                }
                            }
                        )
                    }
                }
            }
        }
    }

    private var templatesGrid: some View {
        VStack(alignment: .leading, spacing: 24) {
            ForEach(AutomationTemplate.groups, id: \.category) { group in
                VStack(alignment: .leading, spacing: 10) {
                    Text(group.category)
                        .font(.system(size: 12, weight: .medium))
                        .tracking(1.0)
                        .foregroundStyle(NtrpColors.faint)
                    LazyVGrid(columns: [GridItem(.adaptive(minimum: 280), spacing: 10)], spacing: 10) {
                        ForEach(group.items) { template in
                            TemplateCard(template: template) {
                                automationEditor = .create(template.draft)
                            }
                        }
                    }
                }
            }
        }
    }

    private var memoryTabs: some View {
        HStack(spacing: 20) {
            ForEach(MemoryTab.allCases) { tab in
                tabButton(title: tab.title, active: memoryTab == tab) {
                    memoryTab = tab
                }
            }
            Spacer()
        }
        .padding(.horizontal, 22)
        .padding(.bottom, 8)
    }

    private var memoryBody: some View {
        Group {
            if memoryTab == .facts {
                MemoryEntityPane(
                    kind: .facts,
                    items: surface.facts,
                    query: $factQuery,
                    selectedID: $selectedFactID,
                    saveText: { id, text in
                        await surface.updateFact(config: store.config, id: id, text: text)
                        await surface.reload(config: store.config, sessionID: store.selectedSessionID)
                    },
                    replaceText: { id, text in
                        await surface.supersedeFact(config: store.config, id: id, text: text)
                        await surface.reload(config: store.config, sessionID: store.selectedSessionID)
                    },
                    archive: { id, archived in
                        await surface.setFactArchived(config: store.config, id: id, archived: archived)
                        await surface.reload(config: store.config, sessionID: store.selectedSessionID)
                    },
                    delete: nil
                )
                .padding(.horizontal, 22)
                .padding(.vertical, 14)
            } else if memoryTab == .patterns {
                MemoryEntityPane(
                    kind: .patterns,
                    items: surface.observations,
                    query: $patternQuery,
                    selectedID: $selectedPatternID,
                    saveText: { id, text in
                        await surface.updateObservation(config: store.config, id: id, summary: text)
                        await surface.reload(config: store.config, sessionID: store.selectedSessionID)
                    },
                    replaceText: nil,
                    archive: nil,
                    delete: { id in
                        await surface.deleteObservation(config: store.config, id: id)
                        selectedPatternID = nil
                        await surface.reload(config: store.config, sessionID: store.selectedSessionID)
                    }
                )
                .padding(.horizontal, 22)
                .padding(.vertical, 14)
            } else {
                ScrollView {
                    switch memoryTab {
                    case .search:
                        recallPane
                    case .facts, .patterns:
                        EmptyView()
                    case .sent:
                        memorySentPane
                    case .cleanup:
                        memoryCleanupPane
                    case .audit:
                        MemoryAuditPane(audit: surface.memoryAudit, stats: surface.memoryStats)
                    }
                }
                .padding(.horizontal, 22)
                .padding(.vertical, 14)
            }
        }
    }

    private var recallPane: some View {
        VStack(alignment: .leading, spacing: 12) {
            HStack(spacing: 8) {
                TextField("Ask what memory would retrieve for a query", text: $recallQuery)
                    .textFieldStyle(.plain)
                    .font(.system(size: 14))
                    .foregroundStyle(NtrpColors.text)
                    .padding(.horizontal, 12)
                    .frame(height: 36)
                    .background(NtrpColors.row.opacity(0.34))
                    .clipShape(RoundedRectangle(cornerRadius: 9, style: .continuous))
                Button("Inspect") {
                    Task {
                        recallResult = await surface.inspectRecall(config: store.config, query: recallQuery)
                        showPromptContext = false
                    }
                }
                .disabled(recallQuery.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty)
            }
            Text("Preview the exact memory context before it reaches a prompt.")
                .font(.system(size: 13))
                .foregroundStyle(NtrpColors.faint)
            RecallResultPane(result: recallResult, showPromptContext: $showPromptContext)
        }
    }

    private var memorySentPane: some View {
        MemorySentPane(
            events: surface.memoryAccessEvents,
            facts: surface.memoryAccessFacts,
            observations: surface.memoryAccessObservations,
            query: $sentQuery,
            selectedID: $selectedSentID
        )
        .task {
            if surface.memoryAccessEvents.isEmpty {
                await surface.loadMemoryAccess(config: store.config)
                selectedSentID = surface.memoryAccessEvents.first?.objectValue?["id"]?.display
            }
        }
    }

    private var memoryCleanupPane: some View {
        VStack(alignment: .leading, spacing: 14) {
            HStack(spacing: 8) {
                Button("Dry run") {
                    Task { pruneResult = await surface.pruneDryRun(config: store.config, bodyText: "{}") }
                }
                .buttonStyle(.plain)
                .font(.system(size: 13, weight: .medium))
                .foregroundStyle(NtrpColors.text)
                .padding(.horizontal, 12)
                .frame(height: 32)
                .background(NtrpColors.row.opacity(0.42))
                .overlay(RoundedRectangle(cornerRadius: 8, style: .continuous).stroke(NtrpColors.sidebarStroke, lineWidth: 1))
                .clipShape(RoundedRectangle(cornerRadius: 8, style: .continuous))

                Button("Apply prune") {
                    Task {
                        pruneResult = await surface.pruneApply(config: store.config, bodyText: "{}")
                        await surface.reload(config: store.config, sessionID: store.selectedSessionID)
                    }
                }
                .buttonStyle(.plain)
                .font(.system(size: 13, weight: .medium))
                .foregroundStyle(Color.red.opacity(0.86))
                .padding(.horizontal, 12)
                .frame(height: 32)
                .background(Color.red.opacity(0.08))
                .clipShape(RoundedRectangle(cornerRadius: 8, style: .continuous))
            }

            MemoryPruneResultPane(result: pruneResult)
        }
    }

    private var fallbackBody: some View {
        VStack(alignment: .leading, spacing: 10) {
            ForEach(paths, id: \.self) { path in
                Text(path)
                    .font(.system(size: 12, weight: .medium, design: .monospaced))
                    .foregroundStyle(NtrpColors.faint)
            }
        }
        .padding(22)
    }

    private func emptyState(title: String, detail: String) -> some View {
        VStack(alignment: .leading, spacing: 7) {
            Text(title)
                .font(.system(size: 16, weight: .medium))
                .foregroundStyle(NtrpColors.text)
            if !detail.isEmpty {
                Text(detail)
                    .font(.system(size: 14))
                    .lineSpacing(3)
                    .foregroundStyle(NtrpColors.muted)
            }
        }
        .frame(maxWidth: 420, alignment: .leading)
        .padding(.vertical, 28)
    }

    private func automationEmptyState(title: String, detail: String) -> some View {
        VStack(alignment: .leading, spacing: 8) {
            emptyState(title: title, detail: detail)
                .padding(.vertical, 0)
            HStack(spacing: 8) {
                Button("Browse templates") {
                    automationTab = .templates
                }
                .buttonStyle(.plain)
                .font(.system(size: 13, weight: .medium))
                .foregroundStyle(NtrpColors.text)
                .padding(.horizontal, 12)
                .frame(height: 32)
                .background(NtrpColors.row.opacity(0.42))
                .overlay(RoundedRectangle(cornerRadius: 8, style: .continuous).stroke(NtrpColors.sidebarStroke, lineWidth: 1))
                .clipShape(RoundedRectangle(cornerRadius: 8, style: .continuous))

                Button("Start from scratch") {
                    automationEditor = .create(nil)
                }
                .buttonStyle(.plain)
                .font(.system(size: 13, weight: .medium))
                .foregroundStyle(NtrpColors.muted)
                .frame(height: 32)
            }
        }
        .padding(.vertical, 28)
    }

    private func saveAutomation(_ seed: AutomationEditorSeed, _ draft: AutomationDraft) async -> String? {
        let payload = draft.payloadText()
        switch seed {
        case .create:
            if await surface.createAutomation(config: store.config, bodyText: payload) == nil {
                return surface.errorMessage ?? "Couldn't create automation."
            }
        case .edit(let item):
            guard let taskID = item.objectValue?.string("task_id"), !taskID.isEmpty else {
                return "Missing task id."
            }
            if await surface.updateAutomation(config: store.config, taskID: taskID, bodyText: payload) == nil {
                return surface.errorMessage ?? "Couldn't save automation."
            }
        }
        await surface.reload(config: store.config, sessionID: store.selectedSessionID)
        automationEditor = nil
        return nil
    }

    private func tabButton(title: String, count: Int? = nil, active: Bool, action: @escaping () -> Void) -> some View {
        Button(action: action) {
            HStack(spacing: 6) {
                Text(title)
                if let count, count > 0 {
                    Text("\(count)")
                        .font(.system(size: 10, weight: .medium))
                        .foregroundStyle(active ? Color.black.opacity(0.82) : NtrpColors.muted)
                        .padding(.horizontal, 7)
                        .frame(height: 18)
                        .background(active ? NtrpColors.text : NtrpColors.row)
                        .clipShape(Capsule())
                }
            }
            .font(.system(size: 15, weight: .medium))
            .foregroundStyle(active ? NtrpColors.text : NtrpColors.muted)
            .overlay(alignment: .bottom) {
                if active {
                    Capsule()
                        .fill(NtrpColors.text)
                        .frame(height: 2)
                        .offset(y: 8)
                }
            }
        }
        .buttonStyle(.plain)
        .frame(height: 34)
    }

    private func automationCount(for tab: AutomationTab) -> Int {
        switch tab {
        case .active: automationGroups.user.count
        case .channels: automationGroups.channels.count
        case .internal: automationGroups.internalItems.count
        case .templates: 0
        }
    }

    private var automationGroups: AutomationGroups {
        var user: [JSONValue] = []
        var internalItems: [JSONValue] = []
        var channels: [JSONValue] = []
        for item in surface.automations {
            guard let object = item.objectValue else { continue }
            if object.string("kind") == "loop", object.bool("read_history") != false {
                continue
            }
            if object.string("kind") == "loop", object.bool("read_history") == false {
                channels.append(item)
            } else if object.bool("builtin") == true || Self.internalHandlers.contains(object.string("handler") ?? "") {
                internalItems.append(item)
            } else {
                user.append(item)
            }
        }
        return AutomationGroups(user: user, internalItems: internalItems, channels: channels)
    }

    private static let internalHandlers: Set<String> = ["knowledge_reflection", "knowledge_retention", "knowledge_health"]
}

private struct AutomationGroups {
    let user: [JSONValue]
    let internalItems: [JSONValue]
    let channels: [JSONValue]
}

private enum AutomationTab: String, CaseIterable, Identifiable {
    case active
    case channels
    case `internal`
    case templates

    var id: String { rawValue }
    var title: String {
        switch self {
        case .active: "Active"
        case .channels: "Channels"
        case .internal: "Internal"
        case .templates: "Templates"
        }
    }
}

private enum MemoryTab: String, CaseIterable, Identifiable {
    case search
    case facts
    case patterns
    case sent
    case cleanup
    case audit

    var id: String { rawValue }
    var title: String {
        switch self {
        case .search: "Search"
        case .facts: "Facts"
        case .patterns: "Patterns"
        case .sent: "Sent"
        case .cleanup: "Cleanup"
        case .audit: "Audit"
        }
    }
}

private enum AutomationEditorSeed: Identifiable {
    case create(AutomationDraft?)
    case edit(JSONValue)

    var id: String {
        switch self {
        case .create(let draft):
            "create-\(draft?.name ?? "blank")-\(draft?.description.count ?? 0)"
        case .edit(let value):
            "edit-\(value.objectValue?.string("task_id") ?? value.id)"
        }
    }

    var initialDraft: AutomationDraft {
        switch self {
        case .create(let draft):
            draft ?? AutomationDraft()
        case .edit(let value):
            AutomationDraft(value: value)
        }
    }

    var isEdit: Bool {
        if case .edit = self { return true }
        return false
    }
}

private enum AutomationScheduleKind: String, CaseIterable, Identifiable {
    case at
    case every
    case event

    var id: String { rawValue }
    var title: String {
        switch self {
        case .at: "At time"
        case .every: "Every"
        case .event: "On event"
        }
    }
}

private enum AutomationEventType: String, CaseIterable, Identifiable {
    case starts
    case ends
    case approaching

    var id: String { rawValue }
}

private struct AutomationSchedule {
    var kind: AutomationScheduleKind = .at
    var at = "09:00"
    var every = "30m"
    var days = "daily"
    var start = ""
    var end = ""
    var event: AutomationEventType = .approaching
    var lead = "15"
}

private struct AutomationDraft: Identifiable {
    var id = UUID()
    var name = ""
    var description = ""
    var schedule = AutomationSchedule()
    var writable = false

    init() {}

    init(value: JSONValue) {
        let object = value.objectValue ?? [:]
        name = object.string("name") ?? ""
        description = object.string("description") ?? ""
        writable = object.bool("writable") ?? false
        guard let trigger = object.array("triggers").first?.objectValue else { return }
        if trigger.string("type") == "event" {
            schedule.kind = .event
            schedule.event = AutomationEventType(rawValue: trigger.string("event_type") ?? "") ?? .approaching
            if let lead = trigger["lead_minutes"]?.display {
                schedule.lead = lead
            }
        } else if let every = trigger.string("every") {
            schedule.kind = .every
            schedule.every = every
            schedule.days = trigger.string("days") ?? ""
            schedule.start = trigger.string("start") ?? ""
            schedule.end = trigger.string("end") ?? ""
        } else if let at = trigger.string("at") {
            schedule.kind = .at
            schedule.at = at
            schedule.days = trigger.string("days") ?? ""
        }
    }

    init(name: String, description: String, schedule: AutomationSchedule, writable: Bool = false) {
        self.name = name
        self.description = description
        self.schedule = schedule
        self.writable = writable
    }

    var valid: Bool {
        !description.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty
    }

    func payloadText() -> String {
        var object: [String: JSONValue] = [
            "name": .string(name.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty ? "Untitled automation" : name.trimmingCharacters(in: .whitespacesAndNewlines)),
            "description": .string(description.trimmingCharacters(in: .whitespacesAndNewlines)),
            "writable": .bool(writable),
        ]
        switch schedule.kind {
        case .at:
            object["trigger_type"] = .string("time")
            object["at"] = .string(schedule.at)
            if !schedule.days.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty {
                object["days"] = .string(schedule.days.trimmingCharacters(in: .whitespacesAndNewlines))
            }
        case .every:
            object["trigger_type"] = .string("time")
            object["every"] = .string(schedule.every)
            if !schedule.days.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty {
                object["days"] = .string(schedule.days.trimmingCharacters(in: .whitespacesAndNewlines))
            }
            if !schedule.start.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty {
                object["start"] = .string(schedule.start.trimmingCharacters(in: .whitespacesAndNewlines))
            }
            if !schedule.end.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty {
                object["end"] = .string(schedule.end.trimmingCharacters(in: .whitespacesAndNewlines))
            }
        case .event:
            object["trigger_type"] = .string("event")
            object["event_type"] = .string(schedule.event.rawValue)
            if !schedule.lead.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty {
                object["lead_minutes"] = .string(schedule.lead.trimmingCharacters(in: .whitespacesAndNewlines))
            }
        }
        return JSONValue.object(object).prettyPrinted()
    }
}

private struct AutomationTemplate: Identifiable {
    let id: String
    let category: String
    let icon: String
    let name: String
    let blurb: String
    let draft: AutomationDraft

    static let all: [AutomationTemplate] = [
        .init(
            id: "daily-standup",
            category: "Status reports",
            icon: "briefcase",
            name: "Daily standup",
            blurb: "Open tasks, blockers, and what to ship today.",
            draft: .init(
                name: "Daily standup",
                description: "Pull my open tasks and highlight blockers. Suggest the two or three things I should ship today, in priority order. Quote PR titles / numbers verbatim when relevant.",
                schedule: .init(kind: .at, at: "09:00", days: "weekdays")
            )
        ),
        .init(
            id: "weekly-pr",
            category: "Status reports",
            icon: "arrow.triangle.pull",
            name: "Weekly PR summary",
            blurb: "Last week's PRs grouped by teammate and theme.",
            draft: .init(
                name: "Weekly PR summary",
                description: "Summarize last week's PRs by teammate and theme. Highlight risky merges or anything still in review. Use PR numbers / titles when available.",
                schedule: .init(kind: .at, at: "09:00", days: "Mon")
            )
        ),
        .init(
            id: "stale-sweep",
            category: "Cleanup",
            icon: "doc.text.magnifyingglass",
            name: "Stale issues sweep",
            blurb: "Top 10 issues with no activity in 14+ days.",
            draft: .init(
                name: "Stale issues sweep",
                description: "Find issues older than 14 days with no activity. Surface the top ten with brief context for why they may have stalled.",
                schedule: .init(kind: .at, at: "16:00", days: "Fri")
            )
        ),
        .init(
            id: "inbox-triage",
            category: "Inbox",
            icon: "tray",
            name: "Inbox triage",
            blurb: "Buckets unread email by priority.",
            draft: .init(
                name: "Inbox triage",
                description: "Triage my unread email since yesterday. Bucket by priority (urgent / today / this week / fyi). Quote the first sentence of each so I can scan fast.",
                schedule: .init(kind: .at, at: "08:00", days: "weekdays")
            )
        ),
        .init(
            id: "calendar-prep",
            category: "Calendar",
            icon: "envelope",
            name: "Meeting prep",
            blurb: "Brief me 15 minutes before each meeting.",
            draft: .init(
                name: "Meeting prep",
                description: "Brief me on the upcoming meeting: who's there, the agenda, and recent context I should walk in with.",
                schedule: .init(kind: .event, event: .approaching, lead: "15")
            )
        ),
    ]

    static var groups: [(category: String, items: [AutomationTemplate])] {
        var order: [String] = []
        var grouped: [String: [AutomationTemplate]] = [:]
        for item in all {
            if grouped[item.category] == nil {
                order.append(item.category)
                grouped[item.category] = []
            }
            grouped[item.category]?.append(item)
        }
        return order.map { ($0, grouped[$0] ?? []) }
    }
}

private struct AutomationEditorOverlay: View {
    let seed: AutomationEditorSeed
    let save: (AutomationEditorSeed, AutomationDraft) async -> String?
    let close: () -> Void

    @State private var draft: AutomationDraft
    @State private var saving = false
    @State private var error: String?

    init(seed: AutomationEditorSeed, save: @escaping (AutomationEditorSeed, AutomationDraft) async -> String?, close: @escaping () -> Void) {
        self.seed = seed
        self.save = save
        self.close = close
        _draft = State(initialValue: seed.initialDraft)
    }

    var body: some View {
        ZStack {
            NtrpModalScrim()
                .ignoresSafeArea()
                .onTapGesture { close() }

            VStack(spacing: 0) {
                header
                    .padding(.horizontal, 20)
                    .padding(.top, 16)
                    .padding(.bottom, 8)

                TextEditor(text: $draft.description)
                    .font(.system(size: 15))
                    .foregroundStyle(NtrpColors.text)
                    .scrollContentBackground(.hidden)
                    .background(Color.clear)
                    .padding(.horizontal, 16)
                    .frame(minHeight: 180)
                    .overlay(alignment: .topLeading) {
                        if draft.description.isEmpty {
                            Text("What should the agent do when this automation fires?")
                                .font(.system(size: 15))
                                .foregroundStyle(NtrpColors.faint)
                                .padding(.horizontal, 21)
                                .padding(.vertical, 9)
                                .allowsHitTesting(false)
                        }
                    }

                schedulePane
                    .padding(.horizontal, 20)
                    .padding(.top, 8)
                    .padding(.bottom, 12)

                if let error {
                    AutomationEditorError(message: error)
                        .padding(.horizontal, 20)
                        .padding(.bottom, 12)
                }

                footer
                    .padding(.horizontal, 12)
                    .padding(.vertical, 10)
                    .background(NtrpColors.row.opacity(0.22))
            }
            .frame(width: 640)
            .frame(maxHeight: 560)
            .background(NtrpColors.surfaceFill(0.58))
            .overlay(RoundedRectangle(cornerRadius: 16, style: .continuous).stroke(NtrpColors.sidebarStroke, lineWidth: 1))
            .clipShape(RoundedRectangle(cornerRadius: 16, style: .continuous))
            .shadow(color: .black.opacity(0.44), radius: 30, x: 0, y: 18)
            .ntrpGlass(cornerRadius: 16, interactive: true)
        }
    }

    private var header: some View {
        HStack(spacing: 8) {
            TextField("Untitled automation", text: $draft.name)
                .textFieldStyle(.plain)
                .font(.system(size: 18, weight: .semibold))
                .foregroundStyle(NtrpColors.text)
            Spacer(minLength: 10)
            iconButton("arrow.counterclockwise", help: "Reset") {
                draft = seed.initialDraft
                error = nil
            }
            iconButton("xmark", help: "Close", action: close)
        }
    }

    private var schedulePane: some View {
        VStack(alignment: .leading, spacing: 10) {
            Picker("", selection: $draft.schedule.kind) {
                ForEach(AutomationScheduleKind.allCases) { kind in
                    Text(kind.title).tag(kind)
                }
            }
            .pickerStyle(.segmented)
            .labelsHidden()
            .frame(width: 300)

            switch draft.schedule.kind {
            case .at:
                HStack(spacing: 8) {
                    scheduleField("At", text: $draft.schedule.at, placeholder: "09:00")
                    scheduleField("Days", text: $draft.schedule.days, placeholder: "daily")
                }
            case .every:
                HStack(spacing: 8) {
                    scheduleField("Interval", text: $draft.schedule.every, placeholder: "30m")
                    scheduleField("Days", text: $draft.schedule.days, placeholder: "weekdays")
                    scheduleField("Start", text: $draft.schedule.start, placeholder: "09:00")
                    scheduleField("End", text: $draft.schedule.end, placeholder: "17:00")
                }
            case .event:
                HStack(spacing: 8) {
                    Picker("Event", selection: $draft.schedule.event) {
                        ForEach(AutomationEventType.allCases) { event in
                            Text(event.rawValue).tag(event)
                        }
                    }
                    .frame(width: 160)
                    if draft.schedule.event == .approaching {
                        scheduleField("Lead (m)", text: $draft.schedule.lead, placeholder: "15")
                    }
                }
            }
        }
    }

    private var footer: some View {
        HStack(spacing: 10) {
            Toggle("Writable", isOn: $draft.writable)
                .toggleStyle(.switch)
                .font(.system(size: 13))
                .foregroundStyle(NtrpColors.muted)
            Spacer()
            Button("Cancel", action: close)
                .buttonStyle(.plain)
                .font(.system(size: 13, weight: .medium))
                .foregroundStyle(NtrpColors.muted)
                .frame(height: 32)
                .padding(.horizontal, 10)
            Button(saving ? "Saving..." : (seed.isEdit ? "Save" : "Create")) {
                Task {
                    guard draft.valid, !saving else { return }
                    saving = true
                    error = await save(seed, draft)
                    saving = false
                }
            }
            .disabled(!draft.valid || saving)
            .buttonStyle(.plain)
            .font(.system(size: 13, weight: .medium))
            .foregroundStyle(Color.black.opacity(0.86))
            .padding(.horizontal, 14)
            .frame(height: 32)
            .background(NtrpColors.text.opacity((!draft.valid || saving) ? 0.4 : 1))
            .clipShape(RoundedRectangle(cornerRadius: 9, style: .continuous))
        }
    }

    private func scheduleField(_ label: String, text: Binding<String>, placeholder: String) -> some View {
        VStack(alignment: .leading, spacing: 4) {
            Text(label.uppercased())
                .font(.system(size: 10, weight: .medium))
                .tracking(0.7)
                .foregroundStyle(NtrpColors.faint)
            TextField(placeholder, text: text)
                .textFieldStyle(.plain)
                .font(.system(size: 13, design: .monospaced))
                .foregroundStyle(NtrpColors.text)
                .padding(.horizontal, 8)
                .frame(height: 30)
                .background(NtrpColors.row.opacity(0.32))
                .overlay(RoundedRectangle(cornerRadius: 7, style: .continuous).stroke(NtrpColors.sidebarStroke, lineWidth: 1))
                .clipShape(RoundedRectangle(cornerRadius: 7, style: .continuous))
        }
    }

    private func iconButton(_ icon: String, help: String, action: @escaping () -> Void) -> some View {
        Button(action: action) {
            Image(systemName: icon)
                .font(.system(size: 12, weight: .medium))
                .foregroundStyle(NtrpColors.faint)
                .frame(width: 28, height: 28)
        }
        .buttonStyle(.plain)
        .help(help)
    }
}

private struct AutomationEditorError: View {
    let message: String

    var body: some View {
        VStack(alignment: .leading, spacing: 3) {
            Text("Couldn't save")
                .font(.system(size: 13, weight: .semibold))
                .foregroundStyle(Color.red.opacity(0.88))
            Text(message)
                .font(.system(size: 13))
                .foregroundStyle(NtrpColors.muted)
                .lineSpacing(2)
        }
        .padding(.horizontal, 12)
        .padding(.vertical, 9)
        .frame(maxWidth: .infinity, alignment: .leading)
        .background(Color.red.opacity(0.09))
        .clipShape(RoundedRectangle(cornerRadius: 10, style: .continuous))
    }
}

private struct AutomationCard: View {
    let item: JSONValue
    let edit: () -> Void
    let run: (String) -> Void
    let toggle: (String) -> Void
    let delete: (String) -> Void

    @State private var hovering = false

    var body: some View {
        let object = item.objectValue ?? [:]
        let id = object.string("task_id") ?? ""
        let enabled = object.bool("enabled") ?? false
        let editable = object.bool("builtin") != true
        VStack(alignment: .leading, spacing: 10) {
            HStack(alignment: .top, spacing: 10) {
                Button {
                    if !id.isEmpty { toggle(id) }
                } label: {
                    Circle()
                        .fill(enabled ? Color.green.opacity(0.85) : Color.clear)
                        .overlay(Circle().stroke(NtrpColors.sidebarStroke, lineWidth: enabled ? 0 : 1))
                        .frame(width: 10, height: 10)
                        .padding(.top, 6)
                }
                .buttonStyle(.plain)

                VStack(alignment: .leading, spacing: 6) {
                    Text(object.string("name") ?? "Untitled")
                        .font(.system(size: 16, weight: .medium))
                        .foregroundStyle(NtrpColors.text)
                        .lineLimit(1)
                    badgeRow(object)
                    Text(object.string("description") ?? "No description.")
                        .font(.system(size: 14))
                        .foregroundStyle(NtrpColors.muted)
                        .lineLimit(2)
                }
                Spacer(minLength: 0)
                HStack(spacing: 2) {
                    cardAction("play", label: "Run now") { if !id.isEmpty { run(id) } }
                    cardAction("trash", label: "Delete") { if !id.isEmpty { delete(id) } }
                }
                .opacity(hovering ? 1 : 0)
            }
            VStack(alignment: .leading, spacing: 4) {
                Text(triggerLabel(object))
                    .lineLimit(1)
                Text(nextLabel(object))
                    .lineLimit(1)
            }
            .font(.system(size: 12, design: .monospaced))
            .foregroundStyle(NtrpColors.faint)
            .padding(.leading, 20)
        }
        .padding(14)
        .background(NtrpColors.surfaceFill(0.38))
        .overlay(RoundedRectangle(cornerRadius: 10, style: .continuous).stroke(NtrpColors.sidebarStroke, lineWidth: 1))
        .clipShape(RoundedRectangle(cornerRadius: 10, style: .continuous))
        .contentShape(RoundedRectangle(cornerRadius: 10, style: .continuous))
        .ntrpGlass(cornerRadius: 10, interactive: true)
        .onTapGesture {
            if editable { edit() }
        }
        .onHover { hovering = $0 }
    }

    private func badgeRow(_ object: [String: JSONValue]) -> some View {
        HStack(spacing: 5) {
            if object.string("running_since") != nil {
                Badge(text: "running", tone: .accent)
            }
            if object.string("kind") == "loop", object.bool("read_history") == false {
                Badge(text: "channel", tone: .neutral)
            }
            if object.bool("builtin") == true {
                Badge(text: "builtin", tone: .neutral)
            }
        }
    }

    private func cardAction(_ icon: String, label: String, action: @escaping () -> Void) -> some View {
        Button(action: action) {
            Image(systemName: icon)
                .font(.system(size: 11, weight: .medium))
                .foregroundStyle(NtrpColors.faint)
                .frame(width: 24, height: 24)
        }
        .buttonStyle(.plain)
        .help(label)
    }

    private func triggerLabel(_ object: [String: JSONValue]) -> String {
        guard let triggers = object["triggers"]?.arrayValue, let first = triggers.first?.objectValue else {
            return "—"
        }
        if let every = first.string("every") {
            return "every \(every)"
        }
        if let at = first.string("at") {
            return "at \(at)"
        }
        return first.string("type") ?? "time"
    }

    private func nextLabel(_ object: [String: JSONValue]) -> String {
        if object.bool("enabled") == false {
            return "paused"
        }
        guard let next = object.string("next_run_at"), let date = ISO8601DateFormatter.ntrp.date(from: next) ?? ISO8601DateFormatter.ntrpFractional.date(from: next) else {
            return ""
        }
        let seconds = Int(date.timeIntervalSinceNow)
        if seconds <= 0 { return "due now" }
        if seconds < 3600 { return "next in \(max(1, seconds / 60))m" }
        if seconds < 86400 { return "next in \(seconds / 3600)h" }
        return "next in \(seconds / 86400)d"
    }
}

private struct TemplateCard: View {
    let template: AutomationTemplate
    let pick: () -> Void

    var body: some View {
        Button(action: pick) {
            HStack(alignment: .top, spacing: 12) {
                Image(systemName: template.icon)
                    .font(.system(size: 14, weight: .medium))
                    .foregroundStyle(NtrpColors.muted)
                    .frame(width: 18, height: 18)
                VStack(alignment: .leading, spacing: 5) {
                    Text(template.name)
                        .font(.system(size: 16, weight: .medium))
                        .foregroundStyle(NtrpColors.text)
                    Text(template.blurb)
                        .font(.system(size: 14))
                        .lineSpacing(3)
                        .foregroundStyle(NtrpColors.muted)
                }
                Spacer(minLength: 0)
            }
        }
        .buttonStyle(.plain)
        .help("Use template")
        .padding(14)
        .frame(maxWidth: .infinity, alignment: .leading)
        .background(NtrpColors.surfaceFill(0.38))
        .overlay(RoundedRectangle(cornerRadius: 10, style: .continuous).stroke(NtrpColors.sidebarStroke, lineWidth: 1))
        .clipShape(RoundedRectangle(cornerRadius: 10, style: .continuous))
        .ntrpGlass(cornerRadius: 10, interactive: true)
    }
}

private struct RecallResultPane: View {
    let result: JSONValue?
    @Binding var showPromptContext: Bool

    var body: some View {
        guard let object = result?.objectValue else {
            return AnyView(
                Text("Run a query to inspect recall")
                    .font(.system(size: 15))
                    .italic()
                    .foregroundStyle(NtrpColors.faint)
                    .frame(maxWidth: .infinity, minHeight: 220)
            )
        }

        let facts = object.array("facts")
        let observations = object.array("observations")
        return AnyView(
            VStack(alignment: .leading, spacing: 18) {
                HStack(spacing: 8) {
                    Text("Recall results")
                        .font(.system(size: 16, weight: .semibold))
                        .foregroundStyle(NtrpColors.text)
                    Spacer()
                    Badge(text: "\(observations.count) patterns", tone: .neutral)
                    Badge(text: "\(facts.count) facts", tone: .neutral)
                    Button(showPromptContext ? "Hide prompt context" : "Show prompt context") {
                        showPromptContext.toggle()
                    }
                    .buttonStyle(.plain)
                    .font(.system(size: 13, weight: .medium))
                    .foregroundStyle(NtrpColors.muted)
                }

                if showPromptContext {
                    Text(object.string("formatted_recall") ?? "No memory matches")
                        .font(.system(size: 13, design: .monospaced))
                        .foregroundStyle(NtrpColors.text)
                        .lineSpacing(3)
                        .padding(12)
                        .frame(maxWidth: .infinity, alignment: .leading)
                        .background(NtrpColors.row.opacity(0.28))
                        .clipShape(RoundedRectangle(cornerRadius: 8, style: .continuous))
                }

                MemorySection(title: "Patterns", items: observations, empty: "No matches")
                MemorySection(title: "Facts", items: facts, empty: "No matches")
            }
        )
    }
}

private struct MemorySection: View {
    let title: String
    let items: [JSONValue]
    let empty: String

    var body: some View {
        VStack(alignment: .leading, spacing: 8) {
            Text(title.uppercased())
                .font(.system(size: 11, weight: .semibold))
                .tracking(0.9)
                .foregroundStyle(NtrpColors.faint)
            if items.isEmpty {
                Text(empty)
                    .font(.system(size: 14))
                    .italic()
                    .foregroundStyle(NtrpColors.faint)
                    .padding(.horizontal, 12)
                    .frame(height: 36)
                    .frame(maxWidth: .infinity, alignment: .leading)
                    .background(NtrpColors.row.opacity(0.22))
                    .clipShape(RoundedRectangle(cornerRadius: 8, style: .continuous))
            } else {
                LazyVStack(spacing: 8) {
                    ForEach(items) { item in
                        MemoryCard(item: item)
                    }
                }
            }
        }
    }
}

private enum MemoryEntityKind {
    case facts
    case patterns

    var searchPlaceholder: String {
        switch self {
        case .facts: "Filter facts"
        case .patterns: "Filter patterns"
        }
    }

    var emptyTitle: String {
        switch self {
        case .facts: "No facts."
        case .patterns: "No patterns."
        }
    }

    var detailPlaceholder: String {
        switch self {
        case .facts: "Select a fact to view details"
        case .patterns: "Select a pattern to view details"
        }
    }

    var textKey: String {
        switch self {
        case .facts: "text"
        case .patterns: "summary"
        }
    }
}

private struct MemoryEntityPane: View {
    let kind: MemoryEntityKind
    let items: [JSONValue]
    @Binding var query: String
    @Binding var selectedID: String?
    let saveText: (String, String) async -> Void
    let replaceText: ((String, String) async -> Void)?
    let archive: ((String, Bool) async -> Void)?
    let delete: ((String) async -> Void)?

    private var filtered: [JSONValue] {
        let trimmed = query.trimmingCharacters(in: .whitespacesAndNewlines).lowercased()
        guard !trimmed.isEmpty else { return items }
        return items.filter { item in
            let object = item.objectValue ?? [:]
            return memoryPrimaryText(item, key: kind.textKey).lowercased().contains(trimmed)
                || (object.string("kind") ?? "").lowercased().contains(trimmed)
                || (object.string("status") ?? "").lowercased().contains(trimmed)
                || (object.string("evidence_level") ?? "").lowercased().contains(trimmed)
        }
    }

    private var selected: JSONValue? {
        filtered.first { memoryRecordID($0) == selectedID } ?? filtered.first
    }

    var body: some View {
        HStack(spacing: 0) {
            VStack(spacing: 10) {
                TextField(kind.searchPlaceholder, text: $query)
                    .textFieldStyle(.plain)
                    .font(.system(size: 13))
                    .foregroundStyle(NtrpColors.text)
                    .padding(.horizontal, 10)
                    .frame(height: 34)
                    .background(NtrpColors.row.opacity(0.32))
                    .clipShape(RoundedRectangle(cornerRadius: 8, style: .continuous))

                if filtered.isEmpty {
                    Text(items.isEmpty ? kind.emptyTitle : "No matches.")
                        .font(.system(size: 14))
                        .foregroundStyle(NtrpColors.faint)
                        .frame(maxWidth: .infinity, minHeight: 160)
                } else {
                    ScrollView {
                        LazyVStack(spacing: 4) {
                            ForEach(filtered) { item in
                                MemoryEntityRow(
                                    kind: kind,
                                    item: item,
                                    selected: memoryRecordID(item) == memoryRecordID(selected)
                                ) {
                                    selectedID = memoryRecordID(item)
                                }
                            }
                        }
                    }
                    .scrollIndicators(.hidden)
                }
            }
            .frame(width: 340)
            .padding(.trailing, 18)

            Rectangle()
                .fill(NtrpColors.sidebarStroke.opacity(0.7))
                .frame(width: 1)

            ScrollView {
                if let selected {
                    MemoryEntityDetail(
                        kind: kind,
                        item: selected,
                        saveText: saveText,
                        replaceText: replaceText,
                        archive: archive,
                        delete: delete
                    )
                } else {
                    Text(kind.detailPlaceholder)
                        .font(.system(size: 15))
                        .italic()
                        .foregroundStyle(NtrpColors.faint)
                        .frame(maxWidth: .infinity, minHeight: 240)
                }
            }
            .scrollIndicators(.hidden)
            .padding(.leading, 22)
        }
        .frame(minHeight: 520)
    }
}

private struct MemoryEntityRow: View {
    let kind: MemoryEntityKind
    let item: JSONValue
    let selected: Bool
    let select: () -> Void

    var body: some View {
        let object = item.objectValue ?? [:]
        Button(action: select) {
            VStack(alignment: .leading, spacing: 6) {
                Text(memoryPrimaryText(item, key: kind.textKey))
                    .font(.system(size: 14))
                    .foregroundStyle(NtrpColors.text)
                    .lineLimit(2)
                HStack(spacing: 7) {
                    if kind == .facts {
                        Text((object.string("kind") ?? "fact").uppercased())
                        Text("·")
                        Text(factStatusLabel(object.string("status")))
                        Text("·")
                        Text(sourceLabel(object.string("source") ?? "memory"))
                    } else {
                        Badge(text: observationEvidenceLabel(object.string("evidence_level")), tone: .neutral)
                        Text("\(object["evidence_count"]?.display ?? "0") sources")
                    }
                    if let accessed = object.string("last_accessed_at") {
                        Text("·")
                        Text(relativeLabel(accessed))
                    }
                }
                .font(.system(size: 11))
                .foregroundStyle(NtrpColors.faint)
            }
            .padding(.horizontal, 12)
            .padding(.vertical, 10)
            .frame(maxWidth: .infinity, alignment: .leading)
            .background(selected ? NtrpColors.rowActive : Color.clear)
            .clipShape(RoundedRectangle(cornerRadius: 8, style: .continuous))
        }
        .buttonStyle(.plain)
    }
}

private struct MemoryEntityDetail: View {
    let kind: MemoryEntityKind
    let item: JSONValue
    let saveText: (String, String) async -> Void
    let replaceText: ((String, String) async -> Void)?
    let archive: ((String, Bool) async -> Void)?
    let delete: ((String) async -> Void)?

    @State private var mode: EditMode?
    @State private var draft = ""
    @State private var busy = false

    private enum EditMode {
        case edit
        case replace
    }

    var body: some View {
        let object = item.objectValue ?? [:]
        let id = memoryRecordID(item) ?? ""
        let text = memoryPrimaryText(item, key: kind.textKey)
        VStack(alignment: .leading, spacing: 18) {
            HStack(alignment: .top, spacing: 12) {
                VStack(alignment: .leading, spacing: 8) {
                    HStack(spacing: 8) {
                        if kind == .facts {
                            Badge(text: factStatusLabel(object.string("status")), tone: .neutral)
                            Badge(text: (object.string("kind") ?? "fact").uppercased(), tone: .neutral)
                        } else {
                            Badge(text: observationEvidenceLabel(object.string("evidence_level")), tone: .neutral)
                            Badge(text: "\(object["evidence_count"]?.display ?? "0") sources", tone: .neutral)
                        }
                    }
                    if mode == nil {
                        Text(text)
                            .font(.system(size: 15))
                            .foregroundStyle(NtrpColors.text)
                            .lineSpacing(3)
                            .frame(maxWidth: .infinity, alignment: .leading)
                    }
                }
                Spacer()
            }

            if mode != nil {
                TextEditor(text: $draft)
                    .font(.system(size: 15))
                    .foregroundStyle(NtrpColors.text)
                    .scrollContentBackground(.hidden)
                    .padding(10)
                    .frame(minHeight: 150)
                    .background(NtrpColors.row.opacity(0.24))
                    .clipShape(RoundedRectangle(cornerRadius: 9, style: .continuous))
            }

            MemoryEntityMeta(kind: kind, item: item)

            HStack(spacing: 8) {
                Spacer()
                if let mode {
                    Button("Cancel") {
                        self.mode = nil
                        draft = text
                    }
                    .buttonStyle(.plain)
                    .foregroundStyle(NtrpColors.muted)
                    .disabled(busy)

                    Button(mode == .replace ? "Create replacement" : "Save changes") {
                        Task {
                            guard !id.isEmpty else { return }
                            busy = true
                            if mode == .replace, let replaceText {
                                await replaceText(id, draft.trimmingCharacters(in: .whitespacesAndNewlines))
                            } else {
                                await saveText(id, draft.trimmingCharacters(in: .whitespacesAndNewlines))
                            }
                            busy = false
                            self.mode = nil
                        }
                    }
                    .buttonStyle(.plain)
                    .font(.system(size: 13, weight: .medium))
                    .foregroundStyle(NtrpColors.text)
                    .padding(.horizontal, 12)
                    .frame(height: 32)
                    .background(NtrpColors.row.opacity(0.42))
                    .clipShape(RoundedRectangle(cornerRadius: 8, style: .continuous))
                    .disabled(busy || draft.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty || draft == text)
                } else {
                    if let delete {
                        Button("Delete") {
                            Task {
                                guard !id.isEmpty else { return }
                                busy = true
                                await delete(id)
                                busy = false
                            }
                        }
                        .buttonStyle(.plain)
                        .foregroundStyle(Color.red.opacity(0.86))
                        .disabled(busy)
                    }
                    if let archive {
                        let archived = object.string("status") == "archived"
                        Button(archived ? "Restore" : "Archive") {
                            Task {
                                guard !id.isEmpty else { return }
                                busy = true
                                await archive(id, !archived)
                                busy = false
                            }
                        }
                        .buttonStyle(.plain)
                        .foregroundStyle(NtrpColors.muted)
                        .disabled(busy)
                    }
                    if replaceText != nil {
                        Button("Replace claim") {
                            draft = text
                            mode = .replace
                        }
                        .buttonStyle(.plain)
                        .foregroundStyle(NtrpColors.muted)
                        .disabled(busy)
                    }
                    Button(kind == .facts ? "Fix typo" : "Edit") {
                        draft = text
                        mode = .edit
                    }
                    .buttonStyle(.plain)
                    .font(.system(size: 13, weight: .medium))
                    .foregroundStyle(NtrpColors.text)
                    .padding(.horizontal, 12)
                    .frame(height: 32)
                    .background(NtrpColors.row.opacity(0.42))
                    .clipShape(RoundedRectangle(cornerRadius: 8, style: .continuous))
                    .disabled(busy)
                }
            }
        }
        .padding(.bottom, 20)
        .onChange(of: memoryRecordID(item)) { _, _ in
            mode = nil
            draft = memoryPrimaryText(item, key: kind.textKey)
            busy = false
        }
    }
}

private struct MemoryEntityMeta: View {
    let kind: MemoryEntityKind
    let item: JSONValue

    var body: some View {
        let object = item.objectValue ?? [:]
        VStack(alignment: .leading, spacing: 0) {
            ForEach(metaRows(object), id: \.label) { row in
                HStack(alignment: .top, spacing: 12) {
                    Text(row.label)
                        .font(.system(size: 12, weight: .medium, design: .monospaced))
                        .foregroundStyle(NtrpColors.faint)
                        .frame(width: 120, alignment: .leading)
                    Text(row.value)
                        .font(.system(size: 13))
                        .foregroundStyle(NtrpColors.muted)
                        .lineLimit(3)
                    Spacer(minLength: 0)
                }
                .padding(.vertical, 8)
                if row.label != metaRows(object).last?.label {
                    Divider().overlay(NtrpColors.sidebarStroke.opacity(0.7))
                }
            }
        }
        .padding(.horizontal, 12)
        .background(NtrpColors.row.opacity(0.22))
        .clipShape(RoundedRectangle(cornerRadius: 10, style: .continuous))
    }

    private func metaRows(_ object: [String: JSONValue]) -> [(label: String, value: String)] {
        if kind == .facts {
            return [
                row("Created", object.string("created_at")),
                row("Last accessed", object.string("last_accessed_at")),
                row("Access count", object["access_count"]?.display),
                row("Salience", object["salience"]?.display),
                row("Confidence", object["confidence"]?.display),
                row("Source", object.string("source")),
                row("Session", object.string("source_session_id")),
                row("Message", object["source_message_id"]?.display)
            ].compactMap { $0 }
        }
        return [
            row("Created", object.string("created_at")),
            row("Last accessed", object.string("last_accessed_at")),
            row("Access count", object["access_count"]?.display),
            row("Evidence", object.string("evidence_level")),
            row("Sources", object["evidence_count"]?.display),
            row("Created by", object.string("created_by"))
        ].compactMap { $0 }
    }

    private func row(_ label: String, _ value: String?) -> (label: String, value: String)? {
        guard let value, !value.isEmpty else { return nil }
        return (label, value)
    }
}

private struct MemoryAuditPane: View {
    let audit: JSONValue?
    let stats: JSONValue?

    var body: some View {
        let auditObject = audit?.objectValue ?? [:]
        let statsObject = stats?.objectValue ?? [:]
        VStack(alignment: .leading, spacing: 14) {
            HStack(spacing: 10) {
                MemoryMetricCard(title: "Facts", value: metricValue(statsObject["facts"]) ?? metricValue(auditObject["facts"]) ?? "—")
                MemoryMetricCard(title: "Patterns", value: metricValue(statsObject["observations"]) ?? metricValue(auditObject["observations"]) ?? "—")
                MemoryMetricCard(title: "Storage", value: storageHealth(auditObject))
            }
            if let audit {
                MemoryKeyValueList(value: audit)
            } else {
                Text("No audit data.")
                    .font(.system(size: 14))
                    .foregroundStyle(NtrpColors.faint)
            }
        }
    }

    private func metricValue(_ value: JSONValue?) -> String? {
        guard let value else { return nil }
        if let object = value.objectValue {
            if let total = object["total"]?.display { return total }
            if let active = object["active"]?.display { return active }
            if let missing = object["no_embedding"]?.display { return "\(missing) missing embeddings" }
        }
        return value.display
    }

    private func storageHealth(_ object: [String: JSONValue]) -> String {
        if let facts = object.value("storage", "facts", "ok")?.boolValue,
           let observations = object.value("storage", "observations", "ok")?.boolValue {
            return facts && observations ? "ok" : "check"
        }
        return "—"
    }
}

private struct MemoryPruneResultPane: View {
    let result: JSONValue?

    var body: some View {
        guard let result else {
            return AnyView(
                Text("Run cleanup to preview candidates.")
                    .font(.system(size: 15))
                    .italic()
                    .foregroundStyle(NtrpColors.faint)
                    .frame(maxWidth: .infinity, minHeight: 180)
            )
        }
        return AnyView(
            VStack(alignment: .leading, spacing: 12) {
                if let summary = result.objectValue?.object("summary") {
                    HStack(spacing: 10) {
                        ForEach(summary.keys.sorted(), id: \.self) { key in
                            MemoryMetricCard(title: key.replacingOccurrences(of: "_", with: " "), value: summary[key]?.display ?? "—")
                        }
                    }
                }
                MemoryKeyValueList(value: result)
            }
        )
    }
}

private struct MemorySentPane: View {
    let events: [JSONValue]
    let facts: [JSONValue]
    let observations: [JSONValue]
    @Binding var query: String
    @Binding var selectedID: String?

    private var filteredEvents: [JSONValue] {
        let trimmed = query.trimmingCharacters(in: .whitespacesAndNewlines).lowercased()
        guard !trimmed.isEmpty else { return events }
        return events.filter { event in
            let object = event.objectValue ?? [:]
            return (object.string("source") ?? "").lowercased().contains(trimmed)
                || (object.string("query") ?? "").lowercased().contains(trimmed)
                || (object.string("policy_version") ?? "").lowercased().contains(trimmed)
        }
    }

    private var selected: JSONValue? {
        filteredEvents.first { $0.objectValue?["id"]?.display == selectedID } ?? filteredEvents.first
    }

    var body: some View {
        HStack(spacing: 0) {
            VStack(spacing: 10) {
                TextField("Filter sent memory", text: $query)
                    .textFieldStyle(.plain)
                    .font(.system(size: 13))
                    .foregroundStyle(NtrpColors.text)
                    .padding(.horizontal, 10)
                    .frame(height: 34)
                    .background(NtrpColors.row.opacity(0.32))
                    .clipShape(RoundedRectangle(cornerRadius: 8, style: .continuous))

                if filteredEvents.isEmpty {
                    Text(events.isEmpty ? "No sent-memory records yet." : "No matches.")
                        .font(.system(size: 14))
                        .foregroundStyle(NtrpColors.faint)
                        .frame(maxWidth: .infinity, minHeight: 160)
                } else {
                    ScrollView {
                        LazyVStack(spacing: 4) {
                            ForEach(filteredEvents) { event in
                                MemorySentRow(
                                    event: event,
                                    selected: event.objectValue?["id"]?.display == selected?.objectValue?["id"]?.display
                                ) {
                                    selectedID = event.objectValue?["id"]?.display
                                }
                            }
                        }
                    }
                    .scrollIndicators(.hidden)
                }
            }
            .frame(width: 340)
            .padding(.trailing, 18)

            Rectangle()
                .fill(NtrpColors.sidebarStroke.opacity(0.7))
                .frame(width: 1)

            ScrollView {
                if let selected {
                    MemorySentDetail(event: selected, facts: facts, observations: observations)
                } else {
                    Text("Select a sent-memory record")
                        .font(.system(size: 15))
                        .italic()
                        .foregroundStyle(NtrpColors.faint)
                        .frame(maxWidth: .infinity, minHeight: 240)
                }
            }
            .scrollIndicators(.hidden)
            .padding(.leading, 22)
        }
        .frame(minHeight: 480)
    }
}

private struct MemorySentRow: View {
    let event: JSONValue
    let selected: Bool
    let select: () -> Void

    var body: some View {
        let object = event.objectValue ?? [:]
        Button(action: select) {
            VStack(alignment: .leading, spacing: 5) {
                Text(sourceLabel(object.string("source") ?? "memory"))
                    .font(.system(size: 14, weight: .medium))
                    .foregroundStyle(NtrpColors.text)
                    .lineLimit(1)
                Text(object.string("query") ?? "no query")
                    .font(.system(size: 12))
                    .foregroundStyle(NtrpColors.faint)
                    .lineLimit(2)
                HStack(spacing: 7) {
                    Text("\(object.array("injected_fact_ids").count + object.array("injected_observation_ids").count) injected")
                    Text("·")
                    Text("\(object["formatted_chars"]?.display ?? "0") chars")
                    if let created = object.string("created_at") {
                        Text("·")
                        Text(relativeLabel(created))
                    }
                }
                .font(.system(size: 11))
                .foregroundStyle(NtrpColors.faint)
            }
            .padding(.horizontal, 12)
            .padding(.vertical, 10)
            .frame(maxWidth: .infinity, alignment: .leading)
            .background(selected ? NtrpColors.rowActive : Color.clear)
            .clipShape(RoundedRectangle(cornerRadius: 8, style: .continuous))
        }
        .buttonStyle(.plain)
    }
}

private struct MemorySentDetail: View {
    let event: JSONValue
    let facts: [JSONValue]
    let observations: [JSONValue]

    var body: some View {
        let object = event.objectValue ?? [:]
        VStack(alignment: .leading, spacing: 18) {
            HStack(alignment: .top, spacing: 12) {
                VStack(alignment: .leading, spacing: 5) {
                    Text(sourceLabel(object.string("source") ?? "memory"))
                        .font(.system(size: 18, weight: .semibold))
                        .foregroundStyle(NtrpColors.text)
                    Text([object.string("created_at"), object.string("policy_version")].compactMap { $0 }.joined(separator: " · "))
                        .font(.system(size: 13))
                        .foregroundStyle(NtrpColors.faint)
                }
                Spacer()
                Badge(text: "\(object["formatted_chars"]?.display ?? "0") chars", tone: .neutral)
            }

            if let query = object.string("query"), !query.isEmpty {
                MemoryDetailBlock(title: "Query", text: query)
            }

            MemoryIDSection(title: "Injected patterns", ids: object.array("injected_observation_ids"), records: observations, textKey: "summary")
            MemoryIDSection(title: "Injected facts", ids: object.array("injected_fact_ids"), records: facts, textKey: "text")
            MemoryIDSection(title: "Omitted facts", ids: object.array("omitted_fact_ids"), records: facts, textKey: "text")

            if let details = object["details"] {
                MemoryKeyValueList(value: details)
            }
        }
        .padding(.bottom, 20)
    }
}

private struct MemoryIDSection: View {
    let title: String
    let ids: [JSONValue]
    let records: [JSONValue]
    let textKey: String

    var body: some View {
        if !ids.isEmpty {
            VStack(alignment: .leading, spacing: 8) {
                Text("\(title.uppercased()) (\(ids.count))")
                    .font(.system(size: 11, weight: .semibold))
                    .tracking(0.9)
                    .foregroundStyle(NtrpColors.faint)
                ForEach(ids, id: \.display) { id in
                    Text(recordText(for: id.display))
                        .font(.system(size: 13))
                        .foregroundStyle(NtrpColors.muted)
                        .lineLimit(3)
                        .padding(.horizontal, 12)
                        .padding(.vertical, 9)
                        .frame(maxWidth: .infinity, alignment: .leading)
                        .background(NtrpColors.row.opacity(0.24))
                        .clipShape(RoundedRectangle(cornerRadius: 8, style: .continuous))
                }
            }
        }
    }

    private func recordText(for id: String) -> String {
        records.first { $0.objectValue?["id"]?.display == id }?.objectValue?.string(textKey) ?? "#\(id)"
    }
}

private struct MemoryDetailBlock: View {
    let title: String
    let text: String

    var body: some View {
        VStack(alignment: .leading, spacing: 8) {
            Text(title.uppercased())
                .font(.system(size: 11, weight: .semibold))
                .tracking(0.9)
                .foregroundStyle(NtrpColors.faint)
            Text(text)
                .font(.system(size: 13))
                .foregroundStyle(NtrpColors.muted)
                .lineSpacing(3)
                .padding(.horizontal, 12)
                .padding(.vertical, 9)
                .frame(maxWidth: .infinity, alignment: .leading)
                .background(NtrpColors.row.opacity(0.24))
                .clipShape(RoundedRectangle(cornerRadius: 8, style: .continuous))
        }
    }
}

private struct MemoryMetricCard: View {
    let title: String
    let value: String

    var body: some View {
        VStack(alignment: .leading, spacing: 4) {
            Text(title.uppercased())
                .font(.system(size: 10, weight: .semibold))
                .tracking(0.8)
                .foregroundStyle(NtrpColors.faint)
            Text(value)
                .font(.system(size: 18, weight: .semibold))
                .foregroundStyle(NtrpColors.text)
        }
        .padding(12)
        .frame(maxWidth: .infinity, alignment: .leading)
        .background(NtrpColors.surfaceFill(0.34))
        .overlay(RoundedRectangle(cornerRadius: 10, style: .continuous).stroke(NtrpColors.sidebarStroke, lineWidth: 1))
        .clipShape(RoundedRectangle(cornerRadius: 10, style: .continuous))
    }
}

private struct MemoryKeyValueList: View {
    let value: JSONValue

    var body: some View {
        VStack(alignment: .leading, spacing: 0) {
            ForEach(rows.prefix(12), id: \.key) { row in
                HStack(alignment: .top, spacing: 12) {
                    Text(row.key)
                        .font(.system(size: 12, weight: .medium, design: .monospaced))
                        .foregroundStyle(NtrpColors.faint)
                        .frame(width: 170, alignment: .leading)
                    Text(row.value)
                        .font(.system(size: 13))
                        .foregroundStyle(NtrpColors.muted)
                        .lineLimit(3)
                    Spacer(minLength: 0)
                }
                .padding(.vertical, 8)
                if row.key != rows.prefix(12).last?.key {
                    Divider().overlay(NtrpColors.sidebarStroke.opacity(0.7))
                }
            }
        }
        .padding(.horizontal, 12)
        .background(NtrpColors.row.opacity(0.22))
        .clipShape(RoundedRectangle(cornerRadius: 10, style: .continuous))
    }

    private var rows: [(key: String, value: String)] {
        flatten(value, prefix: "")
    }

    private func flatten(_ value: JSONValue, prefix: String) -> [(key: String, value: String)] {
        if let object = value.objectValue {
            return object.keys.sorted().flatMap { key in
                flatten(object[key] ?? .null, prefix: prefix.isEmpty ? key : "\(prefix).\(key)")
            }
        }
        if let array = value.arrayValue {
            return [(prefix, "\(array.count) items")]
        }
        return [(prefix, value.display)]
    }
}

private struct MemoryCard: View {
    let item: JSONValue

    var body: some View {
        let object = item.objectValue ?? [:]
        VStack(alignment: .leading, spacing: 6) {
            Text(object.string("text") ?? object.string("summary") ?? object.string("title") ?? item.display)
                .font(.system(size: 14, weight: .medium))
                .foregroundStyle(NtrpColors.text)
                .lineLimit(3)
            HStack(spacing: 8) {
                if let id = object["id"]?.display {
                    Text(id)
                }
                if let status = object.string("status") {
                    Text(status)
                }
            }
            .font(.system(size: 11, design: .monospaced))
            .foregroundStyle(NtrpColors.faint)
        }
        .padding(12)
        .frame(maxWidth: .infinity, alignment: .leading)
        .background(NtrpColors.row.opacity(0.34))
        .clipShape(RoundedRectangle(cornerRadius: 9, style: .continuous))
    }
}

private struct Badge: View {
    enum Tone {
        case accent
        case neutral
    }

    let text: String
    let tone: Tone

    var body: some View {
        Text(text)
            .font(.system(size: 11, weight: .medium))
            .foregroundStyle(tone == .accent ? NtrpColors.accent : NtrpColors.muted)
            .padding(.horizontal, 7)
            .frame(height: 20)
            .background(tone == .accent ? NtrpColors.accent.opacity(0.13) : NtrpColors.row)
            .clipShape(Capsule())
    }
}

private func sourceLabel(_ source: String) -> String {
    source.replacingOccurrences(of: "_", with: " ")
}

private func memoryRecordID(_ value: JSONValue?) -> String? {
    value?.objectValue?["id"]?.display
}

private func memoryPrimaryText(_ value: JSONValue, key: String) -> String {
    let object = value.objectValue ?? [:]
    return object.string(key) ?? object.string("text") ?? object.string("summary") ?? object.string("title") ?? value.display
}

private func factStatusLabel(_ status: String?) -> String {
    switch status {
    case "archived": "archived"
    case "superseded": "superseded"
    case "expired": "expired"
    case "temporary": "temporary"
    case "pinned": "pinned"
    case "active": "active"
    default: status ?? "active"
    }
}

private func observationEvidenceLabel(_ level: String?) -> String {
    switch level {
    case "strong": "strong"
    case "moderate": "moderate"
    case "weak": "weak"
    case "single": "single"
    default: level ?? "evidence"
    }
}

private func relativeLabel(_ iso: String) -> String {
    guard let date = ISO8601DateFormatter.ntrp.date(from: iso) ?? ISO8601DateFormatter.ntrpFractional.date(from: iso) else {
        return iso
    }
    let seconds = Int(Date().timeIntervalSince(date))
    if seconds < 60 { return "now" }
    if seconds < 3600 { return "\(seconds / 60)m ago" }
    if seconds < 86400 { return "\(seconds / 3600)h ago" }
    return "\(seconds / 86400)d ago"
}
