import { useEffect, useState } from "react";
import {
  ActivityHeader,
  ActivityTail,
  ActivityTrace,
  type ActivityItem,
} from "./ActivityTrace";

const KINDS = ["read", "search", "list", "find"] as const;
const SAMPLE_TARGETS: Record<string, string[]> = {
  read: ["bash.ts", "main.tsx", "store.ts", "styles.css", "package.json"],
  search: ['"createSignal"', '"useEffect"', '"setState"', '"renderMarkdown"'],
  list: ["components", "src", "hooks", "components/trace"],
  find: ["**/*.tsx", "**/*.ts", "src/**/Message.tsx"],
};

function randomItem(): ActivityItem {
  const kind = KINDS[Math.floor(Math.random() * KINDS.length)];
  const targets = SAMPLE_TARGETS[kind];
  const target = targets[Math.floor(Math.random() * targets.length)];
  return { id: crypto.randomUUID(), kind, target };
}

export function Demo() {
  const [items, setItems] = useState<ActivityItem[]>([]);
  const [label, setLabel] = useState("Calling");
  const [expanded, setExpanded] = useState(false);

  useEffect(() => {
    const interval = setInterval(() => {
      setItems((prev) => [...prev, randomItem()]);
    }, 1400);

    const finish = setTimeout(() => {
      setLabel("Called");
      clearInterval(interval);
    }, 14000);

    return () => {
      clearInterval(interval);
      clearTimeout(finish);
    };
  }, []);

  const done = label === "Called";
  const collapsed = done && !expanded;
  const max = done && expanded ? undefined : 3;

  return (
    <div className="grid place-items-center min-h-screen bg-bg-main">
      <div className="w-[560px] p-10 rounded-2xl border border-line bg-bg-main">
        <p className="mb-6 text-[12px] uppercase tracking-[0.08em] text-faint">
          Activity trace · demo
        </p>
        <ActivityTrace>
          <ActivityHeader
            label={label}
            count={items.length}
            onToggle={done ? () => setExpanded((v) => !v) : undefined}
            expanded={expanded}
          />
          <ActivityTail items={items} max={max} collapsed={collapsed} />
        </ActivityTrace>
        <p className="mt-10 text-[12px] text-faint">
          Reload (<kbd className="font-mono">⌘R</kbd>) to restart. After 14s, click the header to expand the full list.
        </p>
      </div>
    </div>
  );
}
