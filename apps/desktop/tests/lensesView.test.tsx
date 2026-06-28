import { expect, test } from "bun:test";
import { act } from "react";
import React from "react";
import { createRoot } from "react-dom/client";
import { renderToStaticMarkup } from "react-dom/server";
import { JSDOM } from "jsdom";
import { ClaimBlock } from "@/components/memory/ClaimBlock";
import { LensEvidenceSearch } from "@/components/memory/LensEvidenceSearch";
import { GroupedProfiles, LensHeader } from "@/components/memory/LensesView";
import type { Lens, ProjectedGroup } from "@/api/memoryItems";

const lens: Lens = {
  id: "records",
  name: "Records",
  criterion: "approved record entries",
  entity_type: "item",
  scope: { kind: "user", key: null },
  detail_level: "structured",
  render_mode: "flat",
  provenance: "user_authored",
  status: "active",
  promoted_to: null,
  created_at: "2026-01-01T00:00:00Z",
  updated_at: "2026-01-01T00:00:00Z",
};

const config = { serverUrl: "http://server", apiKey: "test" };

// ─── Static render tests ───────────────────────────────────────────────

test("lens header keeps only the refresh action", () => {
  const html = renderToStaticMarkup(<LensHeader lens={lens} onRefresh={() => {}} refreshing={false} />);
  expect(html).toContain('aria-label="Re-evaluate"');
  expect(html).not.toContain("Group by subject");
  expect(html).not.toContain("Provenance graph");
});

test("profile rows hide source claims by default", () => {
  const groups: ProjectedGroup[] = [
    {
      subject: "Record A",
      markdown: "- stored fact <!--claim:c1-->",
      synthesized: true,
      blocks: [
        {
          claim_id: "c1",
          content: "Stored fact A.",
          provenance: "recorded",
          corroboration: 1,
          feedback: "none",
          source_refs: [],
        },
      ],
    },
  ];

  const html = renderToStaticMarkup(
    <GroupedProfiles
      groups={groups}
      editingId={null}
      busyId={null}
      exiting={null}
      onOpen={() => {}}
      onClose={() => {}}
      onCommit={() => {}}
      onPeek={() => {}}
      onExitDone={() => {}}
    />,
  );

  expect(html).toContain("Record A");
  expect(html).toContain("Sources");
  expect(html).not.toContain("Stored fact A.");
  expect(html).not.toContain("Source claim");
});

test("source claim editor keeps normal text spacing", () => {
  const html = renderToStaticMarkup(
    <ClaimBlock
      block={{
        claim_id: "c1",
        content: "Stored fact A.",
        provenance: "recorded",
        corroboration: 1,
        feedback: "none",
        source_refs: [],
      }}
      editing
      busy={false}
      onOpen={() => {}}
      onClose={() => {}}
      onCommit={() => {}}
      onPeek={() => {}}
    />,
  );

  expect(html).toContain("tracking-normal");
  expect(html).toContain("text-left");
});

test("collapsed evidence search shows Find entries, not claim authoring", () => {
  const html = renderToStaticMarkup(
    <LensEvidenceSearch
      config={config}
      lens={lens}
      memberIds={new Set()}
      onEditCriterion={() => {}}
      onPeekClaim={() => {}}
      onRefresh={() => {}}
    />,
  );
  expect(html).toContain("Find entries");
  expect(html).not.toContain("Add to this lens");
  expect(html).not.toContain("Add a claim");
});

// ─── Behavior tests (DOM-driven) ────────────────────────────────────────
//
// Search is driven via the `seed` prop — the real group-header seeding path,
// which runs the identical live-search effect a keystroke triggers (onChange ->
// setQuery). Real keystroke entry is covered by the Phase 4 live smoke; this
// pre-jsdom react-dom build can't fire onChange on the autofocused input.

test("opening the search focuses an empty input (no bespoke padding)", async () => {
  const { dom, rootEl, root, restore } = setupDom();
  try {
    await render(root, { config, lens, memberIds: new Set() });
    const openButton = [...rootEl.querySelectorAll("button")].find((b) =>
      b.textContent?.includes("Find entries"),
    );
    if (!openButton) throw new Error("missing Find entries button");
    await act(async () => {
      openButton.dispatchEvent(new dom.window.MouseEvent("click", { bubbles: true }));
    });

    const input = rootEl.querySelector("input");
    if (!input) throw new Error("missing input");
    expect(input.value).toBe("");
    expect(input.getAttribute("style") ?? "").not.toContain("padding-left");

    await act(async () => root.unmount());
  } finally {
    restore();
  }
});

