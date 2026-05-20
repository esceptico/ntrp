import Foundation

enum NtrpAPIError: Error, LocalizedError {
    case invalidURL(String)
    case requestFailed(String)
    case badStatus(Int, String)
    case missingStream

    var errorDescription: String? {
        switch self {
        case .invalidURL(let value):
            return "Invalid URL: \(value)"
        case .requestFailed(let message):
            return message
        case .badStatus(let status, let message):
            return message.isEmpty ? "HTTP \(status)" : message
        case .missingStream:
            return "Server did not return an event stream"
        }
    }
}

final class NtrpAPIClient {
    private let session: URLSession
    private let decoder = JSONDecoder()
    private let encoder = JSONEncoder()

    init(session: URLSession = .shared) {
        self.session = session
    }

    func health(config: AppConfig) async throws -> HealthResponse {
        try await request(config: config, path: "/health")
    }

    func listSessions(config: AppConfig) async throws -> [SessionListItem] {
        let response: SessionListResponse = try await request(config: config, path: "/sessions")
        return response.sessions
    }

    func currentSession(config: AppConfig) async throws -> SessionResponse {
        try await request(config: config, path: "/session")
    }

    func serverConfig(config: AppConfig) async throws -> ServerConfig {
        try await request(config: config, path: "/config")
    }

    func createSession(config: AppConfig, name: String? = nil) async throws -> CreateSessionResponse {
        var body: [String: Any] = [:]
        if let name {
            body["name"] = name
        }
        return try await request(
            config: config,
            path: "/sessions",
            method: "POST",
            body: body
        )
    }

    func history(config: AppConfig, sessionID: String, limit: Int = 100) async throws -> HistoryResponse {
        var components = URLComponents()
        components.path = "/session/history"
        components.queryItems = [
            URLQueryItem(name: "session_id", value: sessionID),
            URLQueryItem(name: "limit", value: String(limit))
        ]
        return try await request(config: config, path: components.string ?? "/session/history")
    }

    func sendMessage(
        config: AppConfig,
        sessionID: String,
        message: String,
        clientID: String,
        images: [[String: Any]] = [],
        skipApprovals: Bool = false
    ) async throws -> ChatMessageResponse {
        try await request(
            config: config,
            path: "/chat/message",
            method: "POST",
            body: [
                "message": message,
                "session_id": sessionID,
                "skip_approvals": skipApprovals,
                "client_id": clientID,
                "images": images
            ] as [String: Any]
        )
    }

    func setSessionAuto(config: AppConfig, sessionID: String, value: Bool) async throws -> JSONValue {
        try await raw(
            config: config,
            path: "/sessions/\(Self.pathComponent(sessionID))/auto",
            method: "POST",
            body: ["value": value]
        )
    }

    func cancel(config: AppConfig, runID: String) async throws {
        let _: EmptyResponse = try await request(
            config: config,
            path: "/cancel",
            method: "POST",
            body: ["run_id": runID]
        )
    }

    func activeRuns(config: AppConfig) async throws -> [ActiveRunSummary] {
        let response: ActiveRunsResponse = try await request(config: config, path: "/chat/runs/status")
        return response.activeRuns
    }

    func backgroundRun(config: AppConfig, runID: String) async throws -> JSONValue {
        try await raw(config: config, path: "/chat/background", method: "POST", body: ["run_id": runID])
    }

    func listBackgroundTasks(config: AppConfig, sessionID: String) async throws -> [BackgroundTaskSummary] {
        let response: BackgroundTasksResponse = try await request(
            config: config,
            path: "/chat/background-tasks?session_id=\(Self.queryValue(sessionID))"
        )
        return response.tasks
    }

    func cancelBackgroundTask(config: AppConfig, sessionID: String, taskID: String) async throws {
        let _: EmptyResponse = try await request(
            config: config,
            path: "/chat/background-tasks/\(Self.pathComponent(taskID))/cancel?session_id=\(Self.queryValue(sessionID))",
            method: "POST"
        )
    }

    func automations(config: AppConfig) async throws -> [AutomationSummary] {
        let response: AutomationsResponse = try await request(config: config, path: "/automations")
        return response.automations
    }

    func cancelQueuedMessage(config: AppConfig, sessionID: String, clientID: String) async throws -> Int {
        let path = "/chat/inject/\(Self.pathComponent(clientID))?session_id=\(Self.queryValue(sessionID))"
        let request = try makeRequest(config: config, path: path, method: "DELETE", body: Optional<Data>.none)
        let (_, response) = try await session.data(for: request)
        return (response as? HTTPURLResponse)?.statusCode ?? 0
    }

