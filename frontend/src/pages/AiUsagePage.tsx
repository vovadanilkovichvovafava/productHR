import { useEffect, useState } from 'react';
import { Sparkles } from 'lucide-react';
import toast from 'react-hot-toast';
import { getAiUsage, type AiUsageSummary } from '@/services/api/aiUsage';
import { parseServerDate } from '@/utils/date';

// «Расход ИИ» (21.10.2026). Владелец: «разбор резюме ест очень много» —
// посчитать было нечем, расход видно было только итогом в консоли Anthropic.
// Теперь каждый вызов Claude записывается (services/ai_usage.py): здесь — на
// что уходят деньги, по разделам приложения, и последние ошибки (в т.ч.
// «кончился баланс»). Цена примерная, по прайсу; точный счёт — в консоли.

const PERIODS = [
  { days: 1, label: 'Сутки' },
  { days: 7, label: '7 дней' },
  { days: 30, label: '30 дней' },
];

const usd = (v: number) => `$${v < 1 ? v.toFixed(3) : v.toFixed(2)}`;
const num = (v: number) => v.toLocaleString('ru');

export default function AiUsagePage() {
  const [days, setDays] = useState(7);
  const [data, setData] = useState<AiUsageSummary | null>(null);

  useEffect(() => {
    let alive = true;
    setData(null);
    getAiUsage(days)
      .then((d) => alive && setData(d))
      .catch(() => {
        if (!alive) return;
        toast.error('Не удалось загрузить расход');
        setData({ days, total_cost_usd: 0, total_calls: 0, by_caller: [], by_day: [], last_errors: [] });
      });
    return () => {
      alive = false;
    };
  }, [days]);

  return (
    <div className="p-6 max-w-5xl mx-auto">
      <div className="mb-5">
        <h1 className="text-2xl font-bold text-white">Расход ИИ</h1>
        <p className="text-dark-400 text-sm mt-1">
          Сколько уходит на Claude и на что — по разделам приложения. Считается с 21.10.2026, цена
          примерная (по прайсу), точный счёт — в консоли Anthropic.
        </p>
      </div>

      <div className="flex gap-2 mb-5">
        {PERIODS.map((p) => (
          <button
            key={p.days}
            type="button"
            onClick={() => setDays(p.days)}
            className={`px-3 py-1.5 rounded-full text-sm border ${
              days === p.days ? 'border-accent-500 text-accent-400' : 'border-dark-700 text-dark-400 hover:text-white'
            }`}
          >
            {p.label}
          </button>
        ))}
      </div>

      {data === null ? (
        <div className="py-16 flex justify-center">
          <div className="w-8 h-8 border-2 border-accent-500 border-t-transparent rounded-full animate-spin" />
        </div>
      ) : (
        <>
          <div className="grid grid-cols-2 gap-3 mb-5">
            <div className="bg-dark-800 border border-dark-700 rounded-xl p-4">
              <div className="text-sm text-dark-400">Потрачено примерно</div>
              <div className="text-2xl font-semibold text-white mt-1">{usd(data.total_cost_usd)}</div>
            </div>
            <div className="bg-dark-800 border border-dark-700 rounded-xl p-4">
              <div className="text-sm text-dark-400">Вызовов Claude</div>
              <div className="text-2xl font-semibold text-white mt-1">{num(data.total_calls)}</div>
            </div>
          </div>

          {data.last_errors.length > 0 && (
            <div className="mb-5 rounded-xl border border-red-500/30 bg-red-500/10 p-4 text-sm">
              <div className="font-semibold text-red-400 mb-2">Последние ошибки</div>
              {data.last_errors.map((e, i) => (
                <div key={i} className="text-white/80">
                  {e.at ? parseServerDate(e.at).toLocaleString('ru', { day: 'numeric', month: 'short', hour: '2-digit', minute: '2-digit' }) : '—'}
                  {' · '}
                  {e.label}: <span className="text-dark-400">{e.error}</span>
                </div>
              ))}
            </div>
          )}

          {data.by_caller.length === 0 ? (
            <div className="py-16 text-center text-dark-400">
              <Sparkles className="w-8 h-8 mx-auto mb-3 opacity-50" />
              За этот период вызовов не было.
            </div>
          ) : (
            <div className="bg-dark-800 border border-dark-700 rounded-xl overflow-x-auto">
              <table className="w-full text-sm">
                <thead>
                  <tr className="text-left text-dark-400 border-b border-dark-700">
                    <th className="px-4 py-2 font-medium">На что</th>
                    <th className="px-4 py-2 font-medium">Модель</th>
                    <th className="px-4 py-2 font-medium text-right">Вызовов</th>
                    <th className="px-4 py-2 font-medium text-right">Токенов вход / выход</th>
                    <th className="px-4 py-2 font-medium text-right">≈ Цена</th>
                    <th className="px-4 py-2 font-medium text-right">Доля</th>
                  </tr>
                </thead>
                <tbody>
                  {data.by_caller.map((r) => (
                    <tr key={`${r.caller}-${r.model}`} className="border-b border-dark-700/60 last:border-0">
                      <td className="px-4 py-2 text-white" title={r.caller || undefined}>
                        {r.label}
                        {r.errors > 0 && <span className="ml-2 text-xs text-red-400">ошибок: {r.errors}</span>}
                      </td>
                      <td className="px-4 py-2 text-dark-400">{r.model || '—'}</td>
                      <td className="px-4 py-2 text-right tabular-nums text-white">{num(r.calls)}</td>
                      <td className="px-4 py-2 text-right tabular-nums text-dark-400">
                        {num(r.input_tokens)} / {num(r.output_tokens)}
                      </td>
                      <td className="px-4 py-2 text-right tabular-nums text-white">{usd(r.cost_usd)}</td>
                      <td className="px-4 py-2 text-right tabular-nums text-dark-400">
                        {data.total_cost_usd > 0 ? `${Math.round((r.cost_usd / data.total_cost_usd) * 100)}%` : '—'}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </>
      )}
    </div>
  );
}
