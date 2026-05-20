import AppKit
import Carbon
import SwiftUI

enum SettingsTab: String, CaseIterable, Identifiable {
    case connection
    case providers
    case integrations
    case models
    case agent
    case context
    case tools
    case mcp
    case appearance

    var id: String { rawValue }

    var title: String {
        switch self {
        case .connection: "Connection"
        case .providers: "Providers"
        case .integrations: "Integrations"
        case .models: "Models"
        case .agent: "Agent"
        case .context: "Context"
        case .tools: "Tools"
        case .mcp: "MCP servers"
        case .appearance: "Appearance"
        }
    }

    var icon: String {
        switch self {
        case .connection: "powerplug"
        case .providers: "key"
        case .integrations: "cable.connector"
        case .models: "sparkles"
        case .agent: "brain"
        case .context: "database"
        case .tools: "wrench"
        case .mcp: "shippingbox"
        case .appearance: "paintpalette"
        }
    }
}

struct SettingsView: View {
    @ObservedObject var store: NtrpStore
    @Binding var activeTab: SettingsTab
    var onClose: (() -> Void)?
    @StateObject private var surface = SurfaceStore()
    @State private var draft: AppConfig = .default
    @State private var providerEditingID: String?
    @State private var providerAPIKey = ""
    @State private var providerPendingID: String?
    @State private var connectionSaving = false
    @State private var modelSavingKey: String?
    @State private var toolQuery = ""
    @State private var toolSavingName: String?
    @State private var integrationPendingID: String?
    @State private var serviceEditingID: String?
    @State private var serviceKey = ""
    @State private var mcpSavingName: String?
    @State private var settingsScrolled = false
    private let contentWidth: CGFloat = 776

    var body: some View {
        ZStack(alignment: .topLeading) {
            ScrollView {
                VStack(spacing: 0) {
                    GeometryReader { geometry in
                        Color.clear.preference(
                            key: SettingsScrollTopPreferenceKey.self,
                            value: geometry.frame(in: .named("settings-scroll")).minY
                        )
                    }
                    .frame(height: 1)
                    .padding(.bottom, -1)

                    activeContent
                        .padding(.horizontal, 20)
                        .padding(.top, 57)
                        .padding(.bottom, 16)
                        .frame(maxWidth: contentWidth, alignment: .topLeading)
                }
            }
            .scrollIndicators(.hidden)
            .coordinateSpace(name: "settings-scroll")
            .mask(settingsScrollMask)
            .frame(maxWidth: contentWidth, maxHeight: .infinity, alignment: .topLeading)
            .onPreferenceChange(SettingsScrollTopPreferenceKey.self) { top in
                let next = top < -0.5
                if settingsScrolled != next {
                    settingsScrolled = next
                }
            }

            settingsHeader
                .padding(.horizontal, 20)
                .padding(.top, 16)
                .padding(.bottom, 12)
                .frame(maxWidth: contentWidth, alignment: .topLeading)
                .background(NtrpColors.canvas.opacity(0.001))
        }
        .frame(maxWidth: .infinity, maxHeight: .infinity)
        .foregroundStyle(NtrpColors.text)
        .onAppear {
            draft = store.config
            Task { await surface.reload(config: store.config, sessionID: store.selectedSessionID) }
        }
    }

    private var settingsHeader: some View {
        HStack(spacing: 12) {
            Text(activeTab.title)
                .font(.system(size: 18, weight: .semibold))
                .tracking(-0.216)
                .foregroundStyle(NtrpColors.text)

            Spacer(minLength: 0)

            if let onClose {
                Button(action: onClose) {
                    Image(systemName: "xmark")
                        .font(.system(size: 15, weight: .medium))
                        .foregroundStyle(NtrpColors.muted)
                        .frame(width: 26, height: 26)
                        .contentShape(Rectangle())
                }
                .buttonStyle(.plain)
                .help("Close")
            }
        }
        .frame(maxWidth: .infinity, alignment: .leading)
    }

    @ViewBuilder
    private var settingsScrollMask: some View {
        if settingsScrolled {
            LinearGradient(
                stops: [
                    .init(color: .clear, location: 0.0),
                    .init(color: .black.opacity(0.08), location: 0.03),
                    .init(color: .black.opacity(0.40), location: 0.08),
                    .init(color: .black, location: 0.17)
                ],
                startPoint: .top,
                endPoint: .bottom
            )
        } else {
            Rectangle()
        }
    }

    @ViewBuilder
    private var activeContent: some View {
        switch activeTab {
        case .connection:
            connectionTab
        case .providers:
            providersTab
        case .integrations:
            integrationsTab
        case .models:
            modelsTab
        case .agent:
            agentTab
        case .context:
            contextTab
        case .tools:
            toolsTab
        case .mcp:
            mcpTab
        case .appearance:
            appearanceTab
        }
    }

    private var reloadButton: some View {
        Button {
            Task { await surface.reload(config: store.config, sessionID: store.selectedSessionID) }
        } label: {
            Label("Reload", systemImage: "arrow.clockwise")
        }
    }

    private func settingsField<Content: View>(
        label: String,
        help: String,
        @ViewBuilder content: () -> Content
    ) -> some View {
        VStack(alignment: .leading, spacing: 4) {
            Text(label.uppercased())
                .font(.system(size: 12, weight: .medium))
                .tracking(0.72)
                .foregroundStyle(NtrpColors.muted)
            content()
                .padding(.horizontal, 12)
                .frame(height: 36)
                .background(NtrpColors.sidebar)
                .overlay(
                    RoundedRectangle(cornerRadius: 9, style: .continuous)
                        .stroke(NtrpColors.sidebarStroke, lineWidth: 1)
                )
                .clipShape(RoundedRectangle(cornerRadius: 9, style: .continuous))
            Text(help)
                .font(.system(size: 12))
                .lineSpacing(1)
                .foregroundStyle(NtrpColors.faint)
        }
    }

    private var connectionTab: some View {
        VStack(alignment: .leading, spacing: 16) {
            Text("Server URL and API key. Stored locally; encrypted with safeStorage when available.")
                .font(.system(size: 14))
                .lineSpacing(3)
                .foregroundStyle(NtrpColors.muted)
                .frame(maxWidth: 440, alignment: .leading)

            settingsField(
                label: "Server URL",
                help: "The address where your ntrp server is running."
            ) {
                TextField("http://localhost:6877", text: $draft.serverURL)
                    .textFieldStyle(.plain)
                    .font(.system(size: 16))
                    .foregroundStyle(NtrpColors.text)
            }

            settingsField(
                label: "API key",
                help: "From your server config. Used as a Bearer token."
            ) {
                SecureField("ntrp_...", text: $draft.apiKey)
                    .textFieldStyle(.plain)
                    .font(.system(size: 16))
                    .foregroundStyle(NtrpColors.text)
            }

            if let error = store.errorMessage, !error.isEmpty {
                SettingsInlineError(title: "Could not connect", message: error)
            }

            HStack {
                Spacer()
                Button {
                    Task {
                        guard !connectionSaving else { return }
                        connectionSaving = true
                        await store.saveConfig(draft)
                        await surface.reload(config: draft.normalized, sessionID: store.selectedSessionID)
                        connectionSaving = false
                    }
                } label: {
                    Text(connectionSaving ? "Checking..." : "Save & reconnect")
                        .font(.system(size: 14, weight: .medium))
                        .tracking(-0.07)
                        .foregroundStyle(Color.black.opacity(0.86))
                        .padding(.horizontal, 14)
                        .frame(height: 32)
                        .background(NtrpColors.text)
                        .clipShape(RoundedRectangle(cornerRadius: 9, style: .continuous))
                }
                .buttonStyle(.plain)
                .disabled(connectionSaving)
                .opacity(connectionSaving ? 0.72 : 1)
            }
        }
        .frame(maxWidth: 560, alignment: .leading)
        .padding(.top, 2)
    }

    private var providersTab: some View {
        let sorted = sortedProviders
        let connected = sorted.filter { $0.objectValue?.bool("connected") == true }
        let setup = sorted.filter { $0.objectValue?.bool("connected") != true }

        return VStack(alignment: .leading, spacing: 16) {
            HStack(alignment: .top, spacing: 12) {
                Text("Connect model providers here. Server connection and tool integrations stay separate.")
                    .font(.system(size: 14))
                    .lineSpacing(3)
                    .foregroundStyle(NtrpColors.muted)
                    .frame(maxWidth: 520, alignment: .leading)
                Spacer()
                Button {
                    Task { await surface.reload(config: store.config, sessionID: store.selectedSessionID) }
                } label: {
                    Label("Refresh", systemImage: surface.isLoading ? "arrow.clockwise.circle" : "arrow.clockwise")
                        .font(.system(size: 13, weight: .medium))
                        .padding(.horizontal, 10)
                        .frame(height: 32)
                }
                .buttonStyle(.plain)
                .background(NtrpColors.row.opacity(0.42))
                .overlay(RoundedRectangle(cornerRadius: 8, style: .continuous).stroke(NtrpColors.sidebarStroke, lineWidth: 1))
                .clipShape(RoundedRectangle(cornerRadius: 8, style: .continuous))
            }

            if let error = surface.errorMessage, !error.isEmpty {
                SettingsInlineError(title: "Could not load providers", message: error)
            }

            if surface.isLoading && sorted.isEmpty {
                Text("Loading providers...")
                    .font(.system(size: 14))
                    .foregroundStyle(NtrpColors.faint)
            } else if surface.errorMessage != nil && sorted.isEmpty {
                SettingsConnectionHint()
            } else {
                ProviderReadinessCard(providers: sorted, chatModel: store.serverConfig?.chatModel)

                ProviderSectionView(
                    title: "Ready providers",
                    detail: "\(connected.count) connected",
                    empty: "No model providers are connected yet.",
                    providers: connected,
                    editingID: $providerEditingID,
                    apiKey: $providerAPIKey,
                    pendingID: $providerPendingID,
                    surface: surface,
                    config: store.config
                )

                ProviderSectionView(
                    title: "Set up more",
                    detail: "\(setup.count) available",
                    empty: "All configured providers are ready.",
                    providers: setup,
                    editingID: $providerEditingID,
                    apiKey: $providerAPIKey,
                    pendingID: $providerPendingID,
                    surface: surface,
                    config: store.config
                )
            }
        }
        .padding(.top, 2)
    }

    private var sortedProviders: [JSONValue] {
        let rank: [String: Int] = [
            "openai-codex": 0,
            "openai": 1,
            "anthropic": 2,
            "google": 3,
            "openrouter": 4,
            "custom": 5,
        ]
        return surface.providers.sorted {
            let left = $0.objectValue?.string("id") ?? ""
            let right = $1.objectValue?.string("id") ?? ""
            return (rank[left] ?? 99, left) < (rank[right] ?? 99, right)
        }
    }

    private var integrationsTab: some View {
        IntegrationsSettingsView(
            services: surface.services,
            gmailAccounts: surface.gmailAccounts,
            config: surface.serverConfig,
            pendingID: $integrationPendingID,
            editingID: $serviceEditingID,
            serviceKey: $serviceKey,
            surface: surface,
            appConfig: store.config,
            selectedSessionID: store.selectedSessionID,
            patchGoogle: patchGoogleIntegration
        )
        .padding(.top, 2)
    }

    private var modelsTab: some View {
        VStack(alignment: .leading, spacing: 18) {
            Text("The chat model and reasoning level live in the composer. These defaults are for background work.")
                .font(.system(size: 13))
                .lineSpacing(3)
                .foregroundStyle(NtrpColors.muted)
                .padding(.horizontal, 14)
                .padding(.vertical, 12)
                .frame(maxWidth: .infinity, alignment: .leading)
                .background(NtrpColors.row.opacity(0.32))
                .overlay(RoundedRectangle(cornerRadius: 10, style: .continuous).stroke(NtrpColors.sidebarStroke, lineWidth: 1))
                .clipShape(RoundedRectangle(cornerRadius: 10, style: .continuous))

            if surface.serverConfig == nil || surface.models == nil {
                SettingsInlineError(
                    title: "Couldn't load models",
                    message: "The server is reachable, but model metadata did not load. Check provider setup, then refresh."
                )
                reloadButton
            } else {
                VStack(spacing: 0) {
                    ModelSettingsSection(
                        title: "Research",
                        description: "Used by research-style sub-agents and deeper investigations.",
                        configKey: "research_model",
                        config: surface.serverConfig,
                        models: surface.models,
                        savingKey: $modelSavingKey,
                        onPatch: patchModelConfig
                    )
                    Divider().overlay(NtrpColors.sidebarStroke)
                    ModelSettingsSection(
                        title: "Memory",
                        description: "Fact extraction and pattern consolidation.",
                        configKey: "memory_model",
                        config: surface.serverConfig,
                        models: surface.models,
                        savingKey: $modelSavingKey,
                        onPatch: patchModelConfig
                    )
                }
            }
        }
        .padding(.top, 2)
    }

