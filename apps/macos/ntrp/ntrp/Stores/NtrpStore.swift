import AppKit
import Foundation
import Combine

private struct CachedSessionView {
    let messages: [TranscriptMessage]
    let pendingApprovals: [PendingApproval]
    let queuedMessageIDs: Set<String>
    let queuedMessages: [QueuedMessage]
    let usage: SessionUsage
    let compacting: Bool
    let lastCompaction: LastCompaction?
    let activeLoops: [LoopSummary]
    let backgroundTasks: [BackgroundTaskSummary]
    let runningAutomations: [AutomationSummary]
    let editingMessageID: String?
    let isStreaming: Bool
    let currentRunID: String?
}

@MainActor
final class NtrpStore: ObservableObject {
    @Published var config: AppConfig
    @Published var sessions: [SessionListItem] = []
    @Published var archivedSessions: [SessionListItem] = []
    @Published var selectedSessionID: String?
    @Published var messages: [TranscriptMessage] = []
    @Published var pendingApprovals: [PendingApproval] = []
    @Published var queuedMessageIDs: Set<String> = []
    @Published var queuedMessages: [QueuedMessage] = []
    @Published var serverConfig: ServerConfig?
    @Published var serverConfigRaw: JSONValue?
    @Published var serverModels: JSONValue?
    @Published var skills: [JSONValue] = []
    @Published var goals: [String: SessionGoal] = [:]
    @Published var pendingGoalProposal: PendingGoalProposal?
    @Published var usage = SessionUsage()
    @Published var compacting = false
    @Published var lastCompaction: LastCompaction?
    @Published var activeLoops: [LoopSummary] = []
    @Published var backgroundTasks: [BackgroundTaskSummary] = []
    @Published var runningAutomations: [AutomationSummary] = []
    @Published var skipApprovals = false
    @Published var editingMessageID: String?
    @Published var isLoading = false
    @Published var isStreaming = false
    @Published var currentRunID: String?
    @Published var activeRunSessionIDs: Set<String> = []
    @Published var unreadDoneSessionIDs: Set<String> = []
    @Published var errorMessage: String?
    @Published var connectionLabel = "Disconnected"

    private let api = NtrpAPIClient()
    private let configStore = KeychainConfigStore()
    private var streamTask: Task<Void, Never>?
    private var activeRunsTask: Task<Void, Never>?
    private var sessionCache: [String: CachedSessionView] = [:]
    private var pendingToolCalls: [String: PendingToolCall] = [:]
    private var pendingToolResults: [String: PendingToolResult] = [:]
    private var backgroundTaskFirstSeen: [String: Date] = [:]
    private var activeAssistantID: String?

    init() {
        self.config = configStore.load()
    }

    func bootstrap() async {
        await reload()
    }

    func reload() async {
        isLoading = true
        errorMessage = nil
        defer { isLoading = false }

        do {
            let health = try await api.health(config: config)
            connectionLabel = health.auth == false ? "Auth failed" : "Connected"

            async let configRequest = api.serverConfig(config: config)
            async let configRawRequest = api.raw(config: config, path: "/config")
            async let modelsRequest = api.raw(config: config, path: "/models")
            async let skillsRequest = api.rawArray(config: config, path: "/skills", key: "skills")
            async let sessionsRequest = api.listSessions(config: config)
            async let currentRequest = api.currentSession(config: config)
            async let archivedRequest = api.archivedSessions(config: config)
            let (loadedConfig, loadedSessions, current, archived) = try await (configRequest, sessionsRequest, currentRequest, archivedRequest)
            serverConfig = loadedConfig
            serverConfigRaw = try? await configRawRequest
            serverModels = try? await modelsRequest
            skills = (try? await skillsRequest) ?? []
            sessions = mergedSessions(loadedSessions, current: current)
            archivedSessions = archived

            let nextID = selectedSessionID ?? current.sessionID
            selectedSessionID = nextID
            await loadSession(nextID)
            startActiveRunsPolling()
        } catch {
            connectionLabel = "Disconnected"
            errorMessage = error.localizedDescription
            stopActiveRunsPolling(clear: true)
        }
    }

    func saveConfig(_ next: AppConfig) async {
        do {
            config = try configStore.save(next)
            await reload()
        } catch {
            errorMessage = error.localizedDescription
        }
    }

    func patchServerConfig(_ patch: [String: JSONValue]) async {
        do {
            guard let body = JSONValue.object(patch).foundationObject else { return }
            _ = try await api.updateConfig(config: config, patch: body)
            await reload()
        } catch {
            errorMessage = error.localizedDescription
        }
    }

    func markdownForSkill(_ skill: JSONValue) async -> MarkdownViewState? {
        guard let object = skill.objectValue else { return nil }
        let name = object.string("name") ?? object.string("id") ?? skill.display
        guard !name.isEmpty else { return nil }

        do {
            let data = try await api.skillContent(config: config, name: name)
            let content = data.objectValue?.string("content") ?? data.display
            let path = data.objectValue?.string("path") ?? object.string("path")
            return MarkdownViewState(
                title: object.string("name") ?? name,
                subtitle: path,
                content: content,
                sourcePath: path
            )
        } catch {
            errorMessage = error.localizedDescription
            if let path = object.string("path"), !path.isEmpty {
                NSWorkspace.shared.open(URL(fileURLWithPath: path))
            }
            return nil
        }
    }

