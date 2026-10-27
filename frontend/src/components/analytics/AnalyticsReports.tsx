import { pluralRu } from '@/utils/plural';
import clsx from 'clsx';
import { ChevronDown, ArrowRight, UserCheck, UserPlus } from 'lucide-react';
import { BAR_COLORS } from './analyticsCatalog';
import type {
  TimeToFillReport, FunnelReport, FunnelByRecruiterReport, RejectionsReport,
  SourceReport, SourcersReport, MovementReport,
} from './analyticsTypes';

// Содержимое отчётов «Аналитики» и мелкие общие части (вынесено из
// DashboardPage, 20.10.2026, без изменений).

// ===== SHARED COMPONENTS =====

export function FilterSelect({
  label,
  value,
  open,
  onClick,
}: {
  label: string;
  value: string;
  open: boolean;
  onClick: () => void;
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      className={clsx('hf-analytics-filter', open && 'hf-analytics-filter-open')}
    >
      {label && <span>{label}</span>}
      <strong>{value}</strong>
      <ChevronDown className="hf-analytics-filter-chevron" />
    </button>
  );
}

function KPICard({ value, label, sub }: { value: string | number; label: string; sub?: string }) {
  return (
    <div className="hf-analytics-kpi">
      <div className="hf-analytics-kpi-value">{value}</div>
      <div className="hf-analytics-kpi-label">{label}</div>
      {sub && <div className="hf-analytics-kpi-sub">{sub}</div>}
    </div>
  );
}

function HBar({ width, color, value, label }: { width: number; color: string; value: number | string; label: string }) {
  return (
    <div className="hf-analytics-bar-row">
      <div className="hf-analytics-bar-label">{label}</div>
      <div className="hf-analytics-bar-track">
        <div
          className="hf-analytics-bar"
          style={{
            width: `${Math.max(width, 2)}%`,
            backgroundColor: color,
          }}
        />
        <span className="hf-analytics-bar-value">{value}</span>
      </div>
    </div>
  );
}

function SectionTitle({ children }: { children: React.ReactNode }) {
  return <h3 className="hf-analytics-section-title">{children}</h3>;
}

function SectionDesc({ children }: { children: React.ReactNode }) {
  return <p className="hf-analytics-section-desc">{children}</p>;
}

function Divider() {
  return <div className="hf-analytics-divider" />;
}

function LegendItem({ color, label, count }: { color: string; label: string; count: number }) {
  return (
    <div className="hf-analytics-legend-item">
      <div className="hf-analytics-legend-name">
        <div className="hf-analytics-legend-dot" style={{ backgroundColor: color }} />
        <span>{label}</span>
      </div>
      <span className="hf-analytics-legend-count">{count}</span>
    </div>
  );
}

// ===== TTF REPORT =====

export function TTFContent({ data }: { data: TimeToFillReport }) {
  const { summary, stage_timings, last_closings } = data;
  const maxDays = Math.max(...stage_timings.map(s => s.avg_days), 1);

  return (
    <>
      {/* KPI row */}
      <div className="hf-analytics-kpi-row">
        <KPICard
          value={summary.avg_days_to_close != null ? `${summary.avg_days_to_close}` : '—'}
          label="Ср. срок закрытия, дн"
        />
        <KPICard
          value={summary.avg_delay_days != null ? `${summary.avg_delay_days}` : '—'}
          label="Ср. просрочка, дн"
        />
        <KPICard
          value={`${summary.closed_positions}/${summary.total_positions}`}
          label="Закрытых позиций"
        />
      </div>

      <Divider />

      {/* Stage timings bars */}
      <SectionTitle>Среднее время на этапе</SectionTitle>
      <SectionDesc>Среднее время нахождения кандидатов на каждом этапе воронки</SectionDesc>

      <div>
        {stage_timings.map(st => (
          <HBar
            key={st.stage}
            width={(st.avg_days / maxDays) * 100}
            color={BAR_COLORS.primary}
            value={st.avg_days > 0 ? `${st.avg_days} дн` : '0 дн'}
            label={st.label}
          />
        ))}
      </div>

      {/* Last closings */}
      {last_closings.length > 0 && (
        <>
          <Divider />
          <SectionTitle>Последние закрытия</SectionTitle>
          <div className="hf-analytics-closing-list">
            {last_closings.map((lc, i) => (
              <div key={i} className="hf-analytics-closing">
                <UserCheck className="hf-analytics-closing-icon" />
                <div className="hf-analytics-closing-main">
                  <div className="hf-analytics-closing-name">{lc.candidate_name}</div>
                  <div className="hf-analytics-closing-vacancy">{lc.vacancy_title}</div>
                  {lc.recruiter_name && (
                    <div className="hf-analytics-closing-recruiter">{lc.recruiter_name}</div>
                  )}
                </div>
                <div className="hf-analytics-closing-side">
                  <div className="hf-analytics-closing-days">
                    {lc.days_to_close != null ? `${lc.days_to_close} дн` : '—'}
                  </div>
                  {lc.closed_date && (
                    <div className="hf-analytics-closing-date">{lc.closed_date}</div>
                  )}
                </div>
              </div>
            ))}
          </div>
        </>
      )}
    </>
  );
}

