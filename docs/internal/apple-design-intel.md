# Apple Design Intel

Concrete specs pulled from Apple HIG, SwiftUI source, WWDC25 #219 ("Meet Liquid Glass"), and third-party reverse-engineering (LogRocket, MockFlow, Amos Gyamfi's spring manifesto, GetStream's spring cheat sheet). Use this as the source of truth when reaching for "Apple-feel" — prefer copying these numbers over inventing new ones.

## When to Use Spring vs Cubic-Bezier

- **Spring** for anything user-driven: drag, tap, sheet/modal entries, sidebar reveal, navigation push, popover open. Springs are interruptible and re-target mid-flight; cubic-beziers can't.
- **Cubic-bezier** for non-interactive transitions: pure crossfades, opacity-only, system-driven things with fixed start/end.
- Apple's standard ease-out: `cubic-bezier(0.25, 0.1, 0.25, 1)` — the WebKit default and UIKit `easeInOut` shape.
- Apple's "ease-out emphasized": `cubic-bezier(0.2, 0, 0, 1)`.
- Default UI durations cluster at 200–350ms for non-spring transitions; spring-driven sheets/modals run ~400–500ms total under the hood.

## SwiftUI Spring Presets (iOS 17+)

All three presets default to `duration: 0.5s`. The differentiator is the baked-in bounce. `extraBounce` adds on top.

| Preset    | Duration | Bounce | Use case                                |
|-----------|----------|--------|-----------------------------------------|
| `.smooth` | 0.5s     | 0.0    | Sheets, modals, content morphs, settles |
| `.snappy` | 0.5s     | 0.15   | Navigation, tab switches, "modern iOS"  |
| `.bouncy` | 0.5s     | 0.30   | Playful UI, attention-grabbing reveals  |

Legacy `.spring()` defaults: `response: 0.55, dampingFraction: 0.825`.
`.interactiveSpring()` (drag tracking): `response: 0.15, dampingFraction: 0.86`.

### framer-motion equivalents

Conversion (mass = 1):

```
stiffness = (2π / duration)²
damping   = 4π × (1 − bounce) / duration
```

Paste-ready transitions:

```ts
// Navigation / tab switch / route change — .snappy
const SPRING_SNAPPY = { type: "spring", stiffness: 158, damping: 21.4, mass: 1 };

// Sheets, modals, drawers — .smooth (no overshoot on big surfaces)
const SPRING_SMOOTH = { type: "spring", stiffness: 158, damping: 25.1, mass: 1 };

// Playful / attention reveal — .bouncy
const SPRING_BOUNCY = { type: "spring", stiffness: 158, damping: 17.6, mass: 1 };

// Drag tracking / interactive resize — .interactiveSpring
const SPRING_DRAG = { type: "spring", stiffness: 1300, damping: 70, mass: 1 };

// Tap press (120ms cubic) → release (snappy spring)
const TAP_PRESS = { duration: 0.12, ease: [0.25, 0.1, 0.25, 1] };
const TAP_RELEASE = { type: "spring", stiffness: 400, damping: 22, mass: 0.8 };

// Popover / menu reveal — origin-anchored, snappy with hint of bounce
const POPOVER = { type: "spring", stiffness: 350, damping: 26, mass: 1 };
// pair with: initial={{ scale: 0.8, opacity: 0 }} animate={{ scale: 1, opacity: 1 }}
// + transform-origin matching the trigger anchor
```

## Liquid Glass (iOS 26 / macOS 26)

**Important caveat:** Liquid Glass is a runtime shader, not a static blur. Apple does not publish blur radii because they adapt per-frame to content luminance, control size, and motion. The values below are CSS approximations from third-party reverse-engineering.

### Material tier blur radii (CSS `backdrop-filter: blur(...) saturate(180%)`)

| Tier      | Blur  | Extra filters         | Use                            |
|-----------|-------|-----------------------|--------------------------------|
| ultraThin | 8px   | saturate(180%)        | Very subtle chrome, scrim hint |
| thin      | 14px  | saturate(180%)        | Inline overlays                |
| regular   | 20px  | saturate(180%)        | Popovers, menus                |
| thick     | 30px  | saturate(180%)        | Modal sheets                   |
| chrome    | 40px  | saturate(180%) brightness(1.1) | Toolbars, navbars     |

### Tint behind the blur

- Light: `rgba(255, 255, 255, 0.72)` for chrome, `rgba(255, 255, 255, 0.15)` for ambient surfaces.
- Dark: `rgba(40, 40, 45, 0.55)` for chrome, darker tints for ambient.
- iOS 26.2 added user-controllable tint intensity — implies it's a single tunable layer.

### What's actually new vs old UIBlurEffect Material

1. **Lensing.** Light bends *into* the glass instead of being scattered. CSS approximation: SVG `feDisplacementMap scale: 40–60` over `feGaussianBlur stdDeviation: 1`.
2. **Specular edge highlights.** 1px inset highlight that reacts to device tilt / pointer position. CSS approx: `box-shadow: inset 0 1px 0 rgba(255,255,255,0.4), inset 0 -1px 0 rgba(0,0,0,0.06)`.
3. **Morphing.** Controls fluidly merge/split via `GlassEffectContainer` with spacing thresholds 20–40.
4. **Motion response.** Glass flexes on touch using a snappy spring (~duration 0.25, bounce 0.1).