    func submitApproval(config: AppConfig, runID: String, toolID: String, approved: Bool) async throws {
        let _: EmptyResponse = try await request(
            config: config,
            path: "/tools/result",
            method: "POST",
            body: [
                "run_id": runID,
                "tool_id": toolID,
                "result": "",
                "approved": approved
            ] as [String: Any]
        )
    }

    func renameSession(config: AppConfig, sessionID: String, name: String) async throws {
        let _: EmptyResponse = try await request(
            config: config,
            path: "/sessions/\(Self.pathComponent(sessionID))",
            method: "PATCH",
            body: ["name": name]
        )
    }

    func archiveSession(config: AppConfig, sessionID: String) async throws {
        let _: EmptyResponse = try await request(config: config, path: "/sessions/\(Self.pathComponent(sessionID))", method: "DELETE")
    }

    func archivedSessions(config: AppConfig) async throws -> [SessionListItem] {
        let response: SessionListResponse = try await request(config: config, path: "/sessions/archived")
        return response.sessions
    }

    func restoreSession(config: AppConfig, sessionID: String) async throws {
        let _: EmptyResponse = try await request(config: config, path: "/sessions/\(Self.pathComponent(sessionID))/restore", method: "POST")
    }

    func permanentlyDeleteSession(config: AppConfig, sessionID: String) async throws {
        let _: EmptyResponse = try await request(config: config, path: "/sessions/\(Self.pathComponent(sessionID))/permanent", method: "DELETE")
    }

    func branchSession(config: AppConfig, sessionID: String, name: String? = nil, upToMessageID: String? = nil) async throws -> SessionListItem {
        var body: [String: Any] = [:]
        if let name { body["name"] = name }
        if let upToMessageID { body["up_to_message_id"] = upToMessageID }
        let response: CreateSessionResponse = try await request(
            config: config,
            path: "/sessions/\(Self.pathComponent(sessionID))/branch",
            method: "POST",
            body: body
        )
        return SessionListItem(
            sessionID: response.sessionID,
            startedAt: response.startedAt,
            lastActivity: response.lastActivity,
            name: response.name,
            messageCount: response.messageCount ?? 0,
            sessionType: "chat",
            originAutomationID: nil,
            archivedAt: nil
        )
    }

    func clearSession(config: AppConfig, sessionID: String) async throws {
        let _: EmptyResponse = try await request(
            config: config,
            path: "/session/clear",
            method: "POST",
            body: ["session_id": sessionID]
        )
    }

    func revertSession(config: AppConfig, sessionID: String, turns: Int = 1, messageID: String? = nil) async throws {
        var body: [String: Any] = ["session_id": sessionID]
        if let messageID {
            body["message_id"] = messageID
        } else {
            body["turns"] = turns
        }
        let _: EmptyResponse = try await request(
            config: config,
            path: "/session/revert",
            method: "POST",
            body: body
        )
    }

    func compact(config: AppConfig, sessionID: String) async throws {
        let _: EmptyResponse = try await request(
            config: config,
            path: "/compact",
            method: "POST",
            body: ["session_id": sessionID]
        )
    }

    func getGoal(config: AppConfig, sessionID: String) async throws -> SessionGoal? {
        try await request(config: config, path: "/sessions/\(Self.pathComponent(sessionID))/goal")
    }

    func setGoal(config: AppConfig, sessionID: String, objective: String) async throws -> SessionGoal {
        try await request(
            config: config,
            path: "/sessions/\(Self.pathComponent(sessionID))/goal",
            method: "POST",
            body: ["objective": objective]
        )
    }

    func proposeGoal(config: AppConfig, sessionID: String) async throws -> GoalProposalResponse {
        try await request(
            config: config,
            path: "/sessions/\(Self.pathComponent(sessionID))/goal/propose",
            method: "POST"
        )
    }

    func updateGoal(config: AppConfig, sessionID: String, status: String) async throws -> SessionGoal {
        try await request(
            config: config,
            path: "/sessions/\(Self.pathComponent(sessionID))/goal",
            method: "PATCH",
            body: ["status": status]
        )
    }

    func clearGoal(config: AppConfig, sessionID: String) async throws {
        let _: EmptyResponse = try await request(
            config: config,
            path: "/sessions/\(Self.pathComponent(sessionID))/goal",
            method: "DELETE"
        )
    }

