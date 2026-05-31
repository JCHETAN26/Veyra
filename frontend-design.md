# Frontend Design Prompt — Veyra Landing Page

> Use this as the brief when asking Claude (or any design tool) to generate
> the landing page for **Veyra** — an AI-native operational intelligence
> platform for data pipelines. The visual reference is **graphite.com** —
> dark-mode-first, code-forward, sophisticated, motion-rich. The page
> must feel less like a SaaS marketing site and more like a piece of
> developer tooling that you happen to be reading about.

---

## 0. The product, in one paragraph

**Veyra is the AI engineer that fixes your data pipelines.** When a Spark
or Databricks job fails — OOM, schema drift, skewed shuffle, dependency
timeout — Veyra detects the failure, explains the root cause with
citations to similar past incidents from your team's history, generates
the exact source-code patch that fixes it, opens a pull request, and
waits for your approval. From a failed nightly ETL to a merged PR in
under 90 seconds, with deterministic fallbacks and human-in-the-loop at
every gate. Target buyer: data platform leads at 50–500-person companies
running Databricks or open-source Spark.

The page sells **transformation, not features**: data teams move from
3am pages and Confluence runbooks to an AI on-call that already knows
your codebase and your incident history.

---

## 1. Visual reference & design philosophy

Pull these specific things from **graphite.com**:

1. **Dark-mode-first sophistication.** Not "black with white text" —
   layered grays (`#0a0a0a` → `#111111` → `#1a1a1a`) with subtle
   gradients between sections. Light mode is a polished alternative,
   not the default.
2. **Code is the hero asset.** Real PySpark, SQL, JSON event logs, and
   git diffs are shown verbatim with proper syntax highlighting, not as
   stock illustrations. Code snippets float in glassmorphic cards with
   soft shadows.
3. **Typography carries the design.** Big, confident headlines in a
   modern sans (Inter, Geist, or Söhne). Monospace (JetBrains Mono or
   Berkeley Mono) for anything code-shaped. Generous letter-spacing on
   small caps section labels.
4. **Restrained color.** One accent — propose **electric violet
   `#7C5CFF`** with a secondary cyan `#22D3EE` for highlights. Used
   sparingly so it pops. Most of the page is monochrome.
5. **Motion that explains, not decorates.** Animations should *teach*
   what the product does — a flowing diagram of the self-healing loop,
   not a parallax tree. Use Framer Motion or CSS scroll-linked
   animations.
6. **Negative space is a feature.** Sections breathe. Each one says one
   thing. Never crammed.
7. **Trust comes from specificity.** Real product screenshots, real
   code, real error messages — never lorem-ipsum stock cards.

What to **avoid**:

- Stock "AI" iconography (no glowing brains, no abstract neural
  networks, no robot illustrations).
- Bright gradients spanning the whole page (no Stripe-style
  rainbow-wash).
- Floating shapes / blob backgrounds.
- Generic SaaS hero illustrations (no "person on a laptop in a chair").

---

## 2. Brand

- **Name:** Veyra (use as one word, capitalized; never "VEYRA" all-caps
  outside the wordmark).
- **Wordmark:** custom sans, slight optical kerning. The "V" can have
  a subtle violet gradient stroke; the rest is white.
- **Tagline (use one):**
  - *"The AI engineer for your data pipelines."*
  - *"From OOM to merged PR in 90 seconds."*
  - *"Self-healing data infrastructure, with you in the loop."*
- **Voice:** confident, technical, terse. Engineers reading this should
  feel respected — no marketing fluff, no "leverage" / "synergy" /
  "empower." When in doubt, copy Linear or Vercel's tone.
- **Personality keywords:** precise, deterministic, calm, principled.

---

## 3. Color palette

