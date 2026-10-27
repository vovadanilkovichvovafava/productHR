import { useState, useEffect } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import { motion } from 'framer-motion';
import { Mail, Lock, Eye, EyeOff, User, Sparkles, CheckCircle, XCircle, Send, AlertCircle } from 'lucide-react';
import toast from 'react-hot-toast';
import { getErrorDetail } from '@/utils';
import { validateInvitation, acceptInvitation, login, type InvitationValidation } from '@/services/api';
import BackgroundEffects from '@/components/BackgroundEffects';
import { useAuthStore } from '@/stores/authStore';

export default function InvitePage() {
  const { token: inviteToken } = useParams<{ token: string }>();
  const navigate = useNavigate();
  const setUser = useAuthStore((s) => s.setUser);

  const [loading, setLoading] = useState(true);
  const [submitting, setSubmitting] = useState(false);
  const [showPassword, setShowPassword] = useState(false);
  const [invitation, setInvitation] = useState<InvitationValidation | null>(null);
  const [telegramBindUrl, setTelegramBindUrl] = useState<string | null>(null);
  const [registrationComplete, setRegistrationComplete] = useState(false);

  const [form, setForm] = useState({
    email: '',
    name: '',
    password: '',
    confirmPassword: ''
  });

  useEffect(() => {
    if (inviteToken) {
      validateInvitation(inviteToken)
        .then(data => {
          setInvitation(data);
          if (data.email) setForm(f => ({ ...f, email: data.email || '' }));
          if (data.name) setForm(f => ({ ...f, name: data.name || '' }));
        })
        .catch(() => {
          setInvitation({ valid: false, expired: false, used: false, org_role: 'member' });
        })
        .finally(() => setLoading(false));
    }
  }, [inviteToken]);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();

    if (form.password !== form.confirmPassword) {
      toast.error('Пароли не совпадают');
      return;
    }

    if (form.password.length < 8) {
      toast.error('Пароль должен быть не менее 8 символов');
      return;
    }

    setSubmitting(true);

    try {
      const response = await acceptInvitation(inviteToken!, {
        email: form.email,
        name: form.name,
        password: form.password
      });

      setTelegramBindUrl(response.telegram_bind_url || null);
      setRegistrationComplete(true);
      toast.success('Регистрация завершена!');
    } catch (error: any) {
      toast.error(getErrorDetail(error, 'Ошибка регистрации'));
    } finally {
      setSubmitting(false);
    }
  };

  const handleContinue = async () => {
    // After registration, establish the cookie session and land in the Factorial cabinet.
    try {
      const user = await login(form.email, form.password);
      setUser(user);
      navigate('/factorial');
    } catch {
      navigate('/login');
    }
  };

  const roleLabels: Record<string, string> = {
    owner: 'Владелец',
    admin: 'Администратор',
    member: 'Сотрудник'
  };

  if (loading) {
    return (
      <div className="min-h-screen w-full max-w-full flex items-center justify-center p-4 relative overflow-x-hidden">
        <BackgroundEffects />
        <div className="w-8 h-8 border-2 border-accent-500 border-t-transparent rounded-full animate-spin" />
      </div>
    );
  }

  // Registration complete - show Telegram binding option
  if (registrationComplete) {
    return (
      <div className="min-h-screen w-full max-w-full flex items-center justify-center p-4 relative overflow-x-hidden">
        <BackgroundEffects />

        <motion.div
          initial={{ opacity: 0, y: 20, scale: 0.95 }}
          animate={{ opacity: 1, y: 0, scale: 1 }}
          transition={{ duration: 0.5, ease: "easeOut" }}
          className="w-full max-w-md relative z-10"
        >
          <div className="glass rounded-2xl p-8 shadow-2xl relative overflow-hidden">
            <div className="absolute -top-20 -right-20 w-40 h-40 bg-green-500/20 rounded-full blur-3xl" />
            <div className="absolute -bottom-20 -left-20 w-40 h-40 bg-accent-500/10 rounded-full blur-3xl" />

            <div className="text-center mb-6 relative">
              <motion.div
                initial={{ scale: 0 }}
                animate={{ scale: 1 }}
                transition={{ delay: 0.2, type: "spring", stiffness: 200 }}
                className="inline-flex items-center justify-center w-16 h-16 rounded-2xl bg-gradient-to-br from-green-500 to-green-600 mb-4 shadow-lg shadow-green-500/30"
              >
                <CheckCircle className="w-8 h-8 text-white" />
              </motion.div>
              <h1 className="text-2xl font-bold text-white mb-2">
                Регистрация завершена!
              </h1>
              <p className="text-dark-400">
                Добро пожаловать в {invitation?.org_name || 'организацию'}
              </p>
            </div>

            <div className="space-y-4">
              {telegramBindUrl && (
                <div className="p-4 rounded-xl bg-accent-500/10 border border-accent-500/20">
                  <div className="flex items-center gap-3 mb-3">
                    <Send className="w-5 h-5 text-accent-400" />
                    <span className="text-dark-200 font-medium">Подключить Telegram</span>
                  </div>
                  <p className="text-dark-400 text-sm mb-3">
                    Привяжите ваш Telegram аккаунт для получения уведомлений и работы с ботом
                  </p>
                  <a
                    href={telegramBindUrl}
                    target="_blank"
                    rel="noopener noreferrer"
                    className="block w-full text-center py-3 rounded-xl bg-[#0088cc] hover:bg-[#0077b5] text-white font-medium transition-colors"
                  >
                    Открыть Telegram
                  </a>
                </div>
              )}

              <motion.button
                whileHover={{ scale: 1.02 }}
                whileTap={{ scale: 0.98 }}
                onClick={handleContinue}
                className="w-full btn-premium text-white font-semibold py-3.5 rounded-xl transition-all duration-300"
              >
                Продолжить в приложение
              </motion.button>
            </div>
          </div>
        </motion.div>
      </div>
    );
  }

  // Invalid, expired or used invitation
  if (!invitation?.valid) {
    return (
      <div className="min-h-screen w-full max-w-full flex items-center justify-center p-4 relative overflow-x-hidden">
        <BackgroundEffects />

        <motion.div
          initial={{ opacity: 0, y: 20, scale: 0.95 }}
          animate={{ opacity: 1, y: 0, scale: 1 }}
          transition={{ duration: 0.5, ease: "easeOut" }}
          className="w-full max-w-md relative z-10"
        >
          <div className="glass rounded-2xl p-8 shadow-2xl relative overflow-hidden">
            <div className="absolute -top-20 -right-20 w-40 h-40 bg-red-500/20 rounded-full blur-3xl" />

            <div className="text-center relative">
              <motion.div
                initial={{ scale: 0 }}
                animate={{ scale: 1 }}
                transition={{ delay: 0.2, type: "spring", stiffness: 200 }}
                className="inline-flex items-center justify-center w-16 h-16 rounded-2xl bg-gradient-to-br from-red-500 to-red-600 mb-4 shadow-lg shadow-red-500/30"
              >
                <XCircle className="w-8 h-8 text-white" />
              </motion.div>
              <h1 className="text-2xl font-bold text-white mb-2">
                {invitation?.expired ? 'Приглашение истекло' :
                 invitation?.used ? 'Приглашение уже использовано' :
                 'Приглашение не найдено'}
              </h1>
              <p className="text-dark-400 mb-6">
                {invitation?.expired ?
                  'Срок действия этого приглашения истёк. Попросите администратора отправить новое.' :
                 invitation?.used ?
                  'Это приглашение уже было использовано для регистрации.' :
                  'Данная ссылка недействительна. Проверьте правильность ссылки.'}
              </p>
              <button
                onClick={() => navigate('/login')}
                className="text-accent-400 hover:text-accent-300 font-medium transition-colors"
              >
                Перейти к входу
              </button>
            </div>
          </div>
        </motion.div>
      </div>
    );
  }

  // Valid invitation - show registration form
  return (
    <div className="min-h-screen w-full max-w-full flex items-center justify-center p-4 relative overflow-x-hidden">
      <BackgroundEffects />

      <motion.div
        initial={{ opacity: 0, y: 20, scale: 0.95 }}
        animate={{ opacity: 1, y: 0, scale: 1 }}
        transition={{ duration: 0.5, ease: "easeOut" }}
        className="w-full max-w-md relative z-10"
      >
        <div className="glass rounded-2xl p-8 shadow-2xl relative overflow-hidden">
          <div className="absolute -top-20 -right-20 w-40 h-40 bg-accent-500/20 rounded-full blur-3xl" />
          <div className="absolute -bottom-20 -left-20 w-40 h-40 bg-purple-500/10 rounded-full blur-3xl" />

          <div className="text-center mb-6 relative">
            <motion.div
              initial={{ scale: 0 }}
              animate={{ scale: 1 }}
              transition={{ delay: 0.2, type: "spring", stiffness: 200 }}
              className="inline-flex items-center justify-center w-16 h-16 rounded-2xl bg-gradient-to-br from-accent-500 to-accent-600 mb-4 shadow-lg shadow-accent-500/30"
            >
              <Sparkles className="w-8 h-8 text-white" />
            </motion.div>
            <h1 className="text-2xl font-bold gradient-text mb-2">
              Присоединиться к {invitation.org_name || 'команде'}
            </h1>
            <p className="text-dark-400">
              Вас пригласили как <span className="text-accent-400">{roleLabels[invitation.org_role] || 'Сотрудник'}</span>
            </p>
          </div>

          <form onSubmit={handleSubmit} className="space-y-4">
            <div className="relative group">
              <User className="absolute left-4 top-1/2 -translate-y-1/2 w-5 h-5 text-dark-400 group-focus-within:text-accent-400 transition-colors" />
              <input
                type="text"
                placeholder="Ваше имя"
                value={form.name}
                onChange={(e) => setForm({ ...form, name: e.target.value })}
                required
                className="w-full input-premium rounded-xl py-3.5 pl-12 pr-4 text-dark-100 placeholder-dark-500 focus:outline-none"
              />
            </div>

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

            <div className="relative group">
              <Lock className="absolute left-4 top-1/2 -translate-y-1/2 w-5 h-5 text-dark-400 group-focus-within:text-accent-400 transition-colors" />
              <input
                type={showPassword ? 'text' : 'password'}
                placeholder="Подтвердите пароль"
                value={form.confirmPassword}
                onChange={(e) => setForm({ ...form, confirmPassword: e.target.value })}
                required
                className="w-full input-premium rounded-xl py-3.5 pl-12 pr-4 text-dark-100 placeholder-dark-500 focus:outline-none"
              />
            </div>

            {form.password && form.confirmPassword && form.password !== form.confirmPassword && (
              <div className="flex items-center gap-2 text-red-400 text-sm">
                <AlertCircle className="w-4 h-4" />
                Пароли не совпадают
              </div>
            )}

            <motion.button
              whileHover={{ scale: 1.02, boxShadow: "0 10px 40px rgba(12, 165, 235, 0.4)" }}
              whileTap={{ scale: 0.98 }}
              disabled={submitting || form.password !== form.confirmPassword}
              type="submit"
              className="w-full btn-premium text-white font-semibold py-3.5 rounded-xl transition-all duration-300 disabled:opacity-50"
            >
              {submitting ? (
                <span className="flex items-center justify-center gap-2">
                  <div className="w-5 h-5 border-2 border-white border-t-transparent rounded-full animate-spin" />
                  Регистрация...
                </span>
              ) : (
                'Зарегистрироваться'
              )}
            </motion.button>
          </form>

          <div className="mt-6 text-center">
            <p className="text-dark-500 text-sm">
              Уже есть аккаунт?{' '}
              <button
                onClick={() => navigate('/login')}
                className="text-accent-400 hover:text-accent-300 transition-colors"
              >
                Войти
              </button>
            </p>
          </div>
        </div>
      </motion.div>
    </div>
  );
}
