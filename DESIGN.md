---
version: "alpha"
name: Manglar
description: >-
  Visual identity of Manglar, the AI assistant for Colombia's open data
  (datos.gov.co). Organic precision: a deep institutional root-blue, a living
  root-to-canopy gradient, Geologica typography, and a data-dot motif taken
  from the isotype.
colors:
  # Brand ramp — order matters: root (deep blue) -> canopy (green)
  primary: "#1b3f92"
  secondary: "#559bc5"
  tertiary: "#68bdbc"
  quaternary: "#69bba6"
  quinary: "#6fbb79"
  # Semantic brand tokens
  on-primary: "#ffffff"
  primary-hover: "#16337a"
  primary-active: "#122a66"
  primary-soft: "#e8eef9"
  # Cool neutrals tinted toward the root blue
  background: "#ffffff"
  foreground: "#0f1b33"
  surface: "#f4f7fb"
  surface-raised: "#ffffff"
  muted-foreground: "#55637a"
  border: "#dde5ef"
  # Dark scheme — "manglar at night", derived from the root blue
  background-dark: "#0a1428"
  foreground-dark: "#eef3fa"
  surface-dark: "#111f3c"
  surface-raised-dark: "#16264a"
  muted-foreground-dark: "#93a3bd"
  border-dark: "#22345a"
  primary-dark: "#68bdbc"
  on-primary-dark: "#0a1428"
  # Status
  success: "#357a45"
  success-soft: "#e4f4e8"
  warning: "#b45309"
  warning-soft: "#fdf1e3"
  destructive: "#c81e3a"
  destructive-soft: "#fbe9ea"
typography:
  display:
    fontFamily: Geologica
    fontSize: 3rem
    fontWeight: 800
    lineHeight: 1.05
    letterSpacing: -0.99px
  h1:
    fontFamily: Geologica
    fontSize: 2.25rem
    fontWeight: 700
    lineHeight: 1.1
    letterSpacing: -0.99px
  h2:
    fontFamily: Geologica
    fontSize: 1.5rem
    fontWeight: 700
    lineHeight: 1.2
    letterSpacing: -0.01em
  h3:
    fontFamily: Geologica
    fontSize: 1.25rem
    fontWeight: 600
    lineHeight: 1.3
  body-lg:
    fontFamily: Geologica
    fontSize: 1.125rem
    fontWeight: 400
    lineHeight: 1.6
  body-md:
    fontFamily: Geologica
    fontSize: 1rem
    fontWeight: 400
    lineHeight: 1.6
  body-sm:
    fontFamily: Geologica
    fontSize: 0.875rem
    fontWeight: 400
    lineHeight: 1.5
  label-caps:
    fontFamily: Geologica
    fontSize: 0.75rem
    fontWeight: 600
    lineHeight: 1.2
    letterSpacing: 0.08em
  code:
    fontFamily: Geist Mono
    fontSize: 0.875rem
    fontWeight: 400
    lineHeight: 1.5
rounded:
  sm: 8px
  md: 12px
  lg: 16px
  full: 9999px
spacing:
  xs: 4px
  sm: 8px
  md: 16px
  lg: 24px
  xl: 32px
  2xl: 48px
  3xl: 64px