| Token | Value | Use |
|---|---|---|
| `--bg-0` | `#0A0A0B` | Page background |
| `--bg-1` | `#111114` | Card / surface backgrounds |
| `--bg-2` | `#1A1A20` | Elevated surfaces, code blocks |
| `--border` | `#26262E` | Hairline borders |
| `--text-1` | `#F5F5F7` | Primary text |
| `--text-2` | `#A1A1AA` | Secondary text |
| `--text-3` | `#52525B` | Tertiary / captions |
| `--accent` | `#7C5CFF` | CTAs, hover states, single-color accents |
| `--accent-glow` | `#7C5CFF` @ 20% | Soft glows behind important elements |
| `--cyan` | `#22D3EE` | "Success" highlights, log timestamps, link hover |
| `--green` | `#34D399` | Status pills (resolved, success) |
| `--amber` | `#FBBF24` | Warning pills (pending approval) |
| `--red` | `#F87171` | Error pills (failed runs) |

Gradients used **sparingly**:

- Hero background: a single radial gradient from `--accent` @ 8% in the
  top-center, fading to transparent over 60% of the viewport.
- Section dividers: 1px line with a 30% violet-to-transparent gradient.

---

## 4. Typography

- **Headlines:** Inter or Geist Sans, weight 600–700, tight leading
  (`line-height: 1.1`), tracking `-0.02em` at large sizes.
- **Body:** Inter, weight 400–500, leading 1.6.
- **Mono:** JetBrains Mono or Geist Mono, weight 400. Used for code,
  shell commands, log lines, run IDs, error classes.
- **Section labels (eyebrow text):** all-caps, weight 500, tracking
  `0.18em`, size `12px`, color `--accent`.

Scale (desktop):

| Element | Size | Weight | Notes |
|---|---|---|---|
| Hero headline | 64–80px | 700 | Two lines max. Last word in `--accent`. |
| Section H2 | 44px | 600 | Single line ideal. |
| Subhead | 20–22px | 400 | Color `--text-2`. |
| Body | 16–17px | 400 | Color `--text-1`, with `--text-2` for paragraphs |
| Code (inline) | 14px | 400 | Mono. `--bg-2` chip background, `--accent` text. |
| Code block | 14–15px | 400 | Mono. Full syntax highlighting. |

---

## 5. Page structure (section-by-section)

The page is **one long scroll**. Eight sections in this order.

---

### Section 1 — Hero

**Layout:** Full viewport. Headline left-aligned, with a live-feeling
"Veyra Console" terminal animation on the right (60% / 40% split on
desktop; stacked on mobile).

**Copy:**

- **Eyebrow:** `AI THAT FIXES YOUR DATA PIPELINES`
- **Headline (two lines):**
  > From OOM error to merged PR
  > in **90 seconds**.

  ("90 seconds" in `--accent`, optionally with a subtle pulsing dot
  before it.)

- **Subhead:** *Veyra detects, explains, patches, and ships fixes to
  your Spark and Databricks jobs — with your approval, on your repo,
  with your team's incident history as memory.*

- **Primary CTA:** `Get started` → `--accent` filled button, 8px radius,
  16px horizontal padding.
- **Secondary CTA:** `Watch the 90-second demo` → ghost button with a
  small play-icon prefix, white text, `--border` outline.

**Hero animation (the showpiece — most important visual on the page):**

A simulated terminal / log stream that auto-plays on a 10-second loop,
showing the actual self-healing arc of a real run. Steps appear with a
~600ms stagger, each with a subtle slide-up + fade-in:

```
[03:42:11]  ingestion ▸ run-2026-05-31-001 received (customer_cdc)
[03:42:11]  detector  ▸ run_failure  java.lang.OutOfMemoryError
[03:42:12]  detector  ▸ excessive_spill  1.2 GiB
[03:42:13]  rca       ▸ category: memory_pressure  confidence 0.87
[03:42:13]  rca       ▸ similar: [seg-2018-04] memory_pressure (0.78)
[03:42:14]  fix       ▸ Broadcast smaller side of the join
[03:42:14]  fix       ▸ spark.sql.shuffle.partitions=400
[03:42:15]  patch     ▸ jobs/customer_cdc.py  diff +3 −0
[03:42:16]  git       ▸ pushed dataforge/fix/run-2026-05-31-001
[03:42:17]  github    ▸ ✓ PR #47 opened
                       https://github.com/acme/data-platform/pull/47
```

