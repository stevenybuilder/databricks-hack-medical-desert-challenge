# CareGap Design System

The single source of truth for the three tabs (`tab_map`, `tab_gaps`, `copilot`).
Tokens and components live in `app/lib/ui.py`; shared data/format helpers live in
`app/lib/tab_common.py`. Do not reinvent styling — consume these.

## Aesthetic: modern dark, airy, frosted, rounded

CareGap keeps its **dark identity** but adopts a modern, layered polish
(reference: vfmatch.org/explore — its *look & feel*, not its content). The
hallmarks the whole app now inherits:

- **Layered dark, not flat-black.** A deep app background with a subtle vertical
  gradient + radial glow; elevated surfaces a few % lighter; hairline borders.
- **Frosted-glass surfaces.** Translucent panel + `backdrop-filter: blur(…)` +
  hairline border + soft shadow. One recipe, reused everywhere.
- **Rounded.** Cards/panels/expanders use a 16px card radius; buttons are pills.
- **Pill buttons.** Every Streamlit button reads as a rounded-full pill with a
  hover lift. Primary buttons are a filled teal pill.
- **Generous whitespace.** Comfortable card padding (~1.2rem) and roomy vertical
  gaps between sections; a calm top spacing.

**Usability is non-negotiable.** Text stays high-contrast on translucent
surfaces (don't over-blur or wash out copy), tap targets stay ≥36px, and every
interactive element has a visible `:focus-visible` ring. Effect never beats
legibility.

## Font

One family, set globally on `html/body/.stApp` and all inputs:

```
--mdn-font: "Inter", "SF Pro Display", ui-sans-serif, -apple-system,
            BlinkMacSystemFont, "Segoe UI", Roboto, "Helvetica Neue",
            system-ui, sans-serif;
```

Use `font-family: var(--mdn-font)` for any custom markup. Numbers in dense
tables/KPIs use tabular figures (already applied via `--mdn-tnum`).

## Color tokens (semantic — use the meaning, not the hex)

Defined in `:root` inside `ui.inject_css`. **Convention: worse = red**
(matches the data's `higher_is_worse` flag).

| Token     | Hex       | Use it for                                                |
|-----------|-----------|-----------------------------------------------------------|
| `--good`  | `#2eccc1` | Deploy / better coverage / passes checks (teal)           |
| `--mid`   | `#ffbe48` | Verify first / caution / mid (amber)                      |
| `--bad`   | `#ff5252` | Danger / worse / fails checks (red)                       |
| `--info`  | `#66d9ff` | Neutral evidence, reference accents, links (sky)          |
| `--text`  | `#eef4ff` | Primary text                                              |
| `--muted` | `#97a8c2` | Secondary text, captions                                  |
| `--panel` / `--bg` / `--line` | (dark theme) | Surfaces, backgrounds, hairlines        |

Component **tones** map onto these: `"deploy"`→good, `"verify"`→mid,
`"danger"`→bad, `"info"`→info, `"neutral"`→muted. Pass the tone, not a color.

## Typographic scale

| Token          | Size     | Use for                              |
|----------------|----------|--------------------------------------|
| `--fs-display` | 1.9rem   | Hero / Copilot greeting              |
| `--fs-h1`      | 1.36rem  | KPI value / primary stat             |
| `--fs-h2`      | 1.06rem  | Tab-intro title, banner title        |
| `--fs-body`    | .88rem   | Body copy                            |
| `--fs-caption` | .72rem   | Captions, kickers, panel headers     |

Spacing tokens: `--sp-1`…`--sp-5` (`.25rem` → `1.5rem`, 4px base).
Rhythm tokens: `--pad-card` (≈1.2rem comfortable card padding) and
`--gap-section` (≈1.1rem vertical breathing room between sections).

## Shape, depth & frosted-glass tokens

| Token            | Value                          | Use it for                                  |
|------------------|--------------------------------|---------------------------------------------|
| `--radius-card`  | `16px`                         | Cards, panels, expanders, floating cards    |
| `--radius-sm`    | `10px`                         | Inputs, inner chips, small controls         |
| `--radius-pill`  | `999px`                        | Buttons, segmented control, chips           |
| `--shadow-card`  | `0 8px 30px rgba(0,0,0,.35)`   | Standard frosted card shadow                |
| `--shadow-float` | `0 12px 40px rgba(0,0,0,.48)`  | Cards floating over the map                 |
| `--glass-bg`     | `rgba(20,28,44,.66)`           | Frosted surface background                  |
| `--glass-bg-soft`| `rgba(16,24,38,.54)`           | Lighter inner surfaces                      |
| `--glass-blur`   | `blur(14px) saturate(125%)`    | Standard backdrop blur                      |
| `--glass-border` | hairline `rgba(148,174,214,.14)` | Frosted-surface hairline border           |

`--mdn-radius` / `--mdn-radius-lg` are back-compat aliases now pointing at
`16px`. Always include both `-webkit-backdrop-filter` and `backdrop-filter`.

**Reusable frosted surfaces (wrap any custom markup):**

- `.mdn-glass` — the standard frosted card recipe (`--glass-bg`, blur, hairline,
  `--shadow-card`, `--pad-card`). Use for any custom card-like container.
- `.mdn-float` — the **floating-card** surface for content positioned **over the
  map** (legend / stat overlay). Slightly **more opaque** than `.mdn-glass` so
  text stays legible against a bright basemap, with a heavier `--shadow-float`.
  The map tab may wrap its overlay container in `class="mdn-float"` directly, or
  call `ui.floating_card(inner_html)` which wraps content in `.mdn-float`.

## Buttons (pills)

All Streamlit buttons — `stButton`, `stFormSubmitButton`, `stDownloadButton`,
and `stPopover` triggers — are styled globally as **pills**: `--radius-pill`,
`.5rem 1.1rem` padding, translucent/elevated bg, hairline border, hover lift
(`translateY(-1px)` + stronger shadow), min-height 36px, and the global focus
ring. `kind="primary"` buttons render as a filled **teal** pill (distinct CTA).
Do not re-style buttons per-tab — just use them.

## Density rule (minimalist with optionality)

**Only the 1–2 most decision-relevant things are visible by default.** Everything
else goes behind a `ui.detail(...)` expander. A tab's first glance should answer
"what do I do and where" — not show every column. Depth is opt-in, never forced.

## Component inventory (`app/lib/ui.py`)

| Component | Signature | Use this for |
|-----------|-----------|--------------|
| `tab_intro` | `tab_intro(title, subtitle="")` | The standard tab header. **Every tab starts with this.** |
| `kpi_row` | `kpi_row(items: list[(label,value,caption)], tone_each=None)` | The ≤3-card KPI strip at the top of a tab. Reuses `stat_card`. |
| `detail` | `detail(label) -> expander` | The ONE progressive-disclosure affordance. `with ui.detail("..."):` for any "expand into more." |
| `panel_header` | `panel_header(text)` | Consistent in-tab section header (the `mdn-panel-h` treatment). |
| `stat_card` | `stat_card(label, value, caption="", tone="neutral")` | A single KPI/stat card (prefer `kpi_row` for the top strip). |
| `decision_banner` | `decision_banner(title, subtitle, tone="info")` | A tone-coded "here is the recommendation" callout. |
| `reason_chips` | `reason_chips(labels: list[str])` | Render reason codes as pill chips. |
| `region_detail` | `region_detail(row, specialty, districts=None)` | District drill-down card (conditions + causal breakdown + cited evidence). |
| `facility_card` | `facility_card(f: dict)` | Clicked-facility detail with status badge + source. |
| `legend` | `legend(low_label, high_label, higher_is_worse)` | Map color-ramp legend (green→red when higher_is_worse). Now wrapped in a `.mdn-legend` frosted container. |
| `floating_card` | `floating_card(inner_html: str)` | Frosted card tuned to **float over the map** (legend / stat overlay) — wraps trusted markup in `.mdn-float`. Or apply `class="mdn-float"` directly. |
| `header` | `header()` | App top bar (called once in app entry). |

Component restyle notes (signatures unchanged): `tab_intro` is now a larger,
confident title with a muted one-line subtitle and breathing room below;
`kpi_row`/`stat_card` are frosted cards (16px radius, soft shadow, value in a
strong weight, kicker in caption style); `detail`/`st.expander` reads as a clean
rounded "show more" affordance with a pill-row header treatment.

## Every tab MUST

1. Start with `ui.tab_intro(title, subtitle)`.
2. Show **≤2 KPIs up top** via `ui.kpi_row(...)` (cap is 3; prefer 2).
3. Put all depth behind `ui.detail(...)` expanders — never dump tables/options inline.
4. Use `ui.panel_header(...)` for section titles and component **tones** for color
   (never hardcode hex; reference tokens if you must write custom markup).