components:
  app-body:
    backgroundColor: "{colors.background}"
    textColor: "{colors.foreground}"
    typography: "{typography.body-md}"
  app-body-dark:
    backgroundColor: "{colors.background-dark}"
    textColor: "{colors.foreground-dark}"
    typography: "{typography.body-md}"
  button-primary:
    backgroundColor: "{colors.primary}"
    textColor: "{colors.on-primary}"
    typography: "{typography.body-md}"
    rounded: "{rounded.md}"
    padding: 12px
    height: 44px
  button-primary-hover:
    backgroundColor: "{colors.primary-hover}"
    textColor: "{colors.on-primary}"
    rounded: "{rounded.md}"
    padding: 12px
    height: 44px
  button-primary-active:
    backgroundColor: "{colors.primary-active}"
    textColor: "{colors.on-primary}"
    rounded: "{rounded.md}"
    padding: 12px
    height: 44px
  button-primary-dark:
    backgroundColor: "{colors.primary-dark}"
    textColor: "{colors.on-primary-dark}"
    rounded: "{rounded.md}"
    padding: 12px
    height: 44px
  button-secondary:
    backgroundColor: "{colors.surface}"
    textColor: "{colors.foreground}"
    rounded: "{rounded.md}"
    padding: 12px
    height: 44px
  button-destructive:
    backgroundColor: "{colors.destructive}"
    textColor: "{colors.on-primary}"
    rounded: "{rounded.md}"
    padding: 12px
    height: 44px
  card:
    backgroundColor: "{colors.surface-raised}"
    textColor: "{colors.foreground}"
    rounded: "{rounded.lg}"
    padding: 24px
  card-dark:
    backgroundColor: "{colors.surface-dark}"
    textColor: "{colors.foreground-dark}"
    rounded: "{rounded.lg}"
    padding: 24px
  chip-source:
    backgroundColor: "{colors.primary-soft}"
    textColor: "{colors.primary}"
    typography: "{typography.body-sm}"
    rounded: "{rounded.full}"
    padding: 8px
  chip-source-dark:
    backgroundColor: "{colors.surface-raised-dark}"
    textColor: "{colors.primary-dark}"
    typography: "{typography.body-sm}"
    rounded: "{rounded.full}"
    padding: 8px
  chat-message-user:
    backgroundColor: "{colors.primary}"
    textColor: "{colors.on-primary}"
    rounded: "{rounded.lg}"
    padding: 16px
  chat-message-assistant:
    backgroundColor: "{colors.surface}"
    textColor: "{colors.foreground}"
    rounded: "{rounded.lg}"
    padding: 16px
  chat-message-assistant-dark:
    backgroundColor: "{colors.surface-dark}"
    textColor: "{colors.foreground-dark}"
    rounded: "{rounded.lg}"
    padding: 16px
  input-text:
    backgroundColor: "{colors.surface-raised}"
    textColor: "{colors.foreground}"
    rounded: "{rounded.md}"
    padding: 12px
    height: 48px
  badge-success:
    backgroundColor: "{colors.success-soft}"
    textColor: "{colors.success}"
    typography: "{typography.body-sm}"
    rounded: "{rounded.full}"
    padding: 4px
  badge-warning:
    backgroundColor: "{colors.warning-soft}"
    textColor: "{colors.warning}"
    typography: "{typography.body-sm}"
    rounded: "{rounded.full}"
    padding: 4px
  badge-destructive:
    backgroundColor: "{colors.destructive-soft}"
    textColor: "{colors.destructive}"
    typography: "{typography.body-sm}"
    rounded: "{rounded.full}"
    padding: 4px
  caption:
    backgroundColor: "{colors.background}"
    textColor: "{colors.muted-foreground}"
    typography: "{typography.body-sm}"
  caption-dark:
    backgroundColor: "{colors.background-dark}"
    textColor: "{colors.muted-foreground-dark}"
    typography: "{typography.body-sm}"
  chart-series-1:
    backgroundColor: "{colors.primary}"
  chart-series-2:
    backgroundColor: "{colors.quinary}"
  chart-series-3:
    backgroundColor: "{colors.secondary}"
  chart-series-4:
    backgroundColor: "{colors.quaternary}"
  chart-series-5:
    backgroundColor: "{colors.tertiary}"
---

## Overview

Manglar is where citizens meet Colombia's open data. A mangrove (manglar) is
an ecosystem where the river meets the sea — interlocking roots that filter,
connect, and nurture life. The product does the same for datos.gov.co: it
roots through thousands of datasets and returns something alive and useful.

The isotype says it literally: **a mangrove tree drawn as data points** —
deep blue roots, a teal trunk, a green canopy. The whole interface is built
from that single idea:

- **Organic precision.** Clean institutional surfaces (white, cool neutrals,
  hairline borders) anchored by the root blue `#1b3f92`. Nothing decorative
  that doesn't carry data or meaning.
- **One living gradient.** The root→canopy ramp
  (`#1b3f92 → #559bc5 → #68bdbc → #69bba6 → #6fbb79`) is the brand's single
  burst of color. It is reserved for brand moments only: the mark, the chat
  FAB accent, a 2px gradient hairline, hero dot-matrix, and data-viz ramps.
  Never behind text, never as a large fill.