    func createSession() async {
        do {
            let created = try await api.createSession(config: config)
            let item = SessionListItem(
                sessionID: created.sessionID,
                startedAt: created.startedAt,
                lastActivity: created.lastActivity,
                name: created.name,
                messageCount: created.messageCount ?? 0,
                sessionType: "chat",
                originAutomationID: nil,
                archivedAt: nil
            )
            sessions.insert(item, at: 0)
            await loadSession(created.sessionID)
        } catch {
            errorMessage = error.localizedDescription
        }
    }

    func selectSession(_ sessionID: String) async {
        if selectedSessionID == sessionID {
            unreadDoneSessionIDs.remove(sessionID)
            return
        }
        await loadSession(sessionID)
    }

    func send(_ text: String, images: [DraftImageAttachment] = []) async {
        let trimmed = text.trimmingCharacters(in: .whitespacesAndNewlines)
        guard (!trimmed.isEmpty || !images.isEmpty), let sessionID = selectedSessionID else { return }

        if let editingMessageID {
            do {
                try await api.revertSession(config: config, sessionID: sessionID, messageID: editingMessageID)
                truncateFrom(editingMessageID)
                self.editingMessageID = nil
            } catch {
                append(TranscriptMessage(id: UUID().uuidString, role: .error, content: error.localizedDescription))
                errorMessage = error.localizedDescription
                return
            }
        }

        let clientID = UUID().uuidString
        let queued = isStreaming || currentRunID != nil
        if queued {
            queuedMessageIDs.insert(clientID)
            queuedMessages.append(QueuedMessage(clientID: clientID, text: trimmed, images: images, status: .pending))
        } else {
            append(TranscriptMessage(id: clientID, role: .user, content: trimmed.isEmpty ? " " : trimmed, images: images))
        }
        errorMessage = nil

        do {
            let response = try await api.sendMessage(
                config: config,
                sessionID: sessionID,
                message: trimmed,
                clientID: clientID,
                images: images.map(\.requestBody),
                skipApprovals: skipApprovals
            )
            currentRunID = response.runID
            activeRunSessionIDs.insert(sessionID)
            startStream(sessionID: sessionID, afterSeq: lastSeq)
        } catch {
            if queued, let index = queuedMessages.firstIndex(where: { $0.clientID == clientID }) {
                queuedMessages[index].status = .failed
            } else {
                append(TranscriptMessage(id: UUID().uuidString, role: .error, content: error.localizedDescription))
            }
            errorMessage = error.localizedDescription
        }
    }

    func toggleAutoApprovals(_ value: Bool) async {
        skipApprovals = value
        if value {
            pendingApprovals.removeAll()
        }
        guard let sessionID = selectedSessionID else { return }
        do {
            _ = try await api.setSessionAuto(config: config, sessionID: sessionID, value: value)
        } catch {
            errorMessage = error.localizedDescription
        }
    }

    func stopCurrentRun() async {
        guard let runID = currentRunID else { return }
        do {
            try await api.cancel(config: config, runID: runID)
            markRunFinished(sessionID: selectedSessionID)
            currentRunID = nil
            isStreaming = false
            streamTask?.cancel()
        } catch {
            errorMessage = error.localizedDescription
        }
    }

    func backgroundCurrentRun() async {
        guard let runID = currentRunID else { return }
        do {
            _ = try await api.backgroundRun(config: config, runID: runID)
            append(TranscriptMessage(id: UUID().uuidString, role: .activity, content: "Run moved to background"))
            if let sessionID = selectedSessionID {
                activeRunSessionIDs.insert(sessionID)
            }
            currentRunID = nil
            isStreaming = false
            streamTask?.cancel()
        } catch {
            errorMessage = error.localizedDescription
        }
    }

    func cancelQueuedMessage(_ clientID: String) async {
        guard let sessionID = selectedSessionID else { return }
        if let index = queuedMessages.firstIndex(where: { $0.clientID == clientID }) {
            queuedMessages[index].status = .cancelling
        }
        do {
            _ = try await api.cancelQueuedMessage(config: config, sessionID: sessionID, clientID: clientID)
            queuedMessageIDs.remove(clientID)
            queuedMessages.removeAll { $0.clientID == clientID }
        } catch {
            if let index = queuedMessages.firstIndex(where: { $0.clientID == clientID }) {
                queuedMessages[index].status = .pending
            }
            errorMessage = error.localizedDescription
        }
    }

    func resolveApproval(_ approval: PendingApproval, approved: Bool) async {
        do {
            try await api.submitApproval(config: config, runID: approval.runID, toolID: approval.id, approved: approved)
            pendingApprovals.removeAll { $0.id == approval.id }
        } catch {
            errorMessage = error.localizedDescription
        }
    }

    func rejectAllApprovals() async {
        await resolveAllApprovals(approved: false)
    }