// ===== FUNNEL =====

export function FunnelContent({ data }: { data: FunnelReport }) {
  const maxCount = Math.max(...data.stages.map(s => s.candidate_count), 1);
  const maxRej = Math.max(...data.stages.map(s => s.rejection_count), 1);
  const legendColors = [
    BAR_COLORS.green,
    BAR_COLORS.red,
    BAR_COLORS.primary,
    BAR_COLORS.blue,
    BAR_COLORS.purple,
    BAR_COLORS.orange,
  ];

  return (
    <div className="hf-analytics-split">
      {/* Chart area */}
      <div className="hf-analytics-chart-main">
        {/* Headers */}
        <div className="hf-analytics-chart-head">
          <div className="hf-analytics-chart-label-spacer" />
          <div className="hf-analytics-chart-head-cell">
            Кандидаты
          </div>
          <div className="hf-analytics-chart-head-side">
            Отказы
          </div>
        </div>

        {/* Bars */}
        <div>
          {data.stages.map(st => (
            <div key={st.stage} className="hf-analytics-funnel-row">
              <div className="hf-analytics-funnel-label">
                {st.label}
              </div>
              {/* Candidate bar */}
              <div className="hf-analytics-funnel-track">
                <div
                  className="hf-analytics-funnel-bar"
                  style={{
                    width: `${Math.max((st.candidate_count / maxCount) * 100, 1)}%`,
                    backgroundColor: BAR_COLORS.green,
                  }}
                />
                {st.candidate_count > 0 && (
                  <span className="hf-analytics-funnel-value">{st.candidate_count}</span>
                )}
              </div>
              {/* Rejection bar */}
              <div className="hf-analytics-funnel-rejections">
                {st.rejection_count > 0 && (
                  <>
                    <div
                      className="hf-analytics-funnel-bar"
                      style={{
                        width: `${(st.rejection_count / maxRej) * 100}%`,
                        backgroundColor: BAR_COLORS.gray_light,
                      }}
                    />
                    <span className="hf-analytics-funnel-value">{st.rejection_count}</span>
                  </>
                )}
              </div>
            </div>
          ))}
        </div>
      </div>

      {/* Right legend */}
      <div className="hf-analytics-legend">
        <div className="hf-analytics-legend-head">
          <span className="hf-analytics-legend-title">Все</span>
          <span className="hf-analytics-legend-total">{data.total_candidates}</span>
        </div>
        {data.sources.map((s, i) => (
          <LegendItem
            key={i}
            color={legendColors[i % legendColors.length]}
            label={s.source === 'unknown' ? 'Не указан' : s.source}
            count={s.count}
          />
        ))}

        {data.rejection_reasons.length > 0 && (
          <div className="hf-analytics-legend-section">
            <div className="hf-analytics-legend-head">
              <span className="hf-analytics-legend-title">Отказы</span>
              <span className="hf-analytics-legend-total">{data.total_rejections}</span>
            </div>
            {data.rejection_reasons.map((r, i) => (
              <LegendItem
                key={i}
                color={i === 0 ? BAR_COLORS.gray_light : i === 1 ? BAR_COLORS.gray_medium : BAR_COLORS.gray_dark}
                label={r.reason}
                count={r.count}
              />
            ))}
          </div>
        )}
      </div>
    </div>
  );
}

// ===== FUNNEL BY RECRUITER =====