- **The dot is the signature.** Circular data-dots echo the isotype:
  five-color brand dots in the header, dot loading states, the FAB. Spend
  boldness there; keep everything else quiet and disciplined.

All user-facing copy is Spanish (es-CO), sentence case, active voice.

### Logo assets

Multiple official assets (source: `LOGO MANGLAR` folder) — copied into
`apps/frontend/public/brand/`:

The variant names describe the **background** the lockup is built for:
`claro` (dark-blue wordmark) sits on light surfaces; `negro` (white
wordmark) sits on dark surfaces.

You can find the differnt png assets in the `public/brand` folder you must use them corresponding to the name of the file. `LOGOTIPO` = wordmark, `ISOTIPO` = mark. 'BLANCO' = white, 'NEGRO' = black, 'CLARO' = light, 'OSCURO' = dark.

The `manglar-loading.webp` is important for all parts of the frontend where we are loading.

Rules: never recolor, stretch, crop, or add effects to the mark — the
multicolor isotype is only ever shown in full color on a light surface (give
it a white chip/circle when it must sit on a brand-blue or dark bar); never
CSS-invert it. Clear space around the lockup = the height of the largest dot
in the isotype. Minimum isotype size 24px; below that the dots lose
legibility — use a single `{colors.primary}` dot instead. Never set the
logotipo claro on dark backgrounds or the logotipo negro on light ones.

## Colors

The five brand colors are a **ramp, not a palette of equals**. Order carries
the story: roots (depth, trust) → canopy (life, answers).

| Token | Hex | Name | Role |
|---|---|---|---|
| `primary` | `#1b3f92` | Azul Raíz | Headlines, primary actions, links, key text. 9.7:1 on white — the only brand color safe for body-size text on light surfaces |
| `secondary` | `#559bc5` | Azul Río | Icons, focus rings, secondary data series. 3.1:1 on white — large text, icons, and non-text UI only |
| `tertiary` | `#68bdbc` | Verde Marea | Fills, highlights, dark-mode primary accent. 2.2:1 on white — never text on light surfaces |
| `quaternary` | `#69bba6` | Verde Brote | Data series, fills. Never text on light surfaces |
| `quinary` | `#6fbb79` | Verde Copa | Positive/growth indicators, data series. Never text on light surfaces |

Neutrals are cool grays tinted toward the root blue so chrome never fights
the brand: `foreground #0f1b33` (15.6:1 on white — default text),
`muted-foreground #55637a` (6.1:1 — captions/metadata), `surface #f4f7fb`,
`border #dde5ef`.

**Dark scheme** ("manglar de noche"): backgrounds derive from the root blue
(`background-dark #0a1428`, surfaces `#111f3c` / `#16264a`). The primary
accent shifts to Verde Marea `#68bdbc` (7.4:1 on the dark background); the
deep Azul Raíz disappears on dark and must not be used there. Chart colors
are identical in both schemes — all five read clearly on both white and
`#0a1428`.

**Status colors** are functional, not decorative, and always paired with an
icon or label: `success #357a45`, `warning #b45309`, `destructive #c81e3a`,
each with a soft tint (`*-soft`) for badge backgrounds.

**The Manglar gradient** — exact stops, brand order:

```css
linear-gradient(90deg, #1b3f92 0%, #559bc5 25%, #68bdbc 50%, #69bba6 75%, #6fbb79 100%)
```

Permitted uses: 2px hairline rules, the FAB pulse ring, dot-matrix hero
texture, Vega-Lite continuous ramps. Forbidden: button backgrounds, text
fills, panels, any area behind copy.

## Typography

**Geologica** is the single brand family — a geometric sans with humanist
warmth that matches the dotted mark: precise circles, friendly rhythm. It is
a variable font (100–900); load it with `next/font/google`, `display: swap`,
`--font-geologica` CSS variable. Geist Mono stays for code/SoQL only.

