import { useEffect, useState } from "react";
import { Download, ExternalLink, FileText, Loader2 } from "lucide-react";
import { getEntityFiles, type EntityFile } from "@/services/api/entities";
import { buildResumeSources } from "./candidateDetail/model";

/**
 * Резюме кандидата прямо в окне сравнения дублей: САМ загруженный файл (PDF в
 * рамке, сканы страниц картинками), а не только распарсенный текст.
 *
 * Зачем: решение «тот же человек или нет» принимается по резюме, а в окне
 * сравнения его не было — рекрутёр видел только текстовую выжимку (а у анкет из
 * расширения и её часто нет) и уходил открывать карточку в соседней вкладке.
 *
 * Файлы тянутся лениво и кэшируются на ВРЕМЯ ОДНОЙ проверки: карусель постоянно
 * возвращается к той же анкете, дёргать API на каждый свайп незачем. Кэш сбрасывает
 * окно сравнения при открытии — иначе загруженное тем временем резюме не появилось
 * бы до перезагрузки страницы.
 */

const filesCache = new Map<number, EntityFile[]>();

/** Сбросить кэш файлов (вызывается при открытии окна сравнения). */
export function clearCompareFilesCache(): void {
  filesCache.clear();
}

export type ResumeTextParts = {
  resumes: Array<{ title?: string; subtitle?: string; sections?: Array<{ title?: string; lines?: string[] }> }>;
  text: string;
  extra: { experience: string; skills: string; languages: string; education: string };
};

function fmtDate(iso?: string | null): string {
  if (!iso) return "";
  const d = new Date(iso);
  return Number.isNaN(d.getTime())
    ? ""
    : d.toLocaleDateString("ru", { day: "numeric", month: "short", year: "numeric" });
}

function TextRow({ label, value }: { label: string; value: string }) {
  if (!value) return null;
  return (
    <div className="rounded-lg bg-slate-50 p-2.5 text-xs">
      <div className="text-slate-500 mb-0.5">{label}</div>
      <div className="text-slate-800 leading-relaxed whitespace-pre-wrap">{value}</div>
    </div>
  );
}

/** Распарсенный/структурный текст резюме — то, что показывалось в окне раньше. */
function ResumeText({ parts }: { parts: ResumeTextParts }) {
  const { resumes, text, extra } = parts;
  const hasExtra = !!(extra.experience || extra.skills || extra.languages || extra.education);
  if (resumes.length === 0 && !text && !hasExtra) {
    return <div className="text-sm text-slate-400">—</div>;
  }
  return (
    <div className="space-y-2">
      {resumes.map((r, i) => (
        <div key={i} className="rounded-lg bg-slate-50 p-2.5 text-xs">
          {r.title && <div className="font-medium text-slate-800">{r.title}</div>}
          {r.subtitle && <div className="text-slate-500">{r.subtitle}</div>}
          {(r.sections || []).map((s, j) => (
            <div key={j} className="mt-1.5">
              {s.title && <div className="text-slate-500">{s.title}</div>}
              {(s.lines || []).length > 0 && (
                <div className="text-slate-800 leading-relaxed whitespace-pre-wrap">
                  {(s.lines || []).join("\n")}
                </div>
              )}
            </div>
          ))}
        </div>
      ))}
      {text && (
        <div className="rounded-lg bg-slate-50 p-2.5 text-xs whitespace-pre-wrap text-slate-800">{text}</div>
      )}
      {resumes.length === 0 && !text && (
        <>
          <TextRow label="Опыт" value={extra.experience} />
          <TextRow label="Навыки" value={extra.skills} />
          <TextRow label="Языки" value={extra.languages} />
          <TextRow label="Образование" value={extra.education} />
        </>
      )}
    </div>
  );
}

type Tab =
  | { key: string; label: string; date?: string | null; kind: "pdf"; file: EntityFile }
  | { key: string; label: string; date?: string | null; kind: "images"; files: EntityFile[] }
  | { key: string; label: string; date?: string | null; kind: "text" };

