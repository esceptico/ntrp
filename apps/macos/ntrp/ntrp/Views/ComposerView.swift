import AppKit
import SwiftUI
import UniformTypeIdentifiers

struct ComposerView: View {
    @ObservedObject var store: NtrpStore
    @ObservedObject var ui: NtrpUIState
    @AppStorage("ntrp.thinkingIntensity") private var thinkingIntensity = "normal"
    @AppStorage("ntrp.thinkingAnimation") private var thinkingAnimation = "comet"
    @State private var text = ""
    @State private var images: [DraftImageAttachment] = []
    @State private var selectedSkill: JSONValue?
    @State private var commandIndex = 0
    @State private var dismissedPickerQuery: String?
    @State private var showThinking = false
    @State private var thinkingLeaving = false
    @State private var sendPressing = false
    @State private var justSent = false
    @FocusState private var focused: Bool

    var body: some View {
        if #available(macOS 26.0, *) {
            GlassEffectContainer(spacing: 8) {
                bodyContent
            }
        } else {
            bodyContent
        }
    }

    private var bodyContent: some View {
        VStack(spacing: 8) {
            QueueCard(store: store)
            if let proposal = visibleGoalProposal {
                GoalProposalCard(
                    objective: proposal.objective,
                    accept: { Task { await store.acceptGoalProposal() } },
                    edit: {
                        if let seed = store.editGoalProposal() {
                            text = seed
                            focused = true
                        }
                    },
                    cancel: { store.cancelGoalProposal() }
                )
            }
            if pickerOpen {
                CommandPickerView(
                    entries: filteredCommands,
                    selectedIndex: $commandIndex,
                    select: applyCommand
                )
            }
            composerCard
        }
        .task(id: store.selectedSessionID) {
            guard let sessionID = store.selectedSessionID else { return }
            while !Task.isCancelled {
                await store.refreshActiveLoops(sessionID: sessionID)
                try? await Task.sleep(for: .seconds(3))
            }
        }
    }

    private var composerCard: some View {
        VStack(alignment: .leading, spacing: 0) {
            if let selectedSkill {
                HStack(spacing: 8) {
                    Button {
                        Task {
                            if let view = await store.markdownForSkill(selectedSkill) {
                                ui.viewingMarkdown = view
                            }
                        }
                    } label: {
                        HStack(spacing: 6) {
                            Image(systemName: "sparkles")
                                .font(.system(size: 13, weight: .medium))
                                .foregroundStyle(NtrpColors.accent)
                            Text(skillDisplayName(selectedSkill))
                                .font(.system(size: 12, weight: .medium))
                                .foregroundStyle(NtrpColors.muted)
                                .lineLimit(1)
                        }
                        .padding(.horizontal, 8)
                        .frame(height: 26)
                        .background(NtrpColors.row.opacity(0.42))
                        .overlay(
                            RoundedRectangle(cornerRadius: 7, style: .continuous)
                                .stroke(NtrpColors.sidebarStroke.opacity(0.7), lineWidth: 1)
                        )
                        .clipShape(RoundedRectangle(cornerRadius: 7, style: .continuous))
                    }
                    .buttonStyle(.plain)
                    .help(skillPath(selectedSkill) ?? skillName(selectedSkill))

                    Button {
                        self.selectedSkill = nil
                    } label: {
                        Image(systemName: "xmark")
                            .font(.system(size: 10, weight: .bold))
                            .foregroundStyle(NtrpColors.faint)
                            .frame(width: 20, height: 20)
                            .contentShape(Rectangle())
                    }
                    .buttonStyle(.plain)
                    .background(NtrpColors.row.opacity(0.0))
                    .clipShape(RoundedRectangle(cornerRadius: 6, style: .continuous))
                    .help("Detach skill")
                }
                .padding(.horizontal, 12)
                .padding(.top, 8)
                .padding(.bottom, 6)
            }

            if store.editingMessageID != nil {
                HStack(spacing: 8) {
                    Text("Editing previous message — pressing send will replace it.")
                        .font(.system(size: 12, weight: .medium))
                        .foregroundStyle(NtrpColors.accent)
                    Spacer()
                    Button {
                        store.cancelEditing()
                        text = ""
                    } label: {
                        HStack(spacing: 4) {
                            Image(systemName: "xmark")
                            Text("cancel")
                        }
                        .font(.system(size: 12))
                        .foregroundStyle(NtrpColors.muted)
                    }
                    .buttonStyle(.plain)
                }
                .padding(.horizontal, 12)
                .padding(.vertical, 6)
                .background(NtrpColors.accent.opacity(0.10))
                .clipShape(
                    UnevenRoundedRectangle(
                        topLeadingRadius: 14,
                        bottomLeadingRadius: 0,
                        bottomTrailingRadius: 0,
                        topTrailingRadius: 14,
                        style: .continuous
                    )
                )
            }

            if !images.isEmpty {
                HStack(spacing: 8) {
                    ForEach(images) { image in
                        ZStack(alignment: .topTrailing) {
                            if let preview = image.preview {
                                Image(nsImage: preview)
                                    .resizable()
                                    .scaledToFill()
                                    .frame(width: 56, height: 56)
                                    .clipShape(RoundedRectangle(cornerRadius: 7, style: .continuous))
                                    .overlay(
                                        RoundedRectangle(cornerRadius: 7, style: .continuous)
                                            .stroke(NtrpColors.sidebarStroke, lineWidth: 1)
                                    )
                            } else {
                                Image(systemName: "photo")
                                    .font(.system(size: 20, weight: .medium))
                                    .foregroundStyle(NtrpColors.muted)
                                    .frame(width: 56, height: 56)
                                    .background(NtrpColors.row.opacity(0.4))
                                    .clipShape(RoundedRectangle(cornerRadius: 7, style: .continuous))
                            }

                            Button {
                                images.removeAll { $0.id == image.id }
                            } label: {
                                Image(systemName: "xmark")
                                    .font(.system(size: 9, weight: .bold))
                                    .foregroundStyle(Color.black.opacity(0.8))
                                    .frame(width: 16, height: 16)
                                    .background(NtrpColors.text)
                                    .clipShape(Circle())
                            }
                            .buttonStyle(.plain)
                            .offset(x: 5, y: -5)
                        }
                        .help(image.filename)
                    }
                    Spacer()
                }
                .padding(.horizontal, 12)
                .padding(.top, 8)
            }

            TextField("Message ntrp…", text: $text, axis: .vertical)
                .textFieldStyle(.plain)
                .font(.system(size: 16))
                .tracking(-0.08)
                .foregroundStyle(NtrpColors.text)
                .lineLimit(1...6)
                .frame(minHeight: 64, alignment: .topLeading)
                .padding(.horizontal, 16)
                .padding(.top, 13)
                .padding(.bottom, 1)
                .focused($focused)
                .onSubmit {
                    if pickerOpen, filteredCommands.indices.contains(commandIndex) {
                        applyCommand(filteredCommands[commandIndex])
                    } else if canSend {
                        send()
                    }
                }
                .onChange(of: text) { _, _ in
                    commandIndex = min(commandIndex, max(0, filteredCommands.count - 1))
                }
                .onKeyPress(.upArrow) {
                    guard pickerOpen else { return .ignored }
                    commandIndex = max(0, commandIndex - 1)
                    return .handled
                }
                .onKeyPress(.downArrow) {
                    guard pickerOpen else { return .ignored }
                    commandIndex = min(max(0, filteredCommands.count - 1), commandIndex + 1)
                    return .handled
                }
                .onKeyPress(.tab) {
                    guard pickerOpen, filteredCommands.indices.contains(commandIndex) else { return .ignored }
                    applyCommand(filteredCommands[commandIndex])
                    return .handled
                }
                .onKeyPress(.escape) {
                    if pickerOpen {
                        dismissedPickerQuery = pickerQuery
                        return .handled
                    }
                    if selectedSkill != nil {
                        selectedSkill = nil
                        return .handled
                    }
                    if isRunning {
                        Task { await store.stopCurrentRun() }
                        return .handled
                    }
                    return .ignored
                }
                .onKeyPress(.delete) {
                    if !pickerOpen, selectedSkill != nil, text.isEmpty {
                        selectedSkill = nil
                        return .handled
                    }
                    return .ignored
                }
                .onPasteCommand(of: [.image, .fileURL]) { providers in
                    attachPastedImages(from: providers)
                }

            GeometryReader { proxy in
                let compact = proxy.size.width <= 520
                let veryCompact = proxy.size.width <= 420
                HStack(spacing: compact ? 4 : 6) {
                    iconButton("photo.badge.plus", action: pickImages)
                    ApprovalModeChip(store: store, showLabel: !compact)

                    LoopChip(store: store, ui: ui, showLabel: !compact)
                    GoalStatusChip(store: store)

                    Spacer(minLength: 4)

                    BudgetChip(usage: store.usage, config: store.serverConfig)

                    ModelReasoningChip(store: store, showModelLabel: !compact)

                    Button(action: primaryAction) {
                        ZStack {
                            Image(systemName: isRunning ? "stop.fill" : "arrow.up")
                                .font(.system(size: 15, weight: .bold))
                                .frame(width: 28, height: 28)
                                .foregroundStyle(Color.black.opacity(0.82))
                                .background(NtrpColors.text)
                                .clipShape(Circle())
                            if showThinking, thinkingAnimation == "send-orbit" {
                                ComposerSendOrbitSpinner(
                                    intensity: thinkingIntensity,
                                    leaving: thinkingLeaving
                                )
                                .frame(width: 34, height: 34)
                            }
                        }
                    }
                    .buttonStyle(.plain)
                    .disabled(store.selectedSessionID == nil || (!isRunning && !canSend))
                    .scaleEffect(sendPressing ? 0.90 : 1)
                    .animation(.snappy(duration: 0.14), value: sendPressing)
                }
                .padding(.horizontal, veryCompact ? 6 : 8)
                .padding(.top, 6)
                .padding(.bottom, 8)
            }
            .frame(height: 42)
        }
        .background(NtrpColors.surfaceFill(0.35))
        .overlay(
            RoundedRectangle(cornerRadius: 14, style: .continuous)
                .stroke(Color.white.opacity(0.12), lineWidth: 1)
        )
        .clipShape(RoundedRectangle(cornerRadius: 14, style: .continuous))
        .shadow(color: .black.opacity(0.48), radius: 22, x: 0, y: 14)
        .ntrpGlass(cornerRadius: 14, interactive: true)
        .overlay {
            composerFeedbackOverlay
        }
        .onAppear { focused = true }
        .onChange(of: awaitingFirstToken) { _, waiting in
            updateThinkingState(waiting: waiting)
        }
        .onChange(of: ui.composerFocusRequest) { _, _ in
            if let seed = ui.composerSeed, !seed.isEmpty {
                text += seed
                ui.composerSeed = nil
            }
            focused = true
        }
        .onChange(of: store.editingMessageID) { _, id in
            loadEditingMessage(id)
        }
    }

    @ViewBuilder
    private var composerFeedbackOverlay: some View {
        if justSent {
            RoundedRectangle(cornerRadius: 14, style: .continuous)
                .fill(
                    LinearGradient(
                        colors: [
                            NtrpColors.text.opacity(0.10),
                            NtrpColors.text.opacity(0.04)
                        ],
                        startPoint: .top,
                        endPoint: .bottom
                    )
                )
                .allowsHitTesting(false)
                .transition(.opacity)
        }
        if showThinking, thinkingAnimation != "send-orbit" {
            ComposerThinkingOverlay(
                style: thinkingAnimation,
                intensity: thinkingIntensity,
                leaving: thinkingLeaving
            )
        }
    }

    private func iconButton(_ icon: String, action: @escaping () -> Void) -> some View {
        Button(action: action) {
            Image(systemName: icon)
                .font(.system(size: 16, weight: .medium))
                .foregroundStyle(NtrpColors.muted)
                .frame(width: 28, height: 28)
        }
        .buttonStyle(.plain)
        .disabled(store.selectedSessionID == nil)
    }

    private var isRunning: Bool {
        store.isStreaming || store.currentRunID != nil
    }

    private var awaitingFirstToken: Bool {
        isRunning && store.messages.last?.role != .assistant
    }

    private var canSend: Bool {
        !text.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty || !images.isEmpty || selectedSkill != nil
    }

    private var visibleGoalProposal: PendingGoalProposal? {
        guard let proposal = store.pendingGoalProposal, proposal.sessionID == store.selectedSessionID else { return nil }
        return proposal
    }

    private func primaryAction() {
        if isRunning {
            Task { await store.stopCurrentRun() }
        } else if canSend {
            send()
        }
    }

    private func flashSendFeedback() {
        sendPressing = true
        justSent = true
        Task { @MainActor in
            try? await Task.sleep(for: .milliseconds(140))
            sendPressing = false
        }
        Task { @MainActor in
            try? await Task.sleep(for: .milliseconds(360))
            justSent = false
        }
    }

    private func updateThinkingState(waiting: Bool) {
        if waiting {
            thinkingLeaving = false
            Task { @MainActor in
                try? await Task.sleep(for: .milliseconds(350))
                if awaitingFirstToken {
                    showThinking = true
                }
            }
            return
        }

        if showThinking {
            thinkingLeaving = true
            Task { @MainActor in
                try? await Task.sleep(for: .milliseconds(250))
                if !awaitingFirstToken {
                    showThinking = false
                    thinkingLeaving = false
                }
            }
        }
    }

    private func loadEditingMessage(_ id: String?) {
        guard let id else { return }
        guard let message = store.messages.first(where: { $0.id == id }) else { return }
        text = message.content
        selectedSkill = nil
        images = []
        focused = true
    }

    private func send() {
        flashSendFeedback()
        let trimmed = text.trimmingCharacters(in: .whitespacesAndNewlines)
        let hasTypedDraft = !trimmed.isEmpty
        let hadSkill = selectedSkill != nil
        let message: String
        if let selectedSkill {
            let name = skillName(selectedSkill)
            message = trimmed.isEmpty ? "/\(name)" : "/\(name) \(trimmed)"
        } else {
            message = text
        }
        let outgoingImages = images
        text = ""
        images = []
        selectedSkill = nil
        if !hadSkill, outgoingImages.isEmpty, runBuiltinIfNeeded(message) {
            return
        }
        Task {
            if hasTypedDraft && !store.pendingApprovals.isEmpty {
                await store.rejectAllApprovals()
            }
            await store.send(message, images: outgoingImages)
        }
    }

    private func runBuiltinIfNeeded(_ message: String) -> Bool {
        guard message.hasPrefix("/") else { return false }
        let parts = message.dropFirst().split(separator: " ", maxSplits: 1, omittingEmptySubsequences: false)
        guard let head = parts.first.map(String.init), commandEntries.contains(where: { $0.name == head && $0.isBuiltin }) else {
            return false
        }
        let args = parts.count > 1 ? String(parts[1]) : ""
        Task { await store.runBuiltinCommand(head, args: args) }
        return true
    }

    private func pickImages() {
        let panel = NSOpenPanel()
        panel.allowedContentTypes = [.png, .jpeg, .gif, .heic, .webP]
        panel.allowsMultipleSelection = true
        panel.canChooseDirectories = false
        panel.begin { response in
            guard response == .OK else { return }
            images.append(contentsOf: panel.urls.compactMap(Self.attachment))
        }
    }

    private func attachPastedImages(from providers: [NSItemProvider]) {
        for provider in providers {
            if provider.hasItemConformingToTypeIdentifier(UTType.fileURL.identifier) {
                provider.loadItem(forTypeIdentifier: UTType.fileURL.identifier, options: nil) { item, _ in
                    guard let url = item as? URL ?? (item as? Data).flatMap(Self.fileURL) else { return }
                    guard Self.isImageURL(url), let attachment = Self.attachment(url: url) else { return }
                    Task { @MainActor in images.append(attachment) }
                }
                continue
            }

            if provider.hasItemConformingToTypeIdentifier(UTType.image.identifier) {
                provider.loadDataRepresentation(forTypeIdentifier: UTType.image.identifier) { data, _ in
                    guard let data, let attachment = Self.attachment(data: data, filename: "pasted-image") else { return }
                    Task { @MainActor in images.append(attachment) }
                }
            }
        }
    }

    nonisolated private static func attachment(url: URL) -> DraftImageAttachment? {
        guard let data = try? Data(contentsOf: url) else { return nil }
        let type = UTType(filenameExtension: url.pathExtension)
        return DraftImageAttachment(
            mediaType: type?.preferredMIMEType ?? "image/png",
            data: data.base64EncodedString(),
            filename: url.lastPathComponent
        )
    }

    nonisolated private static func attachment(data: Data, filename: String) -> DraftImageAttachment? {
        let image = NSImage(data: data)
        let encoded = image.flatMap(Self.pngData) ?? data
        return DraftImageAttachment(
            mediaType: "image/png",
            data: encoded.base64EncodedString(),
            filename: filename
        )
    }

    nonisolated private static func pngData(from image: NSImage) -> Data? {
        guard
            let tiff = image.tiffRepresentation,
            let bitmap = NSBitmapImageRep(data: tiff)
        else {
            return nil
        }
        return bitmap.representation(using: .png, properties: [:])
    }

    nonisolated private static func fileURL(from data: Data) -> URL? {
        guard let value = String(data: data, encoding: .utf8) else { return nil }
        return URL(string: value.trimmingCharacters(in: .whitespacesAndNewlines))
    }

    nonisolated private static func isImageURL(_ url: URL) -> Bool {
        guard let type = UTType(filenameExtension: url.pathExtension) else { return false }
        return type.conforms(to: .image)
    }

    private var pickerQuery: String? {
        guard text.hasPrefix("/") else { return nil }
        let value = String(text.dropFirst())
        guard !value.contains(" "), !value.contains("\n") else { return nil }
        return value
    }

    private var pickerOpen: Bool {
        guard let pickerQuery else { return false }
        return pickerQuery != dismissedPickerQuery && !filteredCommands.isEmpty
    }

    private var filteredCommands: [CommandEntry] {
        guard let query = pickerQuery?.lowercased() else { return [] }
        return commandEntries.filter { !$0.hidden && (query.isEmpty || $0.name.lowercased().hasPrefix(query)) }
    }

    private var commandEntries: [CommandEntry] {
        let builtins = [
            CommandEntry(name: "clear", description: "Clear this session's messages", kind: .builtin),
            CommandEntry(name: "compact", description: "Compact context window", kind: .builtin),
            CommandEntry(name: "revert", description: "Revert one turn", kind: .builtin),
            CommandEntry(name: "branch", description: "Branch into a new session", kind: .builtin),
            CommandEntry(name: "rename", description: "Rename this session", kind: .builtin, hidden: true),
            CommandEntry(name: "cost", description: "Show session cost", kind: .builtin),
            CommandEntry(name: "goal", description: "Set or show this session's goal", kind: .builtin)
        ]
        let skills = store.skills.map {
            CommandEntry(
                name: skillName($0),
                description: $0.objectValue?.string("description") ?? "Skill",
                kind: .skill($0)
            )
        }
        return builtins + skills
    }

    private func applyCommand(_ entry: CommandEntry) {
        switch entry.kind {
        case .skill(let value):
            selectedSkill = value
            text = ""
            focused = true
        case .builtin:
            switch entry.name {
            case "clear", "compact", "revert", "branch", "cost", "goal":
                text = ""
                Task { await store.runBuiltinCommand(entry.name) }
            default:
                text = "/\(entry.name)"
                send()
            }
        }
        dismissedPickerQuery = nil
        commandIndex = 0
    }
}

