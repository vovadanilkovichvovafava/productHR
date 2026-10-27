/**
 * Unified date formatting utilities for the HR-bot application.
 * 
 * This module provides consistent date formatting across all components,
 * eliminating code duplication and ensuring consistent locale handling.
 */

export type DateFormatType = 'short' | 'medium' | 'long' | 'time' | 'relative' | 'datetime';

/**
 * Backend отдаёт datetime как НАИВНЫЙ UTC ISO-стрингой БЕЗ суффикса Z/offset
 * (Pydantic .isoformat() на naive datetime из TIMESTAMP WITHOUT TIME ZONE
 * колонок). `new Date("2026-07-01T08:56:00")` без явного офсета браузер
 * парсит как ЛОКАЛЬНОЕ время — из-за этого смена этапа в 11:56 по Москве
 * (08:56 UTC) отображалась как 08:56. Если офсета нет — трактуем строку как
 * UTC, дописывая Z перед парсингом.
 */
export function parseServerDate(dateString: string | Date): Date {
  if (dateString instanceof Date) return dateString;
  const hasTz = /Z$|[+-]\d{2}:?\d{2}$/.test(dateString);
  return new Date(hasTz ? dateString : `${dateString}Z`);
}

/**
 * Format a date string according to the specified format type.
 * 
 * @param dateString - ISO date string or undefined
 * @param format - Format type (default: 'medium')
 * @returns Formatted date string or empty string if invalid
 * 
 * @example
 * formatDate('2024-01-15T10:30:00Z', 'relative') // '10:30' (today) or 'Вчера' or '15 янв'
 * formatDate('2024-01-15T10:30:00Z', 'short') // '15 янв'
 * formatDate('2024-01-15T10:30:00Z', 'medium') // '15 янв 2024'
 * formatDate('2024-01-15T10:30:00Z', 'long') // '15 января 2024, 10:30'
 * formatDate('2024-01-15T10:30:00Z', 'time') // '10:30'
 * formatDate('2024-01-15T10:30:00Z', 'datetime') // '15.01.2024 10:30'
 */
export function formatDate(
  dateString: string | Date | undefined | null,
  format: DateFormatType = 'medium'
): string {
  if (!dateString) return '';
  
  try {
    const date = parseServerDate(dateString);
    
    // Check for invalid date
    if (isNaN(date.getTime())) return '';
    
    const now = new Date();
    const diff = now.getTime() - date.getTime();
    const days = Math.floor(diff / (1000 * 60 * 60 * 24));

    switch (format) {
      case 'relative':
        // Smart relative formatting for chat lists, activity feeds
        if (days === 0) {
          return date.toLocaleTimeString('ru-RU', { 
            hour: '2-digit', 
            minute: '2-digit' 
          });
        }
        if (days === 1) return 'Вчера';
        if (days < 7) {
          return date.toLocaleDateString('ru-RU', { weekday: 'short' });
        }
        return date.toLocaleDateString('ru-RU', { 
          day: '2-digit', 
          month: '2-digit' 
        });
      
      case 'short':
        // Short format: "15 янв"
        return date.toLocaleDateString('ru-RU', { 
          day: 'numeric', 
          month: 'short' 
        });
      
      case 'medium':
        // Medium format: "15 янв 2024"
        return date.toLocaleDateString('ru-RU', { 
          day: 'numeric', 
          month: 'short', 
          year: 'numeric' 
        });
      
      case 'long':
        // Long format: "15 января 2024, 10:30"
        return date.toLocaleDateString('ru-RU', {
          year: 'numeric',
          month: 'long',
          day: 'numeric',
          hour: '2-digit',
          minute: '2-digit'
        });
      
      case 'time':
        // Time only: "10:30"
        return date.toLocaleTimeString('ru-RU', { 
          hour: '2-digit', 
          minute: '2-digit' 
        });
      
      case 'datetime':
        // Date and time: "15.01.2024 10:30"
        return date.toLocaleDateString('ru-RU', {
          day: '2-digit',
          month: '2-digit',
          year: 'numeric',
          hour: '2-digit',
          minute: '2-digit'
        });
      
      default:
        return date.toLocaleDateString('ru-RU');
    }
  } catch {
    return '';
  }
}

/**
 * Format a date as a relative time string (e.g., "2 часа назад", "вчера").
 * 
 * @param dateString - ISO date string
 * @returns Human-readable relative time
 */
export function formatRelativeTime(dateString: string | Date | undefined | null): string {
  if (!dateString) return '';
  
  try {
    const date = parseServerDate(dateString);
    if (isNaN(date.getTime())) return '';
    
    const now = new Date();
    const diffMs = now.getTime() - date.getTime();
    const diffMinutes = Math.floor(diffMs / (1000 * 60));
    const diffHours = Math.floor(diffMs / (1000 * 60 * 60));
    const diffDays = Math.floor(diffMs / (1000 * 60 * 60 * 24));
    
    if (diffMinutes < 1) return 'только что';
    if (diffMinutes < 60) return `${diffMinutes} мин. назад`;
    if (diffHours < 24) return `${diffHours} ч. назад`;
    if (diffDays === 1) return 'вчера';
    if (diffDays < 7) return `${diffDays} дн. назад`;
    
    return formatDate(date, 'medium');
  } catch {
    return '';
  }
}

/**
 * Check if a date is today.
 */
export function isToday(dateString: string | Date | undefined | null): boolean {
  if (!dateString) return false;
  
  try {
    const date = parseServerDate(dateString);
    const today = new Date();
    
    return (
      date.getDate() === today.getDate() &&
      date.getMonth() === today.getMonth() &&
      date.getFullYear() === today.getFullYear()
    );
  } catch {
    return false;
  }
}

/**
 * Check if a date is in the past.
 */
export function isPast(dateString: string | Date | undefined | null): boolean {
  if (!dateString) return false;

  try {
    const date = parseServerDate(dateString);
    return date.getTime() < Date.now();
  } catch {
    return false;
  }
}

/**
 * Calculate age in full years from a birth date (YYYY-MM-DD или ISO-строка).
 * Учитывает, наступил ли день рождения в этом году. Используется, чтобы
 * возраст кандидата (extra_data.age) всегда пересчитывался из точной даты
 * рождения (extra_data.birth_date) при её сохранении, а не хранился как
 * отдельное несвязанное число.
 */
export function calculateAge(birthDate: string | undefined | null): number | null {
  if (!birthDate) return null;
  const birth = new Date(birthDate);
  if (isNaN(birth.getTime())) return null;
  const now = new Date();
  let age = now.getFullYear() - birth.getFullYear();
  const monthDiff = now.getMonth() - birth.getMonth();
  if (monthDiff < 0 || (monthDiff === 0 && now.getDate() < birth.getDate())) {
    age -= 1;
  }
  return age >= 0 ? age : null;
}