export function FunnelByRecruiterContent({ data }: { data: FunnelByRecruiterReport }) {
  return (
    <>
      <FunnelContent data={data.summary} />

      {data.by_recruiter.length > 0 && (
        <>
          <Divider />
          <SectionTitle>По рекрутерам</SectionTitle>
          <div className="hf-analytics-recruiter-list">
            {data.by_recruiter.map(rec => {
              const maxCount = Math.max(...rec.stages.map(s => s.candidate_count), 1);
              return (
                <div key={rec.recruiter_id} className="hf-analytics-recruiter-card">
                  <div className="hf-analytics-recruiter-head">
                    <div className="hf-analytics-recruiter-person">
                      <div className="hf-analytics-recruiter-avatar">
                        {rec.recruiter_name.charAt(0)}
                      </div>
                      <span className="hf-analytics-recruiter-name">{rec.recruiter_name}</span>
                    </div>
                    <div className="hf-analytics-recruiter-meta">
                      {rec.total_candidates} {pluralRu(rec.total_candidates, 'кандидат', 'кандидата', 'кандидатов')} · {rec.total_rejections} {pluralRu(rec.total_rejections, 'отказ', 'отказа', 'отказов')}
                    </div>
                  </div>
                  <div>
                    {rec.stages.map(st => (
                      <div key={st.stage} className="hf-analytics-recruiter-row">
                        <div className="hf-analytics-recruiter-stage">{st.label}</div>
                        <div className="hf-analytics-funnel-track">
                          <div
                            className="h-5 rounded-sm"
                            style={{
                              width: `${Math.max((st.candidate_count / maxCount) * 100, 1)}%`,
                              backgroundColor: BAR_COLORS.green,
                            }}
                          />
                          {st.candidate_count > 0 && (
                            <span className="hf-analytics-funnel-value">{st.candidate_count}</span>
                          )}
                        </div>
                      </div>
                    ))}
                  </div>
                </div>
              );
            })}
          </div>
        </>
      )}
    </>
  );
}

// ===== REJECTIONS =====

export function RejectionsContent({ data }: { data: RejectionsReport }) {
  const maxCount = Math.max(...data.by_stage.map(s => s.count), 1);

  return (
    <div className="hf-analytics-split">
      <div className="hf-analytics-chart-main">
        <SectionTitle>Отказы по этапам</SectionTitle>
        <SectionDesc>На каком этапе кандидаты получают отказ</SectionDesc>

        <div>
          {data.by_stage.map(st => (
            <HBar
              key={st.stage}
              width={(st.count / maxCount) * 100}
              color={BAR_COLORS.red}
              value={st.count}
              label={st.label}
            />
          ))}
        </div>
      </div>

      {/* Right legend */}
      <div className="hf-analytics-legend">
        <div className="hf-analytics-legend-head">
          <span className="hf-analytics-legend-title">Всего отказов</span>
          <span className="hf-analytics-legend-total">{data.total_rejections}</span>
        </div>
        {data.top_reasons.map((r, i) => (
          <LegendItem
            key={i}
            color={i === 0 ? BAR_COLORS.gray_light : i === 1 ? BAR_COLORS.gray_medium : BAR_COLORS.gray_dark}
            label={r.reason}
            count={r.count}
          />
        ))}
      </div>
    </div>
  );
}

// ===== SOURCES =====

export function SourcesContent({ data }: { data: SourceReport }) {
  const maxCount = Math.max(...data.sources.map(s => s.count), 1);
  const colors = [
    BAR_COLORS.green,
    BAR_COLORS.red,
    BAR_COLORS.primary,
    BAR_COLORS.blue,
    BAR_COLORS.purple,
    BAR_COLORS.orange,
  ];

  return (
    <>
      <div className="hf-analytics-kpi-row hf-analytics-kpi-row-compact">
        <KPICard value={data.total_candidates} label="Всего кандидатов" />
        <KPICard value={data.sources.length} label="Источников" />
      </div>

      <SectionTitle>Распределение по источникам</SectionTitle>
      <div className="hf-analytics-bars">
        {data.sources.map((s, i) => (
          <HBar
            key={i}
            width={(s.count / maxCount) * 100}
            color={colors[i % colors.length]}
            value={s.count}
            label={s.source === 'unknown' ? 'Не указан' : s.source}
          />
        ))}
      </div>
    </>
  );
}

// ===== SOURCERS =====

/** Кого привели сорсеры и что из этого вышло.
 *
 * Сорсер — внешний человек без доступа в систему, поэтому в базе он живёт
 * меткой с kind='sourcer', а не пользователем. Считается по связям
 * кандидат↔метка, отдельного хранилища нет.
 *
 * Оформление намеренно повторяет «Воронку по рекрутерам»: те же карточки с
 * аватаркой и полосами, чтобы отчёт не выглядел чужим на этой странице.
 */
