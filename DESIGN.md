# RiskDiff design system

Read this before changing anything under `web/`. It is binding for every page and component.

## The idea

RiskDiff should feel like an analyst's marked-up copy of an SEC filing: calm, precise, credible to a
bank, with one memorable visual idea. That idea is the **highlighter**: words that are new or changed
in this year's filing text carry a real highlighter stroke, the way an analyst marks up a printed 10-K.
Spend boldness there; keep everything around it quiet.

Color encodes the **direction of a disclosure change**, never good or bad:

| Meaning | Family | Where |
|---|---|---|
| More disclosure language (New risk, Expanded) | blue | badges, level meters, heatmap cells, change-mix bars |
| Less disclosure language (Dropped risk, Scaled back) | orange | same |
| Rewritten in both directions (Major update) | ink on light gray | same |
| Potential became actual | amber | its badge and its card, the most important signal |
| Newly named, New figure disclosed | ink on light gray | badges |

Blue and orange are value-neutral and colorblind-safe. Green and red are never used for direction:
finance readers read them as good and bad, and RiskDiff never says a change is good or bad.

Audience: portfolio managers, advisors and bank judges, fluent in finance, not technical. Every screen
must make sense in five seconds.

## Tokens (implemented in `web/src/app/globals.css`, `@theme`)

### Fonts

* Interface: **Public Sans** (`--font-sans`, loaded with `next/font/google`).
* Filing quotes and filing text: **Source Serif 4** (`--font-serif`). The filing speaks in serif; the
  product speaks in sans. Never the other way round.
* Figures use tabular numerals everywhere (`font-variant-numeric: tabular-nums` on `body`).
* No monospace in the interface except the audit trail's identifiers.

### Type scale (px)

| Token | Size | Line height | Use |
|---|---|---|---|
| `text-xs` | 14 | 1.45 | the floor: badges, table notes, footer, nothing smaller exists |
| `text-sm` | 15 | 1.5 | secondary UI text, labels, captions |
| `text-base` | 17 | 1.55 | UI body text |
| `text-lg` | 22 | 1.3 | card and section headings, the summary statement |
| `text-xl` | 32 | 1.2 | page section titles |
| `text-2xl` | 44 | 1.1 | the page title (home headline) |
| `.filing-text`, `.quote` | 18 | 1.65 | filing sentences in the serif |

Weights: 400 and 500 only. 600 (`font-title`) is allowed for the page title alone. Tailwind's
`font-semibold` and `font-bold` resolve to 500 on purpose, so legacy classes cannot reintroduce
heavy weights.

### Neutrals

| Token | Value | Use |
|---|---|---|
| `ink` | `#14213D` | text |
| `ink-secondary` | `#3E4A5F` | the lightest allowed for anything people need to read |
| `ink-muted` | `#627187` | last-year text and disabled states only (adjusted from `#6B7A90`, which was 4.1:1 on the page color) |
| `line` | `#D9DFE7` | rules and borders |
| `paper` | `#F5F7FA` | page background |
| `surface` | `#FFFFFF` | cards, header, footer |

`ink-faint` is a legacy alias of `ink-secondary`; do not use it in new code.

### Direction of change

| Token pair | Text | Background | Label |
|---|---|---|---|
| `more-strong-fg` / `more-strong-bg` | `#174A85` | `#DCE8F7` | New risk |
| `more-fg` / `more-bg` | `#2C64A8` | `#E6EFFA` | Expanded |
| `less-strong-fg` / `less-strong-bg` | `#96420F` | `#F8E3D6` | Dropped risk |
| `less-fg` / `less-bg` | `#A64B18` | `#FBEDE3` | Scaled back (text adjusted from `#B5541C`, which was 4.3:1 on its tint) |
| `rewrite-fg` / `rewrite-bg` | `#14213D` | `#E6E9EF` | Major update |
| `actual-fg` / `actual-bg` | `#7A4B00` | `#FCEFC7` | Potential became actual. Its badge also carries a 1px inset ring in `actual-fg` at 60%, because the tint sits in the highlighter's family and reviewers read the badge as a highlighted word |
| `signal-fg` / `signal-bg` | `#14213D` | `#EEF1F5` | Newly named, New figure disclosed |

