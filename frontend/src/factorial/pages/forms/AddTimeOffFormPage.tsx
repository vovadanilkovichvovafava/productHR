import { useState } from 'react';
import { Palmtree as TreePalm } from 'lucide-react';
import { useNavigate } from 'react-router-dom';
import { Input } from '@/factorial/components/ui/input';
import { Textarea } from '@/factorial/components/ui/textarea';
import FactorialFormPage from '@/factorial/components/FactorialFormPage';
import FormField from '@/factorial/components/FormField';
import DatePickerFactorial from '@/factorial/components/DatePickerFactorial';
import { useMockSave } from '@/factorial/components/MockSaveToast';

export default function AddTimeOffFormPage() {
  const navigate = useNavigate();
  const mockSave = useMockSave();
  const [policy, setPolicy] = useState('Time off policy');
  const [type, setType] = useState('Отпуск');
  const [employee, setEmployee] = useState('');
  const [descr, setDescr] = useState('');
  const [unit, setUnit] = useState<'days' | 'hours'>('days');
  const [from, setFrom] = useState('');
  const [to, setTo] = useState('');

  const onSubmit = () => {
    mockSave();
    navigate('/factorial/calendar');
  };

  return (
    <FactorialFormPage
      icon={<TreePalm className="w-7 h-7 text-rose-500" strokeWidth={1.5} />}
      iconBg="bg-rose-50"
      breadcrumb={[{ label: 'Календарь', href: '/factorial/calendar' }, { label: 'Добавить отпуск' }]}
      title="Добавить отпуск"
      subtitle="Запросить временное отсутствие и выбрать тип отсутствия"
      submitLabel="Создать"
      onSubmit={onSubmit}
    >
      <FormField label="Политика">
        <select
          value={policy}
          onChange={(e) => setPolicy(e.target.value)}
          className="w-full px-3 py-2 rounded-fx-lg border border-border bg-white text-fx-sm"
        >
          <option>Time off policy</option>
        </select>
      </FormField>
      <FormField label="Тип отсутствия">
        <select
          value={type}
          onChange={(e) => setType(e.target.value)}
          className="w-full px-3 py-2 rounded-fx-lg border border-border bg-white text-fx-sm"
        >
          <option>Отпуск</option>
          <option>Больничный</option>
          <option>Личное</option>
        </select>
      </FormField>
      <FormField label="Сотрудник">
        <Input
          value={employee}
          onChange={(e) => setEmployee(e.target.value)}
          placeholder="🔍 Выберите сотрудников"
        />
      </FormField>
      <FormField label="Описание">
        <Textarea value={descr} onChange={(e) => setDescr(e.target.value)} rows={3} />
      </FormField>
      <div className="inline-flex p-1 rounded-fx-lg border border-card-border-soft bg-white">
        <button
          type="button"
          onClick={() => setUnit('days')}
          className={`px-4 py-1.5 text-fx-sm rounded ${
            unit === 'days' ? 'bg-sidebar-active font-medium' : ''
          }`}
        >
          Дни
        </button>
        <button
          type="button"
          onClick={() => setUnit('hours')}
          className={`px-4 py-1.5 text-fx-sm rounded ${
            unit === 'hours' ? 'bg-sidebar-active font-medium' : ''
          }`}
        >
          Часы
        </button>
      </div>
      <FormField label="Диапазон дат">
        <div className="grid grid-cols-2 gap-3">
          <DatePickerFactorial value={from} onChange={setFrom} disablePast />
          <DatePickerFactorial value={to} onChange={setTo} disablePast />
        </div>
      </FormField>
    </FactorialFormPage>
  );
}
