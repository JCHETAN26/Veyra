/**
 * HeroTerminal — the centerpiece animation from frontend-design.md §5.
 *
 * Drop this into any Next.js (App Router or Pages) or Vite + React
 * project. Requirements:
 *   - React 18+
 *   - Tailwind CSS (any version with arbitrary values; v3.4+ ideal)
 *   - framer-motion v11+
 *
 * Quick install (Next.js):
 *   npm i framer-motion
 *   Make sure your `tailwind.config.{js,ts}` includes:
 *       content: ["./frontend/components/**\/*.{ts,tsx}", "..."]
 *
 * Usage:
 *   import { HeroTerminal } from "./HeroTerminal";
 *
 *   export default function Page() {
 *     return (
 *       <main className="bg-[#0A0A0B] min-h-screen flex items-center justify-center p-10">
 *         <HeroTerminal />
 *       </main>
 *     );
 *   }
 *
 * Behavior:
 *   - Auto-plays an ~10s loop: 7s of line-by-line reveal, 3s hold on
 *     the final ✓ PR opened line, then restart.
 *   - Pauses on hover.
 *   - Respects `prefers-reduced-motion: reduce` — falls back to a
 *     static fully-rendered terminal with no animation.
 *
 * Theming:
 *   Colors live as inline Tailwind arbitrary values to keep the file
 *   self-contained. If you've wired up the design tokens from
 *   frontend-design.md §3 into Tailwind, replace the literal hex
 *   values with their tokens (`bg-[var(--bg-2)]`, etc).
 */

"use client";

import { motion, useReducedMotion } from "framer-motion";
import { useEffect, useState } from "react";

// ---------------------------------------------------------------------------
// Data
//
// Each line of the simulated log. `delay` is in seconds, relative to the
// start of each loop. The narrative spans timestamps :11 -> :17 (6
// product-seconds) mapped to ~7 real-seconds of animation, followed by a
// 3-second hold on the ✓ PR line before restart.
// ---------------------------------------------------------------------------

type LogTone = "info" | "warn" | "action" | "success";

interface LogLine {
  delay: number;
  timestamp: string;
  source: string;
  message: string;
  tone: LogTone;
  continuation?: boolean;
}

const LINES: LogLine[] = [
  {
    delay: 0.0,
    timestamp: "03:42:11",
    source: "ingestion",
    message: "run-2026-05-31-001 received (customer_cdc)",
    tone: "info",
  },
  {
    delay: 0.5,
    timestamp: "03:42:11",
    source: "detector",
    message: "run_failure  java.lang.OutOfMemoryError",
    tone: "warn",
  },
  {
    delay: 1.2,
    timestamp: "03:42:12",
    source: "detector",
    message: "excessive_spill  1.2 GiB",
    tone: "warn",
  },
  {
    delay: 2.1,
    timestamp: "03:42:13",
    source: "rca",
    message: "category: memory_pressure  confidence 0.87",
    tone: "warn",
  },
  {
    delay: 2.6,
    timestamp: "03:42:13",
    source: "rca",
    message: "similar: [seg-2018-04] memory_pressure (0.78)",
    tone: "warn",
  },
  {
    delay: 3.5,
    timestamp: "03:42:14",
    source: "fix",
    message: "Broadcast smaller side of the join",
    tone: "warn",
  },
  {
    delay: 4.0,
    timestamp: "03:42:14",
    source: "fix",
    message: "spark.sql.shuffle.partitions=400",
    tone: "warn",
  },
  {
    delay: 4.8,
    timestamp: "03:42:15",
    source: "patch",
    message: "jobs/customer_cdc.py  diff +3 −0",
    tone: "warn",
  },
  {
    delay: 5.6,
    timestamp: "03:42:16",
    source: "git",
    message: "pushed dataforge/fix/run-2026-05-31-001",
    tone: "action",
  },
  {
    delay: 6.4,
    timestamp: "03:42:17",
    source: "github",
    message: "✓ PR #47 opened",
    tone: "success",
  },
  {
    delay: 6.7,
    timestamp: "",
    source: "",
    message: "https://github.com/acme/data-platform/pull/47",
    tone: "info",
    continuation: true,
  },
];

// Total wall-clock duration of one loop iteration, in seconds.
const LOOP_DURATION_S = 10;

// ---------------------------------------------------------------------------
// Style maps
// ---------------------------------------------------------------------------

const TONE_BAR: Record<LogTone, string> = {
  info: "bg-[#3F3F46]",
  warn: "bg-[#FBBF24]",
  action: "bg-[#22D3EE]",
  success: "bg-[#34D399]",
};

const TONE_SOURCE_TEXT: Record<LogTone, string> = {
  info: "text-[#A1A1AA]",
  warn: "text-[#FBBF24]",
  action: "text-[#22D3EE]",
  success: "text-[#34D399]",
};

// ---------------------------------------------------------------------------
// Component
// ---------------------------------------------------------------------------

