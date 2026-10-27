export const colors = {
  primary: '#E61A42',
  primaryHover: '#CC0D38',
  logoOrange: '#F5A51C',
  textPrimary: '#0D1626',
  textSecondary: '#475569',
  textMuted: '#94A3B8',
  border: '#E5E7EB',
  statusProgress: '#10B981',
  statusOverdue: '#EF4444',
  statusPending: '#F59E0B',
  avatarPalette: [
    { bg: '#FDE2E4', fg: '#9C1933' },
    { bg: '#E2E8F0', fg: '#1F2937' },
    { bg: '#FEF3C7', fg: '#92400E' },
    { bg: '#D1FAE5', fg: '#065F46' },
    { bg: '#DBEAFE', fg: '#1E40AF' },
    { bg: '#E9D8FD', fg: '#553C9A' },
    { bg: '#FCE7F3', fg: '#9D174D' },
    { bg: '#CFFAFE', fg: '#155E75' },
  ],
} as const;

export const layout = {
  sidebarWidth: 240,
  sidebarCollapsedWidth: 64,
  aiDrawerWidth: 380,
  pageGutter: 32,
} as const;