Styling:

- Terminal-shaped frame with three traffic-light dots (gray, not
  colored — subtler).
- Frame: `--bg-2` background, `--border` outline, `border-radius:
  12px`, drop-shadow with a faint violet tint
  (`0 30px 80px -20px rgba(124, 92, 255, 0.25)`).
- Each line has a 5px-wide colored left bar matching its severity
  (gray for info, amber for `rca`/`fix`, green for `git`/`github`).
- Timestamp in `--text-3`, system name in `--cyan`, message in
  `--text-1`. The final `✓ PR #47` line glows softly in `--green`.
- Below the terminal: a thin caption — *"Real output. Real run.
  No script. Try it yourself →"*

Background of the hero: the radial violet gradient described in §3,
plus an extremely faint dot grid (`--text-3` at 4% opacity, 24px
spacing) that fades to transparent over the bottom 30%.

---

### Section 2 — Social proof / logo strip

A single horizontal row of customer / partner / integration logos in
desaturated white, ~32px tall, with `opacity: 0.6` (full opacity on
hover). Eyebrow above: `TRUSTED BY DATA TEAMS AT`.

For the MVP page, use these as placeholders (real logos, real
companies that align with the audience): Databricks, Snowflake,
dbt Labs, Apache Spark, OpenLineage, GitHub.

Subtle: this is the only logo strip on the page. Don't repeat it.

---

### Section 3 — "How it works" — the loop

This is the page's second hero. The whole product fits in one diagram.

**Eyebrow:** `THE SELF-HEALING LOOP`
**H2:** *Six stages, deterministic at every step.*
**Subhead:** *Veyra runs the same loop a senior data engineer would —
just faster, and with memory of every incident your team has ever
shipped.*

**Diagram:** A horizontal flow of six stations, connected by a thin
violet line that animates left-to-right when the section scrolls into
view. Each station is a compact card (~140px wide, ~180px tall) with:

- A monochrome line icon at the top (no fills, 24px stroke).
- The stage name in mono caps (e.g. `DETECT`).
- A one-line description.
- A subtle hover state that reveals a code snippet on click /
  tap-and-hold.

The six stations:

1. **DETECT** — *Rule-based + ML detectors raise typed incidents.*
2. **EXPLAIN** — *LLM RCA cites prior incidents from your team's history.*
3. **RECALL** — *Operational RAG finds similar past failures via semantic embeddings.*
4. **PROPOSE** — *Typed FixAction with parameters, rollback, and impact estimate.*
5. **APPROVE** — *Human-in-the-loop gate. Nothing ships without you.*
6. **APPLY** — *Patch generated, branch pushed, PR opened.*

Below the diagram: a 1-line note in `--text-3`: *"Every stage is
swappable. Every step is logged. Every fix is reviewable."*

---

### Section 4 — Live, side-by-side product demo

This is the most code-heavy section and the most graphite-ish.

**Layout:** Two columns. Left column: a 50-line PySpark file with the
schema-drift bug, syntax-highlighted, with a red squiggle under the
buggy line and an inline annotation. Right column: the same file after
Veyra's patch, with the new lines highlighted in green and the
removed/changed lines crossed out in dim red.

**Eyebrow:** `THIS ISN'T A MOCKUP`
**H2:** *Veyra wrote this PR. Last night. At 3:14 AM.*
**Subhead:** *A real ClassCastException, a real RAG-cited postmortem,
a real diff. The output below is verbatim from a Veyra run against an
open-source sample repo.*

**Code (left — before):**

```python
"""customer_cdc — apply daily CDC events to the customers Delta table."""
from pyspark.sql import SparkSession, functions as F

def apply_cdc(spark: SparkSession) -> None:
    events = spark.read.json("s3://prod-events/customer_cdc/2026-05-31/")
    customers = spark.table("warehouse.customers")
    merged = events.join(customers, on="customer_id", how="left")
    result = (
        merged.groupBy("customer_id")
        .agg(F.max("event_ts").alias("latest_event_ts"))
    )
    result.write.format("delta").mode("overwrite").saveAsTable(
        "warehouse.customer_latest_events"
    )
```