private struct QueueCard: View {
    @ObservedObject var store: NtrpStore

    var body: some View {
        if !store.queuedMessages.isEmpty {
            VStack(alignment: .leading, spacing: 6) {
                ForEach(store.queuedMessages) { message in
                    QueueRow(store: store, message: message)
                }
            }
            .padding(.horizontal, 12)
            .padding(.top, 8)
            .padding(.bottom, 20)
            .frame(maxWidth: .infinity, alignment: .leading)
            .background(NtrpColors.surfaceFill(0.55))
            .overlay(
                RoundedRectangle(cornerRadius: 14, style: .continuous)
                    .stroke(NtrpColors.sidebarStroke.opacity(0.85), lineWidth: 1)
            )
            .clipShape(RoundedRectangle(cornerRadius: 14, style: .continuous))
            .shadow(color: .black.opacity(0.18), radius: 5, x: 0, y: 2)
            .ntrpGlass(cornerRadius: 14, interactive: false)
            .padding(.horizontal, 16)
            .padding(.bottom, -12)
            .zIndex(-1)
        }
    }
}

private struct QueueRow: View {
    @ObservedObject var store: NtrpStore
    let message: QueuedMessage

    var body: some View {
        HStack(spacing: 8) {
            Circle()
                .fill(dotColor)
                .frame(width: 4, height: 4)
            Text(label)
                .font(.system(size: 13))
                .foregroundStyle(textColor)
                .italic(message.status == .cancelling)
                .lineLimit(1)
                .truncationMode(.tail)
            if !message.images.isEmpty && message.status != .cancelling {
                Text("+\(message.images.count) img")
                    .font(.system(size: 11))
                    .foregroundStyle(NtrpColors.faint)
            }
            Spacer(minLength: 8)
            Button {
                Task { await store.cancelQueuedMessage(message.clientID) }
            } label: {
                if message.status == .cancelling {
                    NtrpSpinner()
                        .frame(width: 20, height: 20)
                } else {
                    Image(systemName: "xmark")
                        .font(.system(size: 10, weight: .bold))
                        .foregroundStyle(NtrpColors.faint)
                        .frame(width: 20, height: 20)
                }
            }
            .buttonStyle(.plain)
            .disabled(message.status == .cancelling || message.status == .sent)
        }
    }

