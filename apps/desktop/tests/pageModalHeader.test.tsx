import { afterEach, expect, test } from "bun:test";
import { act } from "react";
import { createRoot } from "react-dom/client";
import { PageModal } from "@/components/ui/PageModal";

// PageModal portals into #app; set one up + a mount host.
function setup() {
  const app = document.createElement("div");
  app.id = "app";
  document.body.appendChild(app);
  const host = document.createElement("div");
  document.body.appendChild(host);
  const root = createRoot(host);
  return {
    app,
    root,
    cleanup: () => {
      root.unmount();
      app.remove();
      host.remove();
    },
  };
}

afterEach(() => {
  document.querySelectorAll("#app").forEach((n) => n.remove());
});

test("PageModal header keeps min-w-0 so a long title/subtitle can't push the close button off-screen", async () => {
  const { app, root, cleanup } = setup();
  try {
    await act(async () => {
      root.render(
        <PageModal
          open
          onClose={() => {}}
          ariaLabel="t"
          header={{ title: "x".repeat(80), subtitle: "y".repeat(120) }}
        >
          <div>body</div>
        </PageModal>,
      );
    });
    const header = app.querySelector("header");
    expect(header).not.toBeNull();
    // The header is a grid item (min-width:auto by default); without min-w-0 a
    // long nowrap title expands it past the fixed-width panel and the close
    // button gets clipped by the panel's overflow-hidden. This guards the fix.
    expect(header!.className).toContain("min-w-0");
    // Title/subtitle must carry `truncate` so the constrained header clips them.
    expect(header!.querySelector(".truncate")).not.toBeNull();
    // The close control must render.
    expect(app.querySelector('[aria-label="Close"]')).not.toBeNull();
  } finally {
    cleanup();
  }
});