export function HeroTerminal() {
  const prefersReducedMotion = useReducedMotion();
  const [paused, setPaused] = useState(false);
  const [loopKey, setLoopKey] = useState(0);

  // Restart the loop every LOOP_DURATION_S, unless paused or reduced-motion.
  useEffect(() => {
    if (prefersReducedMotion || paused) return;
    const handle = window.setInterval(() => {
      setLoopKey((k) => k + 1);
    }, LOOP_DURATION_S * 1000);
    return () => window.clearInterval(handle);
  }, [prefersReducedMotion, paused]);

  return (
    <div
      className="
        relative w-full max-w-[640px]
        rounded-[14px]
        border border-[#26262E]
        bg-[#111114]
        font-mono text-[13px] leading-[1.6]
        shadow-[0_30px_80px_-20px_rgba(124,92,255,0.25)]
        select-none
      "
      onMouseEnter={() => setPaused(true)}
      onMouseLeave={() => setPaused(false)}
      aria-label="Veyra self-healing loop, live demonstration"
      role="img"
    >
      {/* Title bar with traffic-light dots */}
      <div className="flex items-center gap-2 px-4 py-3 border-b border-[#26262E]">
        <span className="h-3 w-3 rounded-full bg-[#3F3F46]" />
        <span className="h-3 w-3 rounded-full bg-[#3F3F46]" />
        <span className="h-3 w-3 rounded-full bg-[#3F3F46]" />
        <span className="ml-3 text-[11px] uppercase tracking-[0.18em] text-[#52525B]">
          veyra console — run-2026-05-31-001
        </span>
      </div>

      {/* Log body */}
      <div className="px-5 py-5 space-y-1.5">
        {LINES.map((line, idx) => (
          <LogRow
            key={`${loopKey}-${idx}`}
            line={line}
            prefersReducedMotion={prefersReducedMotion ?? false}
          />
        ))}
      </div>

      {/* Glow on the success line — overlay positioned absolutely so it
          doesn't push other rows. */}
      <SuccessGlow loopKey={loopKey} reduced={prefersReducedMotion ?? false} />
    </div>
  );
}

// ---------------------------------------------------------------------------
// One row
// ---------------------------------------------------------------------------

function LogRow({
  line,
  prefersReducedMotion,
}: {
  line: LogLine;
  prefersReducedMotion: boolean;
}) {
  const initial = prefersReducedMotion ? false : { opacity: 0, y: 6 };
  const animate = { opacity: 1, y: 0 };
  const transition = prefersReducedMotion
    ? { duration: 0 }
    : { delay: line.delay, duration: 0.35, ease: [0.22, 1, 0.36, 1] as const };

  // Continuation lines have no timestamp / source — render indented under the
  // previous row.
  if (line.continuation) {
    return (
      <motion.div
        initial={initial}
        animate={animate}
        transition={transition}
        className="flex"
      >
        <span className="w-[5px] mr-3" />
        <span className="w-[78px] shrink-0" />
        <span className="w-[76px] shrink-0" />
        <span className="text-[#52525B] underline decoration-dotted underline-offset-2">
          {line.message}
        </span>
      </motion.div>
    );
  }

  return (
    <motion.div
      initial={initial}
      animate={animate}
      transition={transition}
      className="flex items-baseline"
    >
      <span className={`w-[5px] h-[14px] mr-3 rounded-sm ${TONE_BAR[line.tone]}`} />
      <span className="w-[78px] shrink-0 text-[#52525B]">[{line.timestamp}]</span>
      <span className={`w-[76px] shrink-0 ${TONE_SOURCE_TEXT[line.tone]}`}>
        {line.source}
      </span>
      <span className="text-[#52525B] mr-2">▸</span>
      <span className={line.tone === "success" ? "text-[#F5F5F7] font-medium" : "text-[#F5F5F7]"}>
        {line.message}
      </span>
    </motion.div>
  );
}

// ---------------------------------------------------------------------------
// Success glow — a soft green pulse that appears under the final line.
// Implemented as an absolutely-positioned div that fades in at the same
// delay as the ✓ PR line and lingers until the loop restarts.
// ---------------------------------------------------------------------------

function SuccessGlow({ loopKey, reduced }: { loopKey: number; reduced: boolean }) {
  if (reduced) return null;
  const successLine = LINES.find((l) => l.tone === "success");
  if (!successLine) return null;

  return (
    <motion.div
      key={loopKey}
      initial={{ opacity: 0 }}
      animate={{ opacity: [0, 0.55, 0.4] }}
      transition={{
        delay: successLine.delay,
        duration: 0.9,
        times: [0, 0.4, 1],
      }}
      className="pointer-events-none absolute left-0 right-0 bottom-[64px] h-[40px]"
      style={{
        background:
          "radial-gradient(ellipse at center, rgba(52,211,153,0.45) 0%, transparent 70%)",
        filter: "blur(8px)",
      }}
      aria-hidden
    />
  );
}

export default HeroTerminal;
