import { useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { Mail, Lock, Eye, EyeOff, Sparkles, KeyRound } from 'lucide-react';
import toast from 'react-hot-toast';
import { useAuthStore } from '@/stores/authStore';
import { login, changePassword } from '@/services/api';
import { getDefaultLandingPath } from '@/utils/landing';

// Helper to extract error message from API response
const getErrorMessage = (error: any, fallback: string): string => {
  const detail = error?.response?.data?.detail;
  if (!detail) return fallback;
  if (typeof detail === 'string') return detail;
  // Pydantic validation error returns array of {type, loc, msg, input, ctx}
  if (Array.isArray(detail) && detail.length > 0) {
    return detail[0]?.msg || fallback;
  }
  return fallback;
};

export default function LoginPage() {
  const [showPassword, setShowPassword] = useState(false);
  const [showNewPassword, setShowNewPassword] = useState(false);
  const [loading, setLoading] = useState(false);
  const [form, setForm] = useState({ email: '', password: '' });
  const [mustChangePassword, setMustChangePassword] = useState(false);
  const [newPasswordForm, setNewPasswordForm] = useState({ newPassword: '', confirmPassword: '' });
  const { setUser, user } = useAuthStore();
  const navigate = useNavigate();

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setLoading(true);

    try {
      const loggedInUser = await login(form.email, form.password);
      // Cookie is set by backend, login returns the User directly
      setUser(loggedInUser);

      // Check if user must change password
      if (loggedInUser.must_change_password) {
        setMustChangePassword(true);
        toast('Необходимо сменить пароль', { icon: '🔐' });
      } else {
        toast.success('С возвращением!');
        navigate(getDefaultLandingPath(loggedInUser));
      }
    } catch (error: any) {
      toast.error(getErrorMessage(error, 'Ошибка авторизации'));
    } finally {
      setLoading(false);
    }
  };

  const handleChangePassword = async (e: React.FormEvent) => {
    e.preventDefault();

    if (newPasswordForm.newPassword !== newPasswordForm.confirmPassword) {
      toast.error('Пароли не совпадают');
      return;
    }

    if (newPasswordForm.newPassword.length < 8) {
      toast.error('Пароль должен быть минимум 8 символов');
      return;
    }

    setLoading(true);
    try {
      await changePassword(form.password, newPasswordForm.newPassword);
      // Update user state to remove must_change_password flag
      if (user) {
        setUser({ ...user, must_change_password: false });
      }
      toast.success('Пароль успешно изменён!');
      navigate(getDefaultLandingPath(user));
    } catch (error: any) {
      toast.error(getErrorMessage(error, 'Ошибка смены пароля'));
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="min-h-screen flex items-center justify-center p-4 bg-dark-900">
      <div className="w-full max-w-md">
        <div className="border border-white/[0.06] bg-white/[0.02] rounded-2xl p-8">
          <div className="text-center mb-8">
            <div className="inline-flex items-center justify-center w-14 h-14 rounded-2xl bg-accent-500 mb-4">
              <Sparkles className="w-7 h-7 text-white" />
            </div>
            <h1 className="text-3xl font-bold text-dark-100 mb-2">
              Чат Аналитика
            </h1>
            <p className="text-dark-400">
              Войдите в систему
            </p>
          </div>

          {!mustChangePassword ? (
            /* Login Form */
            <>
              <form onSubmit={handleSubmit} className="space-y-5">
                <div className="relative group">
                  <Mail className="absolute left-4 top-1/2 -translate-y-1/2 w-5 h-5 text-dark-400 group-focus-within:text-accent-400 transition-colors" />
                  <input
                    type="email"
                    placeholder="Email адрес"
                    value={form.email}
                    onChange={(e) => setForm({ ...form, email: e.target.value })}
                    required
                    className="w-full input-premium rounded-xl py-3.5 pl-12 pr-4 text-dark-100 placeholder-dark-500 focus:outline-none"
                  />
                </div>

                <div className="relative group">
                  <Lock className="absolute left-4 top-1/2 -translate-y-1/2 w-5 h-5 text-dark-400 group-focus-within:text-accent-400 transition-colors" />
                  <input
                    type={showPassword ? 'text' : 'password'}
                    placeholder="Пароль"
                    value={form.password}
                    onChange={(e) => setForm({ ...form, password: e.target.value })}
                    required
                    className="w-full input-premium rounded-xl py-3.5 pl-12 pr-12 text-dark-100 placeholder-dark-500 focus:outline-none"
                  />
                  <button
                    type="button"
                    onClick={() => setShowPassword(!showPassword)}
                    className="absolute right-4 top-1/2 -translate-y-1/2 text-dark-400 hover:text-dark-200"
                  >
                    {showPassword ? <EyeOff className="w-5 h-5" /> : <Eye className="w-5 h-5" />}
                  </button>
                </div>

                <button
                  disabled={loading}
                  type="submit"
                  className="w-full bg-accent-500 hover:bg-accent-600 text-white font-semibold py-3.5 rounded-xl transition-colors duration-200 disabled:opacity-50"
                >
                  {loading ? (
                    <span className="flex items-center justify-center gap-2">
                      <div className="w-5 h-5 border-2 border-white border-t-transparent rounded-full animate-spin" />
                      Загрузка...
                    </span>
                  ) : (
                    'Войти'
                  )}
                </button>
              </form>

              <div className="mt-6 text-center">
                <p className="text-dark-500 text-sm">
                  Нет аккаунта? Обратитесь к администратору
                </p>
              </div>
            </>
          ) : (
            /* Password Change Form */
            <>
              <div className="text-center mb-6">
                <div className="inline-flex items-center justify-center w-12 h-12 rounded-xl bg-yellow-500/20 mb-3">
                  <KeyRound className="w-6 h-6 text-yellow-400" />
                </div>
                <h2 className="text-xl font-semibold text-dark-100 mb-1">Смена пароля</h2>
                <p className="text-dark-400 text-sm">
                  Администратор сбросил ваш пароль. Установите новый пароль для продолжения.
                </p>
              </div>

              <form onSubmit={handleChangePassword} className="space-y-5">
                <div className="relative group">
                  <Lock className="absolute left-4 top-1/2 -translate-y-1/2 w-5 h-5 text-dark-400 group-focus-within:text-accent-400 transition-colors" />
                  <input
                    type={showNewPassword ? 'text' : 'password'}
                    placeholder="Новый пароль"
                    value={newPasswordForm.newPassword}
                    onChange={(e) => setNewPasswordForm({ ...newPasswordForm, newPassword: e.target.value })}
                    required
                    minLength={8}
                    className="w-full input-premium rounded-xl py-3.5 pl-12 pr-12 text-dark-100 placeholder-dark-500 focus:outline-none"
                  />
                  <button
                    type="button"
                    onClick={() => setShowNewPassword(!showNewPassword)}
                    className="absolute right-4 top-1/2 -translate-y-1/2 text-dark-400 hover:text-dark-200"
                  >
                    {showNewPassword ? <EyeOff className="w-5 h-5" /> : <Eye className="w-5 h-5" />}
                  </button>
                </div>

                <div className="relative group">
                  <Lock className="absolute left-4 top-1/2 -translate-y-1/2 w-5 h-5 text-dark-400 group-focus-within:text-accent-400 transition-colors" />
                  <input
                    type={showNewPassword ? 'text' : 'password'}
                    placeholder="Подтвердите пароль"
                    value={newPasswordForm.confirmPassword}
                    onChange={(e) => setNewPasswordForm({ ...newPasswordForm, confirmPassword: e.target.value })}
                    required
                    minLength={8}
                    className="w-full input-premium rounded-xl py-3.5 pl-12 pr-4 text-dark-100 placeholder-dark-500 focus:outline-none"
                  />
                </div>

                <button
                  disabled={loading || newPasswordForm.newPassword !== newPasswordForm.confirmPassword}
                  type="submit"
                  className="w-full bg-accent-500 hover:bg-accent-600 text-white font-semibold py-3.5 rounded-xl transition-colors duration-200 disabled:opacity-50"
                >
                  {loading ? (
                    <span className="flex items-center justify-center gap-2">
                      <div className="w-5 h-5 border-2 border-white border-t-transparent rounded-full animate-spin" />
                      Сохранение...
                    </span>
                  ) : (
                    'Сохранить новый пароль'
                  )}
                </button>
              </form>

              {newPasswordForm.newPassword && newPasswordForm.confirmPassword && newPasswordForm.newPassword !== newPasswordForm.confirmPassword && (
                <p className="mt-3 text-red-400 text-sm text-center">Пароли не совпадают</p>
              )}
            </>
          )}
        </div>
      </div>
    </div>
  );
}