**Code (right — after, with diff highlighting):**

```diff
"""customer_cdc — apply daily CDC events to the customers Delta table."""
from pyspark.sql import SparkSession, functions as F

def apply_cdc(spark: SparkSession) -> None:
    events = spark.read.json("s3://prod-events/customer_cdc/2026-05-31/")
+   events = events.withColumn("customer_id", F.col("customer_id").cast("long"))
    customers = spark.table("warehouse.customers")
    merged = events.join(customers, on="customer_id", how="left")
    ...
```

**Below the two columns:** a horizontal "PR header" card mocked up to
look like the top of a GitHub pull request page:

```
acme/data-platform  ▸  PR #47

fix(dependency_failure): Cast customer_id to long after CDC ingestion

opened by  veyra-bot  ·  base: main  ←  dataforge/fix/run-2026-05-31-001

🟢 Veyra analyzer confidence: 0.87
🟢 Similar past incident: seg-2018-04 (memory_pressure, score 0.78)
🟢 Rollback: Remove the cast() call.

[Approve and merge]   [Request changes]
```

Make the "Approve and merge" button look real-but-Veyra-styled
(`--green` filled, white text, GitHub-shaped pill).

---

### Section 5 — Three pillars

A 3-column grid. Each pillar = headline + 2-sentence description + a
small code-shaped illustration (a stylized log line, a stylized
embedding, a stylized fix). No icons; the illustrations carry the
visual.

**Eyebrow:** `WHY VEYRA`
**H2:** *Built for production. Not for demos.*

| Pillar | Headline | Body |
|---|---|---|
| 1 | **Memory of every incident.** | *Veyra remembers every past failure your team has shipped — the error class, the fix that worked, the runbook that nobody updated. The LLM cites them by run-id in its explanation.* |
| 2 | **Deterministic at every gate.** | *Each LLM call has a deterministic rule-based fallback. The loop never breaks because of a flaky API. Every fix waits for your approval before it ships.* |
| 3 | **Real code, real PRs.** | *Veyra doesn't paste suggestions into Slack. It generates a strictly-typed patch, applies it with drift detection, pushes a branch, and opens the PR. You review the diff like any other PR.* |

---

### Section 6 — Comparison table

The page's most direct competitive statement.

**Eyebrow:** `THE TRANSFORMATION`
**H2:** *What 3 AM looks like before and after Veyra.*

Side-by-side table. Two columns: `Before` (in muted `--text-2`) and
`After` (in `--text-1` with `--accent` highlights). Each row is a real
on-call activity, written in the data-engineer's own voice.

| Stage | Before | After |
|---|---|---|
| Page | Pagerduty wakes you at 3:14 AM. | Slack `#alerts` shows: "Veyra opened PR #47." |
| Triage | You open three tabs: Databricks logs, Airflow, dbt. | You open one tab: the PR. |
| Recall | You grep Confluence for "OutOfMemoryError." | Veyra already cited the 2018 postmortem in the RCA. |
| Fix | You write the cast, push, open the PR, post the screenshot. | You click "Approve and merge." |
| Sleep | You're up. | You're asleep. |

---

### Section 7 — Technical specs / "for the engineer reading this"

Engineers don't trust marketing. Give them the spec sheet.

**Eyebrow:** `UNDER THE HOOD`
**H2:** *No hidden magic. No vendor lock-in.*

A 2×3 grid of compact cards. Each card has a header label and a
2–3-line technical fact. No fluff.

