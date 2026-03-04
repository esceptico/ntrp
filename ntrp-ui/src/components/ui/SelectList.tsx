import React, { useState, useCallback, useMemo, useEffect, useRef } from "react";
import type { ScrollBoxRenderable } from "@opentui/core";
import { useKeypress, useAccentColor, type Key } from "../../hooks/index.js";
import { colors, useThemeVersion } from "./colors.js";
import { Dialog } from "./Dialog.js";
import { Hints } from "./Hints.js";
import { BULLET } from "../../lib/constants.js";

// --- Types ---

export interface SelectOption<T = string> {
  value: T;
  title: string;
  description?: string;
  category?: string;
  indicator?: string;
}

export interface SelectKeybind<T = string> {
  key: string;
  label: string;
  action: (option: SelectOption<T>, index: number) => void;
}

export interface SelectListProps<T = string> {
  options: SelectOption<T>[];
  onSelect: (option: SelectOption<T>) => void;
  onClose?: () => void;
  search?: boolean;
  searchPlaceholder?: string;
  keybinds?: SelectKeybind<T>[];
  visibleLines?: number;
  initialIndex?: number;
  emptyMessage?: string;
  onMove?: (option: SelectOption<T>, index: number) => void;
  renderItem?: (option: SelectOption<T>, ctx: RenderItemContext) => React.ReactNode;
  width?: number;
  isActive?: boolean;
}

export interface RenderItemContext {
  isSelected: boolean;
  index: number;
  colors: { text: string; indicator: string };
}

// --- Entry types for grouped rendering ---

type Entry<T> = { type: "header"; category: string } | { type: "option"; option: SelectOption<T> };

function buildEntries<T>(options: SelectOption<T>[], search: string): {
  entries: Entry<T>[];
  selectableIndices: number[];
} {
  const hasCategories = options.some(o => o.category);
  const lower = search.toLowerCase();
  const filtered = search
    ? options.filter(o => o.title.toLowerCase().includes(lower) || (o.category?.toLowerCase().includes(lower)))
    : options;

  if (!hasCategories || search) {
    const entries: Entry<T>[] = filtered.map(o => ({ type: "option", option: o }));
    return { entries, selectableIndices: entries.map((_, i) => i) };
  }

  const groups = new Map<string, SelectOption<T>[]>();
  for (const o of filtered) {
    const cat = o.category || "";
    if (!groups.has(cat)) groups.set(cat, []);
    groups.get(cat)!.push(o);
  }

  const entries: Entry<T>[] = [];
  const selectableIndices: number[] = [];

  for (const [category, items] of groups) {
    if (category) entries.push({ type: "header", category });
    for (const option of items) {
      selectableIndices.push(entries.length);
      entries.push({ type: "option", option });
    }
  }

  return { entries, selectableIndices };
}

// --- SelectList ---