    func resolveAllApprovals(approved: Bool) async {
        let approvals = pendingApprovals
        for approval in approvals {
            try? await api.submitApproval(config: config, runID: approval.runID, toolID: approval.id, approved: approved)
        }
        pendingApprovals.removeAll()
    }

    func renameSelectedSession(_ name: String) async {
        guard let sessionID = selectedSessionID else { return }
        await renameSession(sessionID, name: name)
    }

    func renameSession(_ sessionID: String, name: String) async {
        let trimmed = name.trimmingCharacters(in: .whitespacesAndNewlines)
        guard !trimmed.isEmpty else { return }
        do {
            try await api.renameSession(config: config, sessionID: sessionID, name: trimmed)
            sessions = sessions.map {
                $0.sessionID == sessionID
                    ? SessionListItem(
                        sessionID: $0.sessionID,
                        startedAt: $0.startedAt,
                        lastActivity: $0.lastActivity,
                        name: trimmed,
                        messageCount: $0.messageCount,
                        sessionType: $0.sessionType,
                        originAutomationID: $0.originAutomationID,
                        archivedAt: $0.archivedAt
                    )
                    : $0
            }
        } catch {
            errorMessage = error.localizedDescription
        }
    }

    func archiveSelectedSession() async {
        guard let sessionID = selectedSessionID else { return }
        await archiveSession(sessionID)
    }

    func archiveSession(_ sessionID: String) async {
        do {
            try await api.archiveSession(config: config, sessionID: sessionID)
            if let archived = sessions.first(where: { $0.sessionID == sessionID }) {
                archivedSessions.insert(archived, at: 0)
            }
            sessions.removeAll { $0.sessionID == sessionID }
            if selectedSessionID != sessionID {
                return
            } else if let next = sessions.first?.sessionID {
                await loadSession(next)
            } else {
                await createSession()
            }
        } catch {
            errorMessage = error.localizedDescription
        }
    }

    func branchSelectedSession(name: String? = nil) async {
        guard let sessionID = selectedSessionID else { return }
        do {
            let branched = try await api.branchSession(config: config, sessionID: sessionID, name: name)
            sessions.insert(branched, at: 0)
            await loadSession(branched.sessionID)
        } catch {
            errorMessage = error.localizedDescription
        }
    }

    func branchAtMessage(_ messageID: String) async {
        guard let sessionID = selectedSessionID else { return }
        do {
            let branched = try await api.branchSession(config: config, sessionID: sessionID, upToMessageID: messageID)
            sessions.insert(branched, at: 0)
            await loadSession(branched.sessionID)
        } catch {
            errorMessage = error.localizedDescription
        }
    }

    func editMessage(_ message: TranscriptMessage) {
        editingMessageID = message.id
    }

    func cancelEditing() {
        editingMessageID = nil
    }

    func clearSelectedSession() async {
        guard let sessionID = selectedSessionID else { return }
        do {
            try await api.clearSession(config: config, sessionID: sessionID)
            messages = []
            await reload()
        } catch {
            errorMessage = error.localizedDescription
        }
    }

    func revertSelectedSession(turns: Int = 1) async {
        guard let sessionID = selectedSessionID else { return }
        do {
            try await api.revertSession(config: config, sessionID: sessionID, turns: turns)
            await loadSession(sessionID)
        } catch {
            errorMessage = error.localizedDescription
        }
    }

    func compactSelectedSession() async {
        guard let sessionID = selectedSessionID else { return }
        await compactSession(sessionID)
    }

    func compactSession(_ sessionID: String) async {
        do {
            try await api.compact(config: config, sessionID: sessionID)
            if selectedSessionID == sessionID {
                await loadSession(sessionID)
            } else {
                await reload()
            }
        } catch {
            errorMessage = error.localizedDescription
        }
    }

    func restoreArchivedSession(_ sessionID: String) async {
        do {
            try await api.restoreSession(config: config, sessionID: sessionID)
            await reload()
            await loadSession(sessionID)
        } catch {
            errorMessage = error.localizedDescription
        }
    }

    func refreshArchivedSessions() async {
        do {
            archivedSessions = try await api.archivedSessions(config: config)
        } catch {
            errorMessage = error.localizedDescription
        }
    }

    func deleteArchivedSession(_ sessionID: String) async {
        do {
            try await api.permanentlyDeleteSession(config: config, sessionID: sessionID)
            archivedSessions.removeAll { $0.sessionID == sessionID }
        } catch {
            errorMessage = error.localizedDescription
        }
    }

