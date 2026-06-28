import { useEffect, useMemo, useRef, useState } from "react";
import clsx from "clsx";
import { activityItemStatus } from "@/lib/agent";
import { resolutionFromResult, type HtmlWidgetResolution } from "@/lib/htmlWidget";
import { respondToHtmlInput } from "@/actions/htmlInput";
import { Badge, type BadgeTone } from "@/components/ui/Badge";
import { Button } from "@/components/ui/Button";
import { BlurSwap } from "@/components/ui/BlurSwap";
import type { ActivityItem } from "@/stores";
import { buildSrcdoc, snapshotThemeVars, WIDGET_SANDBOX } from "@/features/chat/lib/srcdoc";

const INITIAL_HEIGHT = 160;
const MIN_HEIGHT = 56;
const MAX_HEIGHT = 640;

// Relative so it resolves next to index.html under both the Vite dev server
// and the packaged file:// build (vite base is "./").
const WIDGET_FRAME_SRC = "widget-frame.html";

interface BridgeMessage {
  jsonrpc?: unknown;
  method?: unknown;
  params?: { values?: unknown; height?: unknown };
}

// The render_html tool's lifted card. The iframe loads the widget-frame.html
// shell (NOT srcdoc directly: srcdoc inherits the app's strict CSP, which
// blocks the widget's inline scripts — the shell is a real document with its
// own inline-friendly CSP, and nests the sandboxed srcdoc widget inside).
// The shell announces ui/ready, the card answers ui/init with the built
// srcdoc, and relays the widget's bridge messages upward unchanged.
// Input-mode cards stay interactive until the call resolves (envelope in
// `item.result`, or a local optimistic action while the POST is in flight),
// then freeze — pointer-events is the only lever the host has into a sandboxed
// document, and keeping the iframe mounted preserves the user's entered values.
export function HtmlWidgetCard({ item }: { item: ActivityItem }) {
  const widget = item.htmlWidget;
  const [height, setHeight] = useState(INITIAL_HEIGHT);
  const [localAction, setLocalAction] = useState<HtmlWidgetResolution["action"] | null>(null);
  const iframeRef = useRef<HTMLIFrameElement>(null);

  const srcdoc = useMemo(
    () => buildSrcdoc(widget?.html ?? "", snapshotThemeVars(document.documentElement)),
    [widget?.html],
  );
  const srcdocRef = useRef(srcdoc);
  srcdocRef.current = srcdoc;

  const resolution = resolutionFromResult(item.result);
  const pending =
    widget?.mode === "input" && !resolution && !localAction && activityItemStatus(item) === "ongoing";
  const frozen = widget?.mode === "input" && (resolution != null || localAction != null);

  const resolve = (action: HtmlWidgetResolution["action"], values: Record<string, unknown>) => {
    setLocalAction(action);
    void respondToHtmlInput(item.id, action, values).then((ok) => {
      if (!ok) setLocalAction(null);
    });
  };

  useEffect(() => {
    const onMessage = (event: MessageEvent) => {
      if (event.source !== iframeRef.current?.contentWindow) return;
      const message = event.data as BridgeMessage | null;
      if (message?.jsonrpc !== "2.0") return;
      if (message.method === "ui/ready") {
        iframeRef.current?.contentWindow?.postMessage(
          { jsonrpc: "2.0", method: "ui/init", params: { srcdoc: srcdocRef.current } },
          "*",
        );
        return;
      }
      if (message.method === "ui/size-changed") {
        const reported = message.params?.height;
        if (typeof reported === "number" && Number.isFinite(reported)) {
          setHeight(Math.min(Math.max(reported, MIN_HEIGHT), MAX_HEIGHT));
        }
        return;
      }
      if (!pending) return;
      if (message.method === "ui/submit") {
        const values = message.params?.values;
        resolve("accept", values && typeof values === "object" ? (values as Record<string, unknown>) : {});
      } else if (message.method === "ui/cancel") {
        resolve("cancel", {});
      }
    };
    window.addEventListener("message", onMessage);
    return () => window.removeEventListener("message", onMessage);
    // resolve only closes over item.id (and stable setters), covered below.
  }, [pending, item.id]);

  if (!widget) return null;

  const badge = widgetBadge(item, widget.mode, pending, resolution?.action ?? localAction);

  return (
    <div className="surface-card overflow-hidden">
      <div className="px-3 py-2 border-b border-line-soft flex items-center gap-2">
        <span className="min-w-0 flex-1 truncate text-sm font-medium text-ink">{widget.title}</span>
        {badge && (
          <BlurSwap swapKey={badge.label} blur={3} className="shrink-0">
            <Badge tone={badge.tone}>{badge.label}</Badge>
          </BlurSwap>
        )}
        {pending && (
          <Button
            variant="danger"
            size="sm"
            onClick={() => resolve("decline", {})}
            className="shrink-0"
          >
            Decline
          </Button>
        )}
      </div>
      <div className={clsx(frozen && "pointer-events-none opacity-60")}>
        <iframe
          ref={iframeRef}
          sandbox={WIDGET_SANDBOX}
          src={WIDGET_FRAME_SRC}
          title={widget.title}
          style={{ height }}
          className="w-full border-0 block"
        />
      </div>
    </div>
  );
}

function widgetBadge(
  item: ActivityItem,
  mode: "display" | "input",
  pending: boolean,
  action: HtmlWidgetResolution["action"] | null,
): { tone: BadgeTone; label: string } | null {
  if (item.error) return { tone: "bad", label: "Error" };
  if (mode !== "input") return null;
  if (action === "accept") return { tone: "ok", label: "Submitted" };
  if (action === "decline") return { tone: "neutral", label: "Declined" };
  if (action === "cancel") return { tone: "neutral", label: "Dismissed" };
  if (pending) return { tone: "accent", label: "Awaiting input" };
  return null;
}