    func raw(config: AppConfig, path: String, method: String = "GET", body: Any? = nil) async throws -> JSONValue {
        let response: RawResponse = try await request(config: config, path: path, method: method, body: body)
        return response.value
    }

    func rawArray(config: AppConfig, path: String, key: String) async throws -> [JSONValue] {
        let value = try await raw(config: config, path: path)
        return value.objectValue?.array(key) ?? []
    }

    func updateConfig(config: AppConfig, patch: Any) async throws -> JSONValue {
        try await raw(config: config, path: "/config", method: "PATCH", body: patch)
    }

    func updateToolOverride(config: AppConfig, currentConfig: JSONValue?, toolName: String, decision: String?) async throws -> JSONValue {
        var overrides = currentConfig?.objectValue?.object("tool_overrides") ?? [:]
        if let decision, !decision.isEmpty {
            overrides[toolName] = .string(decision)
        } else {
            overrides.removeValue(forKey: toolName)
        }
        return try await updateConfig(config: config, patch: ["tool_overrides": JSONValue.object(overrides).foundationObject ?? [:]])
    }

    func addMCPServer(config: AppConfig, body: Any) async throws -> JSONValue {
        try await raw(config: config, path: "/mcp/servers", method: "POST", body: body)
    }

    func updateMCPServer(config: AppConfig, name: String, body: Any) async throws -> JSONValue {
        try await raw(config: config, path: "/mcp/servers/\(Self.pathComponent(name))", method: "PUT", body: body)
    }

    func updateMCPTools(config: AppConfig, name: String, tools: [String]?) async throws -> JSONValue {
        try await raw(
            config: config,
            path: "/mcp/servers/\(Self.pathComponent(name))/tools",
            method: "PUT",
            body: ["tools": tools as Any]
        )
    }

    func createAutomation(config: AppConfig, body: Any) async throws -> JSONValue {
        try await raw(config: config, path: "/automations", method: "POST", body: body)
    }

    func updateAutomation(config: AppConfig, taskID: String, body: Any) async throws -> JSONValue {
        try await raw(config: config, path: "/automations/\(Self.pathComponent(taskID))", method: "PATCH", body: body)
    }

    func createLoop(config: AppConfig, body: Any) async throws -> JSONValue {
        try await raw(config: config, path: "/loops", method: "POST", body: body)
    }

    func updateLoop(config: AppConfig, taskID: String, body: Any) async throws -> JSONValue {
        try await raw(config: config, path: "/loops/\(Self.pathComponent(taskID))", method: "PATCH", body: body)
    }

    func deleteLoop(config: AppConfig, taskID: String) async throws -> JSONValue {
        try await raw(config: config, path: "/loops/\(Self.pathComponent(taskID))", method: "DELETE")
    }

    func updateFact(config: AppConfig, id: String, text: String) async throws -> JSONValue {
        try await raw(config: config, path: "/facts/\(Self.pathComponent(id))", method: "PATCH", body: ["text": text])
    }

    func supersedeFact(config: AppConfig, id: String, text: String) async throws -> JSONValue {
        try await raw(config: config, path: "/facts/\(Self.pathComponent(id))/supersede", method: "POST", body: ["text": text])
    }

    func updateObservation(config: AppConfig, id: String, summary: String) async throws -> JSONValue {
        try await raw(config: config, path: "/observations/\(Self.pathComponent(id))", method: "PATCH", body: ["summary": summary])
    }

    func memoryPruneDryRun(config: AppConfig, body: Any) async throws -> JSONValue {
        try await raw(config: config, path: "/memory/prune/dry-run", method: "POST", body: body)
    }

    func memoryPruneApply(config: AppConfig, body: Any) async throws -> JSONValue {
        try await raw(config: config, path: "/memory/prune/apply", method: "POST", body: body)
    }

    func skillContent(config: AppConfig, name: String) async throws -> JSONValue {
        try await raw(config: config, path: "/skills/\(Self.pathComponent(name))/content")
    }

    func installSkill(config: AppConfig, source: String) async throws -> JSONValue {
        try await raw(config: config, path: "/skills/install", method: "POST", body: ["source": source])
    }

    func deleteSkill(config: AppConfig, name: String) async throws -> JSONValue {
        try await raw(config: config, path: "/skills/\(Self.pathComponent(name))", method: "DELETE")
    }

    func createNotifier(config: AppConfig, body: Any) async throws -> JSONValue {
        try await raw(config: config, path: "/notifiers/configs", method: "POST", body: body)
    }