    private var label: String {
        if !message.text.isEmpty { return message.text }
        if !message.images.isEmpty { return "\(message.images.count) image\(message.images.count == 1 ? "" : "s")" }
        return "Queued"
    }

    private var dotColor: Color {
        switch message.status {
        case .pending:
            NtrpColors.accent
        case .cancelling, .sent:
            NtrpColors.faint
        case .failed:
            .red
        }
    }

    private var textColor: Color {
        switch message.status {
        case .failed:
            .red
        case .cancelling:
            NtrpColors.faint
        default:
            NtrpColors.text.opacity(0.78)
        }
    }
}

private struct ComposerThinkingOverlay: View {
    let style: String
    let intensity: String
    let leaving: Bool

    private var peak: Double {
        switch intensity {
        case "subtle": 0.50
        case "strong": 1.0
        default: 0.78
        }
    }

    private var shoulder: Double {
        switch intensity {
        case "subtle": 0.16
        case "strong": 0.45
        default: 0.28
        }
    }

    private var duration: Double {
        switch intensity {
        case "subtle": 3.6
        case "strong": 1.8
        default: 2.6
        }
    }

    var body: some View {
        TimelineView(.animation) { context in
            let time = context.date.timeIntervalSinceReferenceDate
            let progress = (time.truncatingRemainder(dividingBy: duration)) / duration
            let wave = (sin(progress * .pi * 2 - .pi / 2) + 1) / 2

            switch style {
            case "breath":
                RoundedRectangle(cornerRadius: 14, style: .continuous)
                    .strokeBorder(Color.clear, lineWidth: 1)
                    .shadow(
                        color: NtrpColors.accent.opacity((0.04 + wave * 0.21) * peak),
                        radius: 24,
                        x: 0,
                        y: 0
                    )
                    .opacity(leaving ? 0 : 1)
                    .animation(.easeOut(duration: 0.25), value: leaving)
                    .allowsHitTesting(false)
            case "hue-cycle":
                RoundedRectangle(cornerRadius: 14, style: .continuous)
                    .strokeBorder(NtrpColors.accent.opacity((0.10 + wave * 0.28) * peak), lineWidth: 1)
                    .opacity(leaving ? 0 : 1)
                    .animation(.easeOut(duration: 0.25), value: leaving)
                    .allowsHitTesting(false)
            default:
                RoundedRectangle(cornerRadius: 14, style: .continuous)
                    .strokeBorder(gradient, lineWidth: 1.6)
                    .opacity(leaving ? 0 : 1)
                    .rotationEffect(.degrees(progress * 360))
                    .shadow(color: NtrpColors.accent.opacity(peak * 0.18), radius: 6)
                    .animation(.easeOut(duration: 0.25), value: leaving)
                    .allowsHitTesting(false)
            }
        }
    }

