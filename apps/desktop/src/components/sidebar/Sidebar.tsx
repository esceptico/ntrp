import { Brain, Pencil, Settings as SettingsIcon, Zap } from "lucide-react";
import { originFromEvent } from "../../lib/tokens/motion";
import { useStore } from "../../store";
import { createSession, fetchAutomations } from "../../actions";
import { ICON } from "../../lib/icons";
import { useVisibilityPoll } from "../../lib/hooks";
import { NavRow } from "./NavRow";
import { SessionList } from "./SessionList";

export function Sidebar() {
  const openSettings = useStore((s) => s.openSettings);
  const openAutomations = useStore((s) => s.openAutomations);
  const openMemory = useStore((s) => s.openMemory);
  useVisibilityPoll(fetchAutomations, 20_000);

  return (
    <aside className="sidebar flex flex-col h-full">
      {/* Drag region. Height tuned so nav rows start just below the
          macOS traffic-lights zone, not below a 38px chrome ribbon. */}
      <div className="drag-spacer shrink-0 h-[22px]" />
      <nav className="flex flex-col gap-px px-2.5 pt-2">
        <NavRow
          icon={<Pencil size={ICON.LG} strokeWidth={2} />}
          label="New session"
          onClick={() => void createSession()}
        />
        <NavRow
          icon={<Zap size={ICON.LG} strokeWidth={2} />}
          label="Automations"
          onClick={(e) => openAutomations(originFromEvent(e.currentTarget))}
        />
        <NavRow
          icon={<Brain size={ICON.LG} strokeWidth={2} />}
          label="Memory"
          onClick={(e) => openMemory(originFromEvent(e.currentTarget))}
        />
      </nav>
      <SessionList />
      <nav className="flex flex-col gap-px px-2.5 pt-1.5 pb-3">
        <NavRow
          icon={<SettingsIcon size={ICON.LG} strokeWidth={2} />}
          label="Settings"
          onClick={(e) => openSettings(originFromEvent(e.currentTarget))}
        />
      </nav>
    </aside>
  );
}