Essentially unchanged uses `ink-secondary` on `surface` with a `line` border.

### Highlighter and strike

* Added or changed words in **this year's** quotes: `highlighter` `#FFD95A`, drawn as a marker stroke
  over the lower part of the line, `linear-gradient(transparent 35%, #FFD95A 35%)`, with
  `box-decoration-break: clone`. Never a full box, never a border. Class: `.hl`.
* Removed words in **last year's** quotes: struck through in `strike` `#B5541C` (`text-decoration:
  line-through`, 1.5px; a decoration, so the orange stays at the brief's value), text stays readable.
  Class: `.strike`.
* The highlighter only marks words the deterministic diff identified (`diff_spans`, or a whole
  sentence whose status is `added`). It never marks anything an LLM wrote.

### Shape, elevation, motion

* Radius: 8px for controls (`rounded-md`), 12px for the few real cards (`rounded-lg`), 6px for badges
  (`rounded-sm`), 0 for rules.
* No drop shadows, except one subtle shadow on hover for clickable cards (`hover:shadow-card`).
* No gradients other than the highlighter.
* `prefers-reduced-motion` disables the citation flash transition and smooth scrolling.

### Spacing and measure

4px base; steps 4 / 8 / 12 / 16 / 24 / 32 / 48 / 64 (Tailwind 1, 2, 3, 4, 6, 8, 12, 16). Running text
is capped at about 72 characters (`max-w-prose-72`). Cards stack to one column below about 900px.

## Components

* `ChangeBadge`: solid tint background, colored text from the direction tokens, 14–15px, 6px radius.
  No outline-only pills. One implementation, used in lists, cards, the detail page and Trends.
* `ChangeLevel`: "Wording change: High / Medium / Low" as a 3-segment meter of equal squares filled in
  ink; the number sits in a tooltip and the aria-label. The meter shows magnitude only. Direction is
  the badge beside it: two outside reviews read direction-colored segments as a severity gauge, and a
  gray "Major update" at High looked fainter than a blue "Expanded" at Medium.
* Before/after card: badge, 22px short title, one quiet source line; two columns "Last year" (muted
  serif, thin muted left rule, removed words struck) and "This year" (ink serif, ink left rule,
  highlighter on changed words); "Open in SEC filing" and "See the full change" in the footer.
* Legend: one line near the top of the company page explains blue, orange and amber once.

## Copy

* Labels are sentence case: "Last year", "This year", "Top change".
* Each concept is explained once: a legend, a tooltip or the methodology page, not a helper sentence
  under every element.
* Company names are display names ("NVIDIA", "Amazon"), the official SEC name lives in the audit trail.
* Lists and cards use short titles; the full official risk heading appears only on the detail page.
* Wording is "newly added", "more language", "less language", "most widespread new disclosures". Never
  "impact", "biggest risk", "riskier", likelihoods or advice.

## Don'ts (each checkable by looking)

* No uppercase tracked-out labels.
* No middle-dot meta strings ("FY2025 · filed Feb 26 · 29 risk factors"): use labeled stats or a sentence.
* No arrows appended to link text; the external-link icon appears only on links that leave the site.
* No purple or indigo anywhere.
* No dashed borders.
* No helper sentence under every element.
* No cards inside cards; sections are separated by spacing and one rule; only clickable items are cards.
* No emoji.
* No text smaller than 14px.
* No gray text lighter than `#3E4A5F` for anything people need to read.
* No green or red for the direction of a change.
* No gradients except the highlighter, no shadows except the hover shadow on clickable cards.

## Accessibility

WCAG AA contrast for all text (measured: ink on paper 14.9:1, secondary on paper 8.3:1, muted on paper
4.6:1, badge text on its tint between 5.0:1 and 14.1:1, ink on the highlighter 11.7:1, white on accent 8.9:1); visible keyboard
focus (3px `more-strong-fg` outline); color is never the only carrier of meaning (every colored element
also has a word or a number); numbers in charts are available in tooltips and to screen readers;
reduced motion is respected.