**The -0.99px tracking is a headline privilege.** Tight tracking is what
makes the wordmark feel like the logotipo — but it destroys body-text
readability. Apply `-0.99px` (≈ -0.02em at 48px) only to `display` and `h1`
≥ 24px, plus the in-app "Manglar" wordmark. `h2` gets a gentler `-0.01em`.
Everything at body size and below: tracking 0, always.

| Token | Size / Weight / LH | Use |
|---|---|---|
| `display` | 3rem / 800 / 1.05, -0.99px | Hero headline only |
| `h1` | 2.25rem / 700 / 1.1, -0.99px | Page titles, empty states |
| `h2` | 1.5rem / 700 / 1.2, -0.01em | Section titles |
| `h3` | 1.25rem / 600 / 1.3 | Card titles, chart titles |
| `body-lg` | 1.125rem / 400 / 1.6 | Chat lead paragraph, intros |
| `body-md` | 1rem / 400 / 1.6 | Default body, chat messages |
| `body-sm` | 0.875rem / 400 / 1.5 | Captions, metadata, chips |
| `label-caps` | 0.75rem / 600 / +0.08em, uppercase | Eyebrows, table headers — the deliberate counterpoint to the tight display tracking |
| `code` | 0.875rem Geist Mono | SoQL blocks, dataset IDs, permalinks |

Hierarchy comes from weight and spacing, not from color: headlines in
`foreground` or `primary`, never in the light ramp tones. Tabular figures
(`font-feature-settings: "tnum"`) for numeric columns in data tables.

## Layout

- **Chat-first.** The product is a conversation: single centered column,
  `max-width: 768px` (3xl) for the chat stream; `max-width: 1152px` (6xl)
  for page chrome. Line length never exceeds ~75 characters.
- **Spacing rhythm** on the 4px grid: `xs 4 / sm 8 / md 16 / lg 24 / xl 32 /
  2xl 48 / 3xl 64`. Component padding 12–24px; section gaps 48–64px. No
  arbitrary values.
- **Header:** 64px, hairline bottom border, isotype + wordmark left,
  five-dot brand strip (the five ramp colors as 8px dots) as the only
  decoration.
- **Breakpoints:** 375 / 768 / 1024 / 1440, mobile-first. The chat FAB
  (`64px`, bottom-right, 24px margins) and its panel must respect safe-area
  insets; the panel is `min(400px, 100vw - 32px)` wide.
- **z-index scale:** base 0, sticky header 10, chat panel 40, FAB 50,
  toast 100. Nothing else.

## Elevation & Depth

Flat by default; elevation is reserved for floating elements. Shadows are
tinted with the root blue (`rgb(15 27 51 / …)`), never pure black:

| Level | Use | Shadow |
|---|---|---|
| 0 | Cards, inputs | none — 1px `border` hairline |
| 1 | Hover on interactive cards | `0 1px 2px rgb(15 27 51 / 0.06), 0 2px 8px rgb(15 27 51 / 0.04)` |
| 2 | Popovers, chat panel | `0 8px 24px rgb(15 27 51 / 0.12)` |
| 3 | FAB | `0 4px 16px rgb(27 63 146 / 0.35)` |

Dark scheme: elevation is expressed with `border-dark` hairlines plus
`0 8px 24px rgb(0 0 0 / 0.4)` for floating elements — tinted shadows are
invisible on dark surfaces.

## Shapes

- Radius scale: `sm 8 / md 12 / lg 16 / full`. Cards and chat bubbles `lg`,
  buttons/inputs `md`, chips/badges/avatar/FAB `full`. Chat bubbles keep one
  `sm` corner on the sender side (bottom-right for user, bottom-left for
  assistant) — the only asymmetry allowed.
- **The dot motif:** perfect circles only, sized from the 4px grid (4, 8,
  12px). Used for the header brand strip, loading indicators (three dots,
  `tertiary → quaternary → quinary`, 300ms stagger), and the dot-matrix
  texture.
- **Gradient hairline:** 2px, full gradient, appears once per view max
  (under the header or above the chat input).
- No sharp-cornered containers, no skeuomorphism, no glassmorphism.

## Components

**Buttons.** One primary action per view: solid `primary` (44px min height,
`md` radius, 600-weight label). Hover `primary-hover`, active
`primary-active`, focus-visible 2px `secondary` ring offset 2px. Secondary
buttons are `surface` fills with a `border` hairline — never the light ramp
tones. Dark scheme: primary button becomes `primary-dark` with
`on-primary-dark` text.

