/** @type {import('tailwindcss').Config} */
export default {
  darkMode: ["class"],
  content: [
    "./index.html",
    "./src/**/*.{js,ts,jsx,tsx}",
  ],
  theme: {
    extend: {
      // Professional Calm Color System (UX-DR9)
      colors: {
        // Primary palette
        primary: {
          DEFAULT: "#3B82F6", // blue-500
          50: "#EFF6FF",
          100: "#DBEAFE",
          200: "#BFDBFE",
          300: "#93C5FD",
          400: "#60A5FA",
          500: "#3B82F6",
          600: "#2563EB",
          700: "#1D4ED8",
          800: "#1E40AF",
          900: "#1E3A8A",
          foreground: "#FFFFFF", // white text on primary background
        },
        // Surface colors
        surface: {
          DEFAULT: "#F8FAFC", // slate-50
          50: "#F8FAFC",
          100: "#F1F5F9",
          200: "#E2E8F0",
          300: "#CBD5E1",
          400: "#94A3B8",
          500: "#64748B",
          600: "#475569",
          700: "#334155",
          800: "#1E293B",
          900: "#0F172A",
        },
        // Secondary palette (for Badge secondary variant)
        secondary: {
          DEFAULT: "#F1F5F9", // slate-100
          foreground: "#0F172A", // slate-900 text on secondary
        },
        // Destructive palette (for Badge destructive variant)
        destructive: {
          DEFAULT: "#EF4444", // red-500
          foreground: "#FFFFFF", // white text on destructive
        },
        // Foreground (default text color)
        foreground: {
          DEFAULT: "#0F172A", // slate-900
        },
        // Semantic colors
        success: {
          DEFAULT: "#22C55E", // green-500
          light: "#DCFCE7",
        },
        warning: {
          DEFAULT: "#F59E0B", // amber-500
          light: "#FEF3C7",
        },
        error: {
          DEFAULT: "#EF4444", // red-500
          light: "#FEE2E2",
        },
        info: {
          DEFAULT: "#3B82F6", // blue-500
          light: "#DBEAFE",
        },
        // Agent colors (UX-DR19)
        agent: {
          alice: "#EC4899",  // pink-500
          bob: "#3B82F6",    // blue-500
          mary: "#22C55E",   // green-500
          sarah: "#A855F7",  // purple-500
          jack: "#F97316",   // orange-500
        },
      },
      // Typography (UX-DR10) — System font stack
      fontFamily: {
        sans: [
          "-apple-system",
          "BlinkMacSystemFont",
          '"Segoe UI"',
          "Roboto",
          '"Helvetica Neue"',
          "Arial",
          "sans-serif",
        ],
        mono: [
          "ui-monospace",
          "SFMono-Regular",
          '"SF Mono"',
          "Consolas",
          '"Liberation Mono"',
          "Menlo",
          "monospace",
        ],
      },
      // Border radius matching Shadcn/ui defaults
      borderRadius: {
        lg: "var(--radius)",
        md: "calc(var(--radius) - 2px)",
        sm: "calc(var(--radius) - 4px)",
      },
      // Animations (UX-DR13)
      keyframes: {
        'slide-up': {
          '0%': { transform: 'translateY(10px)', opacity: '0' },
          '100%': { transform: 'translateY(0)', opacity: '1' },
        },
        'bounce-dot': {
          '0%, 80%, 100%': { transform: 'translateY(0)' },
          '40%': { transform: 'translateY(-8px)' },
        },
      },
      animation: {
        'slide-up': 'slide-up 200ms ease-out',
        'bounce-dot': 'bounce-dot 1.4s ease-in-out infinite',
        'bounce-dot-delay-1': 'bounce-dot 1.4s ease-in-out infinite 160ms',
        'bounce-dot-delay-2': 'bounce-dot 1.4s ease-in-out infinite 320ms',
      },
    },
  },
  plugins: [
    require("tailwindcss-animate"),
    require("@tailwindcss/typography")
  ],
}
