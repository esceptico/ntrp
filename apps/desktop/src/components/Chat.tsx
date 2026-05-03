import { useStore } from "../store";
import { Messages } from "./Messages";
import { Composer } from "./Composer";
import { RunChip } from "./RunChip";

function ChatHeader() {
  const sessionId = useStore((s) => s.currentSessionId);
  const sessions = useStore((s) => s.sessions);
  const session = sessions.find((s) => s.session_id === sessionId);

  const title = session?.name || (sessionId ? "untitled" : "no session");
  const meta = sessionId ? sessionId.slice(0, 8) : "—";

  return (
    <div className="chat-header flex items-center gap-3 px-[18px] h-[52px]">
      <div className="flex-1 min-w-0 flex items-baseline gap-2.5 pl-1">
        <h1 className="m-0 text-[14px] font-semibold tracking-[-0.01em] text-ink truncate max-w-[50%]">
          {title}
        </h1>
        <span className="text-[11.5px] text-faint font-mono tracking-[-0.01em] truncate">
          {meta}
        </span>
      </div>
      <RunChip />
    </div>
  );
}

export function Chat() {
  return (
    <main className="min-w-0 grid grid-rows-[auto_minmax(0,1fr)_auto] bg-bg-main rounded-tl-xl overflow-hidden">
      <ChatHeader />
      <Messages />
      <Composer />
    </main>
  );
}
