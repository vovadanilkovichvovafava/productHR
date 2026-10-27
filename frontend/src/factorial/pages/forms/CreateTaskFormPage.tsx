import { useState } from 'react';
import { CheckCircle2 } from 'lucide-react';
import { useNavigate } from 'react-router-dom';
import { Input } from '@/factorial/components/ui/input';
import { Textarea } from '@/factorial/components/ui/textarea';
import FactorialFormPage from '@/factorial/components/FactorialFormPage';
import FormSection from '@/factorial/components/FormSection';
import FormField from '@/factorial/components/FormField';
import DatePickerFactorial from '@/factorial/components/DatePickerFactorial';
import RichTextToolbar from '@/factorial/components/RichTextToolbar';
import FileDropZone from '@/factorial/components/FileDropZone';
import { useMockSave } from '@/factorial/components/MockSaveToast';

export default function CreateTaskFormPage() {
  const navigate = useNavigate();
  const mockSave = useMockSave();
  const [title, setTitle] = useState('');
  const [descr, setDescr] = useState('');
  const [assignee, setAssignee] = useState('CEO MST');
  const [dueDate, setDueDate] = useState('');

  const onSubmit = () => {
    mockSave();
    navigate('/factorial/tasks');
  };

  return (
    <FactorialFormPage
      icon={<CheckCircle2 className="w-7 h-7 text-rose-500" strokeWidth={1.5} />}
      iconBg="bg-rose-50"
      breadcrumb={[{ label: 'Задачи', href: '/tasks' }, { label: 'Новая задача' }]}
      title="Создать задачу"
      subtitle="Что нужно сделать сегодня?"
      submitLabel="Создать"
      onSubmit={onSubmit}
    >
      <FormSection>
        <FormField label="Название задачи" required>
          <Input
            value={title}
            onChange={(e) => setTitle(e.target.value)}
            placeholder="Введите название задачи"
          />
        </FormField>
        <FormField label="Описание задачи">
          <div>
            <RichTextToolbar />
            <Textarea
              value={descr}
              onChange={(e) => setDescr(e.target.value)}
              placeholder="Добавьте описание, чтобы помочь сотруднику понять задачу"
              className="rounded-t-none"
              rows={4}
            />
          </div>
        </FormField>
        <FormField label="Исполнители">
          <Input
            value={assignee}
            onChange={(e) => setAssignee(e.target.value)}
            placeholder="🔍 CEO MST"
          />
        </FormField>
        <div className="flex items-center gap-2 text-fx-sm text-text-muted">
          <input type="checkbox" className="rounded border-card-border-soft" />
          Создайте отдельное задание для каждого выбранного сотрудника.
        </div>
        <FormField label="Срок выполнения">
          <DatePickerFactorial value={dueDate} onChange={setDueDate} disablePast />
        </FormField>
        <FormField label="Вложения">
          <FileDropZone hint="любое изображение, видео или GIF" />
        </FormField>
      </FormSection>
    </FactorialFormPage>
  );
}
