import type { Config } from "tailwindcss";

const config: Config = {
  content: [
    "./app/**/*.{js,ts,jsx,tsx,mdx}",
    "./components/**/*.{js,ts,jsx,tsx,mdx}",
    "./lib/**/*.{js,ts,jsx,tsx,mdx}",
  ],
  theme: {
    extend: {
      colors: {
        bg: {
          base: "var(--bg-base)",
          rail: "var(--bg-rail)",
          thread: "var(--bg-thread)",
          raised: "var(--bg-raised)",
          emph: "var(--bg-emph)",
          input: "var(--bg-input)",
        },
        line: {
          DEFAULT: "var(--line)",
          strong: "var(--line-strong)",
          hi: "var(--line-hi)",
        },
        text: {
          DEFAULT: "var(--text)",
          2: "var(--text-2)",
          3: "var(--text-3)",
          4: "var(--text-4)",
        },
        accent: {
          fg: "var(--accent-fg)",
          solid: "var(--accent-solid)",
          soft: "var(--accent-soft)",
          ring: "var(--accent-ring)",
          glow: "var(--accent-glow)",
        },
        ok: {
          fg: "var(--ok-fg)",
          bg: "var(--ok-bg)",
          bd: "var(--ok-bd)",
        },
        err: {
          fg: "var(--err-fg)",
          bg: "var(--err-bg)",
          bd: "var(--err-bd)",
        },
        warn: {
          fg: "var(--warn-fg)",
          bg: "var(--warn-bg)",
          bd: "var(--warn-bd)",
        },
      },
      fontFamily: {
        sans: ["var(--font-sans)", "Inter", "ui-sans-serif", "system-ui", "sans-serif"],
        mono: ["var(--font-mono)", "JetBrains Mono", "ui-monospace", "monospace"],
      },
      borderRadius: {
        sm: "8px",
        md: "10px",
        lg: "14px",
        xl: "18px",
      },
      boxShadow: {
        soft: "0 1px 0 rgba(255,255,255,.04) inset, 0 12px 32px -16px rgba(0,0,0,.6)",
        pop: "0 24px 48px -16px rgba(0,0,0,.6)",
      },
      keyframes: {
        "om-pulse": {
          "0%, 100%": { opacity: "0.3" },
          "50%": { opacity: "1" },
        },
        "om-blink": {
          "50%": { opacity: "0" },
        },
        "om-step-pulse": {
          "0%": { boxShadow: "0 0 0 0 var(--accent-ring)" },
          "70%": { boxShadow: "0 0 0 6px transparent" },
          "100%": { boxShadow: "0 0 0 0 transparent" },
        },
      },
      animation: {
        "om-pulse": "om-pulse 1.2s infinite",
        "om-blink": "om-blink 1s step-end infinite",
        "om-step-pulse": "om-step-pulse 1.5s infinite",
      },
    },
  },
  plugins: [],
};

export default config;