| Card | Label | Body |
|---|---|---|
| 1 | **LLM provider-agnostic** | Anthropic, OpenAI, or Ollama. Switch with one env var. Provider-specific structured output everywhere. |
| 2 | **Deterministic fallbacks** | Every LLM call has a rule-based shadow. Circuit breaker + token budget + retry, per-provider. |
| 3 | **Operational RAG** | bge-small-en-v1.5 via fastembed (ONNX, no torch). Semantic neighbors over your team's incident corpus. |
| 4 | **Real Spark event logs** | Same JSON format the EventLoggingListener writes. Drop it in. No agents to install. |
| 5 | **Open source** | MIT-licensed. Self-host, fork, audit. Your incidents stay in your VPC. |
| 6 | **Approval-gated** | Every fix waits for a human OK. Workflow state machine is persisted and auditable. |

Below the grid: a thin row of integration logos — Databricks, Snowflake,
dbt, Airflow, Temporal, GitHub, OpenLineage — at 24px height.

---

### Section 8 — Final CTA

**Layout:** Centered. Single column, max-width 720px. Generous vertical
padding (`120px` top and bottom).

**Copy:**

- **H2:** *Your next 3 AM page can be Veyra's problem.*
- **Body:** *Get started in under five minutes against your own
  Databricks workspace. Free for individuals, free for OSS, free
  for the first three pipelines on any team.*
- **Primary CTA:** `Get started — free` → large `--accent` button,
  56px tall.
- **Secondary CTA:** `Book a demo` → ghost button.
- Below the CTAs: a single thin line in `--text-3`: *"No credit card.
  No sales call. Your incident history never leaves your cloud."*

Background: a deeper version of the hero's radial gradient. The Veyra
wordmark, large and faint (~30% opacity), watermark behind the heading.

---

### Footer

Four columns: Product, Resources, Company, Legal. Standard. Wordmark
top-left, social icons (GitHub, X, LinkedIn, Discord) top-right.
Copyright line at the bottom. Quiet, restrained.

---

## 6. Navigation

Fixed top nav, 64px tall, `--bg-0` with a 1px bottom border on scroll.

Left: Veyra wordmark.
Center: Product / Docs / Pricing / Changelog (small mono-feel sans,
`--text-2`, hover → `--text-1`).
Right: `Sign in` (text link) + `Get started` (small filled `--accent`
button, 36px tall).

On scroll past 80px, the nav gets a subtle backdrop-blur and the border
appears.

---

## 7. Buttons & components

| Component | Spec |
|---|---|
| Primary button | `--accent` background, white text, `border-radius: 8px`, padding `12px 18px`. Hover: brightness 110% + a 0.5px ring of `--accent-glow`. |
| Secondary button | `transparent` background, `--text-1` text, `--border` outline. Hover: `--bg-1` background. |
| Ghost link | `--text-2` text. Hover: `--text-1` + subtle underline that animates in. |
| Code block | `--bg-2` background, `--border` outline, `border-radius: 12px`, padding `20px 24px`. Tiny "copy" button top-right that fades in on hover. |
| Inline code | `--bg-2` background, `--accent` text, padding `2px 6px`, `border-radius: 4px`. |
| Card | `--bg-1` background, `--border` outline, `border-radius: 16px`, padding `28px`. Hover: outline brightens to `--accent` at 40%, slight Y-translate (`-2px`). |
| Status pill | `--bg-2` background, colored text + colored dot prefix, mono, `border-radius: 999px`. |

---

## 8. Motion & interaction

- **Scroll-linked reveals.** Each section fades in + translates up
  `12px` over `400ms` when it enters the viewport. Use Intersection
  Observer or Framer Motion `whileInView`.
- **Hero terminal.** Auto-plays the 10-second loop. Pauses on hover.
  Each line stagger-animates in via slide-up + opacity.
- **Loop diagram.** The connecting violet line animates left-to-right
  on scroll-into-view (~1.2s). Stations pulse subtly (`scale: 1` →
  `1.02` → `1` on a 4s loop, staggered by station index).
- **Code-block reveal.** When the before/after section enters view,
  the "before" code is shown for ~600ms, then the diff highlights
  fade in line-by-line.
- **PR card.** When the "Approve and merge" button is hovered, a soft
  green glow appears and the button label briefly changes to
  `✓ Merged`.