    private func loadSession(_ sessionID: String) async {
        if selectedSessionID != sessionID {
            snapshotCurrentSession()
        }

        selectedSessionID = sessionID
        unreadDoneSessionIDs.remove(sessionID)
        streamTask?.cancel()
        streamTask = nil
        activeAssistantID = nil
        pendingToolCalls = [:]
        pendingToolResults = [:]
        if !restoreCachedSession(sessionID) {
            pendingApprovals = []
            queuedMessageIDs = []
            queuedMessages = []
            editingMessageID = nil
            usage = SessionUsage()
            compacting = false
            lastCompaction = nil
            activeLoops = []
            backgroundTasks = []
            runningAutomations = []
            messages = []
            isStreaming = false
            currentRunID = nil
        }
        errorMessage = nil

        do {
            let history = try await api.history(config: config, sessionID: sessionID)
            messages = TranscriptBuilder.messages(from: history.messages)
            if let historyUsage = history.usage {
                usage.lastPrompt = historyUsage.lastInputTokens
                usage.messageCount = historyUsage.messageCount
            }
            await refreshActiveLoops(sessionID: sessionID)
            await refreshActivePanel()
            await loadGoal(sessionID: sessionID)
            currentRunID = history.activeRunID
            if history.activeRunID != nil {
                activeRunSessionIDs.insert(sessionID)
                startStream(sessionID: sessionID, afterSeq: lastSeq)
            } else {
                activeRunSessionIDs.remove(sessionID)
                isStreaming = false
            }
        } catch {
            errorMessage = error.localizedDescription
        }
    }

    private func snapshotCurrentSession() {
        guard let sessionID = selectedSessionID else { return }
        sessionCache[sessionID] = CachedSessionView(
            messages: messages,
            pendingApprovals: pendingApprovals,
            queuedMessageIDs: queuedMessageIDs,
            queuedMessages: queuedMessages,
            usage: usage,
            compacting: compacting,
            lastCompaction: lastCompaction,
            activeLoops: activeLoops,
            backgroundTasks: backgroundTasks,
            runningAutomations: runningAutomations,
            editingMessageID: editingMessageID,
            isStreaming: isStreaming,
            currentRunID: currentRunID
        )
    }

    private func restoreCachedSession(_ sessionID: String) -> Bool {
        guard let cached = sessionCache[sessionID] else { return false }
        messages = cached.messages
        pendingApprovals = cached.pendingApprovals
        queuedMessageIDs = cached.queuedMessageIDs
        queuedMessages = cached.queuedMessages
        usage = cached.usage
        compacting = cached.compacting
        lastCompaction = cached.lastCompaction
        activeLoops = cached.activeLoops
        backgroundTasks = cached.backgroundTasks
        runningAutomations = cached.runningAutomations
        editingMessageID = cached.editingMessageID
        isStreaming = cached.isStreaming
        currentRunID = cached.currentRunID
        return true
    }

    private func startStream(sessionID: String, afterSeq: Int?) {
        streamTask?.cancel()
        isStreaming = true
        streamTask = Task { [weak self] in
            guard let self else { return }
            do {
                let stream = try await self.api.streamEvents(config: self.config, sessionID: sessionID, afterSeq: afterSeq)
                for try await event in stream {
                    self.apply(event)
                }
                await MainActor.run {
                    if self.selectedSessionID == sessionID {
                        self.isStreaming = false
                    }
                }
            } catch {
                await MainActor.run {
                    if self.selectedSessionID == sessionID {
                        self.isStreaming = false
                        self.errorMessage = error.localizedDescription
                    }
                }
            }
        }
    }

