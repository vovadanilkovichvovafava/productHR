import { toast } from '@/factorial/components/ui/toast';

export function useMockSave() {
  return () =>
    toast({
      title: 'Demo mode',
      description: 'Действие не сохраняется. Это визуальный клон.',
    });
}
