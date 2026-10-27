import { useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { Input } from '@/factorial/components/ui/input';
import FactorialFormPage from '@/factorial/components/FactorialFormPage';
import FormSection from '@/factorial/components/FormSection';
import FormField from '@/factorial/components/FormField';
import FileDropZone from '@/factorial/components/FileDropZone';
import RichTextEditor from '@/factorial/components/RichTextEditor';
import { useMockSave } from '@/factorial/components/MockSaveToast';

export default function WritePostFormPage() {
  const navigate = useNavigate();
  const mockSave = useMockSave();
  const [title, setTitle] = useState('');
  const [body, setBody] = useState('');

  const onSubmit = () => {
    mockSave();
    navigate('/factorial/dashboard');
  };

  return (
    <FactorialFormPage
      variant="plain"
      breadcrumb={[{ label: 'Главная', href: '/dashboard' }, { label: 'Новый пост' }]}
      title="Написать пост"
      submitLabel="Опубликовать"
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
            placeholder="О чём пост?"
          />
        </FormField>
        <FormField label="Описание">
          <RichTextEditor
            value={body}
            onChange={setBody}
            placeholder="Расскажите подробнее..."
            footerHint="До 150 МБ вложений на одно сообщение"
          />
        </FormField>
      </FormSection>
    </FactorialFormPage>
  );
}