export function SelectList<T = string>({
  options,
  onSelect,
  onClose,
  search = false,
  searchPlaceholder = "Search",
  keybinds,
  visibleLines = 10,
  initialIndex,
  emptyMessage = "No results",
  onMove,
  renderItem,
  width,
  isActive = true,
}: SelectListProps<T>) {
  useThemeVersion();
  const { accentValue } = useAccentColor();
  const [query, setQuery] = useState("");
  const [selectedIdx, setSelectedIdx] = useState(0);

  const { entries, selectableIndices } = useMemo(
    () => buildEntries(options, query),
    [options, query],
  );

  const totalSelectable = selectableIndices.length;
  const mountedRef = useRef(false);

  // Set initial selection
  useEffect(() => {
    if (initialIndex != null && initialIndex >= 0 && initialIndex < totalSelectable) {
      setSelectedIdx(initialIndex);
    }
    mountedRef.current = true;
  }, []); // eslint-disable-line react-hooks/exhaustive-deps

  // Clamp selection when list changes
  useEffect(() => {
    setSelectedIdx(i => Math.max(0, Math.min(i, totalSelectable - 1)));
  }, [totalSelectable]);

  // Fire onMove when selection changes (skip initial mount)
  useEffect(() => {
    if (!mountedRef.current) return;
    if (totalSelectable === 0 || !onMove) return;
    const entryIdx = selectableIndices[selectedIdx];
    const entry = entries[entryIdx];
    if (entry?.type === "option") {
      onMove(entry.option, selectedIdx);
    }
  }, [selectedIdx]); // eslint-disable-line react-hooks/exhaustive-deps

  const selectedEntryIdx = selectableIndices[selectedIdx] ?? 0;
  const scrollRef = useRef<ScrollBoxRenderable | null>(null);

  // Reset scroll position when filter changes (matching OpenCode)
  useEffect(() => {
    setTimeout(() => {
      const scroll = scrollRef.current;
      if (!scroll) return;
      scroll.scrollTo(0);
    }, 0);
  }, [query]);

  // Scroll selected item into view (matching OpenCode's moveTo)
  useEffect(() => {
    setTimeout(() => {
      const scroll = scrollRef.current;
      if (!scroll) return;
      const target = scroll.getChildren().find((child) => child.id === `entry-${selectedEntryIdx}`);
      if (!target) return;
      const y = target.y - scroll.y;
      if (y >= scroll.height) {
        scroll.scrollBy(y - scroll.height + 1);
      }
      if (y < 0) {
        scroll.scrollBy(y);
        if (selectedIdx === 0) scroll.scrollTo(0);
      }
    }, 0);
  }, [selectedEntryIdx, selectedIdx]);

  const handleKeypress = useCallback((key: Key) => {
    // Custom keybinds first
    if (keybinds && !key.ctrl && !key.meta) {
      for (const kb of keybinds) {
        if (key.sequence === kb.key || key.name === kb.key) {
          const entryIdx = selectableIndices[selectedIdx];
          const entry = entries[entryIdx];
          if (entry?.type === "option") {
            kb.action(entry.option, selectedIdx);
          }
          return;
        }
      }
    }

    if (key.name === "escape") {
      if (query) {
        setQuery("");
        setSelectedIdx(0);
      } else {
        onClose?.();
      }
      return;
    }
    if (key.name === "return") {
      const entryIdx = selectableIndices[selectedIdx];
      const entry = entries[entryIdx];
      if (entry?.type === "option") onSelect(entry.option);
      return;
    }
    if (key.name === "up" || key.name === "k") {
      setSelectedIdx(i => Math.max(0, i - 1));
    } else if (key.name === "down" || key.name === "j") {
      setSelectedIdx(i => Math.min(totalSelectable - 1, i + 1));
    } else if (key.name === "pageup") {
      setSelectedIdx(i => Math.max(0, i - 8));
    } else if (key.name === "pagedown") {
      setSelectedIdx(i => Math.min(totalSelectable - 1, i + 8));
    }
  }, [entries, selectableIndices, selectedIdx, totalSelectable, query, keybinds, onSelect, onClose]);

  useKeypress(handleKeypress, { isActive });

  return (
    <box flexDirection="column" width={width}>
      {search && (
        <input
          value={query}
          onInput={(value: string) => { setQuery(value); setSelectedIdx(0); }}
          focused={isActive}
          textColor={colors.text.primary}
          focusedTextColor={colors.text.primary}
          cursorColor={accentValue}
          placeholder={searchPlaceholder}
          placeholderColor={colors.text.disabled}
          width={Math.max(10, (width ?? 40) - 2)}
        />
      )}

      {totalSelectable === 0 ? (
        <box>
          <text><span fg={colors.text.muted}>  {emptyMessage}</span></text>
        </box>
      ) : (
        <scrollbox
          key={query ? "flat" : "grouped"}
          maxHeight={visibleLines - (search ? 1 : 0)}
          verticalScrollbarOptions={{
            visible: true,
            trackOptions: {
              backgroundColor: colors.background.element,
              foregroundColor: colors.border,
            },
          }}
          ref={(r: ScrollBoxRenderable) => { scrollRef.current = r; }}
        >
          {entries.map((entry, actualIdx) => {
            if (entry.type === "header") {
              return (
                <box key={`h-${entry.category}`} id={`entry-${actualIdx}`} paddingTop={actualIdx === 0 ? 0 : 1}>
                  <text>
                    <span fg={accentValue}><strong>   {entry.category}</strong></span>
                  </text>
                </box>
              );
            }

            const isSelected = actualIdx === selectedEntryIdx;
            const { option } = entry;

            if (renderItem) {
              const ctx: RenderItemContext = {
                isSelected,
                index: selectableIndices.indexOf(actualIdx),
                colors: {
                  text: isSelected ? colors.selection.active : colors.text.primary,
                  indicator: isSelected ? colors.selection.active : colors.text.disabled,
                },
              };
              return (
                <box key={String(option.value)} id={`entry-${actualIdx}`} flexDirection="row">
                  <box width={2} flexShrink={0}>
                    <text>
                      <span fg={isSelected ? colors.selection.active : colors.text.disabled}>
                        {isSelected ? `${BULLET}` : "  "}
                      </span>
                    </text>
                  </box>
                  {renderItem(option, ctx)}
                </box>
              );
            }

            return (
              <box
                key={String(option.value)}
                id={`entry-${actualIdx}`}
                flexDirection="row"
                backgroundColor={isSelected ? accentValue : undefined}
              >
                <text>
                  {option.indicator ? (
                    <span fg={isSelected ? colors.contrast : accentValue}> {option.indicator} </span>
                  ) : (
                    <span>   </span>
                  )}
                  <span fg={isSelected ? colors.contrast : colors.text.primary}>
                    {isSelected ? <strong>{option.title}</strong> : option.title}
                  </span>
                  {option.description && (
                    <span fg={isSelected ? colors.contrast : colors.text.disabled}> {option.description}</span>
                  )}
                </text>
              </box>
            );
          })}
        </scrollbox>
      )}
    </box>
  );
}

// --- DialogSelect ---

export interface DialogSelectProps<T = string> extends SelectListProps<T> {
  title: string;
  size?: "medium" | "large" | "full";
  closable?: boolean;
}

function buildHints<T>(keybinds?: SelectKeybind<T>[], hasSearch?: boolean): [string, string][] {
  const hints: [string, string][] = [["↑↓", "move"], ["enter", "select"]];
  if (keybinds) {
    for (const kb of keybinds) {
      hints.push([kb.key, kb.label]);
    }
  }
  hints.push(["esc", hasSearch ? "clear/close" : "close"]);
  return hints;
}

export function DialogSelect<T = string>({
  title,
  size = "medium",
  closable = true,
  ...selectProps
}: DialogSelectProps<T>) {
  const hints = useMemo(
    () => buildHints(selectProps.keybinds, selectProps.search),
    [selectProps.keybinds, selectProps.search],
  );

  return (
    <Dialog
      title={title}
      size={size}
      closable={closable}
      onClose={selectProps.onClose ?? (() => {})}
      footer={<Hints items={hints} />}
    >
      {({ width, height }) => (
        <SelectList {...selectProps} width={width} visibleLines={height} />
      )}
    </Dialog>
  );
}
