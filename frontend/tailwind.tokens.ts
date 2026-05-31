/**
 * Veyra design tokens for Tailwind.
 *
 * Merge into your project's `tailwind.config.ts`:
 *
 *   import { veyraTheme } from "./frontend/tailwind.tokens";
 *
 *   export default {
 *     content: [...],
 *     theme: {
 *       extend: veyraTheme,
 *     },
 *   };
 *
 * The tokens here match the values in `frontend-design.md` §3 (color)
 * and §4 (typography) so the rest of the landing page stays consistent
 * with the brief without re-deriving the palette by hand.
 */

export const veyraTheme = {
  colors: {
    // Layered grays, dark-mode-first. Names mirror the brief.
    bg: {
      0: "#0A0A0B", // Page background
      1: "#111114", // Card / surface backgrounds
      2: "#1A1A20", // Elevated surfaces, code blocks
    },
    border: {
      DEFAULT: "#26262E", // Hairline borders
    },
    text: {
      1: "#F5F5F7", // Primary
      2: "#A1A1AA", // Secondary
      3: "#52525B", // Tertiary / captions
    },
    accent: {
      DEFAULT: "#7C5CFF", // CTAs, hover states, single-color accents
      glow: "rgba(124, 92, 255, 0.20)",
    },
    cyan: "#22D3EE", // "Success" highlights, log timestamps, link hover
    green: "#34D399", // Status pills (resolved, success)
    amber: "#FBBF24", // Status pills (pending approval)
    red: "#F87171", // Status pills (failed)
  },

  fontFamily: {
    // Pair with `next/font` (Next.js) or the relevant Vite font plugin
    // so there's no flash. Mono used for code, run IDs, log lines,
    // error classes — anything code-shaped.
    sans: ["Inter", "Geist Sans", "ui-sans-serif", "system-ui"],
    mono: ["JetBrains Mono", "Geist Mono", "ui-monospace", "monospace"],
  },

  fontSize: {
    // Display scale from §4.
    hero: ["80px", { lineHeight: "1.05", letterSpacing: "-0.02em", fontWeight: "700" }],
    "hero-mobile": ["48px", { lineHeight: "1.08", letterSpacing: "-0.02em", fontWeight: "700" }],
    h2: ["44px", { lineHeight: "1.1", letterSpacing: "-0.015em", fontWeight: "600" }],
    subhead: ["22px", { lineHeight: "1.5", fontWeight: "400" }],
    body: ["17px", { lineHeight: "1.6", fontWeight: "400" }],
    eyebrow: ["12px", { lineHeight: "1.2", letterSpacing: "0.18em", fontWeight: "500" }],
    code: ["14px", { lineHeight: "1.6", fontWeight: "400" }],
  },

  borderRadius: {
    button: "8px",
    card: "16px",
    terminal: "14px",
    pill: "999px",
  },

  boxShadow: {
    // Subtle violet-tinted shadow under the hero terminal and other
    // featured surfaces.
    "violet-glow": "0 30px 80px -20px rgba(124, 92, 255, 0.25)",
    "accent-ring": "0 0 0 6px rgba(124, 92, 255, 0.18)",
  },

  backgroundImage: {
    // The radial hero gradient (centered at top, fading to transparent
    // over ~60% of the viewport).
    "hero-radial":
      "radial-gradient(ellipse 1200px 600px at 50% 0%, rgba(124, 92, 255, 0.08) 0%, transparent 70%)",
    // The CTA section gradient — deeper, centered, behind the watermark.
    "cta-radial":
      "radial-gradient(ellipse 900px 500px at 50% 50%, rgba(124, 92, 255, 0.12) 0%, transparent 75%)",
  },

  letterSpacing: {
    "section-label": "0.18em",
    "tight-display": "-0.02em",
  },
};

export default veyraTheme;