    private func apply(_ event: StreamEvent) {
        let createdAt = eventCreatedAt(event)
        switch event.type {
        case "RUN_STARTED":
            currentRunID = event.runID
            isStreaming = true
            if let sessionID = event.sessionID ?? selectedSessionID {
                activeRunSessionIDs.insert(sessionID)
            }
        case "RUN_FINISHED", "run_cancelled":
            if let runUsage = event.usage {
                usage.lastPrompt = runUsage.prompt
                usage.totalTokens += runUsage.prompt + runUsage.completion
                usage.totalCost += runUsage.cost
            }
            if let messageCount = event.messageCount {
                usage.messageCount = messageCount
            }
            currentRunID = nil
            activeAssistantID = nil
            isStreaming = false
            markRunFinished(sessionID: event.sessionID ?? selectedSessionID)
            markActivityDone()
        case "RUN_ERROR":
            currentRunID = nil
            isStreaming = false
            markRunFinished(sessionID: event.sessionID ?? selectedSessionID)
            append(TranscriptMessage(id: UUID().uuidString, role: .error, content: event.content ?? "Run failed", seq: event.seq, createdAt: createdAt))
        case "TEXT_MESSAGE_START":
            ensureAssistant(id: event.messageID, seq: event.seq, createdAt: createdAt)
        case "TEXT_MESSAGE_CONTENT":
            ensureAssistant(id: event.messageID, seq: event.seq, createdAt: createdAt)
            appendDelta(event.delta ?? "", to: event.messageID ?? activeAssistantID)
        case "TEXT_MESSAGE_END":
            activeAssistantID = nil
        case "REASONING_MESSAGE_START":
            append(TranscriptMessage(id: event.messageID ?? UUID().uuidString, role: .reasoning, content: "", detail: "Reasoning", seq: event.seq, createdAt: createdAt))
        case "REASONING_MESSAGE_CONTENT":
            appendDelta(event.delta ?? "", to: event.messageID)
        case "TOOL_CALL_START":
            guard let id = event.toolCallID else { return }
            pendingToolCalls[id] = PendingToolCall(
                name: event.toolCallName ?? "tool",
                displayName: event.displayName,
                description: event.description,
                arguments: "",
                createdAt: createdAt,
                semanticKind: event.kind,
                depth: event.depth,
                parentToolID: event.parentID
            )
        case "TOOL_CALL_ARGS":
            guard let id = event.toolCallID else { return }
            pendingToolCalls[id]?.arguments += event.delta ?? ""
        case "TOOL_CALL_END":
            guard let id = event.toolCallID, let tool = pendingToolCalls.removeValue(forKey: id) else { return }
            appendActivity(id: id, tool: tool, seq: event.seq)
        case "TOOL_CALL_RESULT":
            guard let id = event.toolCallID else { return }
            appendToolResult(
                id: id,
                result: event.content ?? event.preview ?? "",
                isError: event.isError == true,
                durationMS: event.durationMS,
                depth: event.depth,
                parentToolID: event.parentID,
                usageTotal: event.data?.value(for: "usage", "total")?.intValue,
                cost: event.data?.value(for: "cost")?.doubleValue
            )
        case "approval_needed":
            if let toolID = event.toolID, let runID = currentRunID ?? event.runID {
                pendingApprovals.append(PendingApproval(
                    id: toolID,
                    runID: runID,
                    name: event.name ?? toolID,
                    path: event.path,
                    diff: event.diff,
                    preview: event.contentPreview
                ))
            }
        case "message_ingested":
            if let clientID = event.clientID {
                if let queued = queuedMessages.first(where: { $0.clientID == clientID }) {
                    append(TranscriptMessage(id: clientID, role: .user, content: queued.text.isEmpty ? " " : queued.text, seq: event.seq, createdAt: createdAt, images: queued.images))
                }
                queuedMessageIDs.remove(clientID)
                queuedMessages.removeAll { $0.clientID == clientID }
            }
        case "stream_reset":
            if let sessionID = selectedSessionID {
                Task { await loadSession(sessionID) }
            }
        case "goal_updated":
            if let sessionID = event.sessionID ?? selectedSessionID, let goal = event.goal {
                goals[sessionID] = goal
            }
        case "goal_cleared":
            if let sessionID = event.sessionID ?? selectedSessionID {
                goals.removeValue(forKey: sessionID)
            }
        case "background_task_started":
            append(TranscriptMessage(id: event.toolID ?? UUID().uuidString, role: .activity, content: event.name ?? "Background task started", detail: event.preview, seq: event.seq, createdAt: createdAt))
        case "background_task_progress":
            append(TranscriptMessage(id: UUID().uuidString, role: .activity, content: event.name ?? "Background task", detail: event.content ?? event.preview, seq: event.seq, createdAt: createdAt))
        case "background_task_finished":
            append(TranscriptMessage(id: event.toolID ?? UUID().uuidString, role: .activity, content: event.name ?? "Background task finished", detail: event.content ?? event.preview, seq: event.seq, createdAt: createdAt))
        case "background_task":
            if let taskID = event.taskID, let sessionID = event.sessionID ?? selectedSessionID {
                let next = BackgroundTaskSummary(
                    taskID: taskID,
                    sessionID: sessionID,
                    parentRunID: event.runID,
                    status: event.status,
                    command: event.command ?? taskID,
                    detail: event.description ?? event.content ?? event.preview,
                    resultRef: event.resultRef
                )
                backgroundTasks.removeAll { $0.taskID == taskID }
                backgroundTasks.insert(next, at: 0)
            }
        case "compaction_started":
            compacting = true
        case "compaction_finished":
            compacting = false
            if let before = event.messagesBefore, let after = event.messagesAfter {
                lastCompaction = LastCompaction(before: before, after: after, at: Date())
            }
        case "compaction_error":
            compacting = false
            append(TranscriptMessage(id: UUID().uuidString, role: .error, content: event.content ?? "Compaction failed", seq: event.seq, createdAt: createdAt))
        case "task_started", "task_progress", "task_finished":
            append(TranscriptMessage(id: event.toolID ?? UUID().uuidString, role: .activity, content: event.name ?? event.type, detail: event.content ?? event.preview, seq: event.seq, createdAt: createdAt))
        case "stream_gap":
            if let sessionID = selectedSessionID {
                Task { await loadSession(sessionID) }
            }
        case "session_reloaded":
            break
        default:
            break
        }
    }

    private var lastSeq: Int? {
        messages.compactMap(\.seq).max()
    }

    private func append(_ message: TranscriptMessage) {
        if let index = messages.firstIndex(where: { $0.id == message.id }) {
            if messages[index].createdAt == nil, message.createdAt != nil {
                messages[index].createdAt = message.createdAt
            }
            return
        }
        messages.append(message)
    }

    func appendStatus(_ text: String) {
        append(TranscriptMessage(id: UUID().uuidString, role: .status, content: text))
    }

