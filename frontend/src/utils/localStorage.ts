/**
 * Shared localStorage utility functions
 *
 * Provides type-safe wrappers for localStorage operations with
 * error handling for cases when localStorage is not available
 * (e.g., private browsing mode, storage quota exceeded).
 */

/**
 * Get a value from localStorage with type safety and error handling.
 *
 * @param key - The localStorage key to retrieve
 * @param defaultValue - Default value to return if key doesn't exist or on error
 * @returns The parsed value from localStorage or the default value
 *
 * @example
 * ```ts
 * const history = getLocalStorage<string[]>('search_history', []);
 * const settings = getLocalStorage<UserSettings>('user_settings', defaultSettings);
 * ```
 */
export function getLocalStorage<T>(key: string, defaultValue: T): T {
  try {
    const stored = localStorage.getItem(key);
    if (stored === null) {
      return defaultValue;
    }
    return JSON.parse(stored) as T;
  } catch {
    return defaultValue;
  }
}

/**
 * Set a value in localStorage with type safety and error handling.
 *
 * @param key - The localStorage key to set
 * @param value - The value to store (will be JSON stringified)
 *
 * @example
 * ```ts
 * setLocalStorage('search_history', ['query1', 'query2']);
 * setLocalStorage('user_settings', { theme: 'dark' });
 * ```
 */
export function setLocalStorage<T>(key: string, value: T): void {
  try {
    localStorage.setItem(key, JSON.stringify(value));
  } catch (error) {
    console.warn(`Failed to save to localStorage (key: ${key}):`, error);
  }
}

/**
 * Remove a key from localStorage with error handling.
 *
 * @param key - The localStorage key to remove
 *
 * @example
 * ```ts
 * removeLocalStorage('search_history');
 * ```
 */
export function removeLocalStorage(key: string): void {
  try {
    localStorage.removeItem(key);
  } catch {
    // Ignore errors when removing
  }
}
