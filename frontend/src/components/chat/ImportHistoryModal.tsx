import { useState, useCallback, useEffect, useRef } from 'react';
import { motion, AnimatePresence } from 'framer-motion';
import { X, Upload, FileJson, FileArchive, FileCode, CheckCircle, AlertCircle, Loader2, Apple, Monitor, Trash2, Mic, Video } from 'lucide-react';
import { useMutation, useQueryClient } from '@tanstack/react-query';
import { importTelegramHistory, cleanupBadImport, transcribeAllMedia, repairVideoNotes, ImportResult, CleanupResult, CleanupMode, ImportProgress, getImportProgress, generateImportId, TranscribeAllResult, RepairVideoResult } from '@/services/api';
import toast from 'react-hot-toast';
import clsx from 'clsx';
import { backdropClose } from '@/utils/backdropClose';

interface ImportHistoryModalProps {
  chatId: number;
  chatTitle: string;
  isOpen: boolean;
  onClose: () => void;
}

export default function ImportHistoryModal({ chatId, chatTitle, isOpen, onClose }: ImportHistoryModalProps) {
  const [file, setFile] = useState<File | null>(null);
  const [isDragging, setIsDragging] = useState(false);
  const [result, setResult] = useState<ImportResult | null>(null);
  const [cleanupResult, setCleanupResult] = useState<CleanupResult | null>(null);
  const [platform, setPlatform] = useState<'mac' | 'windows'>('mac');
  const [autoProcess, setAutoProcess] = useState(true);
  const [progress, setProgress] = useState<ImportProgress | null>(null);
  const [importId, setImportId] = useState<string | null>(null);
  const [isImporting, setIsImporting] = useState(false);
  const progressInterval = useRef<ReturnType<typeof setInterval> | null>(null);
  const queryClient = useQueryClient();

  // Poll for progress during import
  useEffect(() => {
    if (importId && isImporting) {
      progressInterval.current = setInterval(async () => {
        try {
          const p = await getImportProgress(chatId, importId);
          setProgress(p);
          if (p.status === 'completed' || p.status === 'error') {
            if (progressInterval.current) {
              clearInterval(progressInterval.current);
            }
          }
        } catch {
          // Ignore errors during polling
        }
      }, 500);

      return () => {
        if (progressInterval.current) {
          clearInterval(progressInterval.current);
        }
      };
    }
  }, [importId, isImporting, chatId]);

  const importMutation = useMutation({
    mutationFn: (file: File) => {
      const newImportId = generateImportId();
      setImportId(newImportId);
      setProgress(null);
      setIsImporting(true);
      return importTelegramHistory(chatId, file, autoProcess, newImportId);
    },
    onSuccess: (data) => {
      setResult(data);
      setProgress(null);
      setImportId(null);
      setIsImporting(false);
      if (data.imported > 0) {
        queryClient.invalidateQueries({ queryKey: ['messages', chatId] });
        queryClient.invalidateQueries({ queryKey: ['chats'] });
        toast.success(`Импортировано ${data.imported} сообщений`);
        // Auto-trigger transcription after successful import
        setTimeout(() => {
          transcribeMutation.mutate();
        }, 500);
      }
    },
    onError: (error: Error) => {
      setProgress(null);
      setImportId(null);
      setIsImporting(false);
      toast.error(error.message);
    },
  });

  const cleanupMutation = useMutation({
    mutationFn: (mode: CleanupMode) => cleanupBadImport(chatId, mode),
    onSuccess: (data) => {
      setCleanupResult(data);
      if (data.deleted > 0) {
        queryClient.invalidateQueries({ queryKey: ['messages', chatId] });
        queryClient.invalidateQueries({ queryKey: ['chats'] });
        toast.success(`Удалено ${data.deleted} сообщений`);
      } else {
        toast.success('Сообщений для удаления не найдено');
      }
    },
    onError: (error: Error) => {
      toast.error(error.message);
    },
  });

  const [transcribeResult, setTranscribeResult] = useState<TranscribeAllResult | null>(null);

  const transcribeMutation = useMutation({
    mutationFn: () => transcribeAllMedia(chatId),
    onSuccess: (data) => {
      setTranscribeResult(data);
      if (data.transcribed > 0) {
        queryClient.invalidateQueries({ queryKey: ['messages', chatId] });
        toast.success(`Транскрибировано ${data.transcribed} из ${data.total_found} сообщений`);
      } else if (data.total_found === 0) {
        toast.success('Все медиа уже транскрибированы');
      } else {
        toast.error('Не удалось транскрибировать сообщения');
      }
    },
    onError: (error: Error) => {
      toast.error(error.message);
    },
  });

  const [repairResult, setRepairResult] = useState<RepairVideoResult | null>(null);

  const repairMutation = useMutation({
    mutationFn: (repairFile: File) => repairVideoNotes(chatId, repairFile),
    onSuccess: (data) => {
      setRepairResult(data);
      if (data.repaired > 0) {
        queryClient.invalidateQueries({ queryKey: ['messages', chatId] });
        toast.success(`Исправлено ${data.repaired} из ${data.total} видео-кружков`);
      } else if (data.total === 0) {
        toast.success('Видео-кружков не найдено');
      } else {
        toast.error('Не удалось исправить видео-кружки');
      }
    },
    onError: (error: Error) => {
      toast.error(error.message);
    },
  });

  const handleDragOver = useCallback((e: React.DragEvent) => {
    e.preventDefault();
    setIsDragging(true);
  }, []);

  const handleDragLeave = useCallback((e: React.DragEvent) => {
    e.preventDefault();
    setIsDragging(false);
  }, []);

  const handleDrop = useCallback((e: React.DragEvent) => {
    e.preventDefault();
    setIsDragging(false);
    const droppedFile = e.dataTransfer.files[0];
    const validExtensions = ['.json', '.zip', '.html', '.htm'];
    const isValid = validExtensions.some(ext => droppedFile?.name.toLowerCase().endsWith(ext));
    if (droppedFile && isValid) {
      setFile(droppedFile);
      setResult(null);
    } else {
      toast.error('Пожалуйста, загрузите JSON, HTML или ZIP файл');
    }
  }, []);

  const handleFileChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    const selectedFile = e.target.files?.[0];
    if (selectedFile) {
      setFile(selectedFile);
      setResult(null);
    }
  };

  const handleImport = () => {
    if (file) {
      importMutation.mutate(file);
    }
  };

  const handleClose = () => {
    setFile(null);
    setResult(null);
    setCleanupResult(null);
    setProgress(null);
    setImportId(null);
    setIsImporting(false);
    if (progressInterval.current) {
      clearInterval(progressInterval.current);
    }
    onClose();
  };

  return (
    <AnimatePresence>
      {isOpen && (
        <motion.div
          initial={{ opacity: 0 }}
          animate={{ opacity: 1 }}
          exit={{ opacity: 0 }}
          className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-dark-950/80"
          {...backdropClose(handleClose)}
        >
          <motion.div
            initial={{ scale: 0.9, opacity: 0 }}
            animate={{ scale: 1, opacity: 1 }}
            exit={{ scale: 0.9, opacity: 0 }}
            className="glass rounded-2xl p-6 max-w-lg w-full max-w-[calc(100%-2rem)] max-h-[90vh] overflow-hidden flex flex-col"
            onClick={(e) => e.stopPropagation()}
            role="dialog"
            aria-modal="true"
            aria-labelledby="import-history-modal-title"
          >
            {/* Header */}
            <div className="flex items-center justify-between mb-6 flex-shrink-0 gap-3">
              <div className="flex-1 min-w-0">
                <h2 id="import-history-modal-title" className="text-xl font-semibold flex items-center gap-2">
                  <Upload className="w-5 h-5 text-accent-400" aria-hidden="true" />
                  Загрузить историю
                </h2>
                <p className="text-sm text-dark-400 mt-1 truncate">{chatTitle}</p>
              </div>
              <button
                onClick={handleClose}
                className="p-2 rounded-lg hover:bg-dark-800/50 transition-colors flex-shrink-0"
                aria-label="Закрыть окно"
              >
                <X className="w-5 h-5" aria-hidden="true" />
              </button>
            </div>

            {/* Instructions */}
            <div className="mb-4 glass-light rounded-xl overflow-hidden max-h-[200px] overflow-y-auto flex-shrink-0">
              {/* Platform tabs */}
              <div className="flex border-b border-white/5 sticky top-0 bg-dark-800/95 backdrop-blur-sm" role="tablist" aria-label="Выбор платформы">
                <button
                  onClick={() => setPlatform('mac')}
                  className={clsx(
                    'flex-1 flex items-center justify-center gap-2 px-4 py-2.5 text-sm font-medium transition-colors',
                    platform === 'mac'
                      ? 'glass-light text-white'
                      : 'text-dark-400 hover:text-dark-200'
                  )}
                  role="tab"
                  aria-selected={platform === 'mac'}
                  aria-controls="platform-mac-panel"
                >
                  <Apple className="w-4 h-4" aria-hidden="true" />
                  macOS
                </button>
                <button
                  onClick={() => setPlatform('windows')}
                  className={clsx(
                    'flex-1 flex items-center justify-center gap-2 px-4 py-2.5 text-sm font-medium transition-colors',
                    platform === 'windows'
                      ? 'glass-light text-white'
                      : 'text-dark-400 hover:text-dark-200'
                  )}
                  role="tab"
                  aria-selected={platform === 'windows'}
                  aria-controls="platform-windows-panel"
                >
                  <Monitor className="w-4 h-4" aria-hidden="true" />
                  Windows
                </button>
              </div>

              {/* Instructions content */}
              <div className="p-4 text-sm">
                <p className="font-medium mb-3">📤 Шаг 1: Экспорт из Telegram</p>
                {platform === 'mac' ? (
                  <ol className="list-decimal list-inside space-y-1.5 text-dark-300 mb-4">
                    <li>Откройте <strong>Telegram Desktop</strong></li>
                    <li>Откройте нужный чат</li>
                    <li>Нажмите <strong>⋮</strong> (три точки) в правом верхнем углу</li>
                    <li>Выберите <strong>Export chat history</strong></li>
                    <li>Выберите нужные данные (текст, фото, документы)</li>
                    <li>Формат: <strong>Machine-readable JSON</strong></li>
                    <li>Нажмите <strong>Export</strong></li>
                  </ol>
                ) : (
                  <ol className="list-decimal list-inside space-y-1.5 text-dark-300 mb-4">
                    <li>Откройте <strong>Telegram Desktop</strong></li>
                    <li>Откройте нужный чат</li>
                    <li>Нажмите на <strong>имя чата</strong> вверху (откроется профиль)</li>
                    <li>Нажмите <strong>⋮</strong> (три точки) → <strong>Export chat history</strong></li>
                    <li>Выберите нужные данные (текст, фото, документы)</li>
                    <li>Формат: <strong>Machine-readable JSON</strong></li>
                    <li>Нажмите <strong>Export</strong></li>
                  </ol>
                )}

                <p className="font-medium mb-3">📦 Шаг 2: Сжатие в ZIP (если файл большой)</p>
                {platform === 'mac' ? (
                  <ol className="list-decimal list-inside space-y-1.5 text-dark-300 mb-4">
                    <li>Откройте папку <code className="px-1 py-0.5 rounded glass-light">Telegram Desktop</code></li>
                    <li>Найдите папку <code className="px-1 py-0.5 rounded glass-light">ChatExport_дата</code></li>
                    <li>Правый клик на <strong>result.json</strong></li>
                    <li>Выберите <strong>Сжать "result.json"</strong></li>
                    <li>Получится файл <strong>result.json.zip</strong></li>
                  </ol>
                ) : (
                  <ol className="list-decimal list-inside space-y-1.5 text-dark-300 mb-4">
                    <li>Откройте папку <code className="px-1 py-0.5 rounded glass-light">Telegram Desktop</code></li>
                    <li>Найдите папку <code className="px-1 py-0.5 rounded glass-light">ChatExport_дата</code></li>
                    <li>Правый клик на <strong>result.json</strong></li>
                    <li>Выберите <strong>Отправить → Сжатая ZIP-папка</strong></li>
                    <li>Получится файл <strong>result.zip</strong></li>
                  </ol>
                )}

                <p className="font-medium mb-3">📥 Шаг 3: Загрузка</p>
                <p className="text-dark-300">Загрузите <strong>result.json</strong> или <strong>ZIP-архив</strong> ниже</p>
              </div>
            </div>

            {/* Content wrapper - scrollable */}
            <div className="flex-1 overflow-y-auto space-y-4">
            {/* Drop zone */}
            <div
              onDragOver={handleDragOver}
              onDragLeave={handleDragLeave}
              onDrop={handleDrop}
              className={`
                relative border-2 border-dashed rounded-xl p-8 text-center transition-all
                ${isDragging ? 'border-accent-400 bg-accent-500/10' : 'border-dark-700 hover:border-dark-500'}
                ${file ? 'border-green-500/50 bg-green-500/5' : ''}
              `}
              role="button"
              aria-label="Область для загрузки файла истории чата"
            >
              <input
                type="file"
                accept=".json,.zip,.html,.htm"
                onChange={handleFileChange}
                className="absolute inset-0 w-full h-full opacity-0 cursor-pointer"
                aria-label="Выбрать файл для загрузки"
              />

              {file ? (
                <div className="flex flex-col items-center gap-2">
                  {file.name.toLowerCase().endsWith('.zip') ? (
                    <FileArchive className="w-12 h-12 text-green-400" />
                  ) : file.name.toLowerCase().endsWith('.html') || file.name.toLowerCase().endsWith('.htm') ? (
                    <FileCode className="w-12 h-12 text-green-400" />
                  ) : (
                    <FileJson className="w-12 h-12 text-green-400" />
                  )}
                  <p className="font-medium truncate max-w-full px-4">{file.name}</p>
                  <p className="text-sm text-dark-400">
                    {file.size > 1024 * 1024
                      ? `${(file.size / 1024 / 1024).toFixed(1)} MB`
                      : `${(file.size / 1024).toFixed(1)} KB`
                    }
                  </p>
                </div>
              ) : (
                <div className="flex flex-col items-center gap-2">
                  <Upload className="w-12 h-12 text-dark-500" />
                  <p className="text-dark-300">
                    Перетащите файл сюда или <span className="text-accent-400">выберите</span>
                  </p>
                  <p className="text-sm text-dark-500">Поддерживается: JSON, HTML, ZIP</p>
                </div>
              )}
            </div>

            {/* Result */}
            {result && (
              <motion.div
                initial={{ opacity: 0, y: 10 }}
                animate={{ opacity: 1, y: 0 }}
                className={`mt-4 p-4 rounded-xl ${result.imported > 0 ? 'bg-green-500/10' : 'bg-yellow-500/10'}`}
                role="status"
                aria-live="polite"
              >
                <div className="flex items-start gap-3">
                  {result.imported > 0 ? (
                    <CheckCircle className="w-5 h-5 text-green-400 flex-shrink-0 mt-0.5" aria-hidden="true" />
                  ) : (
                    <AlertCircle className="w-5 h-5 text-yellow-400 flex-shrink-0 mt-0.5" aria-hidden="true" />
                  )}
                  <div className="flex-1 min-w-0">
                    <p className="font-medium">
                      {result.imported > 0 ? 'Импорт завершён' : 'Нет новых сообщений'}
                    </p>
                    <div className="text-sm text-dark-300 mt-1 space-y-0.5">
                      <p>Импортировано: <strong>{result.imported}</strong></p>
                      <p>Пропущено (дубликаты): <strong>{result.skipped}</strong></p>
                      {result.total_errors > 0 && (
                        <p className="text-red-400">Ошибок: {result.total_errors}</p>
                      )}
                    </div>
                  </div>
                </div>
              </motion.div>
            )}

            {/* Transcribe all section */}
            <div className="p-3 rounded-xl bg-accent-500/5 border border-accent-500/20">
              <div className="flex items-start gap-3">
                <Mic className="w-5 h-5 text-accent-400 flex-shrink-0 mt-0.5" />
                <div className="flex-1 min-w-0">
                  <p className="text-sm font-medium text-accent-300 mb-2">Транскрипция медиа</p>
                  {transcribeResult && (
                    <p className="text-xs text-green-400 mb-2">
                      Транскрибировано: {transcribeResult.transcribed} / {transcribeResult.total_found}
                    </p>
                  )}
                  <div className="flex flex-wrap gap-2">
                    <button
                      onClick={() => transcribeMutation.mutate()}
                      disabled={transcribeMutation.isPending}
                      className="px-3 py-1.5 rounded-lg text-xs bg-accent-500/20 text-accent-300 hover:bg-accent-500/30 disabled:opacity-50 transition-colors flex items-center gap-2"
                    >
                      {transcribeMutation.isPending ? (
                        <>
                          <Loader2 className="w-3 h-3 animate-spin" />
                          Транскрибирую...
                        </>
                      ) : (
                        <>
                          <Mic className="w-3 h-3" />
                          Транскрибировать всё
                        </>
                      )}
                    </button>
                    {file && file.name.toLowerCase().endsWith('.zip') && (
                      <button
                        onClick={() => repairMutation.mutate(file)}
                        disabled={repairMutation.isPending}
                        className="px-3 py-1.5 rounded-lg text-xs bg-purple-500/20 text-purple-300 hover:bg-purple-500/30 disabled:opacity-50 transition-colors flex items-center gap-2"
                      >
                        {repairMutation.isPending ? (
                          <>
                            <Loader2 className="w-3 h-3 animate-spin" />
                            Исправляю...
                          </>
                        ) : (
                          <>
                            <Video className="w-3 h-3" />
                            Починить кружочки
                          </>
                        )}
                      </button>
                    )}
                  </div>
                  {repairResult && (
                    <p className="text-xs text-purple-400 mt-2">
                      Исправлено кружков: {repairResult.repaired} / {repairResult.total}
                    </p>
                  )}
                </div>
              </div>
            </div>

            {/* Cleanup section */}
            <div className="p-3 rounded-xl bg-red-500/5 border border-red-500/20">
              <div className="flex items-start gap-3">
                <Trash2 className="w-5 h-5 text-red-400 flex-shrink-0 mt-0.5" />
                <div className="flex-1 min-w-0">
                  <p className="text-sm font-medium text-red-300 mb-2">Очистить неудачный импорт</p>
                  {cleanupResult && (
                    <p className="text-xs text-green-400 mb-2">
                      Удалено: {cleanupResult.deleted} сообщений
                    </p>
                  )}
                  <div className="flex flex-wrap gap-2">
                    <button
                      onClick={() => cleanupMutation.mutate('today')}
                      disabled={cleanupMutation.isPending}
                      className="px-2.5 py-1 rounded-lg text-xs bg-red-500/20 text-red-300 hover:bg-red-500/30 disabled:opacity-50 transition-colors"
                    >
                      {cleanupMutation.isPending ? '...' : 'Сегодняшние'}
                    </button>
                    <button
                      onClick={() => cleanupMutation.mutate('bad')}
                      disabled={cleanupMutation.isPending}
                      className="px-2.5 py-1 rounded-lg text-xs bg-red-500/20 text-red-300 hover:bg-red-500/30 disabled:opacity-50 transition-colors"
                    >
                      Unknown/Медиа
                    </button>
                    <button
                      onClick={() => cleanupMutation.mutate('duplicates')}
                      disabled={cleanupMutation.isPending}
                      className="px-2.5 py-1 rounded-lg text-xs bg-orange-500/20 text-orange-300 hover:bg-orange-500/30 disabled:opacity-50 transition-colors"
                    >
                      Дубликаты
                    </button>
                    <button
                      onClick={() => cleanupMutation.mutate('all_imported')}
                      disabled={cleanupMutation.isPending}
                      className="px-2.5 py-1 rounded-lg text-xs bg-red-500/20 text-red-300 hover:bg-red-500/30 disabled:opacity-50 transition-colors"
                    >
                      Все импортированные
                    </button>
                    <button
                      onClick={() => cleanupMutation.mutate('all')}
                      disabled={cleanupMutation.isPending}
                      className="px-2.5 py-1 rounded-lg text-xs bg-red-600/30 text-red-200 hover:bg-red-600/50 disabled:opacity-50 transition-colors font-medium"
                    >
                      Все из файла
                    </button>
                    <button
                      onClick={() => {
                        if (confirm('⚠️ Удалить ВСЕ сообщения чата? Это нельзя отменить!')) {
                          cleanupMutation.mutate('clear_all');
                        }
                      }}
                      disabled={cleanupMutation.isPending}
                      className="px-2.5 py-1 rounded-lg text-xs bg-red-700/40 text-red-100 hover:bg-red-700/60 disabled:opacity-50 transition-colors font-bold border border-red-500/50"
                    >
                      🗑️ ОЧИСТИТЬ ВСЁ
                    </button>
                  </div>
                </div>
              </div>
            </div>

            {/* Auto-process option */}
            {!result && file && !importMutation.isPending && (
              <label className="flex items-center gap-2 text-sm text-dark-300 cursor-pointer">
                <input
                  type="checkbox"
                  checked={autoProcess}
                  onChange={(e) => setAutoProcess(e.target.checked)}
                  className="w-4 h-4 rounded border-dark-600 bg-dark-800 text-accent-500 focus:ring-accent-500 focus:ring-offset-dark-900"
                />
                <span>Авто-транскрипция голосовых/видео и парсинг документов</span>
                <span className="text-dark-500">(медленно)</span>
              </label>
            )}

            {/* Import progress indicator */}
            {importMutation.isPending && (
              <motion.div
                initial={{ opacity: 0, y: 10 }}
                animate={{ opacity: 1, y: 0 }}
                className="mt-4 p-4 rounded-xl bg-accent-500/10 border border-accent-500/20"
                role="status"
                aria-live="polite"
                aria-busy="true"
              >
                <div className="flex items-center gap-3 mb-3">
                  <div className="relative flex-shrink-0">
                    <Loader2 className="w-6 h-6 text-accent-400 animate-spin" aria-hidden="true" />
                    <div className="absolute inset-0 w-6 h-6 rounded-full border-2 border-accent-400/20" />
                  </div>
                  <div className="flex-1 min-w-0">
                    <p className="font-medium text-accent-300">
                      {progress?.phase === 'reading_file' && 'Чтение файла...'}
                      {progress?.phase === 'importing' && 'Импорт сообщений...'}
                      {progress?.phase === 'processing_media' && 'Обработка медиа...'}
                      {!progress?.phase && 'Импорт в процессе...'}
                    </p>
                    <p className="text-xs text-dark-400">
                      {progress?.total ? (
                        <>
                          {progress.current} / {progress.total} сообщений
                          {progress.imported > 0 && ` • ${progress.imported} импортировано`}
                          {progress.skipped > 0 && ` • ${progress.skipped} пропущено`}
                        </>
                      ) : (
                        'Не закрывайте окно'
                      )}
                    </p>
                  </div>
                </div>

                {/* Progress bar - real progress when available */}
                <div className="h-2 bg-dark-700 rounded-full overflow-hidden">
                  {progress?.total ? (
                    <motion.div
                      className="h-full bg-gradient-to-r from-accent-500 to-accent-400"
                      initial={{ width: 0 }}
                      animate={{ width: `${Math.round((progress.current / progress.total) * 100)}%` }}
                      transition={{ duration: 0.3 }}
                    />
                  ) : (
                    <motion.div
                      className="h-full bg-gradient-to-r from-accent-500 to-accent-400"
                      initial={{ x: '-100%' }}
                      animate={{ x: '100%' }}
                      transition={{ repeat: Infinity, duration: 1.5, ease: 'linear' }}
                      style={{ width: '50%' }}
                    />
                  )}
                </div>

                {/* Current file being processed */}
                {progress?.current_file && (
                  <p className="text-xs text-dark-500 mt-2 truncate">
                    📁 {progress.current_file}
                  </p>
                )}

                {autoProcess && !progress?.current_file && (
                  <p className="text-xs text-dark-400 mt-2">
                    Авто-обработка включена: транскрипция и парсинг файлов...
                  </p>
                )}
              </motion.div>
            )}
            </div>

            {/* Actions */}
            <div className="flex gap-3 mt-6 flex-shrink-0">
              <button
                onClick={handleClose}
                className="flex-1 px-4 py-2.5 rounded-xl glass-light hover:bg-white/10 transition-colors"
              >
                {result ? 'Закрыть' : 'Отмена'}
              </button>
              {!result && (
                <button
                  onClick={handleImport}
                  disabled={!file || importMutation.isPending}
                  className="flex-1 px-4 py-2.5 rounded-xl bg-accent-500 text-white hover:bg-accent-600 disabled:opacity-50 disabled:cursor-not-allowed transition-colors flex items-center justify-center gap-2"
                  aria-busy={importMutation.isPending}
                >
                  {importMutation.isPending ? (
                    <>
                      <Loader2 className="w-4 h-4 animate-spin" aria-hidden="true" />
                      Импорт...
                    </>
                  ) : (
                    <>
                      <Upload className="w-4 h-4" aria-hidden="true" />
                      Импортировать
                    </>
                  )}
                </button>
              )}
            </div>
          </motion.div>
        </motion.div>
      )}
    </AnimatePresence>
  );
}
