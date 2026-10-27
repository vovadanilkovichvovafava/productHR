import CatalogTemplate from '@/factorial/templates/CatalogTemplate';
import { workflowsCatalog } from '@/factorial/mocks/workflowsCatalog';

export default function WorkflowsPage() {
  return (
    <CatalogTemplate
      breadcrumb={[{ label: 'Рабочие процессы' }]}
      secondaryNav={[
        { label: 'Рабочие процессы', href: '/workflows', end: true },
        { label: 'Опросы', href: '/workflows/surveys' },
      ]}
      sections={workflowsCatalog}
    />
  );
}
