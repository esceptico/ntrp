import { useEffect, useLayoutEffect, useMemo, useRef, useState } from "react";
import { Plus } from "lucide-react";
import { useStore } from "@/stores";
import { fetchAutomations, fetchAutomationSuggestions } from "@/actions/automations";
import { suggestionToPayload } from "@/api/automations";
import { splitAutomationsForTabs } from "@/lib/automationFilters";
import { AutomationEditor, type EditorSeed } from "@/features/automations/components/AutomationEditor";
import { Button } from "@/components/ui/Button";
import { PageModal } from "@/components/ui/PageModal";
import { ScrollFadeTop } from "@/components/ui/ScrollBlur";
import { Tabs } from "@/components/ui/Tabs";
import { TabPanels, useTabDirection } from "@/components/ui/TabPanels";
import { ActiveList, AutomationTab, SystemList, TemplatesList } from "@/features/automations/components/AutomationLists";

export { SuggestionsSection } from "@/features/automations/components/SuggestionsSection";
export { SuggestionCard } from "@/features/automations/components/SuggestionCard";

type Tab = "active" | "system" | "templates";

const TAB_ORDER: Tab[] = ["active", "system", "templates"];

export function AutomationsModal() {
  const open = useStore((s) => s.automationsOpen);
  const close = useStore((s) => s.closeAutomations);
  const origin = useStore((s) => s.modalOrigin);
  const automations = useStore((s) => s.automations);
  const [editor, setEditor] = useState<EditorSeed | null>(null);
  const [tab, setTab] = useState<Tab>("active");

  useEffect(() => {
    if (!open) return;
    void fetchAutomations();
    void fetchAutomationSuggestions();
  }, [open]);

  // When the user has nothing yet, default the page to Templates so the
  // empty Active tab doesn't feel like a dead end.
  useEffect(() => {
    if (!open) return;
    if (automations !== null && automations.length === 0) setTab("templates");
  }, [open, automations]);

  const automationGroups = useMemo(() => (automations ? splitAutomationsForTabs(automations) : null), [automations]);
  const activeCount = automationGroups?.user.length ?? 0;
  const systemCount = automationGroups?.internal.length ?? 0;

  const direction = useTabDirection(TAB_ORDER, tab);
  const scrollRef = useRef<HTMLDivElement>(null);

  useLayoutEffect(() => {
    if (!open) return;
    scrollRef.current?.scrollTo({ top: 0, behavior: "instant" });
  }, [open, tab]);

  return (
    <>
      <PageModal
        open={open}
        onClose={close}
        origin={origin}
        disableEscape={!!editor}
        header={{
          title: "Automations",
          actions: (
            <Button size="sm" leadingIcon={Plus} onClick={() => setEditor({ kind: "create" })}>
              New
            </Button>
          ),
        }}
      >
        <div className="grid h-full min-h-0 grid-rows-[auto_minmax(0,1fr)]">
          <Tabs
            value={tab}
            onChange={(v) => setTab(v as Tab)}
            variant="underline"
            className="items-center gap-5 px-5"
          >
            <AutomationTab value="active" label="Active" count={activeCount} />
            <AutomationTab value="system" label="System" count={systemCount} />
            <AutomationTab value="templates" label="Templates" />
          </Tabs>

          <div className="relative min-h-0 overflow-hidden">
            {/* Scroll lives outside TabPanels — motion transform breaks sticky overlays. */}
            <div ref={scrollRef} className="h-full min-h-0 overflow-y-auto scroll-thin">
              <ScrollFadeTop key={tab} />
              <TabPanels value={tab} direction={direction} className="px-5 py-5">
                {tab === "active" ? (
                  <ActiveList
                    automations={automationGroups?.user ?? null}
                    onEdit={(automation) => setEditor({ kind: "edit", automation })}
                    onPickTemplate={() => setTab("templates")}
                    onCreate={() => setEditor({ kind: "create" })}
                  />
                ) : tab === "system" ? (
                  <SystemList
                    automations={automationGroups?.internal ?? null}
                    onEdit={(automation) => setEditor({ kind: "edit", automation })}
                  />
                ) : (
                  <TemplatesList
                    onPick={(template) => setEditor({ kind: "create", preset: template.payload })}
                    onPickSuggestion={(s) => setEditor({ kind: "create", preset: suggestionToPayload(s) })}
                  />
                )}
              </TabPanels>
            </div>
          </div>
        </div>
      </PageModal>
      <AutomationEditor seed={editor} onClose={() => setEditor(null)} />
    </>
  );
}
