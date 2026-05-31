# Veyra Frontend Assets

Drop-in components and design tokens to pair with `frontend-design.md`.
Whatever Claude (or any AI design tool) generates from that brief, this
directory provides the production-ready building blocks the brief
called out as **standalone deliverables** — so you don't have to
hand-correct the generated code for the parts that matter most.

## What's here

```
frontend/
├── README.md                       (you are here)
├── components/
│   └── HeroTerminal.tsx            The hero animation from §5 Section 1.
└── tailwind.tokens.ts              Design tokens from §3 + §4, as a
                                    Tailwind theme extension.
```

## Quick start: drop the hero into a Next.js app

```bash
# In your generated project:
npm i framer-motion
```

Copy `components/HeroTerminal.tsx` into your project's `components/`
directory.

In your hero section:

```tsx
import { HeroTerminal } from "@/components/HeroTerminal";

export default function Hero() {
  return (
    <section className="relative min-h-screen flex items-center px-8 lg:px-16 bg-[#0A0A0B]">
      <div className="grid grid-cols-1 lg:grid-cols-[1.1fr_1fr] gap-16 max-w-[1200px] mx-auto w-full">
        <div>
          <p className="text-xs font-medium tracking-[0.18em] text-[#7C5CFF] uppercase">
            AI THAT FIXES YOUR DATA PIPELINES
          </p>
          <h1 className="mt-6 text-[64px] lg:text-[80px] font-bold leading-[1.05] tracking-[-0.02em] text-[#F5F5F7]">
            From OOM error to merged PR
            <br />
            in <span className="text-[#7C5CFF]">90 seconds</span>.
          </h1>
          <p className="mt-8 text-xl text-[#A1A1AA] max-w-[560px]">
            Veyra detects, explains, patches, and ships fixes to your Spark
            and Databricks jobs — with your approval, on your repo, with
            your team's incident history as memory.
          </p>
          <div className="mt-10 flex gap-4">
            <button className="px-[18px] py-3 rounded-lg bg-[#7C5CFF] text-white font-medium hover:brightness-110 transition">
              Get started
            </button>
            <button className="px-[18px] py-3 rounded-lg border border-[#26262E] text-[#F5F5F7] hover:bg-[#111114] transition">
              Watch the 90-second demo
            </button>
          </div>
        </div>
        <div className="lg:justify-self-end">
          <HeroTerminal />
        </div>
      </div>
    </section>
  );
}
```

## Tailwind tokens

Merge `tailwind.tokens.ts` into your project's `tailwind.config.ts`
under `theme.extend`. The component file uses literal hex values so it
works without this step, but once tokens are wired the rest of the
landing page stays consistent.

## Design philosophy reminder

From `frontend-design.md` §12 — the page is doing its job if a YC
partner clicking it during interview prep stops on the hero, watches
the loop play once, and thinks *"these people get it."* Every
component in this directory is built to that bar.

If a generated section doesn't meet it: regenerate it. Don't ship the
near-miss.
