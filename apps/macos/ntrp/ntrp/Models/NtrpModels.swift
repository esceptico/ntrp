import AppKit
import Foundation

struct MarkdownViewState: Identifiable, Equatable {
    let id = UUID()
    let title: String
    let subtitle: String?
    let content: String
    let sourcePath: String?
}

struct MermaidViewState: Identifiable, Equatable {
    let id = UUID()
    let code: String
}

struct AppConfig: Equatable {
    var serverURL: String
    var apiKey: String

    static let `default` = AppConfig(serverURL: "http://localhost:6877", apiKey: "")

    var normalized: AppConfig {
        AppConfig(
            serverURL: serverURL.trimmingCharacters(in: .whitespacesAndNewlines).trimmingTrailingSlash(),
            apiKey: apiKey.trimmingCharacters(in: .whitespacesAndNewlines)
        )
    }
}

struct HealthResponse: Decodable {
    let auth: Bool?
    let version: String?
    let hasProviders: Bool?

    enum CodingKeys: String, CodingKey {
        case auth
        case version
        case hasProviders = "has_providers"
    }
}

struct SessionListResponse: Decodable {
    let sessions: [SessionListItem]
}

struct SessionResponse: Decodable {
    let sessionID: String
    let name: String?

    enum CodingKeys: String, CodingKey {
        case sessionID = "session_id"
        case name
    }
}

struct CreateSessionResponse: Decodable {
    let sessionID: String
    let name: String?
    let startedAt: String
    let lastActivity: String
    let messageCount: Int?

    enum CodingKeys: String, CodingKey {
        case sessionID = "session_id"
        case name
        case startedAt = "started_at"
        case lastActivity = "last_activity"
        case messageCount = "message_count"
    }
}

struct SessionListItem: Identifiable, Decodable, Equatable {
    let sessionID: String
    let startedAt: String
    let lastActivity: String
    let name: String?
    let messageCount: Int
    let sessionType: String?
    let originAutomationID: String?
    let archivedAt: String?

    var id: String { sessionID }

    enum CodingKeys: String, CodingKey {
        case sessionID = "session_id"
        case startedAt = "started_at"
        case lastActivity = "last_activity"
        case name
        case messageCount = "message_count"
        case sessionType = "session_type"
        case originAutomationID = "origin_automation_id"
        case archivedAt = "archived_at"
    }
}

struct HistoryResponse: Decodable {
    let messages: [HistoryMessage]
    let activeRunID: String?
    let page: HistoryPage?
    let usage: HistoryUsage?

    enum CodingKeys: String, CodingKey {
        case messages
        case activeRunID = "active_run_id"
        case page
        case usage
    }
}

struct HistoryPage: Decodable {
    let hasMoreBefore: Bool
    let hasMoreAfter: Bool
    let before: String?
    let after: String?

    enum CodingKeys: String, CodingKey {
        case hasMoreBefore = "has_more_before"
        case hasMoreAfter = "has_more_after"
        case before
        case after
    }
}

struct HistoryUsage: Decodable, Equatable {
    let lastInputTokens: Int
    let messageCount: Int

    enum CodingKeys: String, CodingKey {
        case lastInputTokens = "last_input_tokens"
        case messageCount = "message_count"
    }
}

struct HistoryMessage: Decodable {
    let role: String
    let content: String
    let reasoningContent: String?
    let toolCalls: [HistoryToolCall]?
    let toolCallID: String?
    let images: [HistoryImage]?
    let id: String?
    let messageID: String?
    let seq: Int?
    let createdAt: String?
    let isMeta: Bool?

    enum CodingKeys: String, CodingKey {
        case role
        case content
        case reasoningContent = "reasoning_content"
        case toolCalls = "tool_calls"
        case toolCallID = "tool_call_id"
        case images
        case id
        case messageID = "message_id"
        case seq
        case createdAt = "created_at"
        case isMeta = "is_meta"
    }
}

struct HistoryToolCall: Decodable {
    let id: String
    let name: String
    let arguments: String
    let kind: String?
}

struct HistoryImage: Decodable {
    let mediaType: String
    let data: String

