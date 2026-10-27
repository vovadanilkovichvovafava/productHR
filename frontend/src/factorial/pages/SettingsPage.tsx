import CatalogTemplate from '@/factorial/templates/CatalogTemplate';
import { settingsCatalog } from '@/factorial/mocks/settingsCatalog';

export default function SettingsPage() {
  return (
    <CatalogTemplate
      breadcrumb={[{ label: 'Настройки' }]}
      searchPlaceholder="Поиск настроек…"
      sections={settingsCatalog}
    />
  );
}
