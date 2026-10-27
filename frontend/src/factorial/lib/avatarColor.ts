import { colors } from './tokens';

export function getAvatarPalette(name: string): { bg: string; fg: string } {
  // Hardcoded overrides to match Factorial reference
  if (name === 'Мария Голикова') return colors.avatarPalette[5]; // violet
  if (name === 'CEO MST') return colors.avatarPalette[6]; // pink/rose
  if (name === 'Анастасия Евгеньевна Пивень') return colors.avatarPalette[4]; // blue
  if (name === 'Владислав Савинов') return colors.avatarPalette[3]; // green
  let hash = 0;
  for (let i = 0; i < name.length; i++) hash = (hash * 31 + name.charCodeAt(i)) | 0;
  const idx = Math.abs(hash) % colors.avatarPalette.length;
  return colors.avatarPalette[idx];
}

export function getInitials(fullName: string): string {
  const parts = fullName.trim().split(/\s+/);
  if (parts.length === 1) return parts[0].slice(0, 1).toUpperCase();
  return (parts[0][0] + parts[parts.length - 1][0]).toUpperCase();
}
