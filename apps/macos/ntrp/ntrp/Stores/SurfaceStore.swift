import Combine
import Foundation

@MainActor
final class SurfaceStore: ObservableObject {
    @Published var providers: [JSONValue] = []
    @Published var services: [JSONValue] = []
    @Published var gmailAccounts: [JSONValue] = []
    @Published var models: JSONValue?
    @Published var serverConfig: JSONValue?
    @Published var tools: [JSONValue] = []
    @Published var mcpServers: [JSONValue] = []
    @Published var automations: [JSONValue] = []
    @Published var facts: [JSONValue] = []
    @Published var observations: [JSONValue] = []
    @Published var memoryStats: JSONValue?
    @Published var memoryAudit: JSONValue?
    @Published var memoryAccessEvents: [JSONValue] = []
    @Published var memoryAccessFacts: [JSONValue] = []
    @Published var memoryAccessObservations: [JSONValue] = []
    @Published var backgroundTasks: [JSONValue] = []
    @Published var skills: [JSONValue] = []
    @Published var loops: [JSONValue] = []
    @Published var isLoading = false
    @Published var errorMessage: String?

    private let api = NtrpAPIClient()

    func reload(config: AppConfig, sessionID: String?) async {
        isLoading = true
        errorMessage = nil
        defer { isLoading = false }

        async let providersResult = loadArray(config, "/providers", key: "providers")
        async let servicesResult = loadArray(config, "/services", key: "services")
        async let gmailResult = loadArray(config, "/gmail/accounts", key: "accounts")
        async let modelsResult = loadRaw(config, "/models")
        async let configResult = loadRaw(config, "/config")
        async let toolsResult = loadArray(config, "/tools", key: "tools")
        async let mcpResult = loadArray(config, "/mcp/servers", key: "servers")
        async let automationsResult = loadArray(config, "/automations", key: "automations")
        async let factsResult = loadArray(config, "/facts?limit=200&status=active", key: "facts")
        async let observationsResult = loadArray(config, "/observations?limit=200&status=active", key: "observations")
        async let statsResult = loadRaw(config, "/stats")
        async let auditResult = loadRaw(config, "/memory/audit")
        async let skillsResult = loadArray(config, "/skills", key: "skills")
        async let loopsResult = loadArray(config, "/loops", key: "loops")

        providers = await providersResult
        services = await servicesResult
        gmailAccounts = await gmailResult
        models = await modelsResult
        serverConfig = await configResult
        tools = await toolsResult
        mcpServers = await mcpResult
        automations = await automationsResult
        facts = await factsResult
        observations = await observationsResult
        memoryStats = await statsResult
        memoryAudit = await auditResult
        skills = await skillsResult
        loops = await loopsResult

        if let sessionID {
            backgroundTasks = await loadArray(config, "/chat/background-tasks?session_id=\(sessionID)", key: "tasks")
        } else {
            backgroundTasks = []
        }
    }

    func connectProvider(config: AppConfig, providerID: String, apiKey: String) async {
        await mutate(config) {
            try await api.raw(
                config: config,
                path: "/providers/\(NtrpAPIClient.pathComponent(providerID))/connect",
                method: "POST",
                body: ["api_key": apiKey]
            )
        }
    }

    func disconnectProvider(config: AppConfig, providerID: String) async {
        await mutate(config) {
            try await api.raw(config: config, path: "/providers/\(NtrpAPIClient.pathComponent(providerID))", method: "DELETE")
        }
    }

    func startCodexOAuth(config: AppConfig) async -> String? {
        do {
            let value = try await api.raw(config: config, path: "/providers/openai-codex/oauth/browser/start", method: "POST")
            return value.objectValue?.string("url") ?? value.objectValue?.string("auth_url")
        } catch {
            errorMessage = error.localizedDescription
            return nil
        }
    }

    func connectService(config: AppConfig, serviceID: String, apiKey: String) async {
        await mutate(config) {
            try await api.raw(
                config: config,
                path: "/services/\(NtrpAPIClient.pathComponent(serviceID))/connect",
                method: "POST",
                body: ["api_key": apiKey]
            )
        }
    }

