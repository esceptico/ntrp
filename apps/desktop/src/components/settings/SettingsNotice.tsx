import { motion } from "motion/react";
import { RISE_IN, RISE_SETTLED, MOTION, EASE_OUT } from "@/lib/tokens/motion";

export function SettingsConnectionHint({
  title = "Connect the desktop to ntrp first",
  detail = "Check the server URL and API key in the Connection tab, then refresh this view.",
}: {
  title?: string;
  detail?: string;
}) {
  return (
    <div className="rounded-[12px] border border-line-soft bg-surface px-3.5 py-3">
      <div className="text-base font-medium text-ink">{title}</div>
      <div className="mt-1 text-sm text-muted leading-[1.45]">{detail}</div>
    </div>
  );
}

export function SettingsInlineError({ title, message }: { title: string; message: string }) {
  return (
    <motion.div
      role="alert"
      className="grid gap-0.5 px-3 py-2.5 rounded-[10px] bg-bad-soft border border-bad/15"
      initial={{ ...RISE_IN, y: -4 }}
      animate={RISE_SETTLED}
      transition={{ duration: MOTION.row, ease: EASE_OUT }}
    >
      <strong className="text-bad text-sm font-semibold">{title}</strong>
      <span className="text-sm text-bad leading-[1.4]">{message}</span>
    </motion.div>
  );
}