    enum CodingKeys: String, CodingKey {
        case mediaType = "media_type"
        case data
    }

    var draftAttachment: DraftImageAttachment {
        DraftImageAttachment(mediaType: mediaType, data: data, filename: "image")
    }
}

struct ChatMessageResponse: Decodable {
    let runID: String

    enum CodingKeys: String, CodingKey {
        case runID = "run_id"
    }
}

struct ActiveRunSummary: Decodable, Identifiable, Equatable {
    let runID: String?
    let sessionID: String
    let status: String?

    var id: String { sessionID }

    enum CodingKeys: String, CodingKey {
        case runID = "run_id"
        case sessionID = "session_id"
        case status
    }
}

struct ActiveRunsResponse: Decodable {
    let activeRuns: [ActiveRunSummary]

    enum CodingKeys: String, CodingKey {
        case activeRuns = "active_runs"
    }
}

struct DraftImageAttachment: Identifiable, Equatable {
    let id = UUID()
    let mediaType: String
    let data: String
    let filename: String

    var requestBody: [String: Any] {
        ["media_type": mediaType, "data": data]
    }

    var preview: NSImage? {
        guard let bytes = Data(base64Encoded: data) else { return nil }
        return NSImage(data: bytes)
    }
}

struct QueuedMessage: Identifiable, Equatable {
    enum Status: Equatable {
        case pending
        case cancelling
        case sent
        case failed
    }

    let clientID: String
    let text: String
    let images: [DraftImageAttachment]
    var status: Status

    var id: String { clientID }
}

struct SessionGoal: Decodable, Equatable {
    let sessionID: String
    let goalID: String
    let objective: String
    let status: String
    let tokenBudget: Int?
    let tokensUsed: Int
    let timeUsedSeconds: Int

    enum CodingKeys: String, CodingKey {
        case sessionID = "session_id"
        case goalID = "goal_id"
        case objective
        case status
        case tokenBudget = "token_budget"
        case tokensUsed = "tokens_used"
        case timeUsedSeconds = "time_used_seconds"
    }
}

struct PendingGoalProposal: Equatable {
    let sessionID: String
    let objective: String
}

struct GoalProposalResponse: Decodable {
    let objective: String
}

struct StreamEvent: Decodable {
    let type: String
    let timestamp: Double?
    let seq: Int?
    let replay: Bool?
    let sessionID: String?
    let runID: String?
    let messageID: String?
    let role: String?
    let delta: String?
    let content: String?
    let toolCallID: String?
    let toolCallName: String?
    let displayName: String?
    let description: String?
    let detail: String?
    let kind: String?
    let parentID: String?
    let depth: Int?
    let name: String?
    let preview: String?
    let isError: Bool?
    let durationMS: Double?
    let data: JSONValue?
    let usage: RunUsage?
    let messageCount: Int?
    let toolID: String?
    let taskID: String?
    let path: String?
    let diff: String?
    let contentPreview: String?
    let command: String?
    let status: String?
    let resultRef: String?
    let clientID: String?
    let goal: SessionGoal?
    let messagesBefore: Int?
    let messagesAfter: Int?

    enum CodingKeys: String, CodingKey {
        case type
        case timestamp
        case seq
        case replay
        case sessionID = "session_id"
        case runID = "run_id"
        case messageID = "message_id"
        case role
        case delta
        case content
        case toolCallID = "tool_call_id"
        case toolCallName = "tool_call_name"
        case displayName = "display_name"
        case description
        case detail
        case kind
        case parentID = "parent_id"
        case depth
        case name
        case preview
        case isError = "is_error"
        case durationMS = "duration_ms"
        case data
        case usage
        case messageCount = "message_count"
        case toolID = "tool_id"
        case taskID = "task_id"
        case path
        case diff
        case contentPreview = "content_preview"
        case command
        case status
        case resultRef = "result_ref"
        case clientID = "client_id"
        case goal
        case messagesBefore = "messages_before"
        case messagesAfter = "messages_after"
    }
}

struct RunUsage: Decodable, Equatable {
    let prompt: Int
    let completion: Int
    let cacheRead: Int?
    let cost: Double

