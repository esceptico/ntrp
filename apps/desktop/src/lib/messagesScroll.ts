type ScrollFn = (behavior?: "smooth" | "instant") => void;

export const messagesScroll: { scrollToBottom: ScrollFn | null } = {
  scrollToBottom: null,
};
