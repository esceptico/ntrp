import { motion } from "motion/react";
import { Settings, Sparkles } from "lucide-react";
import { useStore } from "@/stores";
import { Button } from "@/components/ui/Button";
import { EASE_DECELERATE, MOTION, RISE_IN, RISE_SETTLED, originFromEvent } from "@/lib/tokens/motion";
import { ICON } from "@/lib/icons";

export function HomeHero() {
  const connected = useStore((s) => s.connected);
  const openSettings = useStore((s) => s.openSettings);
  return (
    <motion.div
      initial={RISE_IN}
      animate={RISE_SETTLED}
      transition={{ duration: MOTION.trace, ease: EASE_DECELERATE }}
      className="mt-[14vh] mx-auto grid gap-5 justify-items-center text-center"
    >
      <span
        aria-hidden
        className="grid place-items-center w-12 h-12 rounded-2xl bg-accent-soft text-accent-strong"
      >
        <Sparkles size={ICON.HERO} strokeWidth={2} />
      </span>
      <div className="grid gap-1.5 max-w-[420px]">
        <h2 className="m-0 text-2xl font-semibold tracking-[-0.018em] text-ink">
          {connected ? "What's on your mind?" : "Connect to get started"}
        </h2>
        <p className="m-0 text-base text-muted leading-snug">
          {connected
            ? "Send a message, or press ⌘K to search memory, agents, and tools."
            : "Open settings to point ntrp at your server."}
        </p>
      </div>
      {!connected && (
        <Button
          variant="secondary"
          size="md"
          leadingIcon={Settings}
          onClick={(e) => openSettings(originFromEvent(e.currentTarget), "connection")}
        >
          Open settings
        </Button>
      )}
    </motion.div>
  );
}