- **CTA hover.** All primary CTAs get a `box-shadow: 0 0 0 6px
  rgba(124,92,255,0.18)` on hover.
- **Cursor.** Default cursor everywhere — no custom-cursor gimmicks.
- **No autoplay video.** The hero is animated CSS/JS, not a video file.

Performance budget: hero animation under 50KB JS, total page weight
under 600KB excluding the font files. No animation should drop below
60fps on a 2020 MacBook Air.

---

## 9. Responsive behavior

| Breakpoint | Behavior |
|---|---|
| < 640px | Single column. Hero terminal stacks below the headline at 90% width. Loop diagram becomes a vertical timeline. Comparison table becomes paired cards. Three pillars stack. Nav collapses into a hamburger that opens a full-screen sheet. |
| 640–1024px | Two columns where appropriate. Hero headline scales to 48–56px. |
| > 1024px | Full design as described. Max content width: `1200px`. |

Touch targets minimum 44×44px. Hover states are keyboard-focusable.

---

## 10. Assets to render

- Veyra wordmark (SVG, white + violet stroke variant + mono dark
  variant).
- One single-glyph mark for favicon / small spaces — a stylized V
  built from two intersecting code-line angle brackets.
- Six line icons for the loop stations (DETECT, EXPLAIN, RECALL,
  PROPOSE, APPROVE, APPLY) — 24px stroke, no fills, single weight.
- Three "code-shape" illustrations for the pillars section.
- Hero terminal frame component (the most reusable element on the
  page).

No photography. No people. No stock anything.

---

## 11. Accessibility

- All text passes WCAG AA contrast against its background. Body text
  on `--bg-0` should test at ≥ 7:1.
- All interactive elements have a visible focus ring (`--accent`,
  2px, offset 2px).
- All animations respect `prefers-reduced-motion: reduce` — disable
  the hero auto-loop, the loop-line draw, and the pulsing stations.
- All code blocks have a proper `<code>` tag and a hidden "Copy code"
  affordance for screen readers.

---

## 12. Quality bar — what "amazing" means here

The page is doing its job if:

1. A senior data engineer scrolling past in <30 seconds understands
   exactly what Veyra does — without reading the copy carefully.
2. The hero terminal animation makes someone screenshot it and share
   it in Slack.
3. The before/after code section makes someone audibly say *"oh."*
4. There is not a single word on the page that could appear on any
   other AI startup's homepage. Every sentence is Veyra-specific.
5. A YC partner clicking the page during interview prep stops on the
   hero, watches the loop play once, and thinks *"these people get it."*

If any of those fails, the section in question gets rebuilt.

---

## 13. Tech stack suggestion (for whoever implements this)

- **Framework:** Next.js 14 (App Router) or Astro. Either works.
- **Styling:** Tailwind CSS with a custom theme matching the palette
  above. Avoid CSS-in-JS for performance.
- **Motion:** Framer Motion for the orchestrated sequences (hero
  terminal, loop diagram). Plain CSS for everything else.
- **Code highlighting:** Shiki (static, ships zero runtime JS for
  highlighting).
- **Fonts:** Inter via `next/font` (no flash). JetBrains Mono for the
  monospace surface.
- **Deploy:** Vercel. Edge functions where useful.
- **Analytics:** Plausible or Vercel Analytics. No Google Analytics.

---

## 14. Deliverables

When generating the page, please return:

1. The full landing page as a single component tree (or
   route-grouped if Next.js).
2. The `tailwind.config.{js,ts}` with the design tokens above.
3. A standalone, copy-pasteable hero terminal component.
4. A standalone before/after code-diff component.
5. A `README.md` for the design system describing the tokens.

Optimize for: **first-page-load impact**, **legibility on a 15-inch
laptop**, **a single screenshot of the hero being shareable on its own**.

---

**Brief author's note:** the brand to lean into is *quiet
confidence* — Veyra is a tool for engineers who hate being woken up.
Every design choice should feel like the team behind it ships
production software, not marketing campaigns. If a choice would
embarrass a staff engineer reading it, cut it.
