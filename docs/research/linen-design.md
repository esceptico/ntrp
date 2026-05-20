# Linen / Solid-Panel Material — Design Reference

> **Summary:** "Linen" is the modern, solid-surface counterpart to glass — an opaque architectural panel built from a theme fill, a hairline ink ring, and a soft drop shadow. It is the right default whenever you need calm, legible, performance-friendly chrome and the wrong one when you need spatial blending with content beneath.

---

## 1. Identity & Purpose

The name "linen" is a callback to the woven grey texture Apple used in OS X Lion (10.7) and Mountain Lion (10.8) for Notification Center, Mission Control, and the login window — a skeuomorphic background that was scrubbed out in Mavericks (10.9) and fully replaced by flat surfaces in Yosemite (10.10) [1][2]. In modern UI vocabulary the word has migrated: "linen" now denotes any **solid architectural panel** — the deliberate inverse of glass/translucent materials.

It's the right choice when:

- **Legibility dominates** — long-form reading, dense data, anything with small type. Big Sur's heavy translucency was widely criticized for exactly this reason: foreground windows lost contrast, and background windows became indistinguishable [3][4].
- **Performance matters** — `backdrop-filter` is one of the most expensive composited effects in the browser/Electron; linen has zero blur cost.
- **The surface stacks inside another translucent surface** — glass-in-glass samples the wrong containing block; a solid inner panel sidesteps the entire bug class.
- **The mood is "paper" rather than "atmosphere"** — Things 3, Notion, Linear, Stripe Dashboard, Vercel, Raycast all read as calm because their surfaces are opaque and quiet [5][6][7].
- **The user has Reduce Transparency enabled** — Apple's HIG explicitly requires translucent materials to fall back to solid fills under that accessibility flag [8][9]. If your default is linen, you're already there.

Cultured Code articulated the paper-panel ethos best: "our goal was to make the app appear, as much as possible, like a simple white sheet of paper, to place the emphasis on your content" [5].

---

## 2. Surface Anatomy

A linen panel is three layers, no more:

```
┌─ drop shadow (ambient + contact) ──────────┐
│  ┌─ hairline ink ring (inset box-shadow) ─┐│
│  │  background fill (theme surface)       ││
│  └────────────────────────────────────────┘│
└────────────────────────────────────────────┘
```

**Background fill.** Pull from a tonal ladder of neutrals, not from white/black raw. Notion-style dark mode design needs at least four ladder steps: base background, primary elevated surface (cards/panels/sidebars), secondary surface (nested, hover, active), overlay (modals, tooltips, dropdowns) [10]. Linear uses LCH for its ladder so equal "lightness" reads equal to the eye across hues, then derives elevation aliases from three core variables — base, accent, contrast [11].

**Hairline ring.** A 1px inset stroke at low alpha (typical: 6–12% ink in light mode, 8–16% white in dark mode). This is the *ink* that gives the panel an edge without weight.

**Drop shadow.** A single contact shadow for low elevation; a stacked ambient + contact pair for raised surfaces. Linear deliberately refrains from diffuse shadows and ships sharp contained ones like `rgba(0,0,0,0.4) 0 2px 4px 0` [7]. Vercel Geist takes the same line: on the dashboard, shadows are "minimal and close-range (small blur, tight spread)" [12].

**Elevation tiers.** Two systems compete here:

- **Shadow-only ladder** (iOS Cards, Linear, Vercel Geist): each tier is a different shadow recipe; fill stays the same. Geist's named tiers — `base`, `small`–`large`, `tooltip`, `menu`, `modal`, `fullscreen` — bind elevation to z-index band so a tooltip can't sit visually below a card [13].
- **Tonal ladder + shadow** (Material 3): elevation is communicated *primarily* by tonal color overlays, with shadow as a secondary cue. Compose's `Surface` exposes `tonalElevation` and `shadowElevation` separately, and tonal tint is what carries the hierarchy in light theme [14][15].

Pick one. Mixing them produces incoherent depth.

---

## 3. Borders vs Rings