    private var gradient: AngularGradient {
        AngularGradient(
            stops: [
                .init(color: .clear, location: 0.0),
                .init(color: .clear, location: 0.47),
                .init(color: NtrpColors.accent.opacity(shoulder), location: 0.64),
                .init(color: NtrpColors.accent.opacity(peak), location: 0.94),
                .init(color: NtrpColors.accent.opacity(peak), location: 0.97),
                .init(color: NtrpColors.accent.opacity(shoulder), location: 1.0)
            ],
            center: .center
        )
    }
}

private struct ComposerSendOrbitSpinner: View {
    let intensity: String
    let leaving: Bool

    private var peak: Double {
        switch intensity {
        case "subtle": 0.50
        case "strong": 1.0
        default: 0.78
        }
    }

    private var shoulder: Double {
        switch intensity {
        case "subtle": 0.16
        case "strong": 0.45
        default: 0.28
        }
    }

    private var duration: Double {
        switch intensity {
        case "subtle": 1.6
        case "strong": 0.8
        default: 1.15
        }
    }

    var body: some View {
        TimelineView(.animation) { context in
            let time = context.date.timeIntervalSinceReferenceDate
            let progress = (time.truncatingRemainder(dividingBy: duration)) / duration

            Circle()
                .trim(from: 0.02, to: 0.30)
                .stroke(
                    AngularGradient(
                        stops: [
                            .init(color: NtrpColors.accent.opacity(peak), location: 0),
                            .init(color: NtrpColors.accent.opacity(shoulder), location: 1)
                        ],
                        center: .center
                    ),
                    style: StrokeStyle(lineWidth: 1.5, lineCap: .round)
                )
                .rotationEffect(.degrees(progress * 360))
                .opacity(leaving ? 0 : 1)
                .animation(.easeOut(duration: 0.25), value: leaving)
                .allowsHitTesting(false)
        }
    }
}

private struct CommandEntry: Identifiable {
    enum Kind {
        case builtin
        case skill(JSONValue)
    }

