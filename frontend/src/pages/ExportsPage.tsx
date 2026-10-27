import { motion } from 'framer-motion';
import { useUrlTab } from '@/hooks/useUrlTab';
import {
  Download,
  Users,
  BarChart3,
  GitBranch,
  FileSpreadsheet,
  ArrowLeft,
} from 'lucide-react';

type ExportTab = 'overview' | 'users' | 'analytics' | 'stages';

const exportCards = [
  {
    id: 'users' as const,
    icon: Users,
    title: 'Пользователи CSV',
    description: 'Экспорт списка пользователей: ID, имя, email, роль, статус, дата регистрации.',
    filename: 'users',
    endpoint: '/api/exports/users.csv',
    columns: ['id', 'name', 'email', 'role', 'is_active', 'telegram_username', 'created_at'],
  },
  {
    id: 'analytics' as const,
    icon: BarChart3,
    title: 'Аналитика CSV',
    description: 'Экспорт метрик HR аналитики: вакансии, кандидаты, конверсия, время найма.',
    filename: 'analytics',
    endpoint: '/api/exports/analytics.csv',
    columns: ['metric', 'value', 'period', 'department'],
  },
  {
    id: 'stages' as const,
    icon: GitBranch,
    title: 'Этапы прохождения CSV',
    description: 'Экспорт пайплайна кандидатов: вакансия, кандидат, этап, дата, рейтинг.',
    filename: 'stages',
    endpoint: '/api/exports/stages.csv',
    columns: ['vacancy', 'candidate', 'stage', 'applied_at', 'last_stage_change', 'rating', 'source'],
  },
];

export default function ExportsPage() {
  const [activeTab, setActiveTab] = useUrlTab<ExportTab>('tab', 'overview');

  const activeCard = exportCards.find((c) => c.id === activeTab);

  return (
    <div className="h-full w-full max-w-full overflow-y-auto overflow-x-hidden p-6">
      <motion.div
        initial={{ opacity: 0, y: 20 }}
        animate={{ opacity: 1, y: 0 }}
        className="max-w-4xl mx-auto space-y-6 w-full"
      >
        {/* Header */}
        <div>
          <div className="flex items-center gap-3 mb-2">
            <FileSpreadsheet className="w-6 h-6 text-accent-500" />
            <h1 className="text-2xl font-bold">Экспорт CSV</h1>
          </div>
          <p className="text-dark-400">
            Выберите тип данных для экспорта. Файл будет сформирован на сервере и скачан в формате CSV.
          </p>
        </div>

        {activeTab === 'overview' ? (
          /* Cards grid */
          <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
            {exportCards.map((card) => (
              <button
                key={card.id}
                onClick={() => setActiveTab(card.id)}
                className="glass-card rounded-2xl p-6 text-left group cursor-pointer"
              >
                <div className="w-12 h-12 rounded-xl bg-accent-500/20 flex items-center justify-center mb-4 group-hover:bg-accent-500/30 transition-colors">
                  <card.icon className="w-6 h-6 text-accent-400" />
                </div>
                <h3 className="text-lg font-semibold text-white mb-2">{card.title}</h3>
                <p className="text-dark-400 text-sm leading-relaxed">{card.description}</p>
              </button>
            ))}
          </div>
        ) : (
          /* Detail panel for selected export */
          activeCard && (
            <motion.div
              initial={{ opacity: 0, y: 10 }}
              animate={{ opacity: 1, y: 0 }}
              className="glass rounded-2xl p-6 space-y-6"
            >
              {/* Back button */}
              <button
                onClick={() => setActiveTab('overview')}
                className="flex items-center gap-2 text-dark-400 hover:text-white transition-colors text-sm"
              >
                <ArrowLeft className="w-4 h-4" />
                Назад к выбору
              </button>

              {/* Card header */}
              <div className="flex items-center gap-4">
                <div className="w-14 h-14 rounded-xl bg-accent-500/20 flex items-center justify-center">
                  <activeCard.icon className="w-7 h-7 text-accent-400" />
                </div>
                <div>
                  <h2 className="text-xl font-semibold text-white">{activeCard.title}</h2>
                  <p className="text-dark-400 text-sm">{activeCard.description}</p>
                </div>
              </div>

              {/* Columns preview */}
              <div>
                <h3 className="text-sm font-medium text-dark-300 mb-3">Поля в файле:</h3>
                <div className="flex flex-wrap gap-2">
                  {activeCard.columns.map((col) => (
                    <span
                      key={col}
                      className="px-3 py-1.5 bg-dark-800 rounded-lg text-sm text-dark-200 border border-dark-700"
                    >
                      {col}
                    </span>
                  ))}
                </div>
              </div>

              {/* Download button */}
              <div className="pt-2">
                <a
                  href={activeCard.endpoint}
                  download
                  className="inline-flex items-center gap-3 px-6 py-3 btn-premium text-white font-medium rounded-xl"
                >
                  <Download className="w-5 h-5" />
                  Скачать {activeCard.filename}.csv
                </a>
                <p className="text-dark-500 text-xs mt-3">
                  Файл формируется на сервере. Имя файла включает текущую дату.
                </p>
              </div>
            </motion.div>
          )
        )}
      </motion.div>
    </div>
  );
}
