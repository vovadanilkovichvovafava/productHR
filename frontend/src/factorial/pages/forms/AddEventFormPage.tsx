import { useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { format } from 'date-fns';
import { Input } from '@/factorial/components/ui/input';
import FactorialFormPage from '@/factorial/components/FactorialFormPage';
import FormSection from '@/factorial/components/FormSection';
import FormField from '@/factorial/components/FormField';
import FileDropZone from '@/factorial/components/FileDropZone';
import RichTextEditor from '@/factorial/components/RichTextEditor';
import DatePickerFactorial from '@/factorial/components/DatePickerFactorial';
import TimePickerFactorial from '@/factorial/components/TimePickerFactorial';
import { useMockSave } from '@/factorial/components/MockSaveToast';

export default function AddEventFormPage() {
  const navigate = useNavigate();
  const mockSave = useMockSave();
  const [title, setTitle] = useState('');
  const [descr, setDescr] = useState('');
  const [date, setDate] = useState(format(new Date(), 'yyyy-MM-dd'));
  const [time, setTime] = useState(format(new Date(), 'HH:mm'));
  const [location, setLocation] = useState('');

  const onSubmit = () => {
    mockSave();
    navigate('/factorial/dashboard');
  };

  return (
    <FactorialFormPage
      variant="plain"
      breadcrumb={[{ label: 'Главная', href: '/dashboard' }, { label: 'Новое событие' }]}
      title="Создать событие"
      submitLabel="Продолжить"
      onSubmit={onSubmit}
    >
      <FormSection heading="Основная информация">
        <FormField label="Обложка поста">
          <FileDropZone hint="любое изображение, видео или GIF" subHint="1200x600px" size="lg" />
        </FormField>
        <FormField label="Заголовок">
          <Input
            value={title}
            onChange={(e) => setTitle(e.target.value)}
            placeholder="напр., Всемирный день психического здоровья"
          />
        </FormField>
        <FormField label="Описание">
          <RichTextEditor
            value={descr}
            onChange={setDescr}
            placeholder="Поделитесь, что в этом особенного"
            footerHint="До 150 МБ вложений на одно сообщение"
          />
        </FormField>
      </FormSection>

      <FormSection heading="Настройки поста">
        <div className="grid grid-cols-3 gap-3">
          <FormField label="Дата начала ивента">
            <DatePickerFactorial value={date} onChange={setDate} disablePast />
          </FormField>
          <FormField label="Время начала">
            <TimePickerFactorial value={time} onChange={setTime} />
          </FormField>
          <FormField label="Место проведения ивента">
            <Input
              value={location}
              onChange={(e) => setLocation(e.target.value)}
              placeholder="Где это будет проходить?"
            />
          </FormField>
        </div>
      </FormSection>
    </FactorialFormPage>
  );
}