    let name: String
    let description: String
    let kind: Kind
    var hidden = false

    var id: String {
        switch kind {
        case .builtin: "builtin:\(name)"
        case .skill: "skill:\(name)"
        }
    }

    var isBuiltin: Bool {
        if case .builtin = kind { return true }
        return false
    }
}

private struct GoalStatusChip: View {
    @ObservedObject var store: NtrpStore
    @State private var popoverOpen = false

    private var goal: SessionGoal? {
        guard let sessionID = store.selectedSessionID else { return nil }
        return store.goals[sessionID]
    }

    var body: some View {
        if let goal {
            Button {
                popoverOpen.toggle()
            } label: {
                HStack(spacing: 5) {
                    Image(systemName: "target")
                        .font(.system(size: 13, weight: .medium))
                    Text("Goal")
                    Text("·")
                    Text(goal.status.replacingOccurrences(of: "_", with: " "))
                }
                .font(.system(size: 13, weight: .medium))
                .foregroundStyle(goal.status == "complete" ? NtrpColors.muted : NtrpColors.accent)
                .padding(.horizontal, 8)
                .frame(height: 28)
                .background(goal.status == "complete" ? Color.clear : NtrpColors.accent.opacity(0.10))
                .clipShape(Capsule())
                .lineLimit(1)
            }
            .buttonStyle(.plain)
            .help(goal.objective)
            .popover(isPresented: $popoverOpen, arrowEdge: .bottom) {
                goalPopover(goal)
                    .frame(width: 360)
                    .padding(12)
        .background(NtrpColors.surfaceFill(0.90))
            }
        }
    }

    private func goalPopover(_ goal: SessionGoal) -> some View {
        VStack(alignment: .leading, spacing: 10) {
            HStack(spacing: 8) {
                Image(systemName: "target")
                    .font(.system(size: 13, weight: .medium))
                    .foregroundStyle(NtrpColors.accent)
                Text("Goal")
                    .font(.system(size: 12, weight: .medium))
                    .foregroundStyle(NtrpColors.muted)
                Spacer()
                Text(goal.status.replacingOccurrences(of: "_", with: " "))
                    .font(.system(size: 10, weight: .medium))
                    .foregroundStyle(NtrpColors.muted)
                    .padding(.horizontal, 6)
                    .frame(height: 20)
                    .overlay(
                        RoundedRectangle(cornerRadius: 5, style: .continuous)
                            .stroke(NtrpColors.sidebarStroke, lineWidth: 1)
                    )
            }

            Text(goal.objective)
                .font(.system(size: 13))
                .foregroundStyle(NtrpColors.text)
                .lineLimit(6)
                .textSelection(.enabled)

            HStack(spacing: 4) {
                if goal.status != "complete" {
                    goalAction(goal.status == "paused" ? "play.fill" : "pause.fill") {
                        Task { await store.runBuiltinCommand("goal", args: goal.status == "paused" ? "resume" : "pause") }
                    }
                    goalAction("checkmark.circle") {
                        Task { await store.runBuiltinCommand("goal", args: "complete") }
                    }
                }
                Spacer()
                goalAction("trash") {
                    Task { await store.runBuiltinCommand("goal", args: "clear") }
                }
            }
        }
    }

    private func goalAction(_ icon: String, action: @escaping () -> Void) -> some View {
        Button(action: action) {
            Image(systemName: icon)
                .font(.system(size: 12, weight: .medium))
                .foregroundStyle(NtrpColors.faint)
                .frame(width: 28, height: 28)
                .contentShape(Rectangle())
        }
        .buttonStyle(.plain)
    }
}

private struct CommandPickerView: View {
    let entries: [CommandEntry]
    @Binding var selectedIndex: Int
    let select: (CommandEntry) -> Void

    var body: some View {
        VStack(alignment: .leading, spacing: 0) {
            commandSection("Commands", entries: entries.enumerated().filter { isBuiltin($0.element) })
            if entries.contains(where: { !isBuiltin($0) }) {
                Divider().overlay(NtrpColors.sidebarStroke.opacity(0.7))
                commandSection("Skills", entries: entries.enumerated().filter { !isBuiltin($0.element) })
            }
            if let activeName {
                HStack(spacing: 12) {
                    pickerHint(key: "↑↓", label: "navigate")
                    pickerHint(key: "↩", label: "run /\(activeName)")
                    Spacer()
                    pickerHint(key: "esc", label: "dismiss")
                }
                .font(.system(size: 11))
                .foregroundStyle(NtrpColors.faint)
                .padding(.horizontal, 12)
                .frame(height: 30)
                .background(NtrpColors.row.opacity(0.60))
            }
        }
        .frame(maxWidth: .infinity, alignment: .leading)
        .background(NtrpColors.sidebar)
        .overlay(RoundedRectangle(cornerRadius: 10, style: .continuous).stroke(NtrpColors.sidebarStroke, lineWidth: 1))
        .clipShape(RoundedRectangle(cornerRadius: 10, style: .continuous))
        .shadow(color: .black.opacity(0.22), radius: 12, x: 0, y: 8)
    }

    private func commandSection(_ title: String, entries: [(offset: Int, element: CommandEntry)]) -> some View {
        VStack(alignment: .leading, spacing: 2) {
            if !entries.isEmpty {
                Text(title.uppercased())
                    .font(.system(size: 10, weight: .semibold))
                    .tracking(0.9)
                    .foregroundStyle(NtrpColors.faint)
                    .padding(.horizontal, 12)
                    .padding(.top, 9)
                    .padding(.bottom, 2)
                ForEach(entries, id: \.element.id) { indexed in
                    CommandPickerRow(
                        entry: indexed.element,
                        selected: selectedIndex == indexed.offset
                    ) {
                        selectedIndex = indexed.offset
                        select(indexed.element)
                    }
                    .onHover { hovering in
                        if hovering { selectedIndex = indexed.offset }
                    }
                }
            }
        }
        .padding(.bottom, entries.isEmpty ? 0 : 6)
    }

    private func isBuiltin(_ entry: CommandEntry) -> Bool {
        if case .builtin = entry.kind { return true }
        return false
    }

    private var activeName: String? {
        guard entries.indices.contains(selectedIndex) else { return nil }
        return entries[selectedIndex].name
    }

    private func pickerHint(key: String, label: String) -> some View {
        HStack(spacing: 5) {
            Text(key)
                .font(.system(size: 10, weight: .medium, design: .monospaced))
                .foregroundStyle(NtrpColors.muted)
                .padding(.horizontal, 5)
                .frame(minWidth: 16, minHeight: 16)
                .background(NtrpColors.row.opacity(0.7))
                .overlay(
                    RoundedRectangle(cornerRadius: 4, style: .continuous)
                        .stroke(NtrpColors.sidebarStroke, lineWidth: 1)
                )
                .clipShape(RoundedRectangle(cornerRadius: 4, style: .continuous))
            Text(label)
        }
    }
}