    func runBuiltinCommand(_ name: String, args: String = "") async {
        switch name {
        case "cost":
            let total = usage.totalTokens > 0 ? usage.totalTokens : usage.lastPrompt
            appendStatus("Last context: \(usage.lastPrompt.formatted()) tokens · Total: \(total.formatted()) tokens")
        case "rename":
            let name = args.trimmingCharacters(in: .whitespacesAndNewlines)
            guard !name.isEmpty else {
                append(TranscriptMessage(id: UUID().uuidString, role: .error, content: "Usage: /rename <name>"))
                return
            }
            await renameSelectedSession(name)
            appendStatus("Renamed to \"\(name)\".")
        case "goal":
            await runGoalCommand(args)
        case "clear":
            await clearSelectedSession()
        case "compact":
            await compactSelectedSession()
            appendStatus("Context compacted.")
        case "revert":
            let turns = max(1, Int(args.trimmingCharacters(in: .whitespacesAndNewlines)) ?? 1)
            await revertSelectedSession(turns: turns)
            appendStatus("Reverted \(turns) turn\(turns == 1 ? "" : "s").")
        case "branch":
            let trimmed = args.trimmingCharacters(in: .whitespacesAndNewlines)
            let name = trimmed.isEmpty ? nil : trimmed
            await branchSelectedSession(name: name)
        default:
            break
        }
    }

    private func runGoalCommand(_ args: String) async {
        guard let sessionID = selectedSessionID else { return }
        let arg = args.trimmingCharacters(in: .whitespacesAndNewlines)
        do {
            switch arg {
            case "":
                let proposal = try await api.proposeGoal(config: config, sessionID: sessionID)
                let objective = proposal.objective.trimmingCharacters(in: .whitespacesAndNewlines)
                if objective.isEmpty {
                    append(TranscriptMessage(id: UUID().uuidString, role: .error, content: "Goal proposal was empty."))
                    return
                }
                pendingGoalProposal = PendingGoalProposal(sessionID: sessionID, objective: objective)
            case "pause":
                goals[sessionID] = try await api.updateGoal(config: config, sessionID: sessionID, status: "paused")
            case "resume":
                goals[sessionID] = try await api.updateGoal(config: config, sessionID: sessionID, status: "active")
            case "complete":
                goals[sessionID] = try await api.updateGoal(config: config, sessionID: sessionID, status: "complete")
            case "clear":
                try await api.clearGoal(config: config, sessionID: sessionID)
                goals.removeValue(forKey: sessionID)
                appendStatus("Goal cleared.")
            default:
                let goal = try await api.setGoal(config: config, sessionID: sessionID, objective: arg)
                goals[sessionID] = goal
                appendStatus("Goal set: \(goal.objective)")
                let prompt = "Continue working toward this goal: \(goal.objective)"
                await send(prompt)
            }
        } catch {
            append(TranscriptMessage(id: UUID().uuidString, role: .error, content: error.localizedDescription))
            errorMessage = error.localizedDescription
        }
    }

    func acceptGoalProposal() async {
        guard let proposal = pendingGoalProposal else { return }
        do {
            let goal = try await api.setGoal(config: config, sessionID: proposal.sessionID, objective: proposal.objective)
            goals[proposal.sessionID] = goal
            pendingGoalProposal = nil
            if selectedSessionID == proposal.sessionID {
                await send("/goal \(goal.objective)")
            }
        } catch {
            append(TranscriptMessage(id: UUID().uuidString, role: .error, content: error.localizedDescription))
            errorMessage = error.localizedDescription
        }
    }

    func editGoalProposal() -> String? {
        guard let proposal = pendingGoalProposal else { return nil }
        pendingGoalProposal = nil
        return "/goal \(proposal.objective)"
    }

    func cancelGoalProposal() {
        pendingGoalProposal = nil
    }

    private func truncateFrom(_ id: String) {
        guard let index = messages.firstIndex(where: { $0.id == id }) else { return }
        messages = Array(messages.prefix(upTo: index))
    }

    private func ensureAssistant(id: String?, seq: Int?, createdAt: String?) {
        let messageID = id ?? activeAssistantID ?? UUID().uuidString
        activeAssistantID = messageID
        if let index = messages.firstIndex(where: { $0.id == messageID }) {
            if messages[index].createdAt == nil {
                messages[index].createdAt = createdAt
            }
            return
        }
        markActivityDone()
        append(TranscriptMessage(id: messageID, role: .assistant, content: "", seq: seq, createdAt: createdAt))
    }

    private func appendDelta(_ delta: String, to id: String?) {
        guard let id, !delta.isEmpty, let index = messages.firstIndex(where: { $0.id == id }) else { return }
        messages[index].content += delta
    }

    private func appendActivity(id: String, tool: PendingToolCall, seq: Int?) {
        let title = tool.description?.isEmpty == false ? tool.description! : (tool.displayName ?? tool.name)
        append(TranscriptMessage(
            id: id,
            role: .activity,
            content: title,
            detail: "Called \(tool.name)",
            seq: seq,
            createdAt: tool.createdAt,
            toolName: tool.name,
            toolArguments: tool.arguments,
            toolSemanticKind: tool.semanticKind == "agent" ? "agent" : nil,
            toolDepth: tool.depth,
            parentToolID: tool.parentToolID
        ))
        if let pending = pendingToolResults.removeValue(forKey: id) {
            appendToolResult(
                id: id,
                result: pending.result,
                isError: pending.isError,
                durationMS: pending.durationMS,
                depth: pending.depth,
                parentToolID: pending.parentToolID,
                usageTotal: pending.usageTotal,
                cost: pending.cost
            )
        }
    }

