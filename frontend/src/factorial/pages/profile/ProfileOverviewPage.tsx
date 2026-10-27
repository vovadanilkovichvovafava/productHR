import { useState } from 'react';
import { Copy, User, Download, KeyRound, Check } from 'lucide-react';
import { useQuery, useMutation } from '@tanstack/react-query';
import { toast } from '@/factorial/components/ui/toast';
import { getErrorDetail } from '@/utils';
import ProfileTemplate from '@/factorial/templates/ProfileTemplate';
import { getLeaveBalance, downloadEmployeeTemplate, resetEmployeePassword } from '@/factorial/api/employees';
import { myDocuments, employeeDocuments } from '@/factorial/api/documents';
import { formatDateRu, formatTenure } from '@/factorial/lib/formatDate';
import { buildProfileTabs } from '@/factorial/lib/routes';
import { useProfileEmployee } from '@/factorial/lib/useProfileEmployee';
import LeaveBalanceCard from '@/factorial/components/cabinet/LeaveBalanceCard';
import MyDocsMini from '@/factorial/components/cabinet/MyDocsMini';
import EmployeeStatusCard from '@/factorial/components/cabinet/EmployeeStatusCard';
import RequestLeaveModal from '@/factorial/components/RequestLeaveModal';
import HrConfirm from '@/components/hr/HrConfirm';
import { backdropClose } from '@/utils/backdropClose';

const TITLE_ICON = (
  <div className="w-9 h-9 rounded-fx-lg bg-pink-100 flex items-center justify-center">
    <User className="w-5 h-5 text-pink-600" />
  </div>
);