private struct CommandPickerRow: View {
    let entry: CommandEntry
    let selected: Bool
    let select: () -> Void

    var body: some View {
        Button(action: select) {
            HStack(spacing: 9) {
                Image(systemName: icon)
                    .font(.system(size: 13, weight: .medium))
                    .foregroundStyle(selected ? NtrpColors.text : NtrpColors.faint)
                    .frame(width: 18, height: 18)
                Text("/\(entry.name)")
                    .font(.system(size: 13, weight: .medium, design: .monospaced))
                    .foregroundStyle(NtrpColors.text)
                Spacer(minLength: 12)
                Text(entry.description)
                    .font(.system(size: 13))
                    .foregroundStyle(NtrpColors.muted)
                    .lineLimit(1)
            }
            .padding(.horizontal, 10)
            .frame(height: 30)
            .background(selected ? NtrpColors.rowActive : Color.clear)
            .clipShape(RoundedRectangle(cornerRadius: 7, style: .continuous))
        }
        .buttonStyle(.plain)
        .padding(.horizontal, 6)
    }

    private var icon: String {
        switch entry.kind {
        case .skill:
            "sparkles"
        case .builtin:
            switch entry.name {
            case "clear": "trash"
            case "compact": "square.stack.3d.down.right"
            case "revert": "arrow.counterclockwise"
            case "rename": "pencil"
            case "branch": "arrow.triangle.branch"
            case "cost": "dollarsign"
            case "goal": "target"
            default: "questionmark.circle"
            }
        }
    }
}

private func skillName(_ value: JSONValue) -> String {
    value.objectValue?.string("name") ?? value.objectValue?.string("id") ?? value.display
}

private func skillDisplayName(_ value: JSONValue) -> String {
    skillName(value)
        .replacingOccurrences(of: "-", with: " ")
        .replacingOccurrences(of: "_", with: " ")
        .capitalized
}

private func skillPath(_ value: JSONValue) -> String? {
    value.objectValue?.string("path")
}

private struct ModelReasoningChip: View {
    @ObservedObject var store: NtrpStore
    var showModelLabel = true
    @State private var saving = false
    @State private var open = false
    @State private var query = ""

    private var currentModel: String {
        store.serverConfig?.chatModel ?? "model"
    }

    private var currentEffort: String? {
        store.serverConfig?.reasoningEffort
    }

    private var shortModel: String {
        currentModel.split(separator: "/").last.map(String.init) ?? currentModel
    }

    private var groups: [[String: JSONValue]] {
        guard let source = store.serverModels?.value(for: "groups")?.arrayValue, !source.isEmpty else {
            let models = store.serverModels?.value(for: "models")?.arrayValue ?? []
            return [["provider": .string("all"), "models": .array(models)]]
        }
        return source.compactMap(\.objectValue)
    }

    private var filteredGroups: [[String: JSONValue]] {
        let needle = query.trimmingCharacters(in: .whitespacesAndNewlines).lowercased()
        guard !needle.isEmpty else { return groups }
        return groups.compactMap { group in
            let models = modelIDs(in: group).filter { $0.lowercased().contains(needle) }
            guard !models.isEmpty else { return nil }
            var next = group
            next["models"] = .array(models.map { .string($0) })
            return next
        }
    }

    private var efforts: [String] {
        store.serverConfigRaw?.value(for: "reasoning_efforts")?.arrayValue?.map(\.display) ?? []
    }

    private var modelEfforts: [String: JSONValue] {
        store.serverConfigRaw?.value(for: "model_reasoning_efforts")?.objectValue ?? [:]
    }

    var body: some View {
        Button {
            open.toggle()
        } label: {
            HStack(spacing: 5) {
                if showModelLabel {
                    Text(saving ? "Saving..." : shortModel)
                        .font(.system(size: 12, weight: .medium, design: .monospaced))
                        .lineLimit(1)
                }
                if let currentEffort, !currentEffort.isEmpty {
                    if showModelLabel {
                        Text("·")
                    }
                    Text(currentEffort)
                        .font(.system(size: 12, weight: .medium))
                        .lineLimit(1)
                }
                Image(systemName: "chevron.down")
                    .font(.system(size: 13, weight: .semibold))
                    .opacity(0.65)
            }
            .foregroundStyle(NtrpColors.muted)
            .padding(.leading, 10)
            .padding(.trailing, 8)
            .frame(height: 28)
            .background(NtrpColors.row.opacity(0.0))
            .clipShape(Capsule())
        }
        .buttonStyle(.plain)
        .disabled(saving || store.serverConfig == nil)
        .popover(isPresented: $open, arrowEdge: .top) {
            pickerPopover
        }
    }

    private func patch(_ patch: [String: JSONValue]) {
        saving = true
        Task {
            await store.patchServerConfig(patch)
            saving = false
        }
    }

    private var pickerPopover: some View {
        VStack(alignment: .leading, spacing: 0) {
            if !efforts.isEmpty {
                VStack(alignment: .leading, spacing: 7) {
                    Text("REASONING EFFORT")
                        .font(.system(size: 10, weight: .semibold))
                        .tracking(0.9)
                        .foregroundStyle(NtrpColors.faint)
                    HStack(spacing: 5) {
                        effortPill("off", active: currentEffort == nil) {
                            patch(["reasoning_effort": .null])
                        }
                        ForEach(efforts, id: \.self) { effort in
                            effortPill(effort, active: currentEffort == effort) {
                                patch(["reasoning_effort": .string(effort)])
                            }
                        }
                    }
                }
                .padding(.horizontal, 12)
                .padding(.top, 10)
                .padding(.bottom, 9)
                Divider().overlay(NtrpColors.sidebarStroke.opacity(0.7))
            }

            TextField("Search models...", text: $query)
                .textFieldStyle(.plain)
                .font(.system(size: 13))
                .foregroundStyle(NtrpColors.text)
                .padding(.horizontal, 12)
                .frame(height: 34)
                .overlay(alignment: .bottom) {
                    Rectangle()
                        .fill(NtrpColors.sidebarStroke.opacity(0.7))
                        .frame(height: 1)
                }

            ScrollView {
                LazyVStack(alignment: .leading, spacing: 0) {
                    if filteredGroups.isEmpty {
                        Text("No matches.")
                            .font(.system(size: 13))
                            .foregroundStyle(NtrpColors.faint)
                            .italic()
                            .padding(.horizontal, 12)
                            .padding(.vertical, 9)
                    } else {
                        ForEach(filteredGroups.indices, id: \.self) { index in
                            let group = filteredGroups[index]
                            let provider = group.string("provider") ?? "models"
                            if groups.count > 1 {
                                Text(providerLabel(provider).uppercased())
                                    .font(.system(size: 10, weight: .semibold))
                                    .tracking(0.9)
                                    .foregroundStyle(NtrpColors.faint)
                                    .padding(.horizontal, 12)
                                    .padding(.top, index == 0 ? 8 : 10)
                                    .padding(.bottom, 3)
                            }
                            ForEach(modelIDs(in: group), id: \.self) { model in
                                modelRow(model)
                            }
                        }
                    }
                }
                .padding(.vertical, 4)
            }
            .frame(maxHeight: 260)
        }
        .frame(width: 300)
        .background(NtrpColors.surfaceFill(0.62))
        .ntrpGlass(cornerRadius: 14, interactive: true)
    }