    private func appendToolResult(id: String, result: String, isError: Bool, durationMS: Double?, depth: Int?, parentToolID: String?, usageTotal: Int?, cost: Double?) {
        guard let index = messages.firstIndex(where: { $0.id == id }) else {
            pendingToolResults[id] = PendingToolResult(
                result: result,
                isError: isError,
                durationMS: durationMS,
                depth: depth,
                parentToolID: parentToolID,
                usageTotal: usageTotal,
                cost: cost
            )
            return
        }
        let trimmed = result.trimmingCharacters(in: .whitespacesAndNewlines)
        messages[index].toolResult = result
        messages[index].toolResultIsError = isError
        if let durationMS {
            messages[index].toolDurationMS = durationMS
        }
        if let depth {
            messages[index].toolDepth = depth
        }
        if let parentToolID {
            messages[index].parentToolID = parentToolID
        }
        if let usageTotal {
            messages[index].toolUsageTotal = usageTotal
        }
        if let cost {
            messages[index].toolCost = cost
        }
        if !trimmed.isEmpty {
            messages[index].detail = isError ? "Error: \(trimmed)" : trimmed
        }
    }

    private func markActivityDone() {
        // Turn grouping is derived from transcript order in ChatView.
    }

    private func eventCreatedAt(_ event: StreamEvent) -> String? {
        guard let timestamp = event.timestamp else { return nil }
        let date = Date(timeIntervalSince1970: timestamp / 1000)
        return ISO8601DateFormatter.ntrpFractional.string(from: date)
    }

    private func startActiveRunsPolling() {
        activeRunsTask?.cancel()
        activeRunsTask = Task { [weak self] in
            guard let self else { return }
            while !Task.isCancelled {
                await self.refreshActiveRuns()
                try? await Task.sleep(for: .seconds(2))
            }
        }
    }

    private func stopActiveRunsPolling(clear: Bool) {
        activeRunsTask?.cancel()
        activeRunsTask = nil
        if clear {
            activeRunSessionIDs = []
            unreadDoneSessionIDs = []
        }
    }

    private func refreshActiveRuns() async {
        do {
            let runs = try await api.activeRuns(config: config)
            syncActiveRunSessionIDs(Set(runs.map(\.sessionID)))
        } catch {
            // Keep the last known set during transient polling failures.
        }
    }

    private func syncActiveRunSessionIDs(_ next: Set<String>) {
        for sessionID in activeRunSessionIDs where !next.contains(sessionID) {
            if sessionID != selectedSessionID {
                unreadDoneSessionIDs.insert(sessionID)
            }
        }
        activeRunSessionIDs = next
    }

    private func markRunFinished(sessionID: String?) {
        guard let sessionID else { return }
        activeRunSessionIDs.remove(sessionID)
        if sessionID != selectedSessionID {
            unreadDoneSessionIDs.insert(sessionID)
        }
    }

    func refreshActiveLoops(sessionID: String? = nil) async {
        let targetSessionID = sessionID ?? selectedSessionID
        guard let targetSessionID else {
            activeLoops = []
            return
        }
        do {
            let value = try await api.raw(config: config, path: "/loops?session_id=\(NtrpAPIClient.queryValue(targetSessionID))")
            let loops = value.objectValue?.array("loops") ?? []
            activeLoops = loops.compactMap { item in
                guard
                    let object = item.objectValue,
                    object.string("session_id") == targetSessionID,
                    object.bool("enabled") == true,
                    let id = object.string("task_id")
                else {
                    return nil
                }
                return LoopSummary(
                    id: id,
                    every: object.string("every") ?? "",
                    nextRunAt: object.string("next_run_at"),
                    prompt: object.string("prompt"),
                    iterationCount: object.int("iteration_count") ?? 0,
                    maxIterations: object.int("max_iterations"),
                    maxAgeDays: object.int("max_age_days"),
                    stopWhen: object.string("stop_when")
                )
            }
        } catch {
            activeLoops = []
        }
    }

    func stopLoop(_ loop: LoopSummary) async {
        let text = "Cancel the recurring loop with task_id \"\(loop.id)\" by calling delete_automation, then confirm in one short sentence."
        if selectedSessionID == nil {
            do {
                _ = try await api.deleteLoop(config: config, taskID: loop.id)
                appendStatus("Loop stopped · \(self.truncatePrompt(loop.prompt ?? loop.id))")
                activeLoops.removeAll { $0.id == loop.id }
            } catch {
                append(TranscriptMessage(id: UUID().uuidString, role: .error, content: error.localizedDescription))
                errorMessage = error.localizedDescription
            }
            return
        }
        await send(text)
    }