### Vibrancy (secondary content behind glass)

Secondary text shifts toward the dominant background hue with `saturate(1.8)` and a brightness offset (Apple's `autoBackground` recoloring). In practice for our purposes: use `text-white/55` (dark) or `text-black/55` (light) for secondary labels inside any glass surface.

### Light vs dark behavior

- Light mode: luminance-additive (highlights brighter).
- Dark mode: luminance-subtractive (tint darkens, edges glow with `rgba(255,255,255,0.12)`).

## Translucent Toolbar / Scroll Edge Effect

The hallmark iOS toolbar pattern — chrome blurs underlying scrolling content.

- **Blur is always on** when the bar floats over content. The "scroll edge effect" is what changes when content actually crosses behind it:
  - **Soft** (default on iOS): a 16–24px gradient fade of blur opacity from 0 → full as content approaches.
  - **Hard** (optional): a 1px hairline border. Light: `rgba(0, 0, 0, 0.08)`. Dark: `rgba(255, 255, 255, 0.08)`.
- **Bar chrome opacity**: light **0.72**, dark **0.55**, layered over the blur.

## Tap / Active States

- Scale: **0.96** (not 0.95 — that's Material Design).
- Press-down: **~120ms cubic ease-out** (`cubic-bezier(0.25, 0.1, 0.25, 1)`).
- Release: snappy spring so an interrupted release re-targets cleanly. `{ stiffness: 400, damping: 22, mass: 0.8 }`.
- Optional: slight opacity drop to `0.9` during press.

## Anchored / Origin-Relative Transitions

- **Popovers and menus** scale from `0.8 → 1.0` on a snappy spring, with `transform-origin` matching the trigger's anchor edge (e.g., `top right` for a top-right button).
- The genie / context-menu reveal additionally translates ~8px toward the anchor and fades through a short blur (8px → 0px) over the same 0.35s window.
- For framer-motion: `initial={{ scale: 0.8, opacity: 0 }} animate={{ scale: 1, opacity: 1 }}` + Tailwind `origin-top-right` (or matching anchor) on the wrapper.

## Reduce-Motion Behavior

Apple respects `prefers-reduced-motion` strictly: animations are replaced with **opacity crossfades** of similar duration. Don't keep size/position changes — replace them entirely. The system will not auto-degrade springs; you must branch on `useReducedMotion()`.

## Anti-Patterns (Apple Avoids)

- Long durations (>1s) without an interactive feedback target.
- Easing that contradicts physics (ease-in for entrance — entries should ease out).
- Simultaneous animations without hierarchy (chrome and content moving at the same rate).
- Motion without semantic meaning (animation as decoration).
- Jarring transitions between motion types (cubic for one related transition, spring for another).
- Glass on long-form text or dense data (use solid; glass is for chrome only).
- Stacking same-weight materials (a popover with glass over a toolbar with glass — the popover should be one tier heavier or solid).

## Sources

- [GetStream/swiftui-spring-animations (GitHub)](https://github.com/GetStream/swiftui-spring-animations)
- [Amos Gyamfi — Meaning, Maths, Physics of SwiftUI Spring](https://medium.com/@amosgyamfi/the-meaning-maths-and-physics-of-swiftui-spring-animation-amos-gyamfis-manifesto-0044755da208)
- [Amos Gyamfi — SwiftUI Spring Cheat Sheet](https://medium.com/@amosgyamfi/swiftui-spring-animation-cheat-sheet-for-developers-1411fd80eda4)
- [createwithswift — Understanding Spring Animations](https://www.createwithswift.com/understanding-spring-animations-in-swiftui/)
- [Apple Developer — spring(response:dampingFraction:blendDuration:)](https://developer.apple.com/documentation/SwiftUI/Animation/spring(response:dampingFraction:blendDuration:))
- [Apple Developer — snappy preset](https://developer.apple.com/documentation/swiftui/animation/snappy(duration:extrabounce:))
- [Apple Developer — bouncy preset](https://developer.apple.com/documentation/swiftui/animation/bouncy(duration:extrabounce:))
- [WWDC25 #219 Notes — Meet Liquid Glass](https://wwdcnotes.com/documentation/wwdcnotes/wwdc25-219-meet-liquid-glass/)
- [conorluddy/LiquidGlassReference (GitHub)](https://github.com/conorluddy/LiquidGlassReference)
- [LogRocket — Liquid Glass with CSS and SVG](https://blog.logrocket.com/how-create-liquid-glass-effects-css-and-svg/)
- [MockFlow — Designing iOS 26 Screens with Liquid Glass](https://mockflow.com/blog/designing-ios-26-screens-with-liquid-glass-design)
- [Maxime Heckel — Physics behind spring animations](https://blog.maximeheckel.com/posts/the-physics-behind-spring-animations/)
- [Apple Newsroom — New software design (June 2025)](https://www.apple.com/newsroom/2025/06/apple-introduces-a-delightful-and-elegant-new-software-design/)