    enum CodingKeys: String, CodingKey {
        case prompt
        case completion
        case cacheRead = "cache_read"
        case cost
    }
}

struct SessionUsage: Equatable {
    var lastPrompt: Int = 0
    var totalTokens: Int = 0
    var totalCost: Double = 0
    var messageCount: Int = 0
}

struct LastCompaction: Equatable {
    let before: Int
    let after: Int
    let at: Date
}

struct LoopSummary: Identifiable, Equatable {
    let id: String
    let every: String
    let nextRunAt: String?
    let prompt: String?
    let iterationCount: Int
    let maxIterations: Int?
    let maxAgeDays: Int?
    let stopWhen: String?
}

struct BackgroundTasksResponse: Decodable {
    let tasks: [BackgroundTaskSummary]
}

struct BackgroundTaskSummary: Identifiable, Decodable, Equatable {
    let taskID: String
    let sessionID: String?
    let parentRunID: String?
    let status: String?
    let command: String
    let detail: String?
    let resultRef: String?

    var id: String { taskID }

    enum CodingKeys: String, CodingKey {
        case taskID = "task_id"
        case sessionID = "session_id"
        case parentRunID = "parent_run_id"
        case status
        case command
        case detail
        case resultRef = "result_ref"
    }
}

struct AutomationsResponse: Decodable {
    let automations: [AutomationSummary]
}

struct AutomationSummary: Identifiable, Decodable, Equatable {
    let taskID: String
    let name: String
    let runningSince: String?
    let status: String?
    let handler: String?
    let builtin: Bool?
    let kind: String?
    let readHistory: Bool?

    var id: String { taskID }

    enum CodingKeys: String, CodingKey {
        case taskID = "task_id"
        case name
        case runningSince = "running_since"
        case status
        case handler
        case builtin
        case kind
        case readHistory = "read_history"
    }

    var isInternal: Bool {
        let internalHandlers = ["knowledge_reflection", "knowledge_retention", "knowledge_health"]
        return builtin == true || handler.map { internalHandlers.contains($0) } == true
    }

    var isIterationLoop: Bool {
        kind == "loop" && readHistory != false
    }
}

struct ServerConfig: Decodable, Equatable {
    let chatModel: String
    let chatModelMaxContext: Int
    let reasoningEffort: String?
    let compressionThreshold: Double
    let maxMessages: Int

    enum CodingKeys: String, CodingKey {
        case chatModel = "chat_model"
        case chatModelMaxContext = "chat_model_max_context"
        case reasoningEffort = "reasoning_effort"
        case compressionThreshold = "compression_threshold"
        case maxMessages = "max_messages"
    }
}

struct TranscriptMessage: Identifiable, Equatable {
    enum Role: Equatable {
        case user
        case assistant
        case reasoning
        case activity
        case approval
        case status
        case error
    }

    let id: String
    var role: Role
    var content: String
    var detail: String?
    var seq: Int?
    var createdAt: String?
    var images: [DraftImageAttachment] = []
    var toolName: String?
    var toolArguments: String?
    var toolResult: String?
    var toolResultIsError: Bool = false
    var toolSemanticKind: String?
    var toolDepth: Int?
    var parentToolID: String?
    var toolDurationMS: Double?
    var toolUsageTotal: Int?
    var toolCost: Double?
}

struct PendingToolCall: Equatable {
    var name: String
    var displayName: String?
    var description: String?
    var arguments: String
    var createdAt: String?
    var semanticKind: String?
    var depth: Int?
    var parentToolID: String?
}

struct PendingToolResult: Equatable {
    var result: String
    var isError: Bool
    var durationMS: Double?
    var depth: Int?
    var parentToolID: String?
    var usageTotal: Int?
    var cost: Double?
}

struct PendingApproval: Identifiable, Equatable {
    let id: String
    let runID: String
    let name: String
    let path: String?
    let diff: String?
    let preview: String?
}

extension String {
    func trimmingTrailingSlash() -> String {
        var value = self
        while value.hasSuffix("/") {
            value.removeLast()
        }
        return value.isEmpty ? self : value
    }
}
