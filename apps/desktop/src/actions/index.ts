// Public action surface — keep this barrel stable so call sites don't have
// to know which file an action lives in. Implementations are organized by
// feature in sibling files.

export { truncatePrompt } from "./_shared";
export {
  historyMessagesToUi,
  loadHistory,
  loadNewerHistory,
  loadOlderHistory,
} from "./history";
export { bootstrap, refresh } from "./bootstrap";
export {
  fetchServerConfig,
  saveAndReconnect,
  updateServerConfig,
} from "./server";
export { fetchSkills, viewSkill } from "./skills";
export {
  archiveSession,
  branchAtMessage,
  createProject,
  createSession,
  fetchArchivedSessions,
  moveSessionToProject,
  permanentlyDeleteSession,
  refreshProjects,
  renameSession,
  restoreArchivedSession,
  saveProject,
  switchSession,
} from "./sessions";
export {
  cancelSubagent,
  cancelQueuedMessage,
  enqueueMessage,
  sendMessage,
  stopRun,
} from "./messages";
export { respondToAllApprovals, respondToApproval } from "./approvals";
export {
  BUILTIN_COMMANDS,
  isBuiltin,
  runBuiltinCommand,
  type BuiltinCommand,
} from "./builtins";
export { refreshLoops, stopLoop, toggleAuto } from "./loops";
export {
  acceptGoalProposal,
  cancelGoalProposal,
  clearGoal,
  editGoalProposal,
  fetchGoal,
  proposeGoal,
  setGoal,
  updateGoal,
} from "./goals";
export {
  createAutomation,
  deleteAutomation,
  fetchAutomations,
  runAutomation,
  toggleAutomation,
  updateAutomation,
} from "./automations";