    private var agentTab: some View {
        AgentSettingsView(config: surface.serverConfig) { patch in
            patchSettingsConfig(patch)
        }
        .padding(.top, 2)
    }

    private var contextTab: some View {
        ContextSettingsView(config: surface.serverConfig) { patch in
            patchSettingsConfig(patch)
        }
        .padding(.top, 2)
    }

    private var toolsTab: some View {
        ToolOverridesView(
            tools: surface.tools,
            config: surface.serverConfig,
            query: $toolQuery,
            savingName: $toolSavingName,
            onPatch: patchToolOverrides
        )
        .padding(.top, 2)
    }

    private var mcpTab: some View {
        MCPSettingsView(
            servers: surface.mcpServers,
            serverConfig: surface.serverConfig,
            surface: surface,
            appConfig: store.config,
            selectedSessionID: store.selectedSessionID,
            savingName: $mcpSavingName,
            onToolDecision: patchToolOverrides
        )
        .padding(.top, 2)
    }

    private var appearanceTab: some View {
        AppearanceSettingsView()
            .padding(.top, 2)
    }

    private func mcpConfigJSON(name: String, fallback object: [String: JSONValue]) -> String {
        if let config = surface.serverConfig?.value(for: "mcp_servers", name) {
            return config.prettyPrinted()
        }
        var config: [String: JSONValue] = [:]
        for key in ["transport", "command", "args", "url", "auth", "enabled"] {
            if let value = object[key], value != .null {
                config[key] = value
            }
        }
        return JSONValue.object(config).prettyPrinted()
    }

    private func mcpAllowedToolsText(name: String) -> String {
        guard let config = surface.serverConfig?.value(for: "mcp_servers", name),
              let tools = config.objectValue?.array("tools"),
              !tools.isEmpty
        else {
            return ""
        }
        return tools.map(\.display).joined(separator: "\n")
    }

    private func patchModelConfig(_ patch: [String: JSONValue]) {
        modelSavingKey = patch.keys.sorted().joined(separator: ":")
        Task {
            _ = await surface.patchConfig(config: store.config, bodyText: JSONValue.object(patch).prettyPrinted())
            await surface.reload(config: store.config, sessionID: store.selectedSessionID)
            await store.reload()
            modelSavingKey = nil
        }
    }

    private func patchToolOverrides(toolName: String, overrides: [String: JSONValue]) {
        toolSavingName = toolName
        Task {
            _ = await surface.patchConfig(
                config: store.config,
                bodyText: JSONValue.object(["tool_overrides": .object(overrides)]).prettyPrinted()
            )
            await surface.reload(config: store.config, sessionID: store.selectedSessionID)
            await store.reload()
            toolSavingName = nil
        }
    }

    private func patchGoogleIntegration(_ enabled: Bool) {
        integrationPendingID = "google"
        Task {
            _ = await surface.patchConfig(
                config: store.config,
                bodyText: JSONValue.object(["integrations": .object(["google": .bool(enabled)])]).prettyPrinted()
            )
            await surface.reload(config: store.config, sessionID: store.selectedSessionID)
            await store.reload()
            integrationPendingID = nil
        }
    }

    private func patchSettingsConfig(_ patch: [String: JSONValue]) {
        Task {
            _ = await surface.patchConfig(config: store.config, bodyText: JSONValue.object(patch).prettyPrinted())
            await surface.reload(config: store.config, sessionID: store.selectedSessionID)
            await store.reload()
        }
    }
}

private struct SettingsScrollTopPreferenceKey: PreferenceKey {
    static var defaultValue: CGFloat = 0

    static func reduce(value: inout CGFloat, nextValue: () -> CGFloat) {
        value = nextValue()
    }
}

struct SettingsSidebarView: View {
    @Binding var activeTab: SettingsTab

    var body: some View {
        VStack(alignment: .leading, spacing: 0) {
            Color.clear
                .frame(height: 22)

            ScrollView {
                VStack(spacing: 1) {
                    ForEach(SettingsTab.allCases) { tab in
                        SettingsSidebarRow(tab: tab, isActive: activeTab == tab) {
                            activeTab = tab
                        }
                    }
                }
                .padding(.horizontal, 10)
                .padding(.top, 8)
                .padding(.bottom, 12)
            }
            .scrollIndicators(.hidden)
        }
        .frame(maxWidth: .infinity, maxHeight: .infinity)
    }
}

private struct SettingsSidebarRow: View {
    let tab: SettingsTab
    let isActive: Bool
    let action: () -> Void
    @State private var hovering = false