    private func effortPill(_ label: String, active: Bool, action: @escaping () -> Void) -> some View {
        Button(action: action) {
            Text(label)
                .font(.system(size: 12, weight: .medium))
                .foregroundStyle(active ? NtrpColors.text : NtrpColors.muted)
                .padding(.horizontal, 8)
                .frame(height: 22)
                .background(active ? NtrpColors.rowActive : NtrpColors.row.opacity(0.45))
                .clipShape(Capsule())
        }
        .buttonStyle(.plain)
    }

    private func modelRow(_ model: String) -> some View {
        Button {
            if model != currentModel {
                patch(["chat_model": .string(model)])
            }
            query = ""
        } label: {
            HStack(spacing: 8) {
                Group {
                    if model == currentModel {
                        Image(systemName: "checkmark")
                            .font(.system(size: 11, weight: .bold))
                            .foregroundStyle(NtrpColors.accent)
                    } else {
                        Color.clear
                    }
                }
                .frame(width: 14)
                Text(model)
                    .font(.system(size: 13, design: .monospaced))
                    .foregroundStyle(NtrpColors.text)
                    .lineLimit(1)
                    .truncationMode(.middle)
                Spacer(minLength: 8)
                if let effort = modelEfforts[model]?.stringValue, !effort.isEmpty {
                    Text(effort)
                        .font(.system(size: 11))
                        .foregroundStyle(NtrpColors.faint)
                        .lineLimit(1)
                }
            }
            .padding(.horizontal, 10)
            .frame(height: 28)
            .background(model == currentModel ? NtrpColors.rowActive.opacity(0.75) : Color.clear)
            .clipShape(RoundedRectangle(cornerRadius: 7, style: .continuous))
        }
        .buttonStyle(.plain)
        .padding(.horizontal, 6)
    }

    private func providerLabel(_ provider: String) -> String {
        switch provider {
        case "anthropic": "Anthropic"
        case "openai": "OpenAI"
        case "google": "Google"
        case "openrouter": "OpenRouter"
        case "xai": "xAI"
        case "custom": "Custom"
        default: provider
        }
    }

    private func modelIDs(in group: [String: JSONValue]) -> [String] {
        group.array("models").compactMap { value in
            if let id = value.stringValue { return id }
            return value.objectValue?.string("id")
        }
    }
}

private struct ApprovalModeChip: View {
    @ObservedObject var store: NtrpStore
    var showLabel = true
    @State private var pending = false

    var body: some View {
        Button {
            pending = true
            Task {
                await store.toggleAutoApprovals(!store.skipApprovals)
                pending = false
            }
        } label: {
            HStack(spacing: 5) {
                Image(systemName: store.skipApprovals ? "shield.slash" : "shield.checkered")
                    .font(.system(size: 14, weight: .medium))
                if showLabel {
                    Text(store.skipApprovals ? "Auto" : "Approve")
                        .font(.system(size: 13, weight: .medium))
                }
            }
            .foregroundStyle(store.skipApprovals ? NtrpColors.accent : NtrpColors.muted)
            .padding(.horizontal, 10)
            .frame(height: 28)
            .background(store.skipApprovals ? NtrpColors.accent.opacity(0.14) : Color.clear)
            .clipShape(Capsule())
            .help(store.skipApprovals ? "Auto-approving every tool call. Click to require approval." : "Approvals required for sensitive tools. Click to enable Auto mode.")
        }
        .buttonStyle(.plain)
        .disabled(pending || store.selectedSessionID == nil)
    }
}

private struct BudgetChip: View {
    let usage: SessionUsage
    let config: ServerConfig?

    var body: some View {
        HStack(spacing: 7) {
            BudgetRing(tokenRatio: tokenRatio, messageRatio: messageRatio)
                .frame(width: 18, height: 18)
            Text(label)
                .font(.system(size: 12))
                .monospacedDigit()
        }
        .foregroundStyle(NtrpColors.muted)
        .padding(.horizontal, 8)
        .frame(height: 28)
        .clipShape(Capsule())
        .help(help)
    }

    private var tokenLimit: Int {
        guard let config else { return 0 }
        return Int(Double(config.chatModelMaxContext) * config.compressionThreshold)
    }

    private var tokenRatio: Double {
        guard tokenLimit > 0 else { return 0 }
        return min(1, Double(usage.lastPrompt) / Double(tokenLimit))
    }

    private var messageRatio: Double {
        guard let maxMessages = config?.maxMessages, maxMessages > 0 else { return 0 }
        return min(1, Double(usage.messageCount) / Double(maxMessages))
    }

    private var label: String {
        if usage.lastPrompt > 0 {
            return formatTokens(usage.lastPrompt)
        }
        return "—"
    }

    private var help: String {
        guard let config else { return "Context budget" }
        return "\(formatTokens(usage.lastPrompt)) / \(formatTokens(tokenLimit)) tokens · \(usage.messageCount) / \(config.maxMessages) msgs"
    }

    private func formatTokens(_ value: Int) -> String {
        if value < 1_000 { return "\(value)" }
        if value < 10_000 {
            let n = Double(value) / 1_000
            return String(format: "%.1fk", n)
        }
        return "\(Int(round(Double(value) / 1_000)))k"
    }
}

private struct GoalProposalCard: View {
    let objective: String
    let accept: () -> Void
    let edit: () -> Void
    let cancel: () -> Void

