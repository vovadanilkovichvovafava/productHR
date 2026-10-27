import { useState, useEffect, useCallback } from "react";
import { motion } from "framer-motion";
import {
  Send,
  Loader2,
  Eye,
  Search,
  Edit3,
  SlidersHorizontal,
} from "lucide-react";
import toast from "react-hot-toast";
import {
  getEmailTemplates,
  previewEmail,
  sendEmail,
  type EmailTemplate,
} from "@/services/api/emailTemplates";

interface SendEmailModalProps {
  entityId: number;
  entityName: string;
  entityEmail?: string;
  vacancyId?: number;
  anchorRect?: DOMRect | null;
  onClose: () => void;
  onSuccess?: () => void;
}

const TYPE_LABELS: Record<string, string> = {
  welcome: "Приветственное",
  rejection: "Отказ",
  interview_invite: "Приглашение на собеседование",
  interview_reminder: "Напоминание",
  offer: "Оффер",
  screening_request: "Скрининг",
  test_assignment: "Тестовое задание",
  follow_up: "Фоллоу-ап",
  custom: "Другое",
};

export default function SendEmailModal({
  entityId,
  entityName,
  entityEmail,
  vacancyId,
  anchorRect,
  onClose,
  onSuccess,
}: SendEmailModalProps) {
  const [templates, setTemplates] = useState<EmailTemplate[]>([]);
  const [selectedTemplateId, setSelectedTemplateId] = useState<number | null>(
    null,
  );
  const [subject, setSubject] = useState("");
  const [body, setBody] = useState("");
  const [loading, setLoading] = useState(true);
  const [previewing, setPreviewing] = useState(false);
  const [sending, setSending] = useState(false);
  const [showPreview, setShowPreview] = useState(false);
  const [templateSearch, setTemplateSearch] = useState("");

  const loadTemplates = useCallback(async () => {
    try {
      const data = await getEmailTemplates();
      setTemplates(data.filter((t) => t.is_active));
    } catch {
      toast.error("Не удалось загрузить шаблоны");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    loadTemplates();
  }, [loadTemplates]);

  useEffect(() => {
    const handleKeyDown = (event: KeyboardEvent) => {
      if (event.key === "Escape" && !sending) {
        onClose();
      }
    };
    document.addEventListener("keydown", handleKeyDown);
    return () => document.removeEventListener("keydown", handleKeyDown);
  }, [onClose, sending]);

  const handleTemplateSelect = async (templateId: number) => {
    setSelectedTemplateId(templateId);
    setPreviewing(true);
    setShowPreview(false);
    try {
      const preview = await previewEmail({
        template_id: templateId,
        entity_id: entityId,
        vacancy_id: vacancyId,
      });
      setSubject(preview.subject);
      setBody(preview.body_html);
    } catch {
      toast.error("Не удалось загрузить превью");
    } finally {
      setPreviewing(false);
    }
  };

  const handleSend = async () => {
    if (!selectedTemplateId) {
      toast.error("Выберите шаблон");
      return;
    }
    if (!entityEmail) {
      toast.error("У кандидата не указан email");
      return;
    }
    setSending(true);
    try {
      const res = await sendEmail({
        template_id: selectedTemplateId,
        entity_id: entityId,
        vacancy_id: vacancyId,
        subject_override: subject,
        body_override: body,
      });
      // B5-fix: бэк возвращает реальный статус. "sent" — реально ушло; иначе
      // письмо лишь поставлено в очередь (SMTP не настроен).
      if (res?.status === "sent") {
        toast.success(`Письмо отправлено на ${entityEmail}`);
      } else {
        toast(`Письмо в очереди: отправка почты ещё не настроена`, { icon: "📭" });
      }
      onSuccess?.();
      onClose();
    } catch {
      toast.error("Ошибка отправки письма");
    } finally {
      setSending(false);
    }
  };

  // Group templates by type
  const filteredTemplates = templates.filter((template) => {
    const query = templateSearch.trim().toLowerCase();
    if (!query) return true;
    return `${template.name} ${TYPE_LABELS[template.template_type || "custom"] || ""}`
      .toLowerCase()
      .includes(query);
  });
  const showTemplatePicker = !selectedTemplateId;
  const demoTemplateLabels = [
    "Холодное письмо",
    "Новое письмо",
    "Отказ",
    "Подтверждение собеседования",
    "Приглашение на вакансию",
  ].filter((label) =>
    label.toLowerCase().includes(templateSearch.trim().toLowerCase()),
  );
  const popoverWidth = 400;
  const popoverHeight = 520; // = max-h поповера ниже; нужно для вертикального клампа
  const viewportWidth =
    typeof window === "undefined" ? 1920 : window.innerWidth;
  const viewportHeight =
    typeof window === "undefined" ? 1080 : window.innerHeight;
  const popoverLeft = anchorRect
    ? Math.min(
        viewportWidth - popoverWidth - 8,
        Math.max(8, anchorRect.left),
      )
    : 710;
  // F4-fix: раньше был только горизонтальный кламп — если кнопка «Письмо» внизу
  // экрана, поповер «съезжал» за нижний край. Теперь держим его в пределах вьюпорта.
  const popoverTop = anchorRect
    ? Math.max(
        8,
        Math.min(viewportHeight - popoverHeight - 8, anchorRect.bottom + 10),
      )
    : 430;

  return (
    <motion.div
      initial={{ opacity: 0 }}
      animate={{ opacity: 1 }}
      exit={{ opacity: 0 }}
      className="fixed inset-0 z-[260]"
    >
      <div className="absolute inset-0 bg-transparent" onClick={onClose} />
      <motion.div
        initial={{ opacity: 0, scale: 0.98, y: -6 }}
        animate={{ opacity: 1, scale: 1, y: 0 }}
        exit={{ opacity: 0, scale: 0.98, y: -6 }}
        transition={{ duration: 0.14, ease: [0.22, 1, 0.36, 1] }}
        style={{ left: popoverLeft, top: popoverTop }}
        className="fixed flex max-h-[520px] w-[400px] flex-col overflow-hidden rounded-[8px] bg-[var(--hf-white)] text-[var(--hf-main-900)] leading-[22px] shadow-[0_0_40px_var(--hf-alpha-300)] dark:bg-[var(--hf-bg-dark)] dark:text-[var(--hf-white)]"
      >
        <div className="px-[16px] pt-[16px] dark:border-[color:var(--hf-white-alpha-10)]">
          <div className="relative">
            <Search
              className="absolute left-[16px] top-1/2 h-[16px] w-[16px] -translate-y-1/2 text-[var(--hf-main-600)]"
              strokeWidth={1.75}
            />
            <input
              value={templateSearch}
              onChange={(e) => setTemplateSearch(e.target.value)}
              placeholder="Поиск..."
              className="h-[40.667px] w-full rounded-[8px] border border-[var(--hf-main-300)] bg-[var(--hf-white)] py-[8px] pl-[42px] pr-[8px] text-[15px] leading-[22px] text-[var(--hf-main-900)] outline-none placeholder:text-[var(--hf-main-600)] focus:border-[var(--hf-main-300)] dark:border-[color:var(--hf-white-alpha-10)] dark:bg-transparent dark:text-[var(--hf-white)]"
              autoFocus
            />
          </div>
          <div className="mt-[16px] flex h-[30px] items-start gap-[24px] border-b border-[var(--hf-ui-border)] text-[15px] font-medium leading-[24px] dark:border-[color:var(--hf-white-alpha-10)]">
            <button className="h-[24px] border-b-[2px] border-[var(--hf-main-900)] text-[var(--hf-main-900)] dark:text-[var(--hf-white)]">
              Общие шаблоны
            </button>
            <button className="h-[24px] text-[var(--hf-main-600)] hover:text-[var(--hf-main-900)] dark:hover:text-[var(--hf-white)]">
              Личные шаблоны
            </button>
          </div>
        </div>

        <div className="min-h-0 flex-1 overflow-y-auto">
          {!entityEmail && (
            <div className="mx-[16px] mt-[12px] rounded-[6px] border border-[color:var(--hf-red-200)] bg-[var(--hf-red-50)] p-[10px] dark:border-[color:var(--hf-status-red-badge)] dark:bg-[var(--hf-status-red-bg)]">
              <p className="text-[14px] leading-[20px] text-[var(--hf-red-600)] dark:text-[var(--hf-status-red)]">
                У кандидата не указан email. Добавьте email через
                "Редактировать" перед отправкой.
              </p>
            </div>
          )}

          {loading ? (
            <div className="flex items-center gap-[8px] px-[16px] py-[18px]">
              <Loader2 className="h-[16px] w-[16px] animate-spin text-[var(--hf-main-600)]" />
              <span className="text-[14px] leading-[20px] text-[var(--hf-main-600)]">
                Загрузка шаблонов...
              </span>
            </div>
          ) : templates.length === 0 && showTemplatePicker ? (
            <div className="px-[8px] py-[8px]">
              {demoTemplateLabels.map((label, index) => (
                <button
                  key={label}
                  type="button"
                  onClick={() =>
                    toast("Создайте шаблон в разделе “Центр отчётов”")
                  }
                  className={`flex h-[40px] w-full items-center ${index === 0 ? "gap-[4px]" : "gap-[12px]"} rounded-[8px] pl-[32px] pr-[8px] text-left text-[15px] leading-[24px] text-[var(--hf-main-900)] transition-colors hover:bg-[var(--hf-main-200)] dark:text-[var(--hf-white)] dark:hover:bg-[var(--hf-white-alpha-06)]`}
                >
                  {index === 0 ? (
                    <span
                      className="relative inline-flex h-[28px] w-[28px] flex-shrink-0 items-center justify-center rounded-full bg-[var(--hf-ui-template-ai)]"
                      aria-hidden="true"
                    >
                      <span className="absolute h-[6px] w-[10px] rotate-[-18deg] rounded-full bg-[var(--hf-white-alpha-90)]" />
                      <span className="absolute h-[6px] w-[10px] rotate-[18deg] rounded-full bg-[var(--hf-white-alpha-70)]" />
                    </span>
                  ) : index === 1 ? (
                    <Edit3
                      className="h-[16px] w-[16px] text-[var(--hf-ui-text-strong)] dark:text-[color:var(--hf-white-alpha-70)]"
                      strokeWidth={1.75}
                    />
                  ) : null}
                  <span className="min-w-0 truncate">{label}</span>
                </button>
              ))}
            </div>
          ) : showTemplatePicker ? (
            <div className="px-[8px] py-[8px]">
              {filteredTemplates.length === 0 && (
                <div className="px-[16px] py-[12px] text-[14px] leading-[20px] text-[var(--hf-main-600)]">
                  Ничего не найдено
                </div>
              )}
              {filteredTemplates.map((template, index) => (
                <button
                  key={template.id}
                  onClick={() => handleTemplateSelect(template.id)}
                  className="flex h-[48px] w-full items-center gap-[12px] rounded-[8px] px-[8px] text-left text-[15px] leading-[24px] text-[var(--hf-main-900)] transition-colors hover:bg-[var(--hf-main-200)] dark:text-[var(--hf-white)] dark:hover:bg-[var(--hf-white-alpha-06)]"
                >
                  {index === 0 ? (
                    <img
                      src="/favicon.ico"
                      alt=""
                      className="h-[28px] w-[28px] rounded-[4px]"
                      onError={(e) => {
                        (e.currentTarget as HTMLImageElement).style.display =
                          "none";
                      }}
                    />
                  ) : (
                    <Edit3
                      className="h-[18px] w-[18px] text-[var(--hf-ui-text-strong)] dark:text-[color:var(--hf-white-alpha-70)]"
                      strokeWidth={1.75}
                    />
                  )}
                  <span className="min-w-0 truncate">{template.name}</span>
                </button>
              ))}
            </div>
          ) : (
            <div className="space-y-[14px] px-[16px] py-[14px]">
              <div className="flex items-center justify-between">
                <div className="min-w-0">
                  <p className="truncate text-[15px] font-medium leading-[22px] text-[var(--hf-main-900)] dark:text-[var(--hf-white)]">
                    {entityName}
                  </p>
                  <p className="truncate text-[13px] leading-[18px] text-[var(--hf-main-600)]">
                    {entityEmail || "email не указан"}
                  </p>
                </div>
                <button
                  onClick={() => {
                    setSelectedTemplateId(null);
                    setSubject("");
                    setBody("");
                  }}
                  className="inline-flex h-[30px] items-center rounded-[6px] px-[8px] text-[13px] leading-[18px] text-[var(--hf-ui-text-soft)] hover:bg-[var(--hf-black-alpha-04)] hover:text-[var(--hf-main-900)] dark:hover:bg-[var(--hf-white-alpha-06)] dark:hover:text-[var(--hf-white)]"
                >
                  Сменить
                </button>
              </div>

              <div>
                <label className="mb-[6px] block text-[14px] leading-[20px] text-[var(--hf-ui-text-muted)] dark:text-[color:var(--hf-white-alpha-55)]">
                  Тема письма
                </label>
                <input
                  value={subject}
                  onChange={(e) => setSubject(e.target.value)}
                  className="h-[40px] w-full rounded-[6px] border border-[var(--hf-ui-border)] bg-[var(--hf-white)] px-[12px] text-[15px] leading-[22px] text-[var(--hf-main-900)] outline-none placeholder:text-[var(--hf-main-600)] focus:border-[var(--hf-cyan-500)] dark:border-[color:var(--hf-white-alpha-10)] dark:bg-transparent dark:text-[var(--hf-white)]"
                  placeholder="Тема..."
                />
              </div>

              <div>
                <div className="mb-[6px] flex items-center justify-between">
                  <label className="text-[14px] leading-[20px] text-[var(--hf-ui-text-muted)] dark:text-[color:var(--hf-white-alpha-55)]">
                    Текст письма
                  </label>
                  <button
                    onClick={() => setShowPreview(!showPreview)}
                    className="flex items-center gap-[4px] text-[13px] leading-[18px] text-[var(--hf-cyan-500)] hover:text-[var(--hf-ui-link-alt)]"
                  >
                    <Eye className="h-[14px] w-[14px]" />
                    {showPreview ? "Редактор" : "Превью"}
                  </button>
                </div>
                {previewing ? (
                  <div className="flex items-center justify-center py-[28px]">
                    <Loader2 className="h-[20px] w-[20px] animate-spin text-[var(--hf-main-600)]" />
                  </div>
                ) : showPreview ? (
                  <div
                    className="min-h-[180px] max-h-[260px] w-full overflow-y-auto rounded-[6px] border border-[var(--hf-ui-border)] bg-[var(--hf-white)] p-[12px] text-[15px] leading-[22px] text-[var(--hf-main-900)] dark:border-[color:var(--hf-white-alpha-10)] dark:bg-transparent dark:text-[var(--hf-white)]"
                    dangerouslySetInnerHTML={{ __html: body }}
                  />
                ) : (
                  <textarea
                    value={body
                      .replace(/<br\s*\/?>/gi, "\n")
                      .replace(/<[^>]+>/g, "")}
                    onChange={(e) => {
                      const text = e.target.value;
                      setBody(
                        text
                          .split("\n")
                          .map((l) => l || "<br>")
                          .join("<br>"),
                      );
                    }}
                    rows={8}
                    className="min-h-[180px] w-full resize-none rounded-[6px] border border-[var(--hf-ui-border)] bg-[var(--hf-white)] px-[12px] py-[10px] text-[15px] leading-[22px] text-[var(--hf-main-900)] outline-none placeholder:text-[var(--hf-main-600)] focus:border-[var(--hf-cyan-500)] dark:border-[color:var(--hf-white-alpha-10)] dark:bg-transparent dark:text-[var(--hf-white)]"
                    placeholder="Текст письма..."
                  />
                )}
              </div>
            </div>
          )}
        </div>

        {showTemplatePicker ? (
          <button
            type="button"
            onClick={() =>
              toast("Настройка шаблонов доступна в Центре отчётов")
            }
            className="flex h-[52.667px] flex-shrink-0 items-center gap-[8px] border-t border-[var(--hf-ui-divider-soft)] px-[16px] text-left text-[15px] leading-[20px] text-[var(--hf-main-600)] transition-colors hover:bg-[var(--hf-ui-hover)] hover:text-[var(--hf-main-900)] dark:border-[color:var(--hf-white-alpha-10)] dark:hover:bg-[var(--hf-white-alpha-06)] dark:hover:text-[var(--hf-white)]"
          >
            <SlidersHorizontal
              className="h-[16px] w-[16px]"
              strokeWidth={1.6}
            />
            Настроить шаблоны писем
          </button>
        ) : (
          <div className="flex h-[58px] flex-shrink-0 items-center justify-end gap-[8px] border-t border-[var(--hf-ui-divider-soft)] bg-[var(--hf-ui-hover)] px-[16px] dark:border-[color:var(--hf-white-alpha-10)] dark:bg-[var(--hf-bg-dark)]">
            <button
              onClick={onClose}
              className="inline-flex h-[36px] items-center rounded-[6px] px-[12px] text-[14px] font-medium leading-[20px] text-[var(--hf-ui-text-soft)] hover:bg-[var(--hf-black-alpha-04)] hover:text-[var(--hf-main-900)] dark:text-[color:var(--hf-white-alpha-55)] dark:hover:bg-[var(--hf-white-alpha-06)] dark:hover:text-[var(--hf-white)]"
            >
              Отмена
            </button>
            <button
              onClick={handleSend}
              disabled={sending || !selectedTemplateId || !entityEmail}
              className="inline-flex h-[36px] items-center gap-[8px] rounded-[6px] bg-[var(--hf-main-900)] px-[14px] text-[14px] font-semibold leading-[20px] text-[var(--hf-white)] transition-colors hover:bg-[var(--hf-main-800)] disabled:cursor-not-allowed disabled:bg-[var(--hf-btn-disabled-bg)] disabled:text-[var(--hf-main-600)] disabled:opacity-100 disabled:hover:bg-[var(--hf-btn-disabled-bg)] dark:bg-[var(--hf-white)] dark:text-[var(--hf-main-900)] dark:hover:bg-[var(--hf-white-alpha-90)] dark:disabled:bg-[var(--hf-white-alpha-08)] dark:disabled:text-[color:var(--hf-white-alpha-35)]"
            >
              {sending ? (
                <Loader2 className="h-[16px] w-[16px] animate-spin" />
              ) : (
                <Send className="h-[16px] w-[16px]" />
              )}
              Отправить
            </button>
          </div>
        )}
      </motion.div>
    </motion.div>
  );
}