    private func truncatePrompt(_ value: String) -> String {
        let trimmed = value.trimmingCharacters(in: .whitespacesAndNewlines)
        guard trimmed.count > 80 else { return trimmed }
        return String(trimmed.prefix(77)) + "..."
    }

    private func loadGoal(sessionID: String) async {
        do {
            if let goal = try await api.getGoal(config: config, sessionID: sessionID) {
                goals[sessionID] = goal
            } else {
                goals.removeValue(forKey: sessionID)
            }
        } catch {
            goals.removeValue(forKey: sessionID)
        }
    }

    func refreshActivePanel() async {
        guard let sessionID = selectedSessionID else {
            backgroundTasks = []
            runningAutomations = []
            return
        }

        async let tasksRequest = try? api.listBackgroundTasks(config: config, sessionID: sessionID)
        async let automationsRequest = try? api.automations(config: config)
        let tasks = await tasksRequest ?? []
        let now = Date()
        for task in tasks {
            let key = backgroundTaskKey(sessionID: sessionID, taskID: task.taskID)
            if backgroundTaskFirstSeen[key] == nil {
                backgroundTaskFirstSeen[key] = now
            }
        }
        backgroundTasks = tasks
        runningAutomations = (await automationsRequest ?? []).filter {
            $0.runningSince != nil && !$0.isInternal && !$0.isIterationLoop
        }
    }

    func backgroundTaskElapsed(_ task: BackgroundTaskSummary) -> String {
        guard let sessionID = task.sessionID ?? selectedSessionID,
              let firstSeen = backgroundTaskFirstSeen[backgroundTaskKey(sessionID: sessionID, taskID: task.taskID)]
        else {
            return ""
        }
        return shortElapsed(since: firstSeen)
    }

    private func backgroundTaskKey(sessionID: String, taskID: String) -> String {
        "\(sessionID):\(taskID)"
    }

    func cancelBackgroundTask(_ taskID: String) async {
        guard let sessionID = selectedSessionID else { return }
        do {
            try await api.cancelBackgroundTask(config: config, sessionID: sessionID, taskID: taskID)
            backgroundTasks = backgroundTasks.map {
                if $0.taskID != taskID { return $0 }
                return BackgroundTaskSummary(
                    taskID: $0.taskID,
                    sessionID: $0.sessionID,
                    parentRunID: $0.parentRunID,
                    status: "cancel_requested",
                    command: $0.command,
                    detail: $0.detail,
                    resultRef: $0.resultRef
                )
            }
        } catch {
            errorMessage = error.localizedDescription
        }
    }

    private func mergedSessions(_ sessions: [SessionListItem], current: SessionResponse) -> [SessionListItem] {
        if sessions.contains(where: { $0.sessionID == current.sessionID }) {
            return sessions
        }
        let item = SessionListItem(
            sessionID: current.sessionID,
            startedAt: "",
            lastActivity: "",
            name: current.name,
            messageCount: 0,
            sessionType: "chat",
            originAutomationID: nil,
            archivedAt: nil
        )
        return [item] + sessions
    }
}

enum TranscriptBuilder {
    static func messages(from history: [HistoryMessage]) -> [TranscriptMessage] {
        var toolResults: [String: String] = [:]
        for message in history where message.role == "tool" {
            if let id = message.toolCallID {
                toolResults[id] = message.content
            }
        }

        var output: [TranscriptMessage] = []
        for (index, message) in history.enumerated() {
            if message.isMeta == true || message.role == "tool" { continue }
            let id = message.id ?? message.messageID ?? "history-\(index)"
            if message.role == "user" {
                output.append(TranscriptMessage(
                    id: id,
                    role: .user,
                    content: message.content,
                    seq: message.seq,
                    createdAt: message.createdAt,
                    images: message.images?.map(\.draftAttachment) ?? []
                ))
                continue
            }
            if let reasoning = message.reasoningContent, !reasoning.isEmpty {
                output.append(TranscriptMessage(id: "\(id)-reasoning", role: .reasoning, content: reasoning, detail: "Reasoning", seq: message.seq, createdAt: message.createdAt))
            }
            for tool in message.toolCalls ?? [] {
                output.append(TranscriptMessage(
                    id: tool.id,
                    role: .activity,
                    content: formatToolCall(tool),
                    detail: toolResults[tool.id],
                    seq: message.seq,
                    createdAt: message.createdAt,
                    toolName: tool.name,
                    toolArguments: tool.arguments,
                    toolResult: toolResults[tool.id],
                    toolSemanticKind: tool.kind == "agent" ? "agent" : nil
                ))
            }
            if !message.content.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty {
                output.append(TranscriptMessage(id: id, role: .assistant, content: message.content, seq: message.seq, createdAt: message.createdAt))
            }
        }
        return output
    }

    private static func formatToolCall(_ tool: HistoryToolCall) -> String {
        guard
            let data = tool.arguments.data(using: .utf8),
            let object = try? JSONSerialization.jsonObject(with: data) as? [String: Any],
            !object.isEmpty
        else {
            return tool.name
        }
        let preview = object.prefix(2).map { "\($0.key): \($0.value)" }.joined(separator: ", ")
        return "\(tool.name) \(preview)"
    }
}