    var body: some View {
        HStack(alignment: .top, spacing: 8) {
            Image(systemName: "target")
                .font(.system(size: 14, weight: .medium))
                .foregroundStyle(NtrpColors.accent)
                .frame(width: 18, height: 18)
                .padding(.top, 2)

            VStack(alignment: .leading, spacing: 1) {
                Text("Proposed goal")
                    .font(.system(size: 11, weight: .medium))
                    .foregroundStyle(NtrpColors.muted)
                Text(objective)
                    .font(.system(size: 14))
                    .lineSpacing(1)
                    .foregroundStyle(NtrpColors.text.opacity(0.82))
                    .lineLimit(2)
            }
            .frame(maxWidth: .infinity, alignment: .leading)

            proposalButton("checkmark", filled: true, action: accept)
                .help("Accept goal")
            proposalButton("pencil", action: edit)
                .help("Edit goal")
            proposalButton("xmark", action: cancel)
                .help("Cancel goal")
        }
        .padding(.horizontal, 12)
        .padding(.vertical, 8)
        .background(NtrpColors.surfaceFill(0.55))
        .overlay(
            RoundedRectangle(cornerRadius: 14, style: .continuous)
                .stroke(NtrpColors.sidebarStroke.opacity(0.7), lineWidth: 1)
        )
        .clipShape(RoundedRectangle(cornerRadius: 14, style: .continuous))
        .shadow(color: .black.opacity(0.18), radius: 5, x: 0, y: 2)
        .ntrpGlass(cornerRadius: 14, interactive: false)
    }

    private func proposalButton(_ icon: String, filled: Bool = false, action: @escaping () -> Void) -> some View {
        Button(action: action) {
            Image(systemName: icon)
                .font(.system(size: 12, weight: .semibold))
                .foregroundStyle(filled ? Color.black.opacity(0.82) : NtrpColors.muted)
                .frame(width: 28, height: 28)
                .background(filled ? NtrpColors.text : Color.clear)
                .clipShape(Circle())
                .contentShape(Circle())
        }
        .buttonStyle(.plain)
    }
}

private struct LoopChip: View {
    @ObservedObject var store: NtrpStore
    @ObservedObject var ui: NtrpUIState
    var showLabel = true
    @State private var popoverOpen = false

    private var loops: [LoopSummary] {
        store.activeLoops.sorted { lhs, rhs in
            let lhsDate = lhs.nextRunAt.flatMap(loopDate(from:)) ?? .distantFuture
            let rhsDate = rhs.nextRunAt.flatMap(loopDate(from:)) ?? .distantFuture
            return lhsDate < rhsDate
        }
    }

    var body: some View {
        if let next = loops.first {
            Button {
                popoverOpen.toggle()
            } label: {
                HStack(spacing: 5) {
                    Image(systemName: "arrow.triangle.2.circlepath")
                    if loops.count == 1 {
                        if showLabel {
                            Text("Loop")
                            Text("·")
                        }
                        Text(countdownText(for: next))
                    } else {
                        if showLabel {
                            Text("Loops")
                            Text("·")
                            Text("\(loops.count)")
                            Text("· next")
                        }
                        Text(countdownText(for: next))
                    }
                }
                .font(.system(size: 13, weight: .medium))
                .foregroundStyle(NtrpColors.muted)
                .padding(.horizontal, 10)
                .frame(height: 28)
                .clipShape(Capsule())
            }
            .buttonStyle(.plain)
            .help(next.prompt ?? "Active loop")
            .popover(isPresented: $popoverOpen, arrowEdge: .bottom) {
                loopPopover
                    .frame(width: 360)
                    .padding(12)
                    .background(NtrpColors.surfaceFill(0.90))
            }
        }
    }

    private var loopPopover: some View {
        VStack(alignment: .leading, spacing: 8) {
            Text("Active loops")
                .font(.system(size: 12, weight: .medium))
                .foregroundStyle(NtrpColors.muted)
                .padding(.horizontal, 4)

            ForEach(loops) { loop in
                HStack(alignment: .top, spacing: 8) {
                    Button {
                        Task { await store.stopLoop(loop) }
                    } label: {
                        Image(systemName: "xmark")
                            .font(.system(size: 11, weight: .semibold))
                            .foregroundStyle(NtrpColors.faint)
                            .frame(width: 20, height: 20)
                            .contentShape(Rectangle())
                    }
                    .buttonStyle(.plain)
                    .help("Stop loop")

                    Button {
                        ui.viewingLoop = loop
                        popoverOpen = false
                    } label: {
                        VStack(alignment: .leading, spacing: 2) {
                            Text(loop.prompt ?? "Loop")
                                .font(.system(size: 13))
                                .foregroundStyle(NtrpColors.text)
                                .lineLimit(1)
                                .frame(maxWidth: .infinity, alignment: .leading)
                            Text(loopDetail(loop))
                                .font(.system(size: 11))
                                .foregroundStyle(NtrpColors.faint)
                                .lineLimit(2)
                        }
                        .padding(.vertical, 5)
                        .padding(.trailing, 6)
                        .contentShape(Rectangle())
                    }
                    .buttonStyle(.plain)
                }
                .padding(.horizontal, 6)
                .background(Color.clear)
                .clipShape(RoundedRectangle(cornerRadius: 8, style: .continuous))
            }
        }
    }

    private func countdownText(for loop: LoopSummary) -> String {
        guard
            let nextRunAt = loop.nextRunAt,
            let date = loopDate(from: nextRunAt)
        else {
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

    private func loopDetail(_ loop: LoopSummary) -> String {
        var parts = ["Every \(loop.every)", "next in \(countdownText(for: loop))"]
        if let max = loop.maxIterations {
            parts.append("\(loop.iterationCount)/\(max)")
        } else if loop.iterationCount > 0 {
            parts.append("iter \(loop.iterationCount)")
        }
        if let days = loop.maxAgeDays {
            parts.append("expires after \(days)d")
        }
        if let stopWhen = loop.stopWhen, !stopWhen.isEmpty {
            parts.append("stops when: \(stopWhen)")
        }
        parts.append(loop.id)
        return parts.joined(separator: " · ")
    }
}

private struct BudgetRing: View {
    let tokenRatio: Double
    let messageRatio: Double

    var body: some View {
        ZStack {
            Circle()
                .stroke(NtrpColors.muted.opacity(0.22), lineWidth: 2.2)
            Circle()
                .trim(from: 0, to: tokenRatio)
                .stroke(color(for: tokenRatio), style: StrokeStyle(lineWidth: 2.2, lineCap: .round))
                .rotationEffect(.degrees(-90))
            Circle()
                .inset(by: 4)
                .stroke(NtrpColors.muted.opacity(0.22), lineWidth: 2)
            Circle()
                .inset(by: 4)
                .trim(from: 0, to: messageRatio)
                .stroke(color(for: messageRatio), style: StrokeStyle(lineWidth: 2, lineCap: .round))
                .rotationEffect(.degrees(-90))
        }
    }

    private func color(for ratio: Double) -> Color {
        if ratio >= 0.9 { return Color(red: 0.72, green: 0.27, blue: 0.17) }
        if ratio >= 0.7 { return Color(red: 0.79, green: 0.54, blue: 0.17) }
        return NtrpColors.muted
    }
}
