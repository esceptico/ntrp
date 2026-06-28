import { EASE_OUT, MOTION, ROW_EXIT, SPRING_ROW_ENTRY } from "@/lib/tokens/motion";

// One list-motion recipe for every roster section (todos, agents, workflows,
// automations): under popLayout the removed row dissolves out of flow while
// siblings FLIP up on SPRING_ROW_ENTRY. Spread onto the keyed motion.div.
export const rosterRowMotion = {
  layout: true,
  initial: { opacity: 0, y: -4 },
  animate: { opacity: 1, y: 0 },
  exit: { ...ROW_EXIT, transition: { duration: MOTION.fast, ease: EASE_OUT } },
  transition: { layout: SPRING_ROW_ENTRY, duration: MOTION.row, ease: EASE_OUT },
} as const;
