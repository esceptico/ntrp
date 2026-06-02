import { expect, test } from "bun:test";
import { act } from "react";
import React from "react";
import { createRoot } from "react-dom/client";
import { renderToStaticMarkup } from "react-dom/server";
import { JSDOM } from "jsdom";
import { ClaimBlock } from "../src/components/memory/ClaimBlock.tsx";
import { LensEvidenceSearch } from "../src/components/memory/LensEvidenceSearch.tsx";
import { GroupedProfiles, LensHeader } from "../src/components/memory/LensesView.tsx";
import type { Lens, ProjectedGroup } from "../src/api/memoryItems.ts";

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
  created_at: "2026-01-01T00:00:00Z",
  updated_at: "2026-01-01T00:00:00Z",
};

test("lens header keeps only the refresh action", () => {
  const html = renderToStaticMarkup(
    <LensHeader lens={lens} onRefresh={() => {}} refreshing={false} />,
  );

  expect(html).toContain('aria-label="Re-synthesize"');
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
      exiting={null}
      onOpen={() => {}}
      onClose={() => {}}
      onCommit={() => {}}
      onPeek={() => {}}
    />,
  );

  expect(html).toContain("tracking-normal");
  expect(html).toContain("text-left");
});

test("lens search replaces freeform add at lens level", () => {
  const html = renderToStaticMarkup(
    <LensEvidenceSearch
      config={{ serverUrl: "http://127.0.0.1", apiKey: "test" }}
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

test("entry search is scoped as evidence, not claim authoring", () => {
  const html = renderToStaticMarkup(
    <LensEvidenceSearch
      config={{ serverUrl: "http://127.0.0.1", apiKey: "test" }}
      lens={lens}
      subject="Kevin Gu"
      memberIds={new Set()}
      onEditCriterion={() => {}}
      onPeekClaim={() => {}}
      onRefresh={() => {}}
    />,
  );

  expect(html).toContain("Find evidence");
  expect(html).toContain("Kevin Gu");
  expect(html).not.toContain("Add to this lens");
});

test("lens evidence search input reserves room for the icon", async () => {
  const dom = new JSDOM("<!doctype html><div id=\"root\"></div>", { url: "http://localhost" });
  const prevWindow = globalThis.window;
  const prevDocument = globalThis.document;
  const testGlobal = globalThis as typeof globalThis & { IS_REACT_ACT_ENVIRONMENT?: boolean };
  const prevActEnvironment = testGlobal.IS_REACT_ACT_ENVIRONMENT;

  testGlobal.IS_REACT_ACT_ENVIRONMENT = true;
  globalThis.window = dom.window as unknown as Window & typeof globalThis;
  globalThis.document = dom.window.document;

  try {
    const rootEl = dom.window.document.getElementById("root");
    if (!rootEl) throw new Error("missing root");
    const root = createRoot(rootEl);

    await act(async () => {
      root.render(
        <LensEvidenceSearch
          config={{ serverUrl: "http://server", apiKey: "test" }}
          lens={lens}
          subject="The user"
          memberIds={new Set()}
          onEditCriterion={() => {}}
          onPeekClaim={() => {}}
          onRefresh={() => {}}
        />,
      );
    });

    const openButton = rootEl.querySelector("button");
    if (!openButton) throw new Error("missing open button");
    await act(async () => {
      openButton.dispatchEvent(new dom.window.MouseEvent("click", { bubbles: true }));
    });

    const input = rootEl.querySelector("input");
    if (!input) throw new Error("missing input");
    expect(input.getAttribute("style")).toContain("padding-left: 2rem");
    expect(input.value).toBe("");

    await act(async () => {
      root.unmount();
    });
    await new Promise((resolve) => setTimeout(resolve, 0));
  } finally {
    globalThis.document = prevDocument;
    globalThis.window = prevWindow;
    testGlobal.IS_REACT_ACT_ENVIRONMENT = prevActEnvironment;
  }
});

test("entry evidence search queries scoped memory and renders criterion review", async () => {
  const dom = new JSDOM("<!doctype html><div id=\"root\"></div>", { url: "http://localhost" });
  const prevWindow = globalThis.window;
  const prevDocument = globalThis.document;
  const prevFetch = globalThis.fetch;
  const testGlobal = globalThis as typeof globalThis & { IS_REACT_ACT_ENVIRONMENT?: boolean };
  const prevActEnvironment = testGlobal.IS_REACT_ACT_ENVIRONMENT;
  const calls: string[] = [];

  testGlobal.IS_REACT_ACT_ENVIRONMENT = true;
  globalThis.window = dom.window as unknown as Window & typeof globalThis;
  globalThis.document = dom.window.document;
  globalThis.fetch = async (url) => {
    calls.push(String(url));
    return new Response(
      JSON.stringify({
        mode: "fts",
        degraded: false,
        items: [
          {
            id: "c-kevin",
            content: "Kevin Gu is a Dex collaborator.",
            canonical_subject: "Kevin Gu",
            scope: { kind: "project", key: "dex" },
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
          },
        ],
      }),
      { headers: { "Content-Type": "application/json" } },
    );
  };

  try {
    const rootEl = dom.window.document.getElementById("root");
    if (!rootEl) throw new Error("missing root");
    const root = createRoot(rootEl);
    const projectLens = { ...lens, scope: { kind: "project" as const, key: "dex" } };

    await act(async () => {
      root.render(
        <LensEvidenceSearch
          config={{ serverUrl: "http://server", apiKey: "test" }}
          lens={projectLens}
          subject="Kevin Gu"
          memberIds={new Set()}
          onEditCriterion={() => {}}
          onPeekClaim={() => {}}
          onRefresh={() => {}}
        />,
      );
    });

    const openButton = rootEl.querySelector("button");
    if (!openButton) throw new Error("missing open button");
    await act(async () => {
      openButton.dispatchEvent(new dom.window.MouseEvent("click", { bubbles: true }));
    });

    const searchButton = [...rootEl.querySelectorAll("button")].find((b) => b.textContent?.includes("Search"));
    if (!searchButton) throw new Error("missing search button");
    await act(async () => {
      searchButton.dispatchEvent(new dom.window.MouseEvent("click", { bubbles: true }));
    });

    expect(calls[0]).toContain("/admin/memory/search?");
    expect(calls[0]).toContain("q=Kevin+Gu");
    expect(calls[0]).toContain("scope_kind=project");
    expect(calls[0]).toContain("scope_key=dex");
    expect(rootEl.textContent).toContain("Review criterion");
    expect(rootEl.textContent).toContain("Edit criterion");

    await act(async () => {
      root.unmount();
    });
    await new Promise((resolve) => setTimeout(resolve, 0));
  } finally {
    globalThis.fetch = prevFetch;
    globalThis.document = prevDocument;
    globalThis.window = prevWindow;
    testGlobal.IS_REACT_ACT_ENVIRONMENT = prevActEnvironment;
  }
});

test("lens entry search asks for criterion review when any subject claim is outside the view", async () => {
  const dom = new JSDOM("<!doctype html><div id=\"root\"></div>", { url: "http://localhost" });
  const prevWindow = globalThis.window;
  const prevDocument = globalThis.document;
  const prevFetch = globalThis.fetch;
  const testGlobal = globalThis as typeof globalThis & { IS_REACT_ACT_ENVIRONMENT?: boolean };
  const prevActEnvironment = testGlobal.IS_REACT_ACT_ENVIRONMENT;

  testGlobal.IS_REACT_ACT_ENVIRONMENT = true;
  globalThis.window = dom.window as unknown as Window & typeof globalThis;
  globalThis.document = dom.window.document;
  globalThis.fetch = async () =>
    new Response(
      JSON.stringify({
        mode: "fts",
        degraded: false,
        items: [
          { ...memoryItem("c-in", "Kevin Gu is a Dex employee."), canonical_subject: "Kevin Gu" },
          { ...memoryItem("c-out", "Kevin Gu is a Dex collaborator."), canonical_subject: "Kevin Gu" },
        ],
      }),
      { headers: { "Content-Type": "application/json" } },
    );

  try {
    const rootEl = dom.window.document.getElementById("root");
    if (!rootEl) throw new Error("missing root");
    const root = createRoot(rootEl);

    await act(async () => {
      root.render(
        <LensEvidenceSearch
          config={{ serverUrl: "http://server", apiKey: "test" }}
          lens={lens}
          memberIds={new Set(["c-in"])}
          onEditCriterion={() => {}}
          onPeekClaim={() => {}}
          onRefresh={() => {}}
        />,
      );
    });

    await openAndSearch(dom, rootEl, "Kevin");

    expect(rootEl.textContent).toContain("Kevin Gu");
    expect(rootEl.textContent).toContain("Review criterion");

    await act(async () => {
      root.unmount();
    });
    await new Promise((resolve) => setTimeout(resolve, 0));
  } finally {
    globalThis.fetch = prevFetch;
    globalThis.document = prevDocument;
    globalThis.window = prevWindow;
    testGlobal.IS_REACT_ACT_ENVIRONMENT = prevActEnvironment;
  }
});

test("lens evidence search ignores responses after unmount", async () => {
  const dom = new JSDOM("<!doctype html><div id=\"root\"></div>", { url: "http://localhost" });
  const prevWindow = globalThis.window;
  const prevDocument = globalThis.document;
  const prevFetch = globalThis.fetch;
  const testGlobal = globalThis as typeof globalThis & { IS_REACT_ACT_ENVIRONMENT?: boolean };
  const prevActEnvironment = testGlobal.IS_REACT_ACT_ENVIRONMENT;
  const pending: ((r: Response) => void)[] = [];

  testGlobal.IS_REACT_ACT_ENVIRONMENT = true;
  globalThis.window = dom.window as unknown as Window & typeof globalThis;
  globalThis.document = dom.window.document;
  globalThis.fetch = async () => new Promise<Response>((resolve) => pending.push(resolve));

  try {
    const rootEl = dom.window.document.getElementById("root");
    if (!rootEl) throw new Error("missing root");
    const root = createRoot(rootEl);

    await act(async () => {
      root.render(
        <LensEvidenceSearch
          config={{ serverUrl: "http://server", apiKey: "test" }}
          lens={lens}
          subject="Kevin Gu"
          memberIds={new Set()}
          onEditCriterion={() => {}}
          onPeekClaim={() => {}}
          onRefresh={() => {}}
        />,
      );
    });

    const openButton = rootEl.querySelector("button");
    if (!openButton) throw new Error("missing open button");
    await act(async () => {
      openButton.dispatchEvent(new dom.window.MouseEvent("click", { bubbles: true }));
    });

    const searchButton = [...rootEl.querySelectorAll("button")].find((b) => b.textContent?.includes("Search"));
    if (!searchButton) throw new Error("missing search button");

    await act(async () => {
      searchButton.dispatchEvent(new dom.window.MouseEvent("click", { bubbles: true }));
    });
    await act(async () => {
      root.unmount();
    });

    await act(async () => {
      pending[0](searchResponse([memoryItem("c-kevin", "Kevin Gu is a Dex collaborator.")]));
    });
    expect(rootEl.textContent).toBe("");
    await new Promise((resolve) => setTimeout(resolve, 0));
  } finally {
    globalThis.fetch = prevFetch;
    globalThis.document = prevDocument;
    globalThis.window = prevWindow;
    testGlobal.IS_REACT_ACT_ENVIRONMENT = prevActEnvironment;
  }
});

function memoryItem(id: string, content: string, subject = "Kevin Gu") {
  return {
    id,
    content,
    canonical_subject: subject,
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

function searchResponse(items: ReturnType<typeof memoryItem>[]) {
  return new Response(JSON.stringify({ mode: "fts", degraded: false, items }), {
    headers: { "Content-Type": "application/json" },
  });
}

async function openAndSearch(dom: JSDOM, rootEl: HTMLElement, query?: string) {
  const openButton = rootEl.querySelector("button");
  if (!openButton) throw new Error("missing open button");
  await act(async () => {
    openButton.dispatchEvent(new dom.window.MouseEvent("click", { bubbles: true }));
  });
  if (query) {
    const input = rootEl.querySelector("input");
    if (!input) throw new Error("missing input");
    await act(async () => {
      setInputValue(dom, input, query);
    });
  }
  const searchButton = [...rootEl.querySelectorAll("button")].find((b) => b.textContent?.includes("Search"));
  if (!searchButton) throw new Error("missing search button");
  await act(async () => {
    searchButton.dispatchEvent(new dom.window.MouseEvent("click", { bubbles: true }));
  });
}

function setInputValue(dom: JSDOM, input: HTMLInputElement, value: string) {
  const setter = Object.getOwnPropertyDescriptor(dom.window.HTMLInputElement.prototype, "value")?.set;
  setter?.call(input, value);
  input.dispatchEvent(new dom.window.Event("input", { bubbles: true }));
  input.dispatchEvent(new dom.window.Event("change", { bubbles: true }));
}