export function SourcersContent({ data }: { data: SourcersReport }) {
  if (data.items.length === 0) {
    return (
      <div className="hf-analytics-empty-state">
        <UserPlus className="hf-analytics-empty-icon" />
        <h3>Сорсеров пока нет</h3>
        <p>
          Отметьте метку как сорсера на карточке кандидата: в списке меток
          выберите тип «Сорсер». После этого здесь появится статистика.
        </p>
      </div>
    );
  }

  const conversion = data.total_brought
    ? Math.round((data.total_hired / data.total_brought) * 100)
    : 0;

  return (
    <>
      <div className="hf-analytics-kpi-row hf-analytics-kpi-row-compact">
        <KPICard value={data.total_brought} label="Приведено кандидатов" />
        <KPICard value={data.items.length} label="Сорсеров" />
        <KPICard value={`${conversion}%`} label="Дошли до найма" />
      </div>

      <SectionTitle>По сорсерам</SectionTitle>
      <div className="hf-analytics-recruiter-list">
        {data.items.map((s) => {
          // Полосы меряем от «привёл» этого же сорсера: интересна его
          // собственная воронка, а не сравнение с самым результативным.
          const rows = [
            { label: 'Привёл', value: s.brought, color: BAR_COLORS.primary },
            { label: 'В работе', value: s.in_work, color: BAR_COLORS.blue },
            { label: 'Дошли до оффера', value: s.reached_offer, color: BAR_COLORS.purple },
            { label: 'Наняты', value: s.hired, color: BAR_COLORS.green },
            { label: 'Отказ', value: s.rejected, color: BAR_COLORS.red },
          ];
          return (
            <div key={s.tag_id} className="hf-analytics-recruiter-card">
              <div className="hf-analytics-recruiter-head">
                <div className="hf-analytics-recruiter-person">
                  <div
                    className="hf-analytics-recruiter-avatar"
                    style={{ backgroundColor: s.color }}
                  >
                    {s.name.charAt(0)}
                  </div>
                  <span className="hf-analytics-recruiter-name">
                    {s.name}
                    {s.archived && (
                      <span className="hf-analytics-sourcer-archived" title="Метка убрана из списка выбора, но история сохранена">
                        не в списке
                      </span>
                    )}
                  </span>
                </div>
                <div className="hf-analytics-recruiter-meta">
                  конверсия {s.conversion}%
                </div>
              </div>
              <div>
                {rows.map((r) => (
                  <div key={r.label} className="hf-analytics-recruiter-row">
                    <div className="hf-analytics-recruiter-stage">{r.label}</div>
                    <div className="hf-analytics-funnel-track">
                      <div
                        className="h-5 rounded-sm"
                        style={{
                          width: `${Math.max((r.value / Math.max(s.brought, 1)) * 100, 1)}%`,
                          backgroundColor: r.color,
                        }}
                      />
                      {r.value > 0 && (
                        <span className="hf-analytics-funnel-value">{r.value}</span>
                      )}
                    </div>
                  </div>
                ))}
              </div>
            </div>
          );
        })}
      </div>
    </>
  );
}

// ===== MOVEMENT =====

export function MovementContent({ data }: { data: MovementReport }) {
  const maxCount = Math.max(...data.movements.map(m => m.count), 1);

  return (
    <>
      <div className="mb-6">
        <KPICard value={data.total_movements} label="Всего перемещений" />
      </div>

      <SectionTitle>Перемещения между этапами</SectionTitle>
      <div className="hf-analytics-bars">
        {data.movements.map((m, i) => {
          const color = m.to_stage === 'rejected' ? BAR_COLORS.red
            : m.to_stage === 'hired' ? BAR_COLORS.green
            : BAR_COLORS.primary;
          return (
            <div key={i} className="hf-analytics-bar-row">
              <div className="hf-analytics-movement-label">
                <span className="truncate">{m.from_label}</span>
                <ArrowRight className="hf-analytics-movement-icon" />
                <span className="truncate">{m.to_label}</span>
              </div>
              <div className="hf-analytics-bar-track">
                <div
                  className="h-7 rounded-sm"
                  style={{
                    width: `${Math.max((m.count / maxCount) * 100, 2)}%`,
                    backgroundColor: color,
                  }}
                />
                <span className="hf-analytics-bar-value">{m.count}</span>
              </div>
            </div>
          );
        })}
      </div>
    </>
  );
}
