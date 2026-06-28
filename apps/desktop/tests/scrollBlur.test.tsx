import { expect, test } from "bun:test";
import { act } from "react";
import { createRoot } from "react-dom/client";
import { ScrollBlurTop } from "@/components/ui/ScrollBlur";

test("top blur observes the message scroller without living inside its scroll flow", async () => {
  const rootEl = document.createElement("div");
  document.body.append(rootEl);
  try {
    const scroller = document.createElement("div");
    const blurHost = document.createElement("div");
    rootEl.append(scroller, blurHost);

    const root = createRoot(blurHost);
    await act(async () => {
      root.render(<ScrollBlurTop scrollerRef={{ current: scroller }} />);
    });

    const blur = blurHost.querySelector<HTMLElement>(".scroll-progressive-blur-top");
    expect(blur).not.toBeNull();
    expect(blur?.parentElement).toBe(blurHost);
    expect(scroller.contains(blur)).toBe(false);
    expect(blur?.dataset.scrolled).toBe("false");

    await act(async () => {
      scroller.scrollTop = 12;
      scroller.dispatchEvent(new Event("scroll"));
    });
    expect(blur?.dataset.scrolled).toBe("true");

    await act(async () => {
      scroller.scrollTop = 0;
      scroller.dispatchEvent(new Event("scroll"));
    });
    expect(blur?.dataset.scrolled).toBe("false");

    await act(async () => root.unmount());
  } finally {
    rootEl.remove();
  }
});
