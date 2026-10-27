import { useCallback, useEffect, useState } from "react";
import { KeyRound, ListTodo, Bell, Loader2, AlertTriangle, Link2 as LinkIcon } from "lucide-react";
import clsx from "clsx";
import api from "@/services/api/client";
import AccessHub from "./AccessHub";
import MyTasks from "./MyTasks";
import Notifications from "./Notifications";

/**
 * Оболочка Mini App: авторизация по initData + нижние вкладки.
 *
 * Вход отличается от веба принципиально — пароля нет, личность подтверждает
 * Telegram подписью initData. Сервер её проверяет и ставит те же httpOnly-куки,
 * что и обычный логин, поэтому весь остальной слой API работает без изменений.
 */

export type Me = { id: number; name: string; email: string; role: string; org_role?: string | null };
type Tab = "access" | "tasks" | "bell";

export default function MiniApp() {
  const [me, setMe] = useState<Me | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [tab, setTab] = useState<Tab>("access");
  // 403 «не привязан» — не тупик, а повод предложить привязку
  const [needBind, setNeedBind] = useState(false);

  const auth = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      // Уже есть валидная кука (переоткрыли приложение) — второй вход не нужен
      try {
        const { data } = await api.get("/auth/me");
        setMe(data);
        return;
      } catch {
        /* не авторизованы — идём обычным путём через initData */
      }

      const initData = (window as any)?.Telegram?.WebApp?.initData;
      if (!initData) {
        setError(
          "Откройте приложение через Telegram — вне мессенджера вход невозможен."
        );
        return;
      }
      const { data } = await api.post("/auth/telegram-webapp", { init_data: initData });
      setMe(data.user);
    } catch (e: any) {
      // Аккаунт есть, но этот Telegram к нему не привязан — показываем форму
      // привязки вместо сообщения об ошибке, иначе человек в тупике: кнопки
      // «привязать» в веб-версии нет.
      if (e?.response?.status === 403 && /не привязан/i.test(e?.response?.data?.detail || "")) {
        setNeedBind(true);
        return;
      }
      setError(e?.response?.data?.detail || "Не удалось войти");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => { auth(); }, [auth]);

  if (loading) {
    return (
      <div className="hf-ma-splash">
        <Loader2 className="animate-spin" size={28} />
      </div>
    );
  }

  if (needBind && !me) {
    return <BindForm onBound={(u) => { setNeedBind(false); setMe(u); }} />;
  }

  if (error || !me) {
    return (
      <div className="hf-ma-splash hf-ma-splash-error">
        <AlertTriangle size={30} />
        <p>{error || "Не удалось войти"}</p>
        <button className="hf-ma-retry" onClick={auth}>Повторить</button>
      </div>
    );
  }

  const TABS: { key: Tab; label: string; icon: typeof KeyRound }[] = [
    { key: "access", label: "Доступы", icon: KeyRound },
    { key: "tasks", label: "Задачи", icon: ListTodo },
    { key: "bell", label: "События", icon: Bell },
  ];

  return (
    <div className="hf-ma">
      <div className="hf-ma-body">
        {tab === "access" && <AccessHub me={me} />}
        {tab === "tasks" && <MyTasks userId={me.id} />}
        {tab === "bell" && <Notifications />}
      </div>

      <nav className="hf-ma-nav">
        {TABS.map((t) => {
          const Icon = t.icon;
          return (
            <button
              key={t.key}
              className={clsx("hf-ma-nav-item", tab === t.key && "hf-ma-nav-item-active")}
              onClick={() => setTab(t.key)}
            >
              <Icon size={19} />
              <span>{t.label}</span>
            </button>
          );
        })}
      </nav>
    </div>
  );
}


/**
 * Разовая привязка Telegram к аккаунту.
 *
 * Пароль спрашиваем ровно один раз и только здесь: личность подтверждается
 * дважды — подписью Telegram (её нельзя подделать) и паролем. Это надёжнее
 * прежней команды /bind, которая привязывала кого угодно к любому аккаунту
 * по одному лишь email. Дальше вход идёт автоматически, без пароля.
 */
function BindForm({ onBound }: { onBound: (u: Me) => void }) {
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<string | null>(null);

  const submit = async () => {
    const initData = (window as any)?.Telegram?.WebApp?.initData;
    if (!initData) { setErr("Откройте приложение через Telegram"); return; }
    setBusy(true);
    setErr(null);
    try {
      const { data } = await api.post("/auth/telegram-webapp-bind", {
        init_data: initData, email: email.trim(), password,
      });
      onBound(data.user);
    } catch (e: any) {
      setErr(e?.response?.data?.detail || "Не удалось привязать");
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="hf-ma-bind">
      <LinkIcon size={28} />
      <h2>Привяжите Telegram</h2>
      <p>
        Этот Telegram ещё не связан с вашим аккаунтом. Войдите один раз — дальше
        приложение будет узнавать вас само.
      </p>
      <input
        type="email" inputMode="email" autoComplete="username"
        placeholder="Рабочая почта" value={email}
        onChange={(e) => setEmail(e.target.value)}
      />
      <input
        type="password" autoComplete="current-password"
        placeholder="Пароль" value={password}
        onChange={(e) => setPassword(e.target.value)}
        onKeyDown={(e) => { if (e.key === "Enter") submit(); }}
      />
      {err && <span className="hf-ma-bind-err">{err}</span>}
      <button className="hf-ma-retry" onClick={submit} disabled={busy || !email || !password}>
        {busy ? <Loader2 className="animate-spin" size={16} /> : null}
        Привязать
      </button>
      <span className="hf-ma-bind-hint">
        Пароль тот же, что и на сайте. Если его нет — попросите администратора.
      </span>
    </div>
  );
}
