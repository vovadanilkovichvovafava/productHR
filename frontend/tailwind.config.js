/** @type {import('tailwindcss').Config} */
export default {
  content: [
    "./index.html",
    "./src/**/*.{js,ts,jsx,tsx}",
  ],
  // dark: классы триггерятся по data-theme="dark" на <html>, который
  // ставит useTheme. Без этого dark:bg-... работает только по
  // prefers-color-scheme — модалки в проектах оставались белыми.
  darkMode: ['variant', '&:where([data-theme="dark"], [data-theme="dark"] *)'],
  theme: {
    extend: {
      colors: {
        /* ── Factorial 1:1 port tokens (уникальные ключи; визуально под .factorial-root) ── */
        'app-bg': '#F4F4F5',
        'sidebar-hover': 'rgba(5,38,87,0.04)',
        'sidebar-active': 'rgba(5,38,87,0.06)',
        'sidebar-muted': '#6B7280',
        primary: { DEFAULT: '#E61A42', hover: '#CC0D38', focus: '#B30930' },
        'logo-orange': '#F5A51C',
        'text-primary': '#0D1626',
        'text-secondary': '#475569',
        'text-muted': '#94A3B8',
        'status-active-bg': '#F3F4F6',
        'status-active-text': '#374151',
        'status-progress': '#10B981',
        'status-overdue': '#EF4444',
        'status-pending': '#F59E0B',
        'card-translucent': 'rgba(255,255,255,0.6)',
        'card-border-soft': 'rgba(15,46,87,0.1)',
        border: { DEFAULT: '#E5E7EB', hover: '#D1D5DB' },
        /* ── существующие токены HR-bot ── */
        dark: {
          50: 'var(--tw-dark-50)',
          100: 'var(--tw-dark-100)',
          200: 'var(--tw-dark-200)',
          300: 'var(--tw-dark-300)',
          400: 'var(--tw-dark-400)',
          500: 'var(--tw-dark-500)',
          600: 'var(--tw-dark-600)',
          700: 'var(--tw-dark-700)',
          800: 'var(--tw-dark-800)',
          900: 'var(--tw-dark-900)',
          950: 'var(--tw-dark-950)',
        },
        accent: {
          50: '#f0f9ff',
          100: '#e0f2fe',
          200: '#b9e6fe',
          300: '#7cd4fd',
          400: '#36bffa',
          500: '#0ca5eb',
          600: '#0084c9',
          700: '#0169a3',
          800: '#065986',
          900: '#0b4a6f',
          950: '#072f4a',
        },
        /* HR candidate workspace tokens — additive (не заменяет существующие). */
        'hf-main': {
          50: 'var(--hf-main-50)', 100: 'var(--hf-main-100)', 200: 'var(--hf-main-200)', 300: 'var(--hf-main-300)',
          400: 'var(--hf-main-400)', 500: 'var(--hf-main-500)', 600: 'var(--hf-main-600)', 700: 'var(--hf-main-700)',
          750: 'var(--hf-main-750)', 800: 'var(--hf-main-800)', 900: 'var(--hf-main-900)',
        },
        'hf-cyan': {
          50: 'var(--hf-cyan-50)', 100: 'var(--hf-cyan-100)', 200: 'var(--hf-cyan-200)', 300: 'var(--hf-cyan-300)',
          400: 'var(--hf-cyan-400)', 500: 'var(--hf-cyan-500)', 600: 'var(--hf-cyan-600)', 700: 'var(--hf-cyan-700)',
          800: 'var(--hf-cyan-800)', 900: 'var(--hf-cyan-900)',
        },
        'hf-green': {
          50: 'var(--hf-green-50)', 100: 'var(--hf-green-100)', 200: 'var(--hf-green-200)', 300: 'var(--hf-green-300)',
          400: 'var(--hf-green-400)', 500: 'var(--hf-green-500)', 600: 'var(--hf-green-600)', 700: 'var(--hf-green-700)',
          800: 'var(--hf-green-800)', 900: 'var(--hf-green-900)',
        },
        'hf-red': {
          50: 'var(--hf-red-50)', 100: 'var(--hf-red-100)', 200: 'var(--hf-red-200)', 300: 'var(--hf-red-300)',
          400: 'var(--hf-red-400)', 500: 'var(--hf-red-500)', 600: 'var(--hf-red-600)', 700: 'var(--hf-red-700)',
          800: 'var(--hf-red-800)', 900: 'var(--hf-red-900)',
        },
        'hf-yellow': {
          300: 'var(--hf-yellow-300)', 400: 'var(--hf-yellow-400)', 500: 'var(--hf-yellow-500)', 600: 'var(--hf-yellow-600)',
        },
        'hf-pistou': { 500: 'var(--hf-pistou-green-500)', 600: 'var(--hf-pistou-green-600)' },
        'hf-sidebar': 'var(--hf-sidebar-bg)',
        'hf-fab': 'var(--hf-fab-bg)',
        'hf-body': 'var(--hf-workspace-bg)',
      },
      fontSize: {
        /* Factorial scale (namespaced, чтобы не переопределять дефолт Tailwind на хосте) */
        'fx-xs': ['12px', '1.4'], 'fx-sm': ['13px', '1.5'], 'fx-base': ['14px', '1.5'], 'fx-lg': ['16px', '1.5'],
        'fx-xl': ['18px', '1.4'], 'fx-2xl': ['20px', '1.3'], 'fx-3xl': ['24px', '1.25'], 'fx-4xl': ['32px', '1.2'],
        'hf-4xs': ['11px', '14px'],
        'hf-3xs': ['12px', '16px'],
        'hf-xxs': ['14px', '20px'],
        'hf-xs':  ['15px', '24px'],
        'hf-s':   ['16px', '24px'],
        'hf-m':   ['18px', '24px'],
        'hf-l':   ['20px', '28px'],
        'hf-xl':  ['22px', '28px'],
        'hf-2xl': ['24px', '28px'],
        'hf-5xl': ['30px', '40px'],
      },
      spacing: {
        'hf-xxs': '2px', 'hf-xs': '4px', 'hf-s': '8px', 'hf-m': '12px',
        'hf-l': '16px', 'hf-xl': '20px', 'hf-xxl': '24px',
        'hf-3xl': '32px', 'hf-4xl': '40px', 'hf-5xl': '48px',
      },
      borderRadius: {
        /* Factorial radii: card/pill уникальны (as-is); sm/md/lg под fx- (не трогаем дефолт) */
        'fx-sm': '6px', 'fx-md': '8px', 'fx-lg': '10px', 'card': '16px', 'pill': '9999px',
        'hf-xxs': '2px', 'hf-xs': '4px', 'hf-s': '8px', 'hf-m': '12px',
        'hf-l': '16px', 'hf-xl': '20px', 'hf-xxl': '24px',
        'hf-pill': '999px',
      },
      boxShadow: {
        'card':     '0 2px 20px rgba(13,22,38,0.04)',
        'card-hover': '0 4px 24px rgba(13,22,38,0.08)',
        'drawer':   '-2px 0 16px rgba(0,0,0,0.04)',
        'hf-card':     'var(--hf-shadow-card)',
        'hf-card-lg':  'var(--hf-shadow-card-lg)',
        'hf-dropdown': 'var(--hf-shadow-dropdown)',
      },
      backgroundImage: {
        'fx-love-banner': 'linear-gradient(to right, rgba(245,165,28,0.3), rgba(229,25,67,0.3), rgba(85,150,246,0.3))',
        'fx-logo-gradient': 'linear-gradient(135deg, #F5A51C 0%, #E61A42 100%)',
      },
      fontFamily: {
        'fx-sans': ['Inter', '-apple-system', 'BlinkMacSystemFont', 'Segoe UI', 'system-ui', 'sans-serif'],
        'hf-body': ['var(--hf-font-body)'],
      },
      backdropBlur: {
        xs: '2px',
      },
      animation: {
        'fade-in': 'fadeIn 0.3s ease-out',
        'slide-up': 'slideUp 0.3s ease-out',
        'slide-in': 'slideIn 0.3s ease-out',
        'float': 'float 6s ease-in-out infinite',
        'float-delayed': 'float 8s ease-in-out infinite',
        'float-slow': 'float 10s ease-in-out infinite',
        'pulse-glow': 'pulseGlow 4s ease-in-out infinite',
        'gradient-shift': 'gradientShift 15s ease infinite',
        'shimmer': 'shimmer 2s linear infinite',
        'orbit': 'orbit 20s linear infinite',
        'orbit-reverse': 'orbit 25s linear infinite reverse',
        'pulse-subtle': 'pulseSubtle 2s ease-in-out infinite',
      },
      keyframes: {
        fadeIn: {
          '0%': { opacity: '0' },
          '100%': { opacity: '1' },
        },
        slideUp: {
          '0%': { opacity: '0', transform: 'translateY(10px)' },
          '100%': { opacity: '1', transform: 'translateY(0)' },
        },
        slideIn: {
          '0%': { opacity: '0', transform: 'translateX(-10px)' },
          '100%': { opacity: '1', transform: 'translateX(0)' },
        },
        float: {
          '0%, 100%': { transform: 'translateY(0) translateX(0)' },
          '25%': { transform: 'translateY(-20px) translateX(10px)' },
          '50%': { transform: 'translateY(-10px) translateX(-10px)' },
          '75%': { transform: 'translateY(-30px) translateX(5px)' },
        },
        pulseGlow: {
          '0%, 100%': { opacity: '0.4', transform: 'scale(1)' },
          '50%': { opacity: '0.8', transform: 'scale(1.05)' },
        },
        gradientShift: {
          '0%': { backgroundPosition: '0% 50%' },
          '50%': { backgroundPosition: '100% 50%' },
          '100%': { backgroundPosition: '0% 50%' },
        },
        shimmer: {
          '0%': { backgroundPosition: '-200% 0' },
          '100%': { backgroundPosition: '200% 0' },
        },
        orbit: {
          '0%': { transform: 'rotate(0deg) translateX(150px) rotate(0deg)' },
          '100%': { transform: 'rotate(360deg) translateX(150px) rotate(-360deg)' },
        },
        pulseSubtle: {
          '0%, 100%': { boxShadow: '0 0 8px var(--hf-accent-border-30)' },
          '50%': { boxShadow: '0 0 20px var(--hf-accent-bg-30)' },
        },
      },
    },
  },
  plugins: [],
}
