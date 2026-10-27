import { useState } from 'react';
import { motion } from 'framer-motion';
import { Download, Chrome, Puzzle, FolderOpen, ToggleRight, CheckCircle2, ExternalLink } from 'lucide-react';
import toast from 'react-hot-toast';

const STEPS = [
  {
    icon: Download,
    title: 'Скачайте архив',
    desc: 'Нажмите кнопку ниже — скачается ZIP с расширением.',
  },
  {
    icon: FolderOpen,
    title: 'Распакуйте',
    desc: 'Распакуйте архив в удобную папку (например, ~/Extensions).',
  },
  {
    icon: Chrome,
    title: 'Откройте chrome://extensions',
    desc: 'В браузере Chrome перейдите в Управление расширениями.',
  },
  {
    icon: ToggleRight,
    title: 'Включите режим разработчика',
    desc: 'Переключатель в правом верхнем углу страницы расширений.',
  },
  {
    icon: Puzzle,
    title: 'Загрузите распакованное',
    desc: 'Нажмите "Загрузить распакованное расширение" и выберите папку enceladus-magic-button.',
  },
  {
    icon: CheckCircle2,
    title: 'Готово!',
    desc: 'Расширение появится в панели Chrome. Откройте hh.ru, Habr Career или LinkedIn — и добавляйте кандидатов одним кликом.',
  },
];

export default function ExtensionPage() {
  const [downloading, setDownloading] = useState(false);

  const handleDownload = async () => {
    setDownloading(true);
    try {
      const resp = await fetch('/api/extension/download', {
        credentials: 'include',
      });
      if (!resp.ok) {
        const text = await resp.text().catch(() => '');
        throw new Error(text || `HTTP ${resp.status}`);
      }
      const blob = await resp.blob();
      const url = URL.createObjectURL(blob);
      const a = document.createElement('a');
      a.href = url;
      a.download = 'enceladus-magic-button.zip';
      document.body.appendChild(a);
      a.click();
      document.body.removeChild(a);
      URL.revokeObjectURL(url);
      toast.success('Расширение скачано!');
    } catch (err: any) {
      console.error('Download error:', err);
      toast.error(err?.message || 'Ошибка скачивания');
    } finally {
      setDownloading(false);
    }
  };

  return (
    <div className="min-h-screen p-4 lg:p-8 max-w-3xl mx-auto space-y-8">
      {/* Header */}
      <motion.div
        initial={{ opacity: 0, y: -10 }}
        animate={{ opacity: 1, y: 0 }}
        className="text-center space-y-3"
      >
        <div className="inline-flex items-center justify-center w-16 h-16 rounded-2xl bg-gradient-to-br from-purple-500/20 to-blue-500/20 border border-white/10 mb-2">
          <Puzzle className="w-8 h-8 text-purple-400" />
        </div>
        <h1 className="text-2xl font-bold text-white">Волшебная кнопка</h1>
        <p className="text-white/50 text-sm max-w-md mx-auto">
          Chrome-расширение для добавления кандидатов с hh.ru, Habr Career и LinkedIn прямо в Enceladus одним кликом.
        </p>
      </motion.div>

      {/* Download button */}
      <motion.div
        initial={{ opacity: 0, scale: 0.95 }}
        animate={{ opacity: 1, scale: 1 }}
        transition={{ delay: 0.1 }}
        className="flex justify-center"
      >
        <button
          onClick={handleDownload}
          disabled={downloading}
          className="flex items-center gap-3 px-8 py-4 bg-gradient-to-r from-purple-600 to-blue-600 hover:from-purple-500 hover:to-blue-500 rounded-2xl text-white font-semibold text-lg shadow-lg shadow-purple-500/20 hover:shadow-purple-500/30 transition-all disabled:opacity-50"
        >
          <Download className={`w-5 h-5 ${downloading ? 'animate-bounce' : ''}`} />
          {downloading ? 'Скачивание...' : 'Скачать расширение'}
        </button>
      </motion.div>

      {/* Install steps */}
      <motion.div
        initial={{ opacity: 0, y: 10 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ delay: 0.2 }}
        className="bg-white/[0.04] border border-white/[0.06] rounded-2xl p-6 space-y-1"
      >
        <h2 className="text-lg font-semibold text-white mb-4">Установка</h2>
        <div className="space-y-4">
          {STEPS.map((step, i) => {
            const Icon = step.icon;
            return (
              <div key={i} className="flex items-start gap-4">
                <div className="flex-shrink-0 w-8 h-8 rounded-lg bg-white/[0.06] flex items-center justify-center text-white/40">
                  <Icon className="w-4 h-4" />
                </div>
                <div>
                  <div className="text-sm font-medium text-white">
                    <span className="text-white/30 mr-2">{i + 1}.</span>
                    {step.title}
                  </div>
                  <div className="text-xs text-white/40 mt-0.5">{step.desc}</div>
                </div>
              </div>
            );
          })}
        </div>
      </motion.div>

      {/* Supported sites */}
      <motion.div
        initial={{ opacity: 0, y: 10 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ delay: 0.3 }}
        className="bg-white/[0.04] border border-white/[0.06] rounded-2xl p-6"
      >
        <h2 className="text-lg font-semibold text-white mb-4">Поддерживаемые сайты</h2>
        <div className="grid grid-cols-1 sm:grid-cols-3 gap-3">
          {[
            { name: 'hh.ru', desc: 'Резюме кандидатов', url: 'https://hh.ru' },
            { name: 'Habr Career', desc: 'Профили специалистов', url: 'https://career.habr.com' },
            { name: 'LinkedIn', desc: 'Профессиональные профили', url: 'https://linkedin.com' },
          ].map((site) => (
            <div
              key={site.name}
              className="flex items-center gap-3 p-3 bg-white/[0.03] rounded-xl border border-white/[0.06]"
            >
              <ExternalLink className="w-4 h-4 text-blue-400 flex-shrink-0" />
              <div>
                <div className="text-sm font-medium text-white">{site.name}</div>
                <div className="text-xs text-white/40">{site.desc}</div>
              </div>
            </div>
          ))}
        </div>
      </motion.div>
    </div>
  );
}