test("a seeded search queries the whole pool with no scope filter", async () => {
  const calls: string[] = [];
  const { rootEl, root, restore } = setupDom(async (url) => {
    calls.push(String(url));
    return searchResponse([memoryItem("c-kevin", "Kevin Gu is a Dex collaborator.")]);
  });
  try {
    // A project-scoped lens — the old code leaked scope_kind/scope_key into the query.
    const projectLens = { ...lens, scope: { kind: "project" as const, key: "dex" } };
    await render(root, { config, lens: projectLens, memberIds: new Set(), seed: { term: "kevin", nonce: 1 } });
    await settle();

    expect(calls.length).toBe(1);
    expect(calls[0]).toContain("/admin/memory/search?");
    expect(calls[0]).toContain("q=kevin");
    expect(calls[0]).toContain("mode=fts");
    expect(calls[0]).not.toContain("scope_kind");
    expect(calls[0]).not.toContain("scope_key");
    expect(rootEl.textContent).toContain("Kevin Gu is a Dex collaborator.");

    await act(async () => root.unmount());
  } finally {
    restore();
  }
});

test("in-view results are marked; out-of-view results offer Include (no warn badge)", async () => {
  const { rootEl, root, restore } = setupDom(async () =>
    searchResponse([
      { ...memoryItem("c-in", "Kevin Gu is a Dex employee."), canonical_subject: "Kevin Gu" },
      { ...memoryItem("c-out", "Kevin Gu mentors interns."), canonical_subject: "Kevin Gu" },
    ]),
  );
  try {
    await render(root, { config, lens, memberIds: new Set(["c-in"]), seed: { term: "kevin", nonce: 1 } });
    await settle();

    expect(rootEl.textContent).toContain("In view");
    expect(rootEl.textContent).not.toContain("Review criterion");
    const includeButtons = [...rootEl.querySelectorAll("button")].filter(
      (b) => b.getAttribute("aria-label") === "Include in this view",
    );
    expect(includeButtons.length).toBe(1);

    await act(async () => root.unmount());
  } finally {
    restore();
  }
});

test("including an out-of-view result writes back and marks it Included", async () => {
  const writes: unknown[] = [];
  let refreshed = 0;
  const { dom, rootEl, root, restore } = setupDom(async (url, init) => {
    const path = String(url);
    if (path.includes("/admin/memory/search")) {
      return searchResponse([memoryItem("c-kevin", "Kevin Gu is a Dex collaborator.")]);
    }
    if (path.includes("/admin/memory/lenses/records/writeback")) {
      writes.push(JSON.parse(String(init?.body)));
      return jsonResponse({
        applied: [{ kind: "include", id: "c-kevin" }],
        rejected: [],
        rederive_triggered: true,
      });
    }
    throw new Error(`unexpected fetch ${path}`);
  });
  try {
    await render(root, {
      config,
      lens,
      memberIds: new Set(),
      seed: { term: "kevin", nonce: 1 },
      onRefresh: () => {
        refreshed += 1;
      },
    });
    await settle();

    const includeButton = [...rootEl.querySelectorAll("button")].find(
      (b) => b.getAttribute("aria-label") === "Include in this view",
    );
    if (!includeButton) throw new Error("missing include button");
    await act(async () => {
      includeButton.dispatchEvent(new dom.window.MouseEvent("click", { bubbles: true }));
    });

    expect(writes).toEqual([{ ops: [{ kind: "include", claim_id: "c-kevin" }] }]);
    expect(refreshed).toBe(1);
    expect(rootEl.textContent).toContain("Included");

    await act(async () => root.unmount());
  } finally {
    restore();
  }
});

test("a nonce of 0 does not open the panel", async () => {
  const { rootEl, root, restore } = setupDom(async () => searchResponse([]));
  try {
    await render(root, { config, lens, memberIds: new Set(), seed: { term: "kevin", nonce: 0 } });
    await settle();
    expect(rootEl.textContent).toContain("Find entries");
    expect(rootEl.querySelector("input")).toBeNull();
    await act(async () => root.unmount());
  } finally {
    restore();
  }
});

