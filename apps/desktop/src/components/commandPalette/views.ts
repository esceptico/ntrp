import { Bot, Layers, Monitor, Moon, Palette as PaletteIcon, Sun, type LucideIcon } from "lucide-react";
import { updateServerConfig } from "../../actions";
import { PALETTES, type PaletteId } from "../../lib/palettes";
import type { ThemeChoice } from "../../store";
import { prettyProvider, stripProviderPrefix } from "./filter";
import type { CommandView } from "./types";

/** Provider-level view: one row per provider, drills into model list. */
export function buildProviderView(
  groups: { provider: string; models: string[] }[],
  currentModel: string | undefined,
): CommandView {
  return {
    placeholder: "Filter providers...",
    entries: groups.map((g) => ({
      id: `provider:${g.provider}`,
      section: "provider" as const,
      label: prettyProvider(g.provider),
      hint: `${g.models.length} model${g.models.length === 1 ? "" : "s"}`,
      icon: Layers,
      children: () => buildModelView(g.provider, g.models, currentModel),
      search: `${g.provider.toLowerCase()} provider`,
    })),
  };
}

/** Model-level view: leaf rows that apply chat_model on Enter. */
export function buildModelView(
  provider: string,
  models: string[],
  currentModel: string | undefined,
): CommandView {
  return {
    placeholder: `Filter ${prettyProvider(provider)} models...`,
    entries: models.map((model) => ({
      id: `model:${model}`,
      section: "model" as const,
      label: stripProviderPrefix(model, provider),
      hint: model === currentModel ? "current" : undefined,
      icon: Bot,
      run: async () => {
        if (model === currentModel) return;
        try {
          await updateServerConfig({ chat_model: model });
        } catch {
          /* surfaced via the global error path */
        }
      },
      search: `${model.toLowerCase()} model`,
    })),
  };
}

/** Three-option theme picker — Light / Dark / System. The "current"
 *  hint mirrors what the model switcher shows; selecting the active
 *  theme is a no-op (cheaper than guarding setPref). */
export function buildThemeView(
  current: ThemeChoice,
  setPref: <K extends "theme">(key: K, value: ThemeChoice) => void,
): CommandView {
  const options: { id: ThemeChoice; label: string; icon: LucideIcon }[] = [
    { id: "system", label: "System", icon: Monitor },
    { id: "light", label: "Light", icon: Sun },
    { id: "dark", label: "Dark", icon: Moon },
  ];
  return {
    placeholder: "Choose theme...",
    entries: options.map((opt) => ({
      id: `theme:${opt.id}`,
      section: "appearance" as const,
      label: opt.label,
      hint: opt.id === current ? "current" : undefined,
      icon: opt.icon,
      run: () => setPref("theme", opt.id),
      search: `${opt.label.toLowerCase()} theme`,
    })),
  };
}

/** Color-palette picker (graphite / warm / vercel / raycast / github /
 *  linear / notion / catppuccin). Labels come from PALETTES so adding a
 *  palette in lib/palettes.ts surfaces here automatically. */
export function buildPaletteView(
  current: PaletteId,
  setPref: <K extends "palette">(key: K, value: PaletteId) => void,
): CommandView {
  return {
    placeholder: "Choose palette...",
    entries: PALETTES.map((p) => ({
      id: `palette:${p.id}`,
      section: "appearance" as const,
      label: p.label,
      hint: p.id === current ? "current" : undefined,
      icon: PaletteIcon,
      run: () => setPref("palette", p.id),
      search: `${p.label.toLowerCase()} palette ${p.id}`,
    })),
  };
}