export default function ProfileOverviewPage() {
  const { data: me, isError, byId, employeeId } = useProfileEmployee();
  const base = byId ? `/factorial/employees/${employeeId}` : '/factorial/profile';
  const { data: balance } = useQuery({
    queryKey: ['fx', 'leave-balance', me?.id],
    queryFn: () => getLeaveBalance(me!.id),
    enabled: !!me,
  });
  const { data: docs = [] } = useQuery({
    queryKey: byId ? ['fx', 'emp-signed-docs', employeeId] : ['fx', 'my-docs'],
    queryFn: () => (byId ? employeeDocuments(employeeId!) : myDocuments()),
    enabled: !!me,
  });
  const [requestOpen, setRequestOpen] = useState(false);
  // Сгенерированный временный пароль (показывается один раз в модалке).
  const [genPassword, setGenPassword] = useState<string | null>(null);
  // 'ok' — скопирован, 'failed' — браузер не дал (нет прав/фокуса): пароль
  // остаётся в поле, его копируют руками.
  const [pwCopy, setPwCopy] = useState<'idle' | 'ok' | 'failed'>('idle');
  // Новый пароль сразу отменяет прежний и выкидывает сотрудника отовсюду —
  // поэтому сначала спрашиваем.
  const [confirmReset, setConfirmReset] = useState(false);
  const [exporting, setExporting] = useState(false);

  const resetPw = useMutation({
    mutationFn: () => resetEmployeePassword(me!.id),
    onSuccess: (r) => { setConfirmReset(false); setGenPassword(r.temporary_password); setPwCopy('idle'); },
    onError: (e) => {
      setConfirmReset(false);
      toast({ title: 'Ошибка', description: getErrorDetail(e, 'Не удалось сгенерировать пароль') });
    },
  });

  const copy = async (text: string) => {
    try {
      await navigator.clipboard.writeText(text);
      toast({ title: 'Скопировано', description: text });
    } catch {
      toast({ title: 'Не удалось скопировать', description: `Браузер не дал доступ к буферу. Скопируйте вручную: ${text}` });
    }
  };

  const copyPassword = async (text: string) => {
    try {
      if (!navigator.clipboard) throw new Error('no clipboard');
      await navigator.clipboard.writeText(text);
      setPwCopy('ok');
    } catch {
      setPwCopy('failed');
    }
  };

  const exportCard = async () => {
    if (!me) return;
    setExporting(true);
    try {
      await downloadEmployeeTemplate({ id: me.id });
    } catch (e) {
      toast({ title: 'Ошибка', description: getErrorDetail(e, 'Не удалось выгрузить карточку сотрудника') });
    } finally {
      setExporting(false);
    }
  };

  if (isError) {
    return (
      <ProfileTemplate
        breadcrumb={byId ? [{ label: 'Сотрудники', href: '/factorial/employees' }, { label: me?.user_name || 'Профиль' }] : [{ label: 'Профиль' }]}
        titleIcon={TITLE_ICON}
        title={byId ? (me?.user_name || 'Профиль') : 'Профиль'}
        subNav={buildProfileTabs(base)}
        leftColumn={
          <article className="bg-card-translucent border border-card-border-soft rounded-card shadow-card p-6 text-fx-sm text-text-muted">
            Профиль сотрудника ещё не заведён. Обратитесь к HR, чтобы вас добавили в систему.
          </article>
        }
        rightDetails={[]}
      />
    );
  }

  const email = me?.user_email || '—';
  const startRaw = me?.department_start_date || me?.practice_start_date || me?.created_at || null;
  const startStr = startRaw ? `${formatDateRu(startRaw)} (${formatTenure(startRaw)} назад)` : '—';

  return (
    <ProfileTemplate
      breadcrumb={byId ? [{ label: 'Сотрудники', href: '/factorial/employees' }, { label: me?.user_name || 'Профиль' }] : [{ label: 'Профиль' }]}
      titleIcon={TITLE_ICON}
      title={byId ? (me?.user_name || 'Профиль') : 'Профиль'}
      subNav={buildProfileTabs(base)}
      leftColumn={
        <>
          <div className="flex justify-end gap-2 mb-2">
            {/* Выдача доступа: HR-вид чужого сотрудника (byId), не личный кабинет.
                Пароль генерится ЗДЕСЬ, в момент выхода после ИС, — «Взять в штат»
                в ATS его больше не выдаёт. */}
            {byId && (
              <button
                type="button"
                className="inline-flex items-center gap-1.5 px-3 py-1.5 text-fx-xs font-medium border border-card-border-soft rounded-fx-lg hover:bg-sidebar-hover"
                onClick={() => setConfirmReset(true)}
                disabled={!me || resetPw.isPending}
              >
                <KeyRound className="w-3.5 h-3.5" />
                {resetPw.isPending ? 'Генерируем…' : 'Сгенерировать пароль'}
              </button>
            )}
            <button
              type="button"
              className="inline-flex items-center gap-1.5 px-3 py-1.5 text-fx-xs font-medium border border-card-border-soft rounded-fx-lg hover:bg-sidebar-hover"
              onClick={exportCard}
              disabled={!me || exporting}
            >
              <Download className="w-3.5 h-3.5" />
              {exporting ? 'Выгружаем…' : 'Экспорт'}
            </button>
          </div>

          {confirmReset && (
            <HrConfirm
              title="Сгенерировать новый пароль?"
              subtitle={`Сотрудник ${me?.user_name || ''} сможет войти только с новым паролем.`}
              danger="Текущий пароль сотрудника перестанет действовать, и он будет разлогинен на всех устройствах."
              confirmLabel="Сгенерировать"
              busy={resetPw.isPending}
              onCancel={() => setConfirmReset(false)}
              onConfirm={() => resetPw.mutate()}
            />
          )}

          {genPassword && (
            <div className="fx-modal-overlay" {...backdropClose(() => setGenPassword(null))}>
              <div className="fx-modal" onClick={(e) => e.stopPropagation()}>
                <h3>Временный пароль для входа</h3>
                <div className="fx-sub">
                  Передайте пароль сотруднику — он показывается один раз. Логин — его email
                  ({me?.user_email || '—'}). Прежний пароль (если был) больше не действует.
                </div>
                <div className="flex items-center gap-2" style={{ marginTop: 10 }}>
                  <input
                    readOnly
                    className="fx-input"
                    style={{ flex: 1, fontSize: 15, fontFamily: 'monospace' }}
                    value={genPassword}
                    onFocus={(e) => e.currentTarget.select()}
                    aria-label="Временный пароль"
                  />
                  <button
                    type="button"
                    className="fx-btn fx-btn--secondary"
                    title="Скопировать"
                    onClick={() => copyPassword(genPassword)}
                  >
                    {pwCopy === 'ok' ? <Check className="w-4 h-4" /> : <Copy className="w-4 h-4" />}
                  </button>
                </div>
                {pwCopy === 'ok' && <div className="fx-sub" style={{ marginTop: 6 }}>Пароль скопирован.</div>}
                {pwCopy === 'failed' && (
                  <div style={{ color: '#B91C1C', fontSize: 13, marginTop: 6 }}>
                    Браузер не дал скопировать. Выделите пароль в поле и скопируйте вручную (Ctrl+C / ⌘C).
                  </div>
                )}
                <div className="fx-modal-actions">
                  <button type="button" className="fx-btn fx-btn--primary" onClick={() => setGenPassword(null)}>Готово</button>
                </div>
              </div>
            </div>
          )}
          <LeaveBalanceCard balance={balance} onRequest={() => setRequestOpen(true)} />
          <MyDocsMini docs={docs} />
          <EmployeeStatusCard
            probationEndDate={me?.probation_end_date || null}
            oneYearDate={me?.one_year_date || null}
          />
          {requestOpen && me && <RequestLeaveModal employeeId={me.id} onClose={() => setRequestOpen(false)} />}
        </>
      }
      rightDetails={[
        {
          label: 'Электронная почта',
          value: (
            <button type="button" onClick={() => copy(email)} className="flex items-center gap-2 hover:text-primary group">
              <span>{email}</span>
              <Copy className="w-3 h-3 opacity-0 group-hover:opacity-100" />
            </button>
          ),
        },
        { label: 'Отдел', value: <span>{me?.department_name || '—'}</span> },
        { label: 'Дата начала', value: <span>{startStr}</span> },
        {
          label: 'Рабочие дни',
          value: (
            <div className="flex gap-1 flex-wrap">
              {['Пн', 'Вт', 'Ср', 'Чт', 'Пт'].map((day) => (
                <span key={day} className="px-2 py-1 rounded border border-border text-fx-xs">{day}</span>
              ))}
            </div>
          ),
        },
        // HR-вид карточки (byId) сотрудника, оформленного из кандидата (Task 5, «Взять в штат»).
        // Скрыто в личном кабинете (byId=false) — /all-candidates недоступен обычному member.
        ...(byId && me?.entity_id
          ? [{
              label: 'Кандидат',
              value: (
                <a
                  href={`/all-candidates?entity=${me.entity_id}`}
                  className="inline-flex items-center gap-1.5 text-primary hover:underline"
                >
                  Из кандидата
                </a>
              ),
            }]
          : []),
      ]}
    />
  );
}