    func disconnectService(config: AppConfig, serviceID: String) async {
        await mutate(config) {
            try await api.raw(config: config, path: "/services/\(NtrpAPIClient.pathComponent(serviceID))", method: "DELETE")
        }
    }

    func addGmail(config: AppConfig) async {
        await mutate(config) {
            try await api.raw(config: config, path: "/gmail/add", method: "POST")
        }
    }

    func removeGmail(config: AppConfig, tokenFile: String) async {
        await mutate(config) {
            try await api.raw(config: config, path: "/gmail/\(NtrpAPIClient.pathComponent(tokenFile))", method: "DELETE")
        }
    }

    func toggleAutomation(config: AppConfig, taskID: String) async {
        await mutate(config) {
            try await api.raw(config: config, path: "/automations/\(NtrpAPIClient.pathComponent(taskID))/toggle", method: "POST")
        }
    }

    func runAutomation(config: AppConfig, taskID: String) async {
        await mutate(config) {
            try await api.raw(config: config, path: "/automations/\(NtrpAPIClient.pathComponent(taskID))/run", method: "POST")
        }
    }

    func deleteAutomation(config: AppConfig, taskID: String) async {
        await mutate(config) {
            try await api.raw(config: config, path: "/automations/\(NtrpAPIClient.pathComponent(taskID))", method: "DELETE")
        }
    }

    func toggleMCP(config: AppConfig, name: String, enabled: Bool) async {
        await mutate(config) {
            try await api.raw(
                config: config,
                path: "/mcp/servers/\(NtrpAPIClient.pathComponent(name))/enabled",
                method: "PUT",
                body: ["enabled": enabled]
            )
        }
    }

    func startMCPOAuth(config: AppConfig, name: String) async {
        await mutate(config) {
            try await api.raw(config: config, path: "/mcp/servers/\(NtrpAPIClient.pathComponent(name))/oauth", method: "POST")
        }
    }

    func removeMCP(config: AppConfig, name: String) async {
        await mutate(config) {
            try await api.raw(config: config, path: "/mcp/servers/\(NtrpAPIClient.pathComponent(name))", method: "DELETE")
        }
    }

    func cancelBackgroundTask(config: AppConfig, sessionID: String, taskID: String) async {
        await mutate(config) {
            try await api.raw(
                config: config,
                path: "/chat/background-tasks/\(NtrpAPIClient.pathComponent(taskID))/cancel?session_id=\(NtrpAPIClient.queryValue(sessionID))",
                method: "POST"
            )
        }
    }

    func setFactArchived(config: AppConfig, id: String, archived: Bool) async {
        await mutate(config) {
            try await api.raw(config: config, path: "/facts/\(NtrpAPIClient.pathComponent(id))/metadata", method: "PATCH", body: ["archived": archived])
        }
    }

    func deleteObservation(config: AppConfig, id: String) async {
        await mutate(config) {
            try await api.raw(config: config, path: "/observations/\(NtrpAPIClient.pathComponent(id))", method: "DELETE")
        }
    }

    func patchConfig(config: AppConfig, bodyText: String) async -> JSONValue? {
        await mutateJSON(config, bodyText: bodyText) { body in
            try await api.updateConfig(config: config, patch: body)
        }
    }

    func addMCP(config: AppConfig, bodyText: String) async -> JSONValue? {
        await mutateJSON(config, bodyText: bodyText) { body in
            try await api.addMCPServer(config: config, body: body)
        }
    }

    func updateMCP(config: AppConfig, name: String, bodyText: String) async -> JSONValue? {
        await mutateJSON(config, bodyText: bodyText) { body in
            try await api.updateMCPServer(config: config, name: name, body: body)
        }
    }

    func updateMCPTools(config: AppConfig, name: String, toolsText: String) async {
        let tools = toolsText
            .split(whereSeparator: { $0 == "\n" || $0 == "," })
            .map { String($0).trimmingCharacters(in: .whitespacesAndNewlines) }
            .filter { !$0.isEmpty }
        await mutate(config) {
            try await api.updateMCPTools(config: config, name: name, tools: tools.isEmpty ? nil : tools)
        }
    }