    var body: some View {
        Button(action: action) {
            HStack(spacing: 8) {
                Image(systemName: tab.icon)
                    .font(.system(size: 16, weight: .medium))
                    .frame(width: 16, height: 16)
                Text(tab.title)
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

private struct ModelSettingsSection: View {
    let title: String
    let description: String
    let configKey: String
    let config: JSONValue?
    let models: JSONValue?
    @Binding var savingKey: String?
    let onPatch: ([String: JSONValue]) -> Void

    private var currentModel: String {
        config?.value(for: configKey)?.stringValue ?? ""
    }

    private var currentReasoning: String? {
        guard let current = config?.value(for: configKey)?.stringValue,
              let efforts = config?.value(for: "model_reasoning_efforts")?.objectValue
        else {
            return nil
        }
        return efforts[current]?.stringValue
    }

    private var groups: [[String: JSONValue]] {
        guard let source = models?.value(for: "groups")?.arrayValue, !source.isEmpty else {
            let modelValues = models?.value(for: "models")?.arrayValue ?? []
            return [["provider": .string("all"), "models": .array(modelValues)]]
        }
        return source.compactMap(\.objectValue)
    }

    private var reasoningEfforts: [String] {
        guard let current = config?.value(for: configKey)?.stringValue,
              let efforts = models?.value(for: "reasoning_efforts", current)?.arrayValue
        else {
            return []
        }
        return efforts.map(\.display)
    }

    var body: some View {
        VStack(alignment: .leading, spacing: 10) {
            VStack(alignment: .leading, spacing: 3) {
                Text(title)
                    .font(.system(size: 15, weight: .medium))
                    .foregroundStyle(NtrpColors.text)
                Text(description)
                    .font(.system(size: 12))
                    .foregroundStyle(NtrpColors.faint)
                    .lineLimit(2)
            }

            HStack(spacing: 8) {
                Menu {
                    ForEach(groups.indices, id: \.self) { index in
                        let group = groups[index]
                        Section(group.string("provider") ?? "models") {
                            ForEach(modelIDs(in: group), id: \.self) { model in
                                Button {
                                    guard model != currentModel else { return }
                                    onPatch([configKey: .string(model)])
                                } label: {
                                    HStack {
                                        Text(model)
                                        if model == currentModel {
                                            Image(systemName: "checkmark")
                                        }
                                    }
                                }
                            }
                        }
                    }
                } label: {
                    HStack(spacing: 8) {
                        Text(savingKey == configKey ? "Saving..." : (currentModel.isEmpty ? "Select model" : currentModel))
                            .font(.system(size: 13, weight: .medium, design: .monospaced))
                            .lineLimit(1)
                        Spacer(minLength: 8)
                        Image(systemName: "chevron.down")
                            .font(.system(size: 10, weight: .semibold))
                            .foregroundStyle(NtrpColors.faint)
                    }
                    .foregroundStyle(NtrpColors.text)
                    .padding(.horizontal, 11)
                    .frame(height: 34)
                    .frame(maxWidth: .infinity)
                    .background(NtrpColors.row.opacity(0.42))
                    .overlay(RoundedRectangle(cornerRadius: 9, style: .continuous).stroke(NtrpColors.sidebarStroke, lineWidth: 1))
                    .clipShape(RoundedRectangle(cornerRadius: 9, style: .continuous))
                }
                .buttonStyle(.plain)
                .disabled(savingKey != nil)

                Menu {
                    Button("None") {
                        onPatch(["reasoning_model": .string(currentModel), "reasoning_effort": .null])
                    }
                    ForEach(reasoningEfforts, id: \.self) { effort in
                        Button {
                            onPatch(["reasoning_model": .string(currentModel), "reasoning_effort": .string(effort)])
                        } label: {
                            HStack {
                                Text(effort)
                                if effort == currentReasoning {
                                    Image(systemName: "checkmark")
                                }
                            }
                        }
                    }
                } label: {
                    HStack(spacing: 7) {
                        Image(systemName: "brain")
                            .font(.system(size: 13, weight: .medium))
                        Text(currentReasoning ?? "reasoning")
                            .font(.system(size: 13, weight: .medium))
                            .lineLimit(1)
                        Image(systemName: "chevron.down")
                            .font(.system(size: 10, weight: .semibold))
                            .foregroundStyle(NtrpColors.faint)
                    }
                    .foregroundStyle(NtrpColors.muted)
                    .padding(.horizontal, 10)
                    .frame(height: 34)
                    .background(NtrpColors.row.opacity(0.42))
                    .overlay(RoundedRectangle(cornerRadius: 9, style: .continuous).stroke(NtrpColors.sidebarStroke, lineWidth: 1))
                    .clipShape(RoundedRectangle(cornerRadius: 9, style: .continuous))
                }
                .buttonStyle(.plain)
                .disabled(savingKey != nil || currentModel.isEmpty)
            }
        }
        .padding(.vertical, 14)
    }

    private func modelIDs(in group: [String: JSONValue]) -> [String] {
        group.array("models").compactMap { value in
            if let id = value.stringValue { return id }
            return value.objectValue?.string("id")
        }
    }
}

private struct ToolOverridesView: View {
    let tools: [JSONValue]
    let config: JSONValue?
    @Binding var query: String
    @Binding var savingName: String?
    let onPatch: (String, [String: JSONValue]) -> Void

    private var overrides: [String: JSONValue] {
        config?.value(for: "tool_overrides")?.objectValue ?? [:]
    }

    private var filteredTools: [JSONValue] {
        let needle = query.trimmingCharacters(in: .whitespacesAndNewlines).lowercased()
        let base = tools.filter { $0.objectValue?.string("source") != "mcp" }
        guard !needle.isEmpty else { return base }
        return base.filter { tool in
            guard let object = tool.objectValue else { return false }
            let haystack = [
                object.string("name"),
                object.string("display_name"),
                object.string("description"),
                object.string("source"),
            ]
            .compactMap { $0 }
            .joined(separator: " ")
            .lowercased()
            return haystack.contains(needle)
        }
    }

    private var groups: [(String, [JSONValue])] {
        Dictionary(grouping: filteredTools) { tool in
            tool.objectValue?.string("source") ?? "unknown"
        }
        .map { ($0.key, $0.value) }
        .sorted { $0.0 < $1.0 }
    }

    var body: some View {
        VStack(alignment: .leading, spacing: 16) {
            HStack(alignment: .top, spacing: 12) {
                Text("Override tool approval behavior. Denied tools are hidden from the agent and blocked at execution.")
                    .font(.system(size: 14))
                    .lineSpacing(3)
                    .foregroundStyle(NtrpColors.muted)
                    .frame(maxWidth: 520, alignment: .leading)
                Spacer()
                TextField("Search tools", text: $query)
                    .textFieldStyle(.plain)
                    .font(.system(size: 13))
                    .padding(.horizontal, 10)
                    .frame(width: 220, height: 32)
                    .background(NtrpColors.row.opacity(0.36))
                    .overlay(RoundedRectangle(cornerRadius: 8, style: .continuous).stroke(NtrpColors.sidebarStroke, lineWidth: 1))
                    .clipShape(RoundedRectangle(cornerRadius: 8, style: .continuous))
            }

            if tools.isEmpty {
                Text("Loading tools...")
                    .font(.system(size: 13))
                    .foregroundStyle(NtrpColors.faint)
            } else {
                VStack(alignment: .leading, spacing: 14) {
                    ForEach(groups, id: \.0) { source, items in
                        VStack(alignment: .leading, spacing: 8) {
                            Text("\(formatSource(source)) (\(items.count))".uppercased())
                                .font(.system(size: 11, weight: .semibold))
                                .tracking(1.0)
                                .foregroundStyle(NtrpColors.faint)
                                .padding(.horizontal, 2)

                            VStack(spacing: 0) {
                                ForEach(items) { tool in
                                    ToolOverrideRow(
                                        tool: tool,
                                        overrides: overrides,
                                        saving: savingName == tool.objectValue?.string("name"),
                                        onChange: applyDecision
                                    )
                                    if tool.id != items.last?.id {
                                        Divider().overlay(NtrpColors.sidebarStroke)
                                    }
                                }
                            }
                            .background(NtrpColors.row.opacity(0.20))
                            .overlay(RoundedRectangle(cornerRadius: 10, style: .continuous).stroke(NtrpColors.sidebarStroke, lineWidth: 1))
                            .clipShape(RoundedRectangle(cornerRadius: 10, style: .continuous))
                        }
                    }
                }
            }
        }
    }

    private func applyDecision(tool: JSONValue, decision: String) {
        guard let object = tool.objectValue, let name = object.string("name") else { return }
        var next = overrides
        if decision == baseDecision(tool) {
            next.removeValue(forKey: name)
        } else {
            next[name] = .string(decision)
        }
        onPatch(name, next)
    }

    private func baseDecision(_ tool: JSONValue) -> String {
        tool.objectValue?.value("policy", "requires_approval")?.boolValue == true ? "ask" : "approve"
    }

    private func formatSource(_ source: String) -> String {
        source.trimmingCharacters(in: CharacterSet(charactersIn: "_")).replacingOccurrences(of: "_", with: " ")
    }
}

private struct IntegrationsSettingsView: View {
    let services: [JSONValue]
    let gmailAccounts: [JSONValue]
    let config: JSONValue?
    @Binding var pendingID: String?
    @Binding var editingID: String?
    @Binding var serviceKey: String
    @ObservedObject var surface: SurfaceStore
    let appConfig: AppConfig
    let selectedSessionID: String?
    let patchGoogle: (Bool) -> Void

    private var googleEnabled: Bool {
        config?.value(for: "google_enabled")?.boolValue ?? false
    }

    private var slackServices: [JSONValue] {
        services.filter { service in
            service.objectValue?.string("id")?.hasPrefix("slack_") == true
        }
    }

    private var connectedSlack: [JSONValue] {
        slackServices.filter { $0.objectValue?.bool("connected") == true }
    }

    private var setupSlack: [JSONValue] {
        slackServices.filter { $0.objectValue?.bool("connected") != true }
    }

    private var googleReady: Bool {
        googleEnabled && !gmailAccounts.isEmpty
    }

    var body: some View {
        VStack(alignment: .leading, spacing: 18) {
            HStack(alignment: .top, spacing: 12) {
                Text("Connect the data and action providers ntrp can use as tools. Model providers stay in Providers; MCP servers stay in MCP.")
                    .font(.system(size: 14))
                    .lineSpacing(3)
                    .foregroundStyle(NtrpColors.muted)
                    .frame(maxWidth: 540, alignment: .leading)
                Spacer()
                Button {
                    Task { await surface.reload(config: appConfig, sessionID: selectedSessionID) }
                } label: {
                    Label("Refresh", systemImage: surface.isLoading ? "arrow.clockwise.circle" : "arrow.clockwise")
                        .font(.system(size: 13, weight: .medium))
                        .padding(.horizontal, 10)
                        .frame(height: 32)
                }
                .buttonStyle(.plain)
                .background(NtrpColors.row.opacity(0.42))
                .overlay(RoundedRectangle(cornerRadius: 8, style: .continuous).stroke(NtrpColors.sidebarStroke, lineWidth: 1))
                .clipShape(RoundedRectangle(cornerRadius: 8, style: .continuous))
            }

            IntegrationReadinessCard(
                googleReady: googleReady,
                googleLabel: googleLabel,
                connectedSlackCount: connectedSlack.count
            )

            GoogleIntegrationCard(
                enabled: googleEnabled,
                accounts: gmailAccounts,
                pendingID: $pendingID,
                surface: surface,
                appConfig: appConfig,
                selectedSessionID: selectedSessionID,
                patchGoogle: patchGoogle
            )

            SlackIntegrationCard(
                connected: connectedSlack,
                setup: setupSlack,
                pendingID: $pendingID,
                editingID: $editingID,
                serviceKey: $serviceKey,
                surface: surface,
                appConfig: appConfig,
                selectedSessionID: selectedSessionID
            )
        }
    }

    private var googleLabel: String {
        if googleReady { return "\(gmailAccounts.count) account\(gmailAccounts.count == 1 ? "" : "s")" }
        if googleEnabled { return "enabled, no account" }
        return "disabled"
    }
}

private struct AgentSettingsView: View {
    let config: JSONValue?
    let onPatch: ([String: JSONValue]) -> Void
    @State private var maxDepth = ""
    @State private var saving = false

    var body: some View {
        VStack(alignment: .leading, spacing: 18) {
            if config == nil {
                Text("Loading agent settings...")
                    .font(.system(size: 13))
                    .foregroundStyle(NtrpColors.faint)
            } else {
                SettingsNumberEditor(
                    label: "Max sub-agent depth",
                    help: "How deep ntrp will spawn sub-agents before refusing to recurse further.",
                    suffix: nil,
                    text: $maxDepth,
                    min: 1,
                    max: 16
                )

                HStack {
                    Spacer()
                    Button(saving ? "Saving..." : "Save changes") {
                        guard let value = Int(maxDepth) else { return }
                        saving = true
                        onPatch(["max_depth": .number(Double(value))])
                        Task { @MainActor in saving = false }
                    }
                    .buttonStyle(.borderedProminent)
                    .controlSize(.small)
                    .disabled(Int(maxDepth) == nil || saving)
                }
            }
        }
        .onAppear { sync() }
        .onChange(of: config) { _, _ in sync() }
    }

    private func sync() {
        guard let value = config?.value(for: "max_depth")?.display else { return }
        maxDepth = value
    }
}

private struct AppearanceSettingsView: View {
    private static let defaultQuickShortcut = "CommandOrControl+Shift+Space"

    @AppStorage("ntrp.theme") private var theme = "system"
    @AppStorage("ntrp.palette") private var palette = "graphite"
    @AppStorage("ntrp.showReasoningInChat") private var showReasoning = true
    @AppStorage("ntrp.quickCaptureShortcut") private var quickShortcut = "CommandOrControl+Shift+Space"
    @AppStorage("ntrp.thinkingIntensity") private var thinkingIntensity = "normal"
    @AppStorage("ntrp.thinkingAnimation") private var thinkingAnimation = "comet"
    @AppStorage("ntrp.material") private var material = "linen"
    @AppStorage("ntrp.glassTint") private var glassTint = 42.0
    @AppStorage("ntrp.glassBlur") private var glassBlur = 12.0
    @AppStorage("ntrp.glassSaturate") private var glassSaturate = 140.0
    @AppStorage("ntrp.glassRim") private var glassRim = 42.0
    @State private var recordingShortcut = false
    @State private var shortcutMonitor: Any?
    @State private var previousShortcutForRecording: String?

    private let palettes = [
        ("warm", "Warm", Color(red: 0.11, green: 0.11, blue: 0.10), Color(red: 0.85, green: 0.44, blue: 0.17)),
        ("graphite", "Graphite", Color(red: 0.06, green: 0.07, blue: 0.07), Color(red: 0.33, green: 0.84, blue: 0.75)),
        ("raycast", "Raycast", Color(red: 0.10, green: 0.10, blue: 0.10), Color(red: 1.00, green: 0.39, blue: 0.39)),
        ("notion", "Notion", Color(red: 0.10, green: 0.10, blue: 0.10), Color.white),
    ]

    private let variants: [(String, String, String)] = [
        ("comet", "Comet", "Single arc travels around the rim"),
        ("breath", "Breath", "Wide diffuse halo that breathes slowly"),
        ("hue-cycle", "Border tint", "Border color drifts toward accent"),
        ("send-orbit", "Send orbit", "Spinner around the send button only"),
    ]

    var body: some View {
        VStack(alignment: .leading, spacing: 22) {
            settingsRail {
                AppearanceRow(title: "Mode", hint: "Light, Dark, or follow your system preference.") {
                    Picker("", selection: $theme) {
                        Label("Light", systemImage: "sun.max").tag("light")
                        Label("Dark", systemImage: "moon").tag("dark")
                        Label("System", systemImage: "display").tag("system")
                    }
                    .labelsHidden()
                    .pickerStyle(.segmented)
                    .frame(width: 260)
                }
                AppearanceRow(title: "Palette", hint: "Color scheme used across the app.") {
                    Menu {
                        ForEach(palettes, id: \.0) { item in
                            Button(item.1) { palette = item.0 }
                        }
                    } label: {
                        HStack(spacing: 8) {
                            paletteIcon
                            Text(currentPalette.1)
                            Image(systemName: "chevron.down")
                                .font(.system(size: 11, weight: .semibold))
                        }
                        .font(.system(size: 13, weight: .medium))
                        .foregroundStyle(NtrpColors.text)
                        .padding(.horizontal, 8)
                        .frame(height: 32)
                        .background(NtrpColors.row.opacity(0.34))
                        .overlay(RoundedRectangle(cornerRadius: 8, style: .continuous).stroke(NtrpColors.sidebarStroke, lineWidth: 1))
                        .clipShape(RoundedRectangle(cornerRadius: 8, style: .continuous))
                    }
                    .menuStyle(.borderlessButton)
                }
                AppearanceRow(title: "Reasoning in chat", hint: "Show or hide reasoning rows. Tool calls stay visible.") {
                    Toggle("", isOn: $showReasoning)
                        .toggleStyle(.switch)
                        .labelsHidden()
                        .controlSize(.small)
                }
            }

            settingsRail {
                AppearanceRow(title: "Quick capture shortcut", hint: "Global hotkey to summon the floating composer from anywhere. Enter creates a new session and sends the message.") {
                    HStack(spacing: 8) {
                        Button {
                            startShortcutRecording()
                        } label: {
                            HStack(spacing: 8) {
                                Image(systemName: "keyboard")
                                    .foregroundStyle(recordingShortcut ? NtrpColors.accent : NtrpColors.faint)
                                Text(recordingShortcut ? "Press shortcut..." : quickShortcut)
                                    .font(.system(size: 13, weight: .medium, design: .monospaced))
                                    .foregroundStyle(recordingShortcut ? NtrpColors.accent : NtrpColors.text)
                                    .lineLimit(1)
                            }
                            .padding(.horizontal, 10)
                            .frame(width: 236, height: 32, alignment: .leading)
                            .background(NtrpColors.row.opacity(recordingShortcut ? 0.50 : 0.34))
                            .overlay(RoundedRectangle(cornerRadius: 8, style: .continuous).stroke(recordingShortcut ? NtrpColors.accent.opacity(0.55) : NtrpColors.sidebarStroke, lineWidth: 1))
                            .clipShape(RoundedRectangle(cornerRadius: 8, style: .continuous))
                        }
                        .buttonStyle(.plain)

                        Button("Reset") {
                            quickShortcut = Self.defaultQuickShortcut
                            stopShortcutRecording(restorePrevious: false)
                        }
                        .buttonStyle(.plain)
                        .font(.system(size: 12, weight: .medium))
                        .foregroundStyle(NtrpColors.muted)
                    }
                }
            }

            settingsRail {
                AppearanceRow(title: "Thinking indicator", hint: "Shown on the composer while the agent is running but has not yet streamed its first token.") {
                    Picker("", selection: $thinkingIntensity) {
                        Text("Subtle").tag("subtle")
                        Text("Normal").tag("normal")
                        Text("Strong").tag("strong")
                    }
                    .labelsHidden()
                    .pickerStyle(.segmented)
                    .frame(width: 220)
                }

                LazyVGrid(columns: [GridItem(.adaptive(minimum: 190), spacing: 8)], spacing: 8) {
                    ForEach(variants, id: \.0) { variant in
                        AppearanceVariantCard(
                            id: variant.0,
                            title: variant.1,
                            hint: variant.2,
                            selected: thinkingAnimation == variant.0
                        ) {
                            thinkingAnimation = variant.0
                        }
                    }
                }
                .padding(12)
            }

            settingsRail {
                AppearanceRow(title: "Glass material", hint: "Translucent surfaces with backdrop blur. Off = Linen - solid panels with a hairline ring.") {
                    Toggle("", isOn: Binding(
                        get: { material == "glass" },
                        set: { material = $0 ? "glass" : "linen" }
                    ))
                    .toggleStyle(.switch)
                    .labelsHidden()
                    .controlSize(.small)
                }
                if material == "glass" {
                    AppearanceSliderRow(title: "Tint", hint: "Opacity of the surface color over the backdrop.", value: $glassTint, range: 0...100, unit: "%")
                    AppearanceSliderRow(title: "Blur", hint: "Backdrop blur radius.", value: $glassBlur, range: 0...18, unit: "px")
                    AppearanceSliderRow(title: "Saturate", hint: "Color intensity pulled from behind the surface.", value: $glassSaturate, range: 0...250, unit: "%")
                }
                AppearanceSliderRow(title: "Rim", hint: "Top-edge specular highlight strength.", value: $glassRim, range: 0...100, unit: "%")
                HStack {
                    Spacer()
                    Button("Reset to defaults") {
                        material = "linen"
                        glassTint = 42
                        glassBlur = 12
                        glassSaturate = 140
                        glassRim = 42
                    }
                    .buttonStyle(.plain)
                    .font(.system(size: 12, weight: .medium))
                    .foregroundStyle(NtrpColors.muted)
                    .padding(.horizontal, 14)
                    .padding(.vertical, 10)
                }
            }
        }
        .onDisappear {
            stopShortcutRecording(restorePrevious: true)
        }
    }

    private func startShortcutRecording() {
        stopShortcutRecording(restorePrevious: true)
        previousShortcutForRecording = quickShortcut
        quickShortcut = ""
        recordingShortcut = true
        shortcutMonitor = NSEvent.addLocalMonitorForEvents(matching: .keyDown) { event in
            if event.keyCode == 53 {
                stopShortcutRecording(restorePrevious: true)
                return nil
            }
            if let accelerator = accelerator(from: event) {
                quickShortcut = accelerator
                stopShortcutRecording(restorePrevious: false)
            }
            return nil
        }
    }

    private func stopShortcutRecording(restorePrevious: Bool = false) {
        if restorePrevious,
           recordingShortcut,
           let previousShortcutForRecording,
           quickShortcut.isEmpty
        {
            quickShortcut = previousShortcutForRecording
        }
        recordingShortcut = false
        previousShortcutForRecording = nil
        if let shortcutMonitor {
            NSEvent.removeMonitor(shortcutMonitor)
            self.shortcutMonitor = nil
        }
    }

    private func accelerator(from event: NSEvent) -> String? {
        let flags = event.modifierFlags.intersection([.command, .control, .option, .shift])
        guard !flags.isEmpty, let key = keyName(for: event) else { return nil }

        var parts: [String] = []
        if flags.contains(.command) {
            parts.append("CommandOrControl")
        } else if flags.contains(.control) {
            parts.append("Control")
        }
        if flags.contains(.option) { parts.append("Alt") }
        if flags.contains(.shift) { parts.append("Shift") }
        parts.append(key)
        return parts.joined(separator: "+")
    }

    private func keyName(for event: NSEvent) -> String? {
        if event.keyCode == 49 { return "Space" }
        guard let scalar = event.charactersIgnoringModifiers?.lowercased().unicodeScalars.first,
              scalar.value >= 97,
              scalar.value <= 122
        else { return nil }
        return String(Character(scalar)).uppercased()
    }

    private func settingsRail<Content: View>(@ViewBuilder content: () -> Content) -> some View {
        VStack(spacing: 0) {
            content()
        }
        .background(NtrpColors.row.opacity(0.22))
        .overlay(RoundedRectangle(cornerRadius: 10, style: .continuous).stroke(NtrpColors.sidebarStroke, lineWidth: 1))
        .clipShape(RoundedRectangle(cornerRadius: 10, style: .continuous))
    }

    private var currentPalette: (String, String, Color, Color) {
        palettes.first { $0.0 == palette } ?? palettes[0]
    }

    private var paletteIcon: some View {
        Text("Aa")
            .font(.system(size: 11, weight: .semibold))
            .foregroundStyle(currentPalette.3)
            .frame(width: 22, height: 22)
            .background(currentPalette.2.opacity(0.18))
            .overlay(RoundedRectangle(cornerRadius: 6, style: .continuous).stroke(NtrpColors.sidebarStroke, lineWidth: 1))
            .clipShape(RoundedRectangle(cornerRadius: 6, style: .continuous))
    }
}

private struct AppearanceRow<Control: View>: View {
    let title: String
    let hint: String
    @ViewBuilder var control: Control

    var body: some View {
        HStack(alignment: .center, spacing: 16) {
            VStack(alignment: .leading, spacing: 3) {
                Text(title)
                    .font(.system(size: 15, weight: .medium))
                    .foregroundStyle(NtrpColors.text)
                Text(hint)
                    .font(.system(size: 13))
                    .foregroundStyle(NtrpColors.muted)
                    .lineLimit(2)
            }
            Spacer(minLength: 16)
            control
        }
        .padding(.horizontal, 14)
        .padding(.vertical, 12)
        .overlay(alignment: .bottom) {
            Rectangle()
                .fill(NtrpColors.sidebarStroke.opacity(0.55))
                .frame(height: 1)
        }
    }
}

private struct AppearanceSliderRow: View {
    let title: String
    let hint: String
    @Binding var value: Double
    let range: ClosedRange<Double>
    let unit: String

    var body: some View {
        AppearanceRow(title: title, hint: hint) {
            HStack(spacing: 10) {
                Slider(value: $value, in: range, step: 1)
                    .frame(width: 160)
                Text("\(Int(value.rounded()))\(unit)")
                    .font(.system(size: 13, design: .monospaced))
                    .foregroundStyle(NtrpColors.muted)
                    .frame(width: 52, alignment: .trailing)
            }
        }
    }
}

private struct AppearanceVariantCard: View {
    let id: String
    let title: String
    let hint: String
    let selected: Bool
    let onSelect: () -> Void

    var body: some View {
        Button(action: onSelect) {
            VStack(alignment: .leading, spacing: 9) {
                HStack(spacing: 8) {
                    Text("Ask anything...")
                        .font(.system(size: 12))
                        .foregroundStyle(NtrpColors.faint)
                    Spacer()
                    Image(systemName: id == "send-orbit" ? "arrow.up.circle.fill" : "arrow.up")
                        .font(.system(size: 16, weight: .semibold))
                        .foregroundStyle(selected ? NtrpColors.accent : NtrpColors.muted)
                }
                .padding(.horizontal, 10)
                .frame(height: 42)
                .background(NtrpColors.canvas.opacity(0.55))
                .overlay(RoundedRectangle(cornerRadius: 10, style: .continuous).stroke(selected ? NtrpColors.accent.opacity(0.7) : NtrpColors.sidebarStroke, lineWidth: 1))
                .clipShape(RoundedRectangle(cornerRadius: 10, style: .continuous))

                VStack(alignment: .leading, spacing: 2) {
                    Text(title)
                        .font(.system(size: 13, weight: .medium))
                        .foregroundStyle(NtrpColors.text)
                    Text(hint)
                        .font(.system(size: 12))
                        .foregroundStyle(NtrpColors.faint)
                        .lineLimit(2)
                }
            }
            .padding(10)
            .frame(maxWidth: .infinity, alignment: .leading)
            .background(selected ? NtrpColors.rowActive : NtrpColors.row.opacity(0.24))
            .overlay(RoundedRectangle(cornerRadius: 10, style: .continuous).stroke(selected ? NtrpColors.sidebarStroke.opacity(1) : NtrpColors.sidebarStroke.opacity(0.55), lineWidth: 1))
            .clipShape(RoundedRectangle(cornerRadius: 10, style: .continuous))
        }
        .buttonStyle(.plain)
    }
}

private struct ContextSettingsView: View {
    let config: JSONValue?
    let onPatch: ([String: JSONValue]) -> Void
    @State private var compressionThreshold = ""
    @State private var maxMessages = ""
    @State private var keepRatio = ""
    @State private var summaryMaxTokens = ""
    @State private var consolidationInterval = ""
    @State private var saving = false

    var body: some View {
        VStack(alignment: .leading, spacing: 18) {
            Text("Controls when the agent compresses its conversation history and how aggressively old turns are summarised away.")
                .font(.system(size: 14))
                .lineSpacing(3)
                .foregroundStyle(NtrpColors.muted)
                .frame(maxWidth: 440, alignment: .leading)

            if config == nil {
                Text("Loading context settings...")
                    .font(.system(size: 13))
                    .foregroundStyle(NtrpColors.faint)
            } else {
                SettingsNumberEditor(
                    label: "Compression threshold",
                    help: "Share of the model's context window used before older turns start being compressed.",
                    suffix: "%",
                    text: $compressionThreshold,
                    min: 10,
                    max: 100
                )
                SettingsNumberEditor(
                    label: "Max messages",
                    help: "Hard cap on the number of raw messages kept before compression kicks in.",
                    suffix: nil,
                    text: $maxMessages,
                    min: 10,
                    max: 1000
                )
                SettingsNumberEditor(
                    label: "Keep ratio",
                    help: "Share of recent messages preserved verbatim during compression.",
                    suffix: "%",
                    text: $keepRatio,
                    min: 0,
                    max: 100
                )
                SettingsNumberEditor(
                    label: "Summary max tokens",
                    help: "Upper bound on each compression summary.",
                    suffix: "tokens",
                    text: $summaryMaxTokens,
                    min: 256,
                    max: 8000
                )
                SettingsNumberEditor(
                    label: "Consolidation interval",
                    help: "How many user messages between memory consolidation passes.",
                    suffix: "messages",
                    text: $consolidationInterval,
                    min: 1,
                    max: 500
                )

                HStack {
                    Spacer()
                    Button(saving ? "Saving..." : "Save changes") {
                        guard let patch else { return }
                        saving = true
                        onPatch(patch)
                        Task { @MainActor in saving = false }
                    }
                    .buttonStyle(.borderedProminent)
                    .controlSize(.small)
                    .disabled(patch == nil || saving)
                }
            }
        }
        .onAppear { sync() }
        .onChange(of: config) { _, _ in sync() }
    }

    private var patch: [String: JSONValue]? {
        guard
            let thresholdPercent = Double(compressionThreshold),
            let maxMessagesValue = Int(maxMessages),
            let keepPercent = Double(keepRatio),
            let summaryValue = Int(summaryMaxTokens),
            let intervalValue = Int(consolidationInterval)
        else {
            return nil
        }
        return [
            "compression_threshold": .number(thresholdPercent / 100),
            "max_messages": .number(Double(maxMessagesValue)),
            "compression_keep_ratio": .number(keepPercent / 100),
            "summary_max_tokens": .number(Double(summaryValue)),
            "consolidation_interval": .number(Double(intervalValue)),
        ]
    }

    private func sync() {
        guard let config else { return }
        compressionThreshold = percentText(config.value(for: "compression_threshold"))
        maxMessages = config.value(for: "max_messages")?.display ?? ""
        keepRatio = percentText(config.value(for: "compression_keep_ratio"))
        summaryMaxTokens = config.value(for: "summary_max_tokens")?.display ?? ""
        consolidationInterval = config.value(for: "consolidation_interval")?.display ?? ""
    }

    private func percentText(_ value: JSONValue?) -> String {
        guard let value, let number = Double(value.display) else { return "" }
        return String(Int(round(number * 100)))
    }
}

private struct SettingsNumberEditor: View {
    let label: String
    let help: String
    let suffix: String?
    @Binding var text: String
    let min: Int
    let max: Int

    var body: some View {
        VStack(alignment: .leading, spacing: 6) {
            Text(label.uppercased())
                .font(.system(size: 12, weight: .medium))
                .tracking(1.0)
                .foregroundStyle(NtrpColors.muted)
            HStack(spacing: 8) {
                TextField("", text: $text)
                    .textFieldStyle(.plain)
                    .font(.system(size: 15))
                    .frame(width: 92)
                if let suffix {
                    Text(suffix)
                        .font(.system(size: 13))
                        .foregroundStyle(NtrpColors.faint)
                }
                Spacer()
                Stepper("", value: numericBinding, in: min...max)
                    .labelsHidden()
            }
            .padding(.horizontal, 12)
            .frame(height: 38)
            .background(NtrpColors.row.opacity(0.45))
            .overlay(RoundedRectangle(cornerRadius: 9, style: .continuous).stroke(NtrpColors.sidebarStroke, lineWidth: 1))
            .clipShape(RoundedRectangle(cornerRadius: 9, style: .continuous))
            Text(help)
                .font(.system(size: 13))
                .foregroundStyle(NtrpColors.faint)
        }
        .frame(maxWidth: 560, alignment: .leading)
    }

    private var numericBinding: Binding<Int> {
        Binding(
            get: { Swift.min(Swift.max(Int(text) ?? min, min), max) },
            set: { text = String($0) }
        )
    }
}

private struct IntegrationReadinessCard: View {
    let googleReady: Bool
    let googleLabel: String
    let connectedSlackCount: Int

    private var readyToolsCount: Int {
        (googleReady ? 1 : 0) + connectedSlackCount
    }

    var body: some View {
        HStack(alignment: .top, spacing: 10) {
            Image(systemName: readyToolsCount > 0 ? "checkmark.circle" : "exclamationmark.triangle")
                .font(.system(size: 17, weight: .medium))
                .foregroundStyle(readyToolsCount > 0 ? Color.green.opacity(0.82) : Color.orange.opacity(0.92))
                .frame(width: 20)
            VStack(alignment: .leading, spacing: 3) {
                Text(readyToolsCount > 0 ? "Tools ready" : "Connect tools")
                    .font(.system(size: 14, weight: .semibold))
                    .foregroundStyle(NtrpColors.text)
                Text("Google: \(googleLabel) · Slack: \(connectedSlackCount == 0 ? "none" : "\(connectedSlackCount)")")
                    .font(.system(size: 12))
                    .foregroundStyle(NtrpColors.muted)
                Text("Tool integrations are optional, but connected tools become available to the agent.")
                    .font(.system(size: 12))
                    .foregroundStyle(NtrpColors.faint)
            }
            Spacer(minLength: 0)
        }
        .padding(.horizontal, 12)
        .padding(.vertical, 10)
        .background((readyToolsCount > 0 ? Color.green : Color.orange).opacity(0.08))
        .overlay(RoundedRectangle(cornerRadius: 10, style: .continuous).stroke(NtrpColors.sidebarStroke, lineWidth: 1))
        .clipShape(RoundedRectangle(cornerRadius: 10, style: .continuous))
    }
}

private struct GoogleIntegrationCard: View {
    let enabled: Bool
    let accounts: [JSONValue]
    @Binding var pendingID: String?
    @ObservedObject var surface: SurfaceStore
    let appConfig: AppConfig
    let selectedSessionID: String?
    let patchGoogle: (Bool) -> Void

    var body: some View {
        VStack(spacing: 0) {
            HStack(alignment: .top, spacing: 12) {
                VStack(alignment: .leading, spacing: 5) {
                    HStack(spacing: 8) {
                        ZStack(alignment: .bottomTrailing) {
                            Image(systemName: "envelope")
                                .font(.system(size: 16, weight: .medium))
                            Image(systemName: "calendar")
                                .font(.system(size: 8, weight: .semibold))
                                .offset(x: 4, y: 3)
                        }
                        .foregroundStyle(enabled ? Color.green.opacity(0.84) : NtrpColors.muted)
                        .frame(width: 20, height: 18)
                        Text("Google Workspace")
                            .font(.system(size: 15, weight: .medium))
                            .foregroundStyle(NtrpColors.text)
                        Text(googleBadge)
                            .font(.system(size: 10, weight: .semibold))
                            .padding(.horizontal, 6)
                            .frame(height: 18)
                            .background(enabled ? Color.green.opacity(0.13) : NtrpColors.row.opacity(0.5))
                            .clipShape(Capsule())
                    }
                    Text("Gmail and Calendar share the same Google account token.")
                        .font(.system(size: 12))
                        .foregroundStyle(NtrpColors.faint)
                    Text(googleDetail)
                        .font(.system(size: 12, design: .monospaced))
                        .foregroundStyle(NtrpColors.muted)
                        .lineLimit(1)
                }

                Spacer(minLength: 10)

                Button(pendingID == "gmail:add" ? "Connecting..." : "Add account") {
                    pendingID = "gmail:add"
                    Task {
                        await surface.addGmail(config: appConfig)
                        if !enabled { patchGoogle(true) }
                        await surface.reload(config: appConfig, sessionID: selectedSessionID)
                        pendingID = nil
                    }
                }
                .buttonStyle(.bordered)
                .controlSize(.small)
                .disabled(pendingID != nil)

                Button(pendingID == "google" ? "Saving..." : enabled ? "Disable" : "Enable") {
                    patchGoogle(!enabled)
                }
                .buttonStyle(.bordered)
                .controlSize(.small)
                .disabled(pendingID != nil)
            }
            .padding(.horizontal, 14)
            .padding(.vertical, 12)

            if !accounts.isEmpty {
                VStack(spacing: 8) {
                    ForEach(accounts) { account in
                        GoogleAccountRow(
                            account: account,
                            pendingID: $pendingID,
                            surface: surface,
                            appConfig: appConfig,
                            selectedSessionID: selectedSessionID
                        )
                    }
                }
                .padding(.horizontal, 14)
                .padding(.vertical, 10)
                .background(NtrpColors.row.opacity(0.20))
            }
        }
        .background(NtrpColors.row.opacity(0.30))
        .overlay(RoundedRectangle(cornerRadius: 12, style: .continuous).stroke(NtrpColors.sidebarStroke, lineWidth: 1))
        .clipShape(RoundedRectangle(cornerRadius: 12, style: .continuous))
    }

    private var googleBadge: String {
        if enabled && !accounts.isEmpty { return "ready" }
        if enabled { return "setup" }
        return "paused"
    }

    private var googleDetail: String {
        if accounts.isEmpty { return "No accounts connected." }
        return "\(accounts.count) account\(accounts.count == 1 ? "" : "s") connected"
    }
}

private struct GoogleAccountRow: View {
    let account: JSONValue
    @Binding var pendingID: String?
    @ObservedObject var surface: SurfaceStore
    let appConfig: AppConfig
    let selectedSessionID: String?

    private var object: [String: JSONValue] { account.objectValue ?? [:] }
    private var tokenFile: String { object.string("token_file") ?? "" }
    private var pendingKey: String { "gmail:\(tokenFile)" }

    var body: some View {
        HStack(spacing: 10) {
            VStack(alignment: .leading, spacing: 3) {
                Text(object.string("email") ?? "Unknown account")
                    .font(.system(size: 13, weight: .medium))
                    .foregroundStyle(NtrpColors.text)
                    .lineLimit(1)
                Text(accountDetail)
                    .font(.system(size: 12))
                    .foregroundStyle(object.string("error") == nil ? NtrpColors.faint : Color.red.opacity(0.9))
                    .lineLimit(1)
            }
            Spacer()
            Button {
                pendingID = pendingKey
                Task {
                    await surface.removeGmail(config: appConfig, tokenFile: tokenFile)
                    await surface.reload(config: appConfig, sessionID: selectedSessionID)
                    pendingID = nil
                }
            } label: {
                Image(systemName: pendingID == pendingKey ? "clock" : "trash")
                    .font(.system(size: 13, weight: .medium))
                    .foregroundStyle(NtrpColors.muted)
                    .frame(width: 24, height: 24)
            }
            .buttonStyle(.plain)
            .disabled(pendingID != nil || tokenFile.isEmpty)
        }
    }

    private var accountDetail: String {
        if let error = object.string("error") { return error }
        if object.bool("has_send_scope") == true { return "Read, send, and calendar access" }
        return "Read and calendar access"
    }
}

private struct SlackIntegrationCard: View {
    let connected: [JSONValue]
    let setup: [JSONValue]
    @Binding var pendingID: String?
    @Binding var editingID: String?
    @Binding var serviceKey: String
    @ObservedObject var surface: SurfaceStore
    let appConfig: AppConfig
    let selectedSessionID: String?

    var body: some View {
        VStack(spacing: 0) {
            VStack(alignment: .leading, spacing: 5) {
                HStack(spacing: 8) {
                    Image(systemName: "message")
                        .font(.system(size: 16, weight: .medium))
                        .foregroundStyle(NtrpColors.muted)
                    Text("Slack")
                        .font(.system(size: 15, weight: .medium))
                        .foregroundStyle(NtrpColors.text)
                }
                Text("Token-backed Slack tools. OAuth MCP servers stay in the MCP tab.")
                    .font(.system(size: 12))
                    .foregroundStyle(NtrpColors.faint)
            }
            .frame(maxWidth: .infinity, alignment: .leading)
            .padding(.horizontal, 14)
            .padding(.vertical, 12)

            Divider().overlay(NtrpColors.sidebarStroke)

            VStack(alignment: .leading, spacing: 12) {
                ServiceGroup(title: "Ready", empty: "No Slack tokens connected.", services: connected, pendingID: $pendingID, editingID: $editingID, serviceKey: $serviceKey, surface: surface, appConfig: appConfig, selectedSessionID: selectedSessionID)
                ServiceGroup(title: "Set up", empty: "All Slack token services are connected.", services: setup, pendingID: $pendingID, editingID: $editingID, serviceKey: $serviceKey, surface: surface, appConfig: appConfig, selectedSessionID: selectedSessionID)
            }
            .padding(14)
        }
        .background(NtrpColors.row.opacity(0.30))
        .overlay(RoundedRectangle(cornerRadius: 12, style: .continuous).stroke(NtrpColors.sidebarStroke, lineWidth: 1))
        .clipShape(RoundedRectangle(cornerRadius: 12, style: .continuous))
    }
}

private struct ServiceGroup: View {
    let title: String
    let empty: String
    let services: [JSONValue]
    @Binding var pendingID: String?
    @Binding var editingID: String?
    @Binding var serviceKey: String
    @ObservedObject var surface: SurfaceStore
    let appConfig: AppConfig
    let selectedSessionID: String?

    var body: some View {
        VStack(alignment: .leading, spacing: 8) {
            Text(title.uppercased())
                .font(.system(size: 11, weight: .semibold))
                .tracking(1.0)
                .foregroundStyle(NtrpColors.faint)
            if services.isEmpty {
                Text(empty)
                    .font(.system(size: 13))
                    .foregroundStyle(NtrpColors.faint)
                    .padding(.horizontal, 10)
                    .frame(maxWidth: .infinity, minHeight: 36, alignment: .leading)
                    .background(NtrpColors.row.opacity(0.24))
                    .clipShape(RoundedRectangle(cornerRadius: 9, style: .continuous))
            } else {
                VStack(spacing: 8) {
                    ForEach(services) { service in
                        ServiceConnectionRow(service: service, pendingID: $pendingID, editingID: $editingID, serviceKey: $serviceKey, surface: surface, appConfig: appConfig, selectedSessionID: selectedSessionID)
                    }
                }
            }
        }
    }
}

private struct ServiceConnectionRow: View {
    let service: JSONValue
    @Binding var pendingID: String?
    @Binding var editingID: String?
    @Binding var serviceKey: String
    @ObservedObject var surface: SurfaceStore
    let appConfig: AppConfig
    let selectedSessionID: String?

    private var object: [String: JSONValue] { service.objectValue ?? [:] }
    private var id: String { object.string("id") ?? "" }
    private var connected: Bool { object.bool("connected") == true }
    private var readOnly: Bool { connected && object.bool("from_env") == true }

    var body: some View {
        VStack(spacing: 0) {
            HStack(spacing: 10) {
                Image(systemName: connected ? "checkmark.circle" : "key")
                    .font(.system(size: 15, weight: .medium))
                    .foregroundStyle(connected ? Color.green.opacity(0.84) : NtrpColors.faint)
                    .frame(width: 18)
                VStack(alignment: .leading, spacing: 3) {
                    Text(object.string("name") ?? id)
                        .font(.system(size: 13, weight: .medium))
                        .foregroundStyle(NtrpColors.text)
                    if let pill = connectionPill {
                        Text(pill)
                            .font(.system(size: 11, design: .monospaced))
                            .foregroundStyle(NtrpColors.muted)
                    }
                }
                Spacer()
                Button(actionLabel) {
                    if connected {
                        pendingID = id
                        Task {
                            await surface.disconnectService(config: appConfig, serviceID: id)
                            await surface.reload(config: appConfig, sessionID: selectedSessionID)
                            pendingID = nil
                        }
                    } else {
                        editingID = id
                        serviceKey = ""
                    }
                }
                .buttonStyle(.bordered)
                .controlSize(.small)
                .disabled(readOnly || pendingID != nil || id.isEmpty)
            }
            .padding(10)

            if editingID == id && !connected {
                HStack(spacing: 8) {
                    SecureField("Token", text: $serviceKey)
                        .textFieldStyle(.plain)
                        .font(.system(size: 13))
                        .padding(.horizontal, 10)
                        .frame(height: 34)
                        .background(NtrpColors.row.opacity(0.38))
                        .overlay(RoundedRectangle(cornerRadius: 9, style: .continuous).stroke(NtrpColors.sidebarStroke, lineWidth: 1))
                        .clipShape(RoundedRectangle(cornerRadius: 9, style: .continuous))
                    Button("Connect") {
                        let token = serviceKey.trimmingCharacters(in: .whitespacesAndNewlines)
                        guard !token.isEmpty else { return }
                        pendingID = id
                        Task {
                            await surface.connectService(config: appConfig, serviceID: id, apiKey: token)
                            await surface.reload(config: appConfig, sessionID: selectedSessionID)
                            pendingID = nil
                            editingID = nil
                            serviceKey = ""
                        }
                    }
                    .buttonStyle(.borderedProminent)
                    .controlSize(.small)
                    Button("Cancel") {
                        editingID = nil
                        serviceKey = ""
                    }
                    .buttonStyle(.bordered)
                    .controlSize(.small)
                }
                .padding(.horizontal, 10)
                .padding(.bottom, 10)
            }
        }
        .background(NtrpColors.row.opacity(0.28))
        .overlay(RoundedRectangle(cornerRadius: 10, style: .continuous).stroke(NtrpColors.sidebarStroke, lineWidth: 1))
        .clipShape(RoundedRectangle(cornerRadius: 10, style: .continuous))
    }

    private var actionLabel: String {
        if pendingID == id { return "Working..." }
        if readOnly { return "Configured separately" }
        return connected ? "Disconnect" : "Connect"
    }

    private var connectionPill: String? {
        if object.bool("from_env") == true { return "env" }
        if connected { return "token" }
        return nil
    }
}

private struct ToolOverrideRow: View {
    let tool: JSONValue
    let overrides: [String: JSONValue]
    let saving: Bool
    let onChange: (JSONValue, String) -> Void

    private var object: [String: JSONValue] { tool.objectValue ?? [:] }
    private var name: String { object.string("name") ?? tool.display }
    private var displayName: String { object.string("display_name") ?? name }
    private var description: String? { object.string("description") }
    private var action: String { object.value("policy", "action")?.display ?? "read" }
    private var current: String { overrides[name]?.stringValue ?? baseDecision }
    private var baseDecision: String {
        object.value("policy", "requires_approval")?.boolValue == true ? "ask" : "approve"
    }

    var body: some View {
        HStack(alignment: .top, spacing: 12) {
            VStack(alignment: .leading, spacing: 4) {
                HStack(spacing: 7) {
                    Text(displayName)
                        .font(.system(size: 14, weight: .medium))
                        .foregroundStyle(NtrpColors.text)
                        .lineLimit(1)
                    Text(action.uppercased())
                        .font(.system(size: 10, weight: .semibold))
                        .tracking(0.6)
                        .foregroundStyle(NtrpColors.faint)
                }
                Text(name)
                    .font(.system(size: 11, design: .monospaced))
                    .foregroundStyle(NtrpColors.faint)
                    .lineLimit(1)
                if let description, !description.isEmpty {
                    Text(description)
                        .font(.system(size: 12))
                        .foregroundStyle(NtrpColors.muted)
                        .lineLimit(2)
                }
            }

            Spacer(minLength: 10)

            HStack(spacing: 2) {
                ForEach(["approve", "ask", "deny"], id: \.self) { decision in
                    Button {
                        onChange(tool, decision)
                    } label: {
                        Text(decisionLabel(decision))
                            .font(.system(size: 12, weight: .medium))
                            .foregroundStyle(current == decision ? NtrpColors.text : NtrpColors.muted)
                            .padding(.horizontal, 8)
                            .frame(height: 26)
                            .background(current == decision ? NtrpColors.rowActive : Color.clear)
                            .clipShape(RoundedRectangle(cornerRadius: 7, style: .continuous))
                    }
                    .buttonStyle(.plain)
                    .disabled(saving)
                }
            }
            .padding(2)
            .background(NtrpColors.row.opacity(0.30))
            .overlay(RoundedRectangle(cornerRadius: 9, style: .continuous).stroke(NtrpColors.sidebarStroke, lineWidth: 1))
            .clipShape(RoundedRectangle(cornerRadius: 9, style: .continuous))
            .opacity(saving ? 0.55 : 1)
        }
        .padding(.horizontal, 12)
        .padding(.vertical, 10)
    }

    private func decisionLabel(_ value: String) -> String {
        value.prefix(1).uppercased() + value.dropFirst()
    }
}

private enum MCPSettingsMode: Equatable {
    case list
    case add
    case edit(String)
}

private struct MCPSettingsView: View {
    let servers: [JSONValue]
    let serverConfig: JSONValue?
    @ObservedObject var surface: SurfaceStore
    let appConfig: AppConfig
    let selectedSessionID: String?
    @Binding var savingName: String?
    let onToolDecision: (String, [String: JSONValue]) -> Void

    @State private var mode: MCPSettingsMode = .list

    private var editingServer: JSONValue? {
        guard case .edit(let name) = mode else { return nil }
        return servers.first { $0.objectValue?.string("name") == name }
    }

    var body: some View {
        Group {
            switch mode {
            case .list:
                serverList
            case .add:
                MCPServerForm(
                    mode: .add,
                    server: nil,
                    config: nil,
                    serverConfig: serverConfig,
                    surface: surface,
                    appConfig: appConfig,
                    selectedSessionID: selectedSessionID,
                    savingName: $savingName,
                    onClose: { mode = .list },
                    onSaved: { mode = .list },
                    onToolToggle: toggleTool,
                    onToolDecision: applyToolDecision
                )
            case .edit(let name):
                if let editingServer {
                    MCPServerForm(
                        mode: .edit,
                        server: editingServer,
                        config: serverConfig?.value(for: "mcp_servers", name),
                        serverConfig: serverConfig,
                        surface: surface,
                        appConfig: appConfig,
                        selectedSessionID: selectedSessionID,
                        savingName: $savingName,
                        onClose: { mode = .list },
                        onSaved: {},
                        onRemoved: { mode = .list },
                        onToolToggle: toggleTool,
                        onToolDecision: applyToolDecision
                    )
                } else {
                    serverList
                }
            }
        }
    }

    private var serverList: some View {
        VStack(alignment: .leading, spacing: 16) {
            Text("Connect external tools and data sources via Model Context Protocol.")
                .font(.system(size: 14))
                .foregroundStyle(NtrpColors.muted)
                .frame(maxWidth: 460, alignment: .leading)

            VStack(alignment: .leading, spacing: 8) {
                HStack {
                    Text("SERVERS")
                        .font(.system(size: 11, weight: .semibold))
                        .tracking(1.1)
                        .foregroundStyle(NtrpColors.faint)
                    Spacer()
                    Button {
                        mode = .add
                    } label: {
                        Label("Add server", systemImage: "plus")
                            .font(.system(size: 13, weight: .medium))
                            .padding(.horizontal, 10)
                            .frame(height: 30)
                    }
                    .buttonStyle(.borderedProminent)
                    .controlSize(.small)
                }

                if servers.isEmpty {
                    Text("No MCP servers yet.")
                        .font(.system(size: 13))
                        .foregroundStyle(NtrpColors.faint)
                        .frame(maxWidth: .infinity, minHeight: 72)
                        .background(NtrpColors.row.opacity(0.28))
                        .overlay(RoundedRectangle(cornerRadius: 10, style: .continuous).stroke(NtrpColors.sidebarStroke, lineWidth: 1))
                        .clipShape(RoundedRectangle(cornerRadius: 10, style: .continuous))
                } else {
                    VStack(spacing: 0) {
                        ForEach(Array(servers.enumerated()), id: \.element.id) { index, server in
                            MCPServerRow(
                                server: server,
                                savingName: $savingName,
                                onEdit: { name in mode = .edit(name) },
                                onToggle: toggleServer,
                                onAuthenticate: authenticateServer
                            )
                            if index < servers.count - 1 {
                                Divider().overlay(NtrpColors.sidebarStroke.opacity(0.7))
                            }
                        }
                    }
                    .background(NtrpColors.row.opacity(0.22))
                    .overlay(RoundedRectangle(cornerRadius: 10, style: .continuous).stroke(NtrpColors.sidebarStroke, lineWidth: 1))
                    .clipShape(RoundedRectangle(cornerRadius: 10, style: .continuous))
                }
            }
        }
    }

    private func toggleServer(_ name: String, enabled: Bool) {
        savingName = name
        Task {
            await surface.toggleMCP(config: appConfig, name: name, enabled: enabled)
            await surface.reload(config: appConfig, sessionID: selectedSessionID)
            savingName = nil
        }
    }

    private func authenticateServer(_ name: String) {
        savingName = name
        Task {
            await surface.startMCPOAuth(config: appConfig, name: name)
            await surface.reload(config: appConfig, sessionID: selectedSessionID)
            savingName = nil
        }
    }

    private func toggleTool(server: JSONValue, toolName: String, enabled: Bool) {
        guard let object = server.objectValue, let serverName = object.string("name") else { return }
        let next = object.array("tools")
            .compactMap { tool -> String? in
                guard let toolObject = tool.objectValue else { return nil }
                let name = toolObject.string("name") ?? tool.display
                if name == toolName { return enabled ? name : nil }
                return toolObject.bool("enabled") == true ? name : nil
            }
            .joined(separator: "\n")

        savingName = "\(serverName):tools"
        Task {
            await surface.updateMCPTools(config: appConfig, name: serverName, toolsText: next)
            await surface.reload(config: appConfig, sessionID: selectedSessionID)
            savingName = nil
        }
    }

    private func applyToolDecision(tool: JSONValue, decision: String) {
        guard let object = tool.objectValue else { return }
        let fullName = object.string("full_name") ?? object.string("name") ?? tool.display
        var overrides = serverConfig?.value(for: "tool_overrides")?.objectValue ?? [:]
        let base = object.value("policy", "requires_approval")?.boolValue == true ? "ask" : "approve"
        if decision == base {
            overrides.removeValue(forKey: fullName)
        } else {
            overrides[fullName] = .string(decision)
        }
        onToolDecision(fullName, overrides)
    }
}

private enum MCPServerFormMode {
    case add
    case edit
}

private struct MCPServerForm: View {
    let mode: MCPServerFormMode
    let server: JSONValue?
    let config: JSONValue?
    let serverConfig: JSONValue?
    @ObservedObject var surface: SurfaceStore
    let appConfig: AppConfig
    let selectedSessionID: String?
    @Binding var savingName: String?
    let onClose: () -> Void
    let onSaved: () -> Void
    var onRemoved: (() -> Void)? = nil
    let onToolToggle: (JSONValue, String, Bool) -> Void
    let onToolDecision: (JSONValue, String) -> Void

    @State private var name = ""
    @State private var transport = "http"
    @State private var command = ""
    @State private var argsText = ""
    @State private var envText = ""
    @State private var url = ""
    @State private var headersText = ""
    @State private var busy = false

    private var serverObject: [String: JSONValue] { server?.objectValue ?? [:] }
    private var configObject: [String: JSONValue] { config?.objectValue ?? [:] }
    private var title: String {
        mode == .add ? "Connect to a custom MCP" : "Update \(serverObject.string("name") ?? "MCP") MCP"
    }
    private var valid: Bool {
        !name.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty &&
        (transport == "stdio"
            ? !command.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty
            : !url.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty)
    }

    var body: some View {
        VStack(alignment: .leading, spacing: 16) {
            HStack {
                Button {
                    onClose()
                } label: {
                    Label("Back", systemImage: "chevron.left")
                        .font(.system(size: 13, weight: .medium))
                }
                .buttonStyle(.plain)
                .foregroundStyle(NtrpColors.muted)

                Spacer()

                if mode == .edit {
                    Button(role: .destructive) {
                        remove()
                    } label: {
                        Label("Uninstall", systemImage: "trash")
                            .font(.system(size: 13, weight: .medium))
                    }
                    .buttonStyle(.bordered)
                    .controlSize(.small)
                    .disabled(busy)
                }
            }

            Text(title)
                .font(.system(size: 18, weight: .semibold))
                .foregroundStyle(NtrpColors.text)

            VStack(alignment: .leading, spacing: 12) {
                field("Name") {
                    TextField("MCP server name", text: $name)
                        .disabled(mode == .edit)
                }

                if mode == .edit {
                    Text(transport == "stdio" ? "STDIO" : "Streamable HTTP")
                        .font(.system(size: 13, weight: .medium))
                        .foregroundStyle(NtrpColors.muted)
                        .padding(.horizontal, 12)
                        .frame(height: 32)
                        .background(NtrpColors.row.opacity(0.36))
                        .overlay(RoundedRectangle(cornerRadius: 8, style: .continuous).stroke(NtrpColors.sidebarStroke, lineWidth: 1))
                        .clipShape(RoundedRectangle(cornerRadius: 8, style: .continuous))
                    Text("To switch transport type, uninstall first.")
                        .font(.system(size: 12))
                        .foregroundStyle(NtrpColors.faint)
                } else {
                    Picker("Transport", selection: $transport) {
                        Text("STDIO").tag("stdio")
                        Text("Streamable HTTP").tag("http")
                    }
                    .pickerStyle(.segmented)
                    .frame(maxWidth: 260)
                }

                if transport == "stdio" {
                    field("Command to launch") {
                        TextField("openai-dev-mcp serve-sqlite", text: $command)
                            .font(.system(size: 14, design: .monospaced))
                    }
                    field("Arguments") {
                        TextField("One argument per line", text: $argsText, axis: .vertical)
                            .lineLimit(2...5)
                            .font(.system(size: 13, design: .monospaced))
                    }
                    field("Environment variables") {
                        TextField("KEY=value, one per line", text: $envText, axis: .vertical)
                            .lineLimit(2...5)
                            .font(.system(size: 13, design: .monospaced))
                    }
                } else {
                    field("URL") {
                        TextField("https://mcp.example.com/mcp", text: $url)
                            .font(.system(size: 14, design: .monospaced))
                    }
                    field("Headers") {
                        TextField("Header=value, one per line", text: $headersText, axis: .vertical)
                            .lineLimit(2...5)
                            .font(.system(size: 13, design: .monospaced))
                    }
                }
            }

            if mode == .edit, !serverObject.array("tools").isEmpty {
                MCPToolsSection(
                    server: server ?? .null,
                    serverConfig: serverConfig,
                    savingName: $savingName,
                    onToolToggle: onToolToggle,
                    onToolDecision: onToolDecision
                )
            }

            Spacer(minLength: 0)

            HStack {
                Spacer()
                Button {
                    save()
                } label: {
                    Text(busy ? "Saving..." : "Save")
                        .font(.system(size: 13, weight: .semibold))
                        .padding(.horizontal, 16)
                        .frame(height: 34)
                }
                .buttonStyle(.borderedProminent)
                .disabled(!valid || busy)
            }
        }
        .onAppear(perform: loadInitial)
    }

    private func field<Content: View>(_ label: String, @ViewBuilder content: () -> Content) -> some View {
        VStack(alignment: .leading, spacing: 6) {
            Text(label.uppercased())
                .font(.system(size: 11, weight: .semibold))
                .tracking(1.1)
                .foregroundStyle(NtrpColors.faint)
            content()
                .textFieldStyle(.plain)
                .padding(.horizontal, 10)
                .padding(.vertical, 7)
                .frame(maxWidth: 560, alignment: .leading)
                .background(NtrpColors.row.opacity(0.34))
                .overlay(RoundedRectangle(cornerRadius: 9, style: .continuous).stroke(NtrpColors.sidebarStroke, lineWidth: 1))
                .clipShape(RoundedRectangle(cornerRadius: 9, style: .continuous))
        }
    }

    private func loadInitial() {
        name = serverObject.string("name") ?? ""
        transport = configObject.string("transport") ?? serverObject.string("transport") ?? "http"
        command = configObject.string("command") ?? serverObject.string("command") ?? ""
        url = configObject.string("url") ?? serverObject.string("url") ?? ""
        argsText = (configObject.array("args").isEmpty ? serverObject.array("args") : configObject.array("args"))
            .map(\.display)
            .joined(separator: "\n")
        envText = keyValueText(configObject.object("env"))
        headersText = keyValueText(configObject.object("headers"))
    }

    private func save() {
        guard valid else { return }
        let trimmedName = name.trimmingCharacters(in: .whitespacesAndNewlines)
        let payload = JSONValue.object(["config": .object(configPayload())])
        let body: String
        if mode == .add {
            body = JSONValue.object(["name": .string(trimmedName), "config": .object(configPayload())]).prettyPrinted()
        } else {
            body = payload.prettyPrinted()
        }
        busy = true
        Task {
            if mode == .add {
                _ = await surface.addMCP(config: appConfig, bodyText: body)
            } else {
                _ = await surface.updateMCP(config: appConfig, name: trimmedName, bodyText: body)
            }
            await surface.reload(config: appConfig, sessionID: selectedSessionID)
            busy = false
            onSaved()
        }
    }

    private func remove() {
        guard let serverName = serverObject.string("name") else { return }
        busy = true
        Task {
            await surface.removeMCP(config: appConfig, name: serverName)
            await surface.reload(config: appConfig, sessionID: selectedSessionID)
            busy = false
            onRemoved?()
        }
    }

    private func configPayload() -> [String: JSONValue] {
        var payload: [String: JSONValue] = [
            "transport": .string(transport),
            "enabled": configObject["enabled"] ?? .bool(true),
        ]
        if transport == "stdio" {
            payload["command"] = .string(command.trimmingCharacters(in: .whitespacesAndNewlines))
            let args = argsText
                .split(whereSeparator: \.isNewline)
                .map { JSONValue.string(String($0).trimmingCharacters(in: .whitespacesAndNewlines)) }
                .filter { !$0.display.isEmpty }
            payload["args"] = .array(args)
            if let env = keyValueObject(envText) { payload["env"] = .object(env) }
        } else {
            payload["url"] = .string(url.trimmingCharacters(in: .whitespacesAndNewlines))
            if let headers = keyValueObject(headersText) { payload["headers"] = .object(headers) }
        }
        if let tools = configObject["tools"] {
            payload["tools"] = tools
        }
        return payload
    }

    private func keyValueText(_ object: [String: JSONValue]?) -> String {
        (object ?? [:])
            .map { "\($0.key)=\($0.value.display)" }
            .sorted()
            .joined(separator: "\n")
    }

    private func keyValueObject(_ text: String) -> [String: JSONValue]? {
        let pairs = text
            .split(whereSeparator: \.isNewline)
            .compactMap { line -> (String, JSONValue)? in
                let parts = line.split(separator: "=", maxSplits: 1).map(String.init)
                guard parts.count == 2 else { return nil }
                let key = parts[0].trimmingCharacters(in: .whitespacesAndNewlines)
                let value = parts[1].trimmingCharacters(in: .whitespacesAndNewlines)
                return key.isEmpty ? nil : (key, .string(value))
            }
        return pairs.isEmpty ? nil : Dictionary(uniqueKeysWithValues: pairs)
    }
}

private struct MCPServerRow: View {
    let server: JSONValue
    @Binding var savingName: String?
    let onEdit: (String) -> Void
    let onToggle: (String, Bool) -> Void
    let onAuthenticate: (String) -> Void

    private var object: [String: JSONValue] { server.objectValue ?? [:] }
    private var name: String { object.string("name") ?? server.display }
    private var connected: Bool { object.bool("connected") == true }
    private var enabled: Bool { object.bool("enabled") != false }
    private var transport: String { (object.string("transport") ?? "unknown").uppercased() }
    private var busy: Bool { savingName == name || savingName == "\(name):tools" }
    private var tools: [JSONValue] { object.array("tools") }
    private var needsAuth: Bool {
        (object.string("auth") == "oauth") && !connected
    }

    var body: some View {
        VStack(alignment: .leading, spacing: 0) {
            HStack(alignment: .center, spacing: 12) {
                Circle()
                    .fill(connected ? Color.green.opacity(0.82) : (object.string("error") == nil ? NtrpColors.faint : Color.red.opacity(0.84)))
                    .frame(width: 7, height: 7)

                VStack(alignment: .leading, spacing: 3) {
                    Text(name)
                        .font(.system(size: 15, weight: .medium))
                        .foregroundStyle(NtrpColors.text)
                        .lineLimit(1)
                    Text(statusText)
                        .font(.system(size: 12, design: .monospaced))
                        .foregroundStyle(NtrpColors.faint)
                        .lineLimit(1)
                    if let error = object.string("error"), !error.isEmpty {
                        Text(error)
                            .font(.system(size: 12))
                            .foregroundStyle(Color.red.opacity(0.86))
                            .lineLimit(1)
                    }
                }

                Spacer(minLength: 10)

                if needsAuth {
                    Button("Authenticate") {
                        onAuthenticate(name)
                    }
                    .buttonStyle(.bordered)
                    .controlSize(.small)
                    .disabled(busy)
                }

                Button {
                    onEdit(name)
                } label: {
                    Image(systemName: "gearshape")
                        .font(.system(size: 14, weight: .medium))
                        .frame(width: 28, height: 28)
                }
                .buttonStyle(.plain)
                .foregroundStyle(NtrpColors.muted)

                Toggle("", isOn: Binding(
                    get: { enabled },
                    set: { onToggle(name, $0) }
                ))
                .toggleStyle(.switch)
                .labelsHidden()
                .controlSize(.small)
                .disabled(busy)
            }
            .padding(.horizontal, 13)
            .padding(.vertical, 11)
        }
        .opacity(busy ? 0.65 : 1)
    }

    private var statusText: String {
        var parts = [transport]
        if connected {
            parts.append("\(object.value("tool_count")?.display ?? "\(tools.count)") tools")
        } else if object.string("error") != nil {
            parts.append("error")
        } else if !enabled {
            parts.append("disabled")
        } else {
            parts.append("disconnected")
        }
        return parts.joined(separator: " · ")
    }
}

private struct MCPToolsSection: View {
    let server: JSONValue
    let serverConfig: JSONValue?
    @Binding var savingName: String?
    let onToolToggle: (JSONValue, String, Bool) -> Void
    let onToolDecision: (JSONValue, String) -> Void

    private var serverObject: [String: JSONValue] { server.objectValue ?? [:] }
    private var tools: [JSONValue] { serverObject.array("tools") }
    private var overrides: [String: JSONValue] {
        serverConfig?.value(for: "tool_overrides")?.objectValue ?? [:]
    }

    var body: some View {
        VStack(alignment: .leading, spacing: 7) {
            HStack {
                Text("TOOLS")
                    .font(.system(size: 10, weight: .semibold))
                    .tracking(1)
                    .foregroundStyle(NtrpColors.faint)
                Text("\(tools.count)")
                    .font(.system(size: 11, design: .monospaced))
                    .foregroundStyle(NtrpColors.faint)
                Spacer()
            }
            VStack(spacing: 0) {
                ForEach(Array(tools.enumerated()), id: \.element.id) { index, tool in
                    MCPToolRow(
                        server: server,
                        tool: tool,
                        overrides: overrides,
                        disabled: savingName != nil,
                        onToggle: onToolToggle,
                        onDecision: onToolDecision
                    )
                    if index < tools.count - 1 {
                        Divider().overlay(NtrpColors.sidebarStroke.opacity(0.7))
                    }
                }
            }
            .background(NtrpColors.canvas.opacity(0.26))
            .overlay(RoundedRectangle(cornerRadius: 8, style: .continuous).stroke(NtrpColors.sidebarStroke.opacity(0.8), lineWidth: 1))
            .clipShape(RoundedRectangle(cornerRadius: 8, style: .continuous))
        }
    }
}

private struct MCPToolRow: View {
    let server: JSONValue
    let tool: JSONValue
    let overrides: [String: JSONValue]
    let disabled: Bool
    let onToggle: (JSONValue, String, Bool) -> Void
    let onDecision: (JSONValue, String) -> Void

    private var object: [String: JSONValue] { tool.objectValue ?? [:] }
    private var name: String { object.string("name") ?? tool.display }
    private var fullName: String { object.string("full_name") ?? name }
    private var enabled: Bool { object.bool("enabled") != false }
    private var description: String? { object.string("description") }
    private var baseDecision: String {
        object.value("policy", "requires_approval")?.boolValue == true ? "ask" : "approve"
    }
    private var currentDecision: String {
        overrides[fullName]?.stringValue ?? baseDecision
    }

    var body: some View {
        HStack(alignment: .top, spacing: 10) {
            Toggle("", isOn: Binding(
                get: { enabled },
                set: { onToggle(server, name, $0) }
            ))
            .toggleStyle(.switch)
            .labelsHidden()
            .controlSize(.mini)
            .disabled(disabled)
            .padding(.top, 1)

            VStack(alignment: .leading, spacing: 3) {
                Text(name)
                    .font(.system(size: 13, weight: .medium))
                    .foregroundStyle(NtrpColors.text)
                    .lineLimit(1)
                if let description, !description.isEmpty {
                    Text(description)
                        .font(.system(size: 12))
                        .foregroundStyle(NtrpColors.faint)
                        .lineLimit(2)
                }
            }

            Spacer(minLength: 8)

            HStack(spacing: 2) {
                ForEach(["approve", "ask", "deny"], id: \.self) { decision in
                    Button {
                        onDecision(tool, decision)
                    } label: {
                        Text(decision.capitalized)
                            .font(.system(size: 11, weight: .medium))
                            .foregroundStyle(currentDecision == decision ? NtrpColors.text : NtrpColors.faint)
                            .padding(.horizontal, 7)
                            .frame(height: 24)
                            .background(currentDecision == decision ? NtrpColors.rowActive : Color.clear)
                            .clipShape(RoundedRectangle(cornerRadius: 6, style: .continuous))
                    }
                    .buttonStyle(.plain)
                    .disabled(disabled)
                }
            }
            .padding(2)
            .background(NtrpColors.row.opacity(0.28))
            .overlay(RoundedRectangle(cornerRadius: 8, style: .continuous).stroke(NtrpColors.sidebarStroke, lineWidth: 1))
            .clipShape(RoundedRectangle(cornerRadius: 8, style: .continuous))
        }
        .padding(.horizontal, 10)
        .padding(.vertical, 8)
    }
}

private struct ProviderReadinessCard: View {
    let providers: [JSONValue]
    let chatModel: String?

    private var connectedCount: Int {
        providers.filter { $0.objectValue?.bool("connected") == true }.count
    }

    private var modelCount: Int {
        providers.reduce(0) { total, provider in
            total + (provider.objectValue?.array("models").count ?? 0)
        }
    }

    private var currentProviderReady: Bool {
        guard let chatModel, !chatModel.isEmpty else { return connectedCount > 0 }
        return providers.contains { provider in
            guard provider.objectValue?.bool("connected") == true else { return false }
            return provider.objectValue?.array("models").contains { model in
                if model.display == chatModel { return true }
                return model.objectValue?.string("id") == chatModel
            } ?? false
        }
    }

    var body: some View {
        HStack(alignment: .top, spacing: 10) {
            Image(systemName: currentProviderReady ? "checkmark.circle" : "exclamationmark.triangle")
                .font(.system(size: 17, weight: .medium))
                .foregroundStyle(currentProviderReady ? Color.green.opacity(0.82) : Color.orange.opacity(0.92))
                .frame(width: 20)

            VStack(alignment: .leading, spacing: 3) {
                Text(currentProviderReady ? "Model provider ready" : "Connect a provider")
                    .font(.system(size: 14, weight: .semibold))
                    .foregroundStyle(NtrpColors.text)
                Text(currentProviderReady ? "Current chat model can be served by a connected provider." : "Connect the provider for the selected chat model.")
                    .font(.system(size: 12))
                    .foregroundStyle(NtrpColors.muted)
                    .lineLimit(2)
                Text("\(connectedCount) connected · \(modelCount) available models")
                    .font(.system(size: 12, design: .monospaced))
                    .foregroundStyle(NtrpColors.faint)
            }
            Spacer(minLength: 0)
        }
        .padding(.horizontal, 12)
        .padding(.vertical, 10)
        .background((currentProviderReady ? Color.green : Color.orange).opacity(0.08))
        .overlay(RoundedRectangle(cornerRadius: 10, style: .continuous).stroke(NtrpColors.sidebarStroke, lineWidth: 1))
        .clipShape(RoundedRectangle(cornerRadius: 10, style: .continuous))
    }
}

private struct ProviderSectionView: View {
    let title: String
    let detail: String
    let empty: String
    let providers: [JSONValue]
    @Binding var editingID: String?
    @Binding var apiKey: String
    @Binding var pendingID: String?
    @ObservedObject var surface: SurfaceStore
    let config: AppConfig

    var body: some View {
        VStack(alignment: .leading, spacing: 8) {
            HStack {
                Text(title.uppercased())
                    .font(.system(size: 11, weight: .semibold))
                    .tracking(0.88)
                    .foregroundStyle(NtrpColors.faint)
                Spacer()
                Text(detail)
                    .font(.system(size: 12))
                    .foregroundStyle(NtrpColors.faint)
            }
            .padding(.horizontal, 2)

            if providers.isEmpty {
                Text(empty)
                    .font(.system(size: 13))
                    .foregroundStyle(NtrpColors.faint)
                    .padding(.horizontal, 12)
                    .frame(maxWidth: .infinity, minHeight: 40, alignment: .leading)
                    .background(NtrpColors.row.opacity(0.34))
                    .overlay(RoundedRectangle(cornerRadius: 10, style: .continuous).stroke(NtrpColors.sidebarStroke, lineWidth: 1))
                    .clipShape(RoundedRectangle(cornerRadius: 10, style: .continuous))
            } else {
                VStack(spacing: 8) {
                    ForEach(providers) { provider in
                        ProviderCard(
                            provider: provider,
                            editingID: $editingID,
                            apiKey: $apiKey,
                            pendingID: $pendingID,
                            surface: surface,
                            config: config
                        )
                    }
                }
            }
        }
    }
}

private struct ProviderCard: View {
    let provider: JSONValue
    @Binding var editingID: String?
    @Binding var apiKey: String
    @Binding var pendingID: String?
    @ObservedObject var surface: SurfaceStore
    let config: AppConfig

    private var object: [String: JSONValue] { provider.objectValue ?? [:] }
    private var id: String { object.string("id") ?? "provider" }
    private var name: String { object.string("name") ?? id }
    private var connected: Bool { object.bool("connected") == true }
    private var fromEnv: Bool { object.bool("from_env") == true }
    private var authType: String { object.string("auth_type") ?? "" }
    private var isOAuth: Bool { authType == "oauth" || id == "openai-codex" }
    private var isCustom: Bool { id == "custom" }
    private var pending: Bool { pendingID == id }
    private var editing: Bool { editingID == id }

    var body: some View {
        VStack(spacing: 0) {
            HStack(alignment: .top, spacing: 12) {
                VStack(alignment: .leading, spacing: 5) {
                    HStack(spacing: 8) {
                        Image(systemName: connected ? "checkmark.circle" : "key")
                            .font(.system(size: 16, weight: .medium))
                            .foregroundStyle(connected ? Color.green.opacity(0.82) : NtrpColors.faint)
                            .frame(width: 18)
                        Text(name)
                            .font(.system(size: 15, weight: .medium))
                            .foregroundStyle(NtrpColors.text)
                            .lineLimit(1)
                    }
                    Text(statusLine)
                        .font(.system(size: 12, design: .monospaced))
                        .foregroundStyle(NtrpColors.muted)
                        .lineLimit(1)
                    if !connected {
                        Text(modelCountLabel)
                            .font(.system(size: 12, design: .monospaced))
                            .foregroundStyle(NtrpColors.faint)
                            .lineLimit(1)
                    }
                }

                Spacer(minLength: 10)

                Button {
                    primaryAction()
                } label: {
                    Text(actionLabel)
                        .font(.system(size: 13, weight: .medium))
                        .foregroundStyle(connected ? NtrpColors.text : Color.black.opacity(0.86))
                        .padding(.horizontal, 12)
                        .frame(height: 32)
                        .background(connected ? NtrpColors.row.opacity(0.46) : NtrpColors.text)
                        .clipShape(RoundedRectangle(cornerRadius: 8, style: .continuous))
                }
                .buttonStyle(.plain)
                .disabled(pending || fromEnv)
                .opacity((pending || fromEnv) ? 0.55 : 1)
            }
            .padding(.horizontal, 14)
            .padding(.vertical, 11)

            if editing && !connected && !isOAuth && !isCustom {
                HStack(spacing: 8) {
                    SecureField("API key", text: $apiKey)
                        .textFieldStyle(.plain)
                        .font(.system(size: 14))
                        .padding(.horizontal, 10)
                        .frame(height: 36)
                        .background(NtrpColors.row.opacity(0.42))
                        .overlay(RoundedRectangle(cornerRadius: 9, style: .continuous).stroke(NtrpColors.sidebarStroke, lineWidth: 1))
                        .clipShape(RoundedRectangle(cornerRadius: 9, style: .continuous))

                    Button("Connect") {
                        let trimmed = apiKey.trimmingCharacters(in: .whitespacesAndNewlines)
                        guard !trimmed.isEmpty else { return }
                        pendingID = id
                        Task {
                            await surface.connectProvider(config: config, providerID: id, apiKey: trimmed)
                            await surface.reload(config: config, sessionID: nil)
                            pendingID = nil
                            editingID = nil
                            apiKey = ""
                        }
                    }
                    .buttonStyle(.borderedProminent)
                    .controlSize(.small)

                    Button("Cancel") {
                        editingID = nil
                        apiKey = ""
                    }
                    .buttonStyle(.bordered)
                    .controlSize(.small)
                }
                .padding(.horizontal, 14)
                .padding(.vertical, 12)
                .background(NtrpColors.row.opacity(0.22))
            }
        }
        .background(NtrpColors.row.opacity(0.30))
        .overlay(RoundedRectangle(cornerRadius: 12, style: .continuous).stroke(NtrpColors.sidebarStroke, lineWidth: 1))
        .clipShape(RoundedRectangle(cornerRadius: 12, style: .continuous))
    }

    private var actionLabel: String {
        if pending { return "Working..." }
        if fromEnv { return connected ? "Configured separately" : "Unavailable" }
        if isCustom { return "Manage" }
        if connected { return "Disconnect" }
        if isOAuth { return "Sign in" }
        return "Connect"
    }

    private var statusLine: String {
        if connected {
            var parts = [modelCountLabel]
            if let pill = connectionPill { parts.append(pill) }
            return parts.joined(separator: " · ")
        }
        return providerDescription(id)
    }

    private var connectionPill: String? {
        if fromEnv { return "env" }
        if isOAuth { return "oauth" }
        return connected ? "api key" : nil
    }

    private var modelCountLabel: String {
        let count = object.array("models").count
        return "\(count) model\(count == 1 ? "" : "s")"
    }

    private func primaryAction() {
        if isCustom {
            return
        }
        if isOAuth && !connected {
            pendingID = id
            Task {
                if let url = await surface.startCodexOAuth(config: config),
                   let nsurl = URL(string: url) {
                    NSWorkspace.shared.open(nsurl)
                }
                await surface.reload(config: config, sessionID: nil)
                pendingID = nil
            }
            return
        }
        if connected {
            pendingID = id
            Task {
                await surface.disconnectProvider(config: config, providerID: id)
                await surface.reload(config: config, sessionID: nil)
                pendingID = nil
            }
            return
        }
        editingID = id
        apiKey = ""
    }

    private func providerDescription(_ id: String) -> String {
        switch id {
        case "openai-codex":
            return "Use your OpenAI account login for Codex-backed models."
        case "openai":
            return "Use OpenAI API keys for GPT models and embeddings."
        case "anthropic":
            return "Use Anthropic API keys for Claude models."
        case "google":
            return "Use Gemini API keys for Gemini chat and embeddings."
        case "openrouter":
            return "Use OpenRouter API keys for routed third-party models."
        case "custom":
            return "OpenAI-compatible local or hosted models."
        default:
            return "Connect this model provider."
        }
    }
}

private struct SettingsInlineError: View {
    let title: String
    let message: String

    var body: some View {
        VStack(alignment: .leading, spacing: 3) {
            Text(title)
                .font(.system(size: 13, weight: .semibold))
            Text(message)
                .font(.system(size: 14))
                .lineSpacing(2)
                .foregroundStyle(NtrpColors.muted)
                .lineLimit(3)
        }
        .foregroundStyle(Color.red.opacity(0.9))
        .padding(10)
        .frame(maxWidth: .infinity, alignment: .leading)
        .background(Color.red.opacity(0.09))
        .clipShape(RoundedRectangle(cornerRadius: 10, style: .continuous))
    }
}

private struct SettingsConnectionHint: View {
    var body: some View {
        VStack(alignment: .leading, spacing: 4) {
            Text("Connect the desktop to ntrp first")
                .font(.system(size: 16, weight: .medium))
                .foregroundStyle(NtrpColors.text)
            Text("Check the server URL and API key in the Connection tab, then refresh this view.")
                .font(.system(size: 14))
                .lineSpacing(3)
                .foregroundStyle(NtrpColors.muted)
        }
        .padding(.horizontal, 14)
        .padding(.vertical, 12)
        .frame(maxWidth: .infinity, alignment: .leading)
        .background(NtrpColors.row.opacity(0.30))
        .overlay(RoundedRectangle(cornerRadius: 12, style: .continuous).stroke(NtrpColors.sidebarStroke.opacity(0.7), lineWidth: 1))
        .clipShape(RoundedRectangle(cornerRadius: 12, style: .continuous))
    }
}
