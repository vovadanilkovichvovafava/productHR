import { useState } from 'react';
import { UserPlus } from 'lucide-react';
import { useNavigate } from 'react-router-dom';
import { useMutation } from '@tanstack/react-query';
import { Input } from '@/factorial/components/ui/input';
import FactorialFormPage from '@/factorial/components/FactorialFormPage';
import FormSection from '@/factorial/components/FormSection';
import FormField from '@/factorial/components/FormField';
import { createInvitation } from '@/factorial/api/invitations';
import type { Invitation } from '@/factorial/api/types';
import { getErrorDetail } from '@/utils';

// Добавление НОВОГО сотрудника = приглашение (реальный бэк /invitations).
// Прямое создание Employee невозможно без существующего user_id, а пароль/регистрацию
// сотрудник задаёт сам по ссылке — поэтому единственный корректный путь — инвайт-ссылка.
export default function AddEmployeeFormPage() {
  const navigate = useNavigate();
  const [data, setData] = useState({ email: '', firstName: '', lastName: '' });
  const [link, setLink] = useState('');
  const [err, setErr] = useState('');

  const m = useMutation({
    mutationFn: () =>
      createInvitation({
        email: data.email || undefined,
        name: `${data.firstName} ${data.lastName}`.trim() || undefined,
        org_role: 'member',
      }),
    onSuccess: (inv: Invitation) => {
      setErr('');
      setLink(window.location.origin + inv.invitation_url);
    },
    onError: (e: unknown) => {
      const d = getErrorDetail(e, '');
      setErr(
        /already a member/i.test(d)
          ? 'Этот email уже зарегистрирован в организации — введите другой или оставьте поле пустым.'
          : d || 'Не удалось создать приглашение. Попробуйте ещё раз.',
      );
    },
  });

  const submit = () => {
    if (link) {
      navigate('/factorial/employees');
      return;
    }
    if (m.isPending) return;
    setErr('');
    if (!data.email && !data.firstName && !data.lastName) {
      setErr('Укажите email или имя сотрудника.');
      return;
    }
    m.mutate();
  };

  const copy = () => navigator.clipboard?.writeText(link);

  return (
    <FactorialFormPage
      icon={<UserPlus className="w-7 h-7 text-rose-500" strokeWidth={1.5} />}
      iconBg="bg-rose-50"
      breadcrumb={[{ label: 'Сотрудники', href: '/factorial/employees' }, { label: 'Добавить сотрудника' }]}
      title="Добавить сотрудника"
      submitLabel={link ? 'Перейти к сотрудникам' : m.isPending ? 'Создание…' : 'Создать приглашение'}
      onSubmit={submit}
      tipPanel={
        link
          ? 'Отправьте ссылку сотруднику (веб или Telegram). Он задаст пароль и попадёт в свой личный кабинет.'
          : 'Новый сотрудник добавляется через приглашение. Должность, отдел и остальные детали HR заполнит после того, как сотрудник примет приглашение.'
      }
    >
      {!link ? (
        <>
          <FormSection heading="Данные сотрудника">
            <FormField label="Электронная почта" required error={!data.email ? 'Укажите email' : undefined}>
              <Input
                value={data.email}
                onChange={(e) => setData({ ...data, email: e.target.value })}
                placeholder="ivan@example.com"
                type="email"
              />
            </FormField>
            <div className="grid grid-cols-2 gap-3">
              <FormField label="Имя">
                <Input
                  value={data.firstName}
                  onChange={(e) => setData({ ...data, firstName: e.target.value })}
                  placeholder="Иван"
                />
              </FormField>
              <FormField label="Фамилия">
                <Input
                  value={data.lastName}
                  onChange={(e) => setData({ ...data, lastName: e.target.value })}
                  placeholder="Иванов"
                />
              </FormField>
            </div>
          </FormSection>
          {err && (
            <p className="text-fx-sm" style={{ color: '#B91C1C' }}>
              {err}
            </p>
          )}
        </>
      ) : (
        <FormSection heading="Приглашение готово">
          <p className="text-fx-sm text-text-muted mb-2">Ссылка-приглашение создана. Отправьте её сотруднику:</p>
          <Input readOnly value={link} onFocus={(e) => e.currentTarget.select()} />
          <button
            type="button"
            onClick={copy}
            className="mt-2 inline-flex items-center gap-1.5 px-3 py-1.5 text-fx-sm border border-card-border-soft rounded-fx-lg hover:bg-sidebar-hover"
          >
            Копировать ссылку
          </button>
        </FormSection>
      )}
    </FactorialFormPage>
  );
}