**Chat FAB (ManglarBubble).** 64px circle, white background with a `border`
hairline, full-color isotype inside (never inverted). Idle pulse ring in
`tertiary` (`rgb(104 189 188 / 0.55)`), 2.2s ease-in-out, disabled under
`prefers-reduced-motion`. Panel enters with 200ms ease-out
`translateY(12px) scale(0.95) → 1`. The panel's brand-blue header carries the
isotype on a white circular chip for the same reason.

**Chat messages.** User: `primary` bg, white text, right-aligned. Assistant:
`surface` bg (level 0), `foreground` text, isotype avatar (28px). Streaming
text appears without animation; tool/step indicators use `body-sm` in
`muted-foreground` with a single spinning dot.

**Citations & sources.** `chip-source`: `primary-soft` pill, `primary` text,
dataset title + external-link icon (Lucide, 14px). Sources card: level-0
card, `h3` title, chips stacked with 8px gaps. Every chart answer carries at
least one citation chip and a permalink.

**Charts (Vega-Lite).** The brand ramp is the chart palette — this is where
the five colors work hardest. Inject via `vegaEmbed` config:

- `range.category`: `["#1b3f92", "#6fbb79", "#559bc5", "#69bba6", "#68bdbc"]`
  (alternated dark/light so adjacent series stay distinguishable)
- `range.ramp` (continuous): brand order `["#1b3f92", "#559bc5", "#68bdbc",
  "#69bba6", "#6fbb79"]`
- `range.diverging`: `["#c81e3a", "#f4f7fb", "#1b3f92"]`
- Axis/legend text `muted-foreground` 12px; gridlines `border` 1px, dashed
  only if needed; background transparent; tooltips on, values formatted
  es-CO (`1.234.567,89`). Never red/green-only encodings; direct-label small
  series. Always render the data-table fallback below the chart for screen
  readers.

**Forms.** 48px inputs, `surface-raised` fill, `border` hairline, visible
label above (never placeholder-only). Focus: 2px `secondary` ring. Errors:
`destructive` text + icon below the field, `aria-live="polite"`.

**Loading & empty states.** Loading: isotype with a gentle opacity pulse
(1.6s), alt "Manglar cargando"; skeleton blocks shimmer in `surface` with a
`surface-raised` sweep. Empty chat: `h1` "Pregunta por los datos de
Colombia", three suggestion chips in `chip-source` style. Errors state cause
+ recovery, no apologies.

**Header wordmark.** When rendered as text (fallback for the logotipo):
Geologica 800, `-0.99px` tracking, `primary` color, lowercase "Manglar"
exactly as the logotipo sets it.

## Do's and Don'ts

**Do**

- Use `primary` for every headline, link, and primary action — it is the
  workhorse and the only AA-safe brand color for text on white.
- Reserve the gradient and the light ramp tones for data, dots, and the
  mark. Restraint is what makes them feel alive.
- Pair every status color with an icon or text label.
- Keep `tertiary` as the single dark-mode accent.
- Use Lucide icons (1.5px stroke) exclusively; 44×44px minimum touch
  targets; visible focus rings on everything interactive.
- Honor `prefers-reduced-motion`: kill the FAB pulse, dot stagger, and panel
  animation.

**Don't**

- Don't set body text in `#559bc5`, `#68bdbc`, `#69bba6`, or `#6fbb79` on
  white — all fail WCAG AA (2.2–3.1:1). On the light tones, text is
  `primary` or `foreground`.
- Don't put white text on the three light ramp tones (2.2–2.4:1).
- Don't apply the -0.99px tracking below 24px or to body copy.
- Don't use the gradient behind text, on buttons, or as a panel fill.
- Don't recolor, outline, invert, or shadow the isotype; don't use the
  logotipo claro on dark surfaces or the logotipo negro on light ones.
- Don't use `#1b3f92` for text or small icons in the dark scheme — swap to
  `primary-dark`.
- Don't use emojis as UI icons, and don't introduce new hues beyond this
  file (status colors excepted).