export function CompareResumePreview({
  entityId,
  extraData,
  parts,
}: {
  entityId?: number;
  extraData?: Record<string, unknown>;
  parts: ResumeTextParts;
}) {
  const [files, setFiles] = useState<EntityFile[] | null>(
    entityId != null ? (filesCache.get(entityId) ?? null) : [],
  );
  const [loading, setLoading] = useState(false);
  const [active, setActive] = useState(0);
  const [page, setPage] = useState(0);

  useEffect(() => {
    if (entityId == null || filesCache.has(entityId)) return;
    let alive = true;
    setLoading(true);
    getEntityFiles(entityId)
      .then((data) => {
        filesCache.set(entityId, data);
        if (alive) setFiles(data);
      })
      .catch(() => {
        // Нет доступа к файлам или ошибка сети — молча показываем текстовую
        // версию: сравнение важнее, чем сообщение об отсутствующем вложении.
        if (alive) setFiles([]);
      })
      .finally(() => {
        if (alive) setLoading(false);
      });
    return () => {
      alive = false;
    };
  }, [entityId]);

  useEffect(() => {
    setActive(0);
    setPage(0);
  }, [entityId]);

  const sources = buildResumeSources(files || [], extraData);
  const resumeFiles = (files || []).filter((f) => f.file_type === "resume");
  const imageFiles = resumeFiles.filter((f) => f.mime_type?.startsWith("image/"));

  const tabs: Tab[] = [];
  for (const s of sources) {
    if (s.kind === "pdf" && s.file) {
      tabs.push({ key: `pdf-${s.file.id}`, label: "Файл", date: s.file.created_at, kind: "pdf", file: s.file });
    } else if (s.kind === "images" && imageFiles.length > 0) {
      tabs.push({ key: "images", label: "Сканы", date: imageFiles[0]?.created_at, kind: "images", files: imageFiles });
    }
  }
  tabs.push({ key: "text", label: "Текст", kind: "text" });

  const cur = tabs[Math.min(active, tabs.length - 1)];
  const pages = cur.kind === "images" ? cur.files : [];

  return (
    <div className="mt-3 pt-3 border-t border-slate-200">
      <div className="flex items-center justify-between gap-2 mb-2 flex-wrap">
        <div className="text-[11px] uppercase tracking-wide text-slate-400">Резюме</div>
        <div className="flex items-center gap-1">
          {loading && <Loader2 className="w-3 h-3 animate-spin text-slate-400" />}
          {tabs.length > 1 &&
            tabs.map((t, i) => (
              <button
                key={t.key}
                onClick={() => {
                  setActive(i);
                  setPage(0);
                }}
                // Окно сравнения светлое: активная вкладка — белая «таблетка» с
                // рамкой, а не тёмный прямоугольник (он выбивался из модалки).
                className={`rounded-md px-2 py-0.5 text-[11px] font-medium transition-colors border ${
                  i === active
                    ? "border-slate-300 bg-white text-slate-800 shadow-sm"
                    : "border-transparent text-slate-500 hover:bg-slate-100"
                }`}
              >
                {t.label}
                {t.date ? ` · ${fmtDate(t.date)}` : ""}
              </button>
            ))}
        </div>
      </div>

      {cur.kind === "pdf" && (
        <div>
          <iframe
            key={cur.file.id}
            src={`/api/entities/${entityId}/files/${cur.file.id}/download#toolbar=0&navpanes=0`}
            title={cur.file.file_name}
            className="w-full h-[420px] rounded-lg border border-slate-200 bg-white"
          />
          <div className="flex items-center justify-between gap-2 mt-1.5">
            <span className="inline-flex items-center gap-1 text-[11px] text-slate-400 min-w-0">
              <FileText className="w-3 h-3 shrink-0" />
              <span className="truncate">{cur.file.file_name}</span>
            </span>
            <span className="flex gap-2 shrink-0">
              <a
                href={`/api/entities/${entityId}/files/${cur.file.id}/download`}
                target="_blank"
                rel="noopener noreferrer"
                className="inline-flex items-center gap-1 text-[11px] text-slate-500 hover:text-slate-800"
              >
                <ExternalLink className="w-3 h-3" /> Открыть
              </a>
              <a
                href={`/api/entities/${entityId}/files/${cur.file.id}/download?download=1`}
                download={cur.file.file_name}
                className="inline-flex items-center gap-1 text-[11px] text-slate-500 hover:text-slate-800"
              >
                <Download className="w-3 h-3" /> Скачать
              </a>
            </span>
          </div>
        </div>
      )}

      {cur.kind === "images" && pages.length > 0 && (
        <div>
          <img
            src={`/api/entities/${entityId}/files/${pages[Math.min(page, pages.length - 1)].id}/download`}
            alt={`Резюме, страница ${Math.min(page, pages.length - 1) + 1}`}
            className="w-full rounded-lg border border-slate-200 bg-white"
          />
          {pages.length > 1 && (
            <div className="flex items-center justify-center gap-1.5 mt-1.5">
              {pages.map((p, i) => (
                <button
                  key={p.id}
                  onClick={() => setPage(i)}
                  aria-label={`Страница ${i + 1}`}
                  className={`h-1.5 rounded-full transition-all ${
                    i === Math.min(page, pages.length - 1) ? "w-4 bg-slate-700" : "w-1.5 bg-slate-300"
                  }`}
                />
              ))}
            </div>
          )}
        </div>
      )}

      {cur.kind === "text" && <ResumeText parts={parts} />}
    </div>
  );
}

export default CompareResumePreview;
