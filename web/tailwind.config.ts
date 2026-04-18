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
        surface: {
          base: "var(--color-surface-base)",
          raised: "var(--color-surface-raised)",
          strong: "var(--color-surface-strong)",
          emphasis: "var(--color-surface-emphasis)",
        },
        content: {
          primary: "var(--color-text-primary)",
          secondary: "var(--color-text-secondary)",
          tertiary: "var(--color-text-tertiary)",
        },
        stroke: {
          subtle: "var(--color-border-subtle)",
          strong: "var(--color-border-strong)",
          focus: "var(--color-border-focus)",
        },
        interactive: {
          hover: "var(--color-interactive-hover)",
          active: "var(--color-interactive-active)",
          border: "var(--color-interactive-border)",
        },
        action: {
          DEFAULT: "var(--color-action-bg)",
          foreground: "var(--color-action-fg)",
          muted: "var(--color-action-muted)",
        },
        success: {
          fg: "var(--color-success-fg)",
          bg: "var(--color-success-bg)",
          border: "var(--color-success-border)",
        },
        error: {
          fg: "var(--color-error-fg)",
          bg: "var(--color-error-bg)",
          border: "var(--color-error-border)",
        },
        warning: {
          fg: "var(--color-warning-fg)",
          bg: "var(--color-warning-bg)",
          border: "var(--color-warning-border)",
        },
      },
      boxShadow: {
        shell: "var(--shadow-panel)",
      },
      fontFamily: {
        sans: ["var(--font-sans)"],
        mono: ["var(--font-mono)"],
      },
    },
  },
  plugins: [],
};

export default config;