The CSS choice between `border: 1px solid` and `box-shadow: inset 0 0 0 1px` is not cosmetic — they behave differently:

| | `border` | `box-shadow` inset |
|---|---|---|
| Affects layout / box size | yes | no |
| Stackable (multiple rings) | no | yes |
| Visible inside `overflow: hidden` | yes | yes |
| Subpixel rendering | varies | smoother on hi-DPI [16] |
| Hover/state swaps without jank | content jumps when width changes | seamless [17] |

For linen the ring should almost always be an **inset box-shadow**. It composes with the drop shadow on the same property, avoids the 1px reflow on hover, and lets you stack a second highlight ring (e.g. a faint top-inner highlight for "paper") without touching layout.

**Alpha values that survive both themes.** White-derived alphas on light backgrounds disappear; black-derived alphas on dark backgrounds look like punched holes. The portable answer is an **ink-derived ring with theme-flipped color**:

```css
.linen {
  --ink: 0 0 0;              /* dark ink for light mode */
  background: var(--surface);
  box-shadow:
    inset 0 0 0 1px rgb(var(--ink) / 0.08),
    0 1px 2px rgb(var(--ink) / 0.04),
    0 4px 12px rgb(var(--ink) / 0.06);
}

@media (prefers-color-scheme: dark) {
  .linen { --ink: 255 255 255; }
  /* dark mode: lighter ink, weaker outer shadows (see §4) */
}
```

A cleaner modern variant uses `color-mix()` so the ring inherits from `currentColor` and adapts without media queries [18]:

```css
box-shadow: inset 0 0 0 1px color-mix(in srgb, currentColor 10%, transparent);
```

When to combine `border` + shadow: only when you need the border to participate in layout (a left-rail divider, a table column rule). Otherwise the ring wins.

---

## 4. Shadows

The modern recipe is **layered shadows** — at minimum two layers, one large/soft (ambient) and one small/dense (contact). Refactoring UI codifies it as: a larger softer shadow for indirect light cast around the object, plus a smaller darker shadow for the contact zone underneath that fades as the object lifts [19]. Joshua Comeau's "Designing Beautiful Shadows" pushes this further into a five-layer ramp where blur grows in step with offset to mimic natural falloff [20]:

```css
/* Comeau-style large elevation */
box-shadow:
  1px 2px 2px  hsl(220 60% 50% / .20),
  2px 4px 4px  hsl(220 60% 50% / .20),
  4px 8px 8px  hsl(220 60% 50% / .20),
  8px 16px 16px hsl(220 60% 50% / .20),
  16px 32px 32px hsl(220 60% 50% / .20);
```

For a linen card at rest, two layers is plenty:

```css
/* Resting card — contact + ambient */
box-shadow:
  0 1px 2px  rgb(0 0 0 / .04),
  0 4px 12px rgb(0 0 0 / .06);

/* Floating popover — modal/menu */
box-shadow:
  0 2px 4px   rgb(0 0 0 / .06),
  0 12px 32px rgb(0 0 0 / .12);
```

**When shadows feel cheap:** uniform-blur single shadows with high alpha (the classic `0 4px 8px rgba(0,0,0,0.25)`); shadows whose direction disagrees with the rest of the UI; shadows with hue saturation that doesn't match the page background. Erik Kennedy's first rule — *light comes from the sky* — is the simplest sanity check: every shadow on screen should imply the same overhead light source [21].

**Dark mode shadows.** A shadow is "darker than the surroundings"; on a near-black background there is nowhere left to go. Three working strategies:

