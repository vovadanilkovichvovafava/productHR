import { Sun, Moon } from 'lucide-react';
import { useTheme } from '@/hooks/useTheme';

export default function ThemeToggle() {
  const { theme, toggleTheme } = useTheme();

  return (
    <button
      onClick={toggleTheme}
      className="w-full flex items-center gap-3 px-4 py-3 rounded-xl text-dark-300 hover:text-amber-400 hover:bg-amber-500/10 transition-all duration-200"
      aria-label={theme === 'dark' ? 'Переключить на светлую тему' : 'Переключить на тёмную тему'}
    >
      {theme === 'dark' ? (
        <Sun className="w-5 h-5" aria-hidden="true" />
      ) : (
        <Moon className="w-5 h-5" aria-hidden="true" />
      )}
      <span className="font-medium">
        {theme === 'dark' ? 'Светлая тема' : 'Тёмная тема'}
      </span>
    </button>
  );
}