    func createAutomation(config: AppConfig, bodyText: String) async -> JSONValue? {
        await mutateJSON(config, bodyText: bodyText) { body in
            try await api.createAutomation(config: config, body: body)
        }
    }

    func updateAutomation(config: AppConfig, taskID: String, bodyText: String) async -> JSONValue? {
        await mutateJSON(config, bodyText: bodyText) { body in
            try await api.updateAutomation(config: config, taskID: taskID, body: body)
        }
    }

    func updateFact(config: AppConfig, id: String, text: String) async {
        await mutate(config) {
            try await api.updateFact(config: config, id: id, text: text)
        }
    }

    func supersedeFact(config: AppConfig, id: String, text: String) async {
        await mutate(config) {
            try await api.supersedeFact(config: config, id: id, text: text)
        }
    }

    func updateObservation(config: AppConfig, id: String, summary: String) async {
        await mutate(config) {
            try await api.updateObservation(config: config, id: id, summary: summary)
        }
    }

    func pruneDryRun(config: AppConfig, bodyText: String) async -> JSONValue? {
        await mutateJSON(config, bodyText: bodyText) { body in
            try await api.memoryPruneDryRun(config: config, body: body)
        }
    }

    func pruneApply(config: AppConfig, bodyText: String) async -> JSONValue? {
        await mutateJSON(config, bodyText: bodyText) { body in
            try await api.memoryPruneApply(config: config, body: body)
        }
    }

    func inspectRecall(config: AppConfig, query: String) async -> JSONValue? {
        do {
            return try await api.raw(config: config, path: "/memory/recall/inspect", method: "POST", body: ["query": query])
        } catch {
            errorMessage = error.localizedDescription
            return nil
        }
    }

    func loadMemoryAccess(config: AppConfig) async {
        do {
            let value = try await api.raw(config: config, path: "/memory/access/events?limit=100&include_records=true")
            let object = value.objectValue
            memoryAccessEvents = object?.array("events") ?? []
            memoryAccessFacts = object?.array("facts") ?? []
            memoryAccessObservations = object?.array("observations") ?? []
        } catch {
            errorMessage = error.localizedDescription
            memoryAccessEvents = []
            memoryAccessFacts = []
            memoryAccessObservations = []
        }
    }

    func compact(config: AppConfig, sessionID: String) async {
        await mutate(config) {
            try await api.compact(config: config, sessionID: sessionID)
            return .object(["status": .string("ok")])
        }
    }

    private func mutate(_ config: AppConfig, operation: () async throws -> JSONValue) async {
        do {
            _ = try await operation()
        } catch {
            errorMessage = error.localizedDescription
        }
    }

    private func mutateJSON(
        _ config: AppConfig,
        bodyText: String,
        operation: (Any) async throws -> JSONValue
    ) async -> JSONValue? {
        do {
            let body = try parseJSONBody(bodyText)
            return try await operation(body)
        } catch {
            errorMessage = error.localizedDescription
            return nil
        }
    }

    private func parseJSONBody(_ text: String) throws -> Any {
        let trimmed = text.trimmingCharacters(in: .whitespacesAndNewlines)
        guard let data = trimmed.data(using: .utf8), !trimmed.isEmpty else {
            return [:]
        }
        return try JSONSerialization.jsonObject(with: data)
    }

    private func loadRaw(_ config: AppConfig, _ path: String) async -> JSONValue? {
        do {
            return try await api.raw(config: config, path: path)
        } catch {
            errorMessage = errorMessage ?? error.localizedDescription
            return nil
        }
    }

    private func loadArray(_ config: AppConfig, _ path: String, key: String) async -> [JSONValue] {
        do {
            return try await api.rawArray(config: config, path: path, key: key)
        } catch {
            errorMessage = errorMessage ?? error.localizedDescription
            return []
        }
    }
}
