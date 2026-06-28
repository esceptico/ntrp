import { DISSOLVE_OUT, EASE_OUT, MOTION } from "@/lib/tokens/motion";

// Composer sub-sections (editing banner, image strip, skill pill, goal
// proposal) rise into focus on mount and dissolve out faster on unmount;
// the composer's height snaps at the AnimatePresence boundary.
export const SECTION_ENTER = { duration: MOTION.row, ease: EASE_OUT };
export const SECTION_EXIT = { ...DISSOLVE_OUT, transition: { duration: MOTION.fast, ease: EASE_OUT } };
