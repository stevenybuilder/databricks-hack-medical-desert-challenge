# CareGap Design System

The single source of truth for the three tabs (`tab_map`, `tab_gaps`, `copilot`).
Tokens and components live in `app/lib/ui.py`; shared data/format helpers live in
`app/lib/tab_common.py`. Do not reinvent styling — consume these.

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
| `legend` | `legend(low_label, high_label, higher_is_worse)` | Map color-ramp legend (green→red when higher_is_worse). |
| `header` | `header()` | App top bar (called once in app entry). |

## Every tab MUST

1. Start with `ui.tab_intro(title, subtitle)`.
2. Show **≤2 KPIs up top** via `ui.kpi_row(...)` (cap is 3; prefer 2).
3. Put all depth behind `ui.detail(...)` expanders — never dump tables/options inline.
4. Use `ui.panel_header(...)` for section titles and component **tones** for color
   (never hardcode hex; reference tokens if you must write custom markup).
