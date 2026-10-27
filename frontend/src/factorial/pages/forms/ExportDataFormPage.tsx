import { useState } from 'react';
import { Download } from 'lucide-react';
import { useNavigate } from 'react-router-dom';
import FactorialFormPage from '@/factorial/components/FactorialFormPage';
import FormField from '@/factorial/components/FormField';
import DatePickerFactorial from '@/factorial/components/DatePickerFactorial';
import { useMockSave } from '@/factorial/components/MockSaveToast';

export default function ExportDataFormPage() {
  const navigate = useNavigate();
  const mockSave = useMockSave();
  const [format, setFormat] = useState('CSV');
  const [from, setFrom] = useState('');
  const [to, setTo] = useState('');

  const onSubmit = () => {
    mockSave();
    navigate('/factorial/employees');
  };

  return (
    <FactorialFormPage
      icon={<Download className="w-7 h-7 text-rose-500" strokeWidth={1.5} />}
      iconBg="bg-rose-50"
      breadcrumb={[{ label: 'Сотрудники', href: '/employees' }, { label: 'Экспорт данных' }]}
      title="Экспорт данных"
      subtitle="Выгрузите данные сотрудников в нужном формате"
      submitLabel="Экспортировать"
      onSubmit={onSubmit}
    >
      <FormField label="Формат">
        <select
          value={format}
          onChange={(e) => setFormat(e.target.value)}
          className="w-full px-3 py-2 rounded-fx-lg border border-border bg-white text-fx-sm"
        >
          <option>CSV</option>
          <option>Excel (XLSX)</option>
          <option>PDF</option>
        </select>
      </FormField>
      <FormField label="Период">
        <div className="grid grid-cols-2 gap-3">
          <DatePickerFactorial value={from} onChange={setFrom} />
          <DatePickerFactorial value={to} onChange={setTo} />
        </div>
      </FormField>
    </FactorialFormPage>
  );
}