    func updateNotifier(config: AppConfig, name: String, body: Any) async throws -> JSONValue {
        try await raw(config: config, path: "/notifiers/configs/\(Self.pathComponent(name))", method: "PUT", body: body)
    }

    func deleteNotifier(config: AppConfig, name: String) async throws -> JSONValue {
        try await raw(config: config, path: "/notifiers/configs/\(Self.pathComponent(name))", method: "DELETE")
    }

    func testNotifier(config: AppConfig, name: String) async throws -> JSONValue {
        try await raw(config: config, path: "/notifiers/configs/\(Self.pathComponent(name))/test", method: "POST")
    }

    func streamEvents(config: AppConfig, sessionID: String, afterSeq: Int?) async throws -> AsyncThrowingStream<StreamEvent, Error> {
        var components = URLComponents()
        components.path = "/chat/events/\(Self.pathComponent(sessionID))"
        components.queryItems = [URLQueryItem(name: "stream", value: "true")]
        if let afterSeq {
            components.queryItems?.append(URLQueryItem(name: "after_seq", value: String(afterSeq)))
        }
        let request = try makeRequest(config: config, path: components.string ?? components.path, method: "GET", body: Optional<Data>.none)
        return AsyncThrowingStream { continuation in
            let task = Task {
                do {
                    let (bytes, response) = try await session.bytes(for: request)
                    if let http = response as? HTTPURLResponse, !Self.okStatusCodes.contains(http.statusCode) {
                        throw NtrpAPIError.badStatus(http.statusCode, "")
                    }
                    for try await line in bytes.lines {
                        guard line.hasPrefix("data: ") else { continue }
                        let payload = String(line.dropFirst(6))
                        guard let data = payload.data(using: .utf8) else { continue }
                        let event = try self.decoder.decode(StreamEvent.self, from: data)
                        continuation.yield(event)
                    }
                    continuation.finish()
                } catch {
                    if Task.isCancelled {
                        continuation.finish()
                    } else {
                        continuation.finish(throwing: error)
                    }
                }
            }
            continuation.onTermination = { _ in task.cancel() }
        }
    }

    private func request<T: Decodable>(config: AppConfig, path: String, method: String = "GET", body: Any? = nil) async throws -> T {
        let bodyData = try body.map { try JSONSerialization.data(withJSONObject: $0) }
        let request = try makeRequest(config: config, path: path, method: method, body: bodyData)
        let (data, response) = try await session.data(for: request)
        guard let http = response as? HTTPURLResponse else {
            throw NtrpAPIError.requestFailed("No HTTP response")
        }
        guard Self.okStatusCodes.contains(http.statusCode) else {
            let message = Self.errorMessage(from: data, status: http.statusCode)
            throw NtrpAPIError.badStatus(http.statusCode, message)
        }
        if T.self == EmptyResponse.self {
            return EmptyResponse() as! T
        }
        return try decoder.decode(T.self, from: data)
    }

    static func pathComponent(_ value: String) -> String {
        var allowed = CharacterSet.urlPathAllowed
        allowed.remove(charactersIn: "/?#[]@!$&'()*+,;=")
        return value.addingPercentEncoding(withAllowedCharacters: allowed) ?? value
    }

    static func queryValue(_ value: String) -> String {
        value.addingPercentEncoding(withAllowedCharacters: .urlQueryAllowed) ?? value
    }

    private func makeRequest(config: AppConfig, path: String, method: String, body: Data?) throws -> URLRequest {
        let normalized = config.normalized
        guard let base = URL(string: normalized.serverURL), let url = URL(string: path, relativeTo: base) else {
            throw NtrpAPIError.invalidURL(normalized.serverURL + path)
        }
        var request = URLRequest(url: url)
        request.httpMethod = method
        request.timeoutInterval = 30
        request.setValue("application/json", forHTTPHeaderField: "Accept")
        if let body {
            request.httpBody = body
            request.setValue("application/json", forHTTPHeaderField: "Content-Type")
        }
        if !normalized.apiKey.isEmpty {
            request.setValue("Bearer \(normalized.apiKey)", forHTTPHeaderField: "Authorization")
        }
        return request
    }

    private static let okStatusCodes = 200..<300

    private static func errorMessage(from data: Data, status: Int) -> String {
        if
            let object = try? JSONSerialization.jsonObject(with: data) as? [String: Any],
            let detail = object["detail"] as? String
        {
            return detail
        }
        return String(data: data, encoding: .utf8) ?? "HTTP \(status)"
    }
}

private struct EmptyResponse: Decodable {}
