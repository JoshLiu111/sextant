# Design: Sextant

The locked system. Every Hallmark run reads this first and pages share it. Change it on purpose; the file is the rule.

## System
- Genre: editorial
- Shape of the first page: Conversational FAQ (`/`); every tool, the dashboard, settings, account and operator are app screens
- Theme: Studio (dealt 1/3, seed `free-finance-tools-everyday-e225·89730c67·2026-11-24·r0`)
- Axes: light/roman-serif/warm · posture: restrained · modes: light+dark (`prefers-color-scheme`)

## Tokens
`src/app/tokens.css` is the source of truth; `src/app/globals.css` maps the project's names onto it. The roles:
```css
:root {
  --color-paper: oklch(97.2% 0.006 215);  --color-paper-2: oklch(94% 0.009 215);  --color-paper-3: oklch(90.5% 0.011 215);
  --color-ink: oklch(16% 0.032 250);  --color-ink-2: oklch(34% 0.022 245);  --color-muted: oklch(49% 0.018 240);  --color-rule: oklch(84% 0.010 225);
  --color-accent: oklch(68% 0.172 50);  --color-accent-ink: oklch(16% 0.032 250);  --color-focus: oklch(52% 0.15 48);
  --color-error: oklch(52% 0.19 27);  --color-success: oklch(50% 0.12 150);
  --color-chart-1 … --color-chart-8;  --color-tool;
  --font-display: "Hedvig Letters Serif", Georgia, serif;  --font-body: "Geist", system-ui, sans-serif;
  --radius-card: 3px;  --radius-pill: 3px;  --rule-hair: 1px;  --shadow-card: none;
}
```
The spacing scale, the type scale, the easings and the durations are the scaffold's and live in `tokens.css`. Tailwind utilities read them: `bg-paper`, `bg-paper-2`, `text-ink`, `text-ink-2`, `text-muted`, `border-rule`, `bg-accent text-accent-ink`, `text-error`, `text-success`, `stroke-tool`, `font-display`, `rounded-card`.

## Rules every screen follows
- Never a Tailwind palette colour (`black/60`, `zinc-*`, `blue-500`) and never a `dark:` variant: the tokens swap themselves in dark mode. The one kept name is `text-red-700`, remapped to `--color-error` because e2e asserts the class.
- Hedvig Letters Serif for `h1`/`h2`/`h3` and display figures only; Geist for everything else, `tabular-nums` on every number. No mono.
- Labels, table heads, tabs, nav: Geist a step smaller, sentence case, untracked, `text-muted`.
- The orange fills one thing per screen: the primary action. Orange lines are construction (guides, the active tab rule); never orange type, never an orange field.
- Surfaces climb the ladder: whitespace, a 1px `border-rule` hairline, a `bg-paper-2` well, then a card (`border-rule`, `rounded-card`). Never a card in a card.

## Variants
- **Chart palette (user request: colourful charts).** Eight categorical hues (`--color-chart-1` to `-8`), tuned for light and dark, none of them the action orange. Each tool owns one through `data-tool` on its root (`globals.css`), exposed as `--color-tool`: its charts' primary series and a thin rule by its title. Further series take the other chart colours in a fixed order; reference series take `--color-muted`. Gridlines are `--color-rule`, axis text `--color-muted`, text never wears a series colour.
- **App screens.** The inputs rail, result tabs and key-figures strip (#70) stay. Controls 36 to 40px with a 44px hit target, tables before cards, four data states (loading, empty, error, full) where the logic exists.

## Controls
- Primary: `bg-accent text-accent-ink`, 1px ink border, 3px radius, Geist 500, 40px (app) / 48px (landing).
- Secondary: 1px `border-ink` outline on paper, same radius and height; tertiary is a text link with an orange underline on hover.
- Fields: 1px `border-muted`, 3px radius, `bg-paper-hi`, focus is an instant 2px `--color-focus` outline.

## Motion
- Character: calm. State changes at `--dur-short` on `--ease-out`; the landing's guides draw in once; under reduced motion everything ends at once.

## Exports
`src/app/tokens.css` in this project (Tailwind v4 `@theme static`).