test("responses after unmount are ignored", async () => {
  const pending: ((r: Response) => void)[] = [];
  const { root, rootEl, restore } = setupDom(
    async () => new Promise<Response>((resolve) => pending.push(resolve)),
  );
  try {
    await render(root, { config, lens, memberIds: new Set(), seed: { term: "kevin", nonce: 1 } });
    await settle();
    await act(async () => root.unmount());

    await act(async () => {
      pending[0]?.(searchResponse([memoryItem("c-kevin", "Kevin Gu is a Dex collaborator.")]));
    });
    expect(rootEl.textContent).toBe("");
  } finally {
    restore();
  }
});

test("closing the search dismisses it and discards a late response", async () => {
  const pending: ((r: Response) => void)[] = [];
  const { dom, rootEl, root, restore } = setupDom(
    async () => new Promise<Response>((resolve) => pending.push(resolve)),
  );
  try {
    await render(root, { config, lens, memberIds: new Set(), seed: { term: "kevin", nonce: 1 } });
    await settle();

    const closeButton = [...rootEl.querySelectorAll("button")].find(
      (b) => b.getAttribute("aria-label") === "Close search",
    );
    if (!closeButton) throw new Error("missing close button");
    await act(async () => {
      closeButton.dispatchEvent(new dom.window.MouseEvent("click", { bubbles: true }));
    });

    expect(rootEl.textContent).toContain("Find entries");

    await act(async () => {
      pending[0]?.(searchResponse([memoryItem("c-kevin", "Kevin Gu is a Dex collaborator.")]));
    });
    expect(rootEl.textContent).not.toContain("Kevin Gu is a Dex collaborator.");

    await act(async () => root.unmount());
  } finally {
    restore();
  }
});

// ─── helpers ───────────────────────────────────────────────────────────

type FetchImpl = (url: RequestInfo | URL, init?: RequestInit) => Promise<Response>;

interface EvidenceProps {
  config: { serverUrl: string; apiKey: string };
  lens: Lens;
  memberIds: Set<string>;
  seed?: { term: string; nonce: number };
  onRefresh?: () => void;
}

function setupDom(fetchImpl?: FetchImpl) {
  const dom = new JSDOM('<!doctype html><div id="root"></div>', { url: "http://localhost" });
  const testGlobal = globalThis as typeof globalThis & { IS_REACT_ACT_ENVIRONMENT?: boolean };
  const prev = {
    window: globalThis.window,
    document: globalThis.document,
    fetch: globalThis.fetch,
    act: testGlobal.IS_REACT_ACT_ENVIRONMENT,
  };
  testGlobal.IS_REACT_ACT_ENVIRONMENT = true;
  globalThis.window = dom.window as unknown as Window & typeof globalThis;
  globalThis.document = dom.window.document;
  if (fetchImpl) globalThis.fetch = fetchImpl as typeof globalThis.fetch;

  const rootEl = dom.window.document.getElementById("root");
  if (!rootEl) throw new Error("missing root");
  const root = createRoot(rootEl);

  const restore = () => {
    globalThis.fetch = prev.fetch;
    globalThis.document = prev.document;
    globalThis.window = prev.window;
    testGlobal.IS_REACT_ACT_ENVIRONMENT = prev.act;
  };
  return { dom, rootEl, root, restore };
}

async function render(root: ReturnType<typeof createRoot>, props: EvidenceProps) {
  await act(async () => {
    root.render(
      <LensEvidenceSearch
        config={props.config}
        lens={props.lens}
        memberIds={props.memberIds}
        seed={props.seed}
        onEditCriterion={() => {}}
        onPeekClaim={() => {}}
        onRefresh={props.onRefresh ?? (() => {})}
      />,
    );
  });
}

// Wait past the search debounce (220ms) and flush the resulting fetch/render.
async function settle(ms = 320) {
  await act(async () => {
    await new Promise((resolve) => setTimeout(resolve, ms));
  });
}

function memoryItem(id: string, content: string, subject = "Kevin Gu") {
  return {
    id,
    content,
    canonical_subject: subject,
    labels: [],
    scope: { kind: "user", key: null },
    provenance: "recorded",
    status: "active",
    valid_from: null,
    invalid_at: null,
    source_refs: [],
    corroboration: 0,
    last_relevant_at: null,
    feedback: "none",
    created_at: "2026-01-01T00:00:00Z",
    updated_at: "2026-01-01T00:00:00Z",
  };
}

function jsonResponse(body: unknown) {
  return new Response(JSON.stringify(body), { headers: { "Content-Type": "application/json" } });
}

function searchResponse(items: ReturnType<typeof memoryItem>[]) {
  return jsonResponse({ mode: "fts", degraded: false, items });
}
