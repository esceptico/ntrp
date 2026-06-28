// Public action surface — keep this barrel stable so call sites don't have
// to know which file an action lives in. Implementations are organized by
// feature in sibling files.

export { truncatePrompt } from "@/actions/_shared";
export { refreshChildAgents } from "@/actions/childAgents";
export {
  historyMessagesToUi,
  loadHistory,
  loadNewerHistory,
  loadOlderHistory,
} from "@/actions/history";
export { bootstrap, refresh } from "@/actions/bootstrap";
export {
  fetchServerConfig,
  saveAndReconnect,
  updateServerConfig,
} from "@/actions/server";
export { fetchSkills, viewSkill } from "@/actions/skills";
export {
  archiveProject,
  archiveSession,
  branchAtMessage,
  createProject,
  createSession,
  fetchArchivedSessions,
  moveSessionToProject,
  permanentlyDeleteSession,
  refreshProjects,
  refreshSessions,
  renameSession,
  restoreArchivedSession,
  saveProject,
  switchSession,
  updateSessionModelAction,
} from "@/actions/sessions";
export {
  cancelSubagent,
  cancelQueuedMessage,
  enqueueMessage,
  sendMessage,
  stopRun,
} from "@/actions/messages";
export { respondToAllApprovals, respondToApproval } from "@/actions/approvals";
export { respondToHtmlInput } from "@/actions/htmlInput";
export {
  BUILTIN_COMMANDS,
  isBuiltin,
  runBuiltinCommand,
  type BuiltinCommand,
} from "@/actions/builtins";
export { refreshLoops, stopLoop, toggleAuto } from "@/actions/loops";
export {
  acceptGoalProposal,
  cancelGoalProposal,
  clearGoal,
  editGoalProposal,
  fetchGoal,
  proposeGoal,
  setGoal,
  updateGoal,
} from "@/actions/goals";
export {
  createAutomation,
  deleteAutomation,
  dismissSuggestion,
  fetchAutomations,
  fetchAutomationSuggestions,
  refreshSuggestions,
  runAutomation,
  toggleAutomation,
  updateAutomation,
} from "@/actions/automations";