1. **Lean on the ring, kill the shadow.** Raise ring alpha (12–20% white), drop the outer shadow to a single very deep layer (`0 8px 24px rgb(0 0 0 / .5)`) only on the floating tiers.
2. **Stronger contact, no ambient.** Linear's `rgba(0,0,0,.4) 0 2px 4px 0` is exactly this — short, dense, contained [7].
3. **Skip the top-highlight.** Specular highlights only work on floating cards; on anchored panels they read as decorative shimmer. (This is a documented pain point in glass-style UIs but applies to linen too — don't bolt an inner-top highlight onto a sidebar.)

Vercel Geist's explicit rule: "don't rely on shadow alone to communicate elevation; pair with focus-visible rings… shadow contrast on dark backgrounds is weaker than on light" [13].

---

## 5. Light vs Dark

The single most common bug in a solid-panel system is using **white-derived alphas in light mode**. `rgba(255,255,255,0.08)` on a `#FAFAFA` background is invisible. The portable rule:

- **Light mode:** ink is black-derived. Ring `rgba(0,0,0,0.06–0.12)`, shadow `rgba(0,0,0,0.04–0.08)` for resting, `0.10–0.16` for elevated.
- **Dark mode:** ring is white-derived, *but shadows stay black*. Ring `rgba(255,255,255,0.08–0.16)`, shadow `rgba(0,0,0,0.40–0.60)` and short.

The Notion four-tier ladder transfers cleanly: each tier nudges the surface 4–8% lighter (dark) or darker (light) relative to the one below, and the ring opacity tracks it [10]. Linear's LCH approach is the rigorous version of the same idea — letting the color space, not RGB math, keep the perceived lightness deltas equal across hues [11].

A practical test: render the panel against both a light wall and a dark wall, with no shadow. If you can still see the panel's edge clearly, your ring is doing its job. If it disappears on either, the alpha is wrong for that theme.

---

## 6. Typography & Content on Linen

A solid panel inherits all the standard contrast obligations — Apple's HIG sufficient-contrast bar is 4.5:1 for body text [22], and that's the floor, not the goal. Because linen is opaque, you can use deeper text tones than glass allows; you don't have to compensate for a blurred background bleeding through.

**Dividers inside a panel.** Two valid patterns:

- **Inked rule** — `border-bottom: 1px solid rgb(var(--ink) / 0.06)`. Cheap, traditional, works at any density.
- **Whitespace-only** — drop the rule, add 8–16px of extra vertical breathing room. Linear, Things 3, and Notion lean heavily on this; their panel interiors are quiet because dividers are negative space, not ink [5][6][7].

Mixing both in the same panel is the cluttered failure mode — pick one per surface.

---

## 7. Texture & Grain

The original macOS linen was a literal texture. Modern solid panels almost never reach for one, and when they do the texture is dialed so low it borders on undetectable. The tools and patterns are mature: SVG `feTurbulence` generates a tile-able noise overlay at near-zero file cost [23], and the "grainy gradients" pattern blends a turbulence layer at very low opacity to break up flat fills [24].

Use grain when:

- The fill is a **gradient** and you need to kill banding (especially on dark backgrounds at 8-bit).
- The brand is deliberately tactile (Stripe's marketing surfaces, Apple iWork, illustration-led product pages).

Don't use grain when:

- The panel hosts dense data — noise raises the noise floor of every glyph.
- The product reads "tool" rather than "publication." Linear, Vercel, Raycast all ship zero grain; their calm comes from clean fills + restrained shadow.

A safe baseline if you do add it: an SVG turbulence layer at `opacity: 0.025–0.05`, multiply blend, scoped to the surface, never to scrolling content.

---

## 8. Comparisons

**Linen vs glass.** Glass wins when the goal is spatial continuity — a floating toolbar that needs to feel like part of the canvas beneath it, or chrome on top of media. Linen wins for legibility, performance, and accessibility (Reduce Transparency is a no-op for it) [8]. Big Sur's translucency complaints are the textbook case for picking linen by default and reserving glass for one designated sheet per view [4][9].

**Linen vs flat.** Flat is linen with the shadow removed. Flat reads as *coplanar* — buttons that aren't obviously buttons, panels that don't lift off the page. NN/G's flat-design critique ("click uncertainty") is precisely the cost of stripping shadow [25]. Flat 2.0 / "almost-flat" is the industry's pragmatic settlement: keep the flat aesthetic, restore subtle shadow and color variation so affordance survives [26]. Linen sits inside Flat 2.0.

**Linen vs Material 3 tonal elevation.** M3 says: tint *is* elevation; shadow is the secondary cue [14][15]. Linen says: fill is constant within a tier; shadow + ring carry elevation. Both work; they're different mental models. If your palette is rich and you want elevation to *also* signal brand color temperature, M3's tonal approach is more expressive. If you want a calm neutral chrome, the linen approach is quieter.

---

## 9. References

1. *Get to know OS X Mavericks: Design changes* — Macworld. https://www.macworld.com/article/222218/get-to-know-os-x-mavericks-design-changes.html
2. *The Evolution of macOS UI/UX Design* — Matthias McFarlane. https://medium.com/@mcfarlanematthias/the-evolution-of-macos-ui-ux-design-a-journey-through-skeuomorphism-and-neomorphism-6b5174ef1352
3. *Sidebar: Translucency* — Pixel Envy. https://pxlnv.com/blog/sidebar-translucency/
4. *Big Sur's Transparent Menu Bar* — Michael Tsai. https://mjtsai.com/blog/2020/09/11/big-surs-transparent-menu-bar/
5. *Things — Features* / Cultured Code design notes. https://culturedcode.com/things/features/
6. *Design System Inspired by Notion* — getdesign.md. https://getdesign.md/notion/design-md
7. *How we redesigned the Linear UI (part II)* — Linear. https://linear.app/now/how-we-redesigned-the-linear-ui
8. *Materials* — Apple Human Interface Guidelines. https://developer.apple.com/design/human-interface-guidelines/materials
9. *Soaping up Liquid Glass: less transparency, more contrast* — Six Colors. https://sixcolors.com/post/2025/11/soaping-up-liquid-glass-less-transparency-more-contrast/
10. *Dark Mode Design Systems: Patterns, Tokens, and Hierarchy* — Muzli. https://muz.li/blog/dark-mode-design-systems-a-complete-guide-to-patterns-tokens-and-hierarchy/
11. *A calmer interface for a product in motion* — Linear. https://linear.app/now/behind-the-latest-design-refresh
12. *Vercel Design System Breakdown* — SeedFlip. https://seedflip.co/blog/vercel-design-system
13. *Geist — Material* — Vercel. https://vercel.com/geist/material
14. *Elevation — Material Design 3*. https://m3.material.io/styles/elevation/tokens
15. *Material Design 3 in Compose* — Android Developers. https://developer.android.com/develop/ui/compose/designsystems/material3
16. *box-shadow — CSS-Tricks Almanac*. https://css-tricks.com/almanac/properties/b/box-shadow/
17. *Using box-shadow to construct a border* — Codementor. https://www.codementor.io/@michelre/using-box-shadow-to-construct-a-border-ex0rpxvng
18. *CSS color-mix() pattern for theme-adaptive shadows / borders* (discussion thread). https://github.com/tailwindlabs/tailwindcss/discussions/3177
19. *Refactoring UI* — Wathan & Schoger (shadow chapter notes). https://refactoringui.com/ — summary at https://gist.github.com/edjw/a4547a82004222f2532d08bfbaf1596b
20. *Designing Beautiful Shadows in CSS* — Josh W. Comeau. https://www.joshwcomeau.com/css/designing-shadows/
21. *7 Rules for Creating Gorgeous UI (Part 1)* — Erik D. Kennedy. https://www.learnui.design/blog/7-rules-for-creating-gorgeous-ui-part-1.html
22. *Sufficient Contrast evaluation criteria* — App Store Connect Help. https://developer.apple.com/help/app-store-connect/manage-app-accessibility/sufficient-contrast-evaluation-criteria/
23. *SVG Filter Effects: Creating Texture with feTurbulence* — Codrops. https://tympanus.net/codrops/2019/02/19/svg-filter-effects-creating-texture-with-feturbulence/
24. *Grainy Gradients* — CSS-Tricks. https://css-tricks.com/grainy-gradients/
25. *Flat Design: Its Origins, Its Problems, and Why Flat 2.0 Is Better for Users* — Nielsen Norman Group. https://www.nngroup.com/articles/flat-design/
26. *Flat 2.0 & How It Solves Flat Design's Usability Problems* — Hongkiat. https://www.hongkiat.com/blog/flat-20/
