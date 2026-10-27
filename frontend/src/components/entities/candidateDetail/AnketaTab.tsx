import { AnketaResponses } from "@/features/forms/AnketaResponses";
import type { FormDispatchInfo } from "@/services/api/forms";
import ImportedParticipations, { readParticipations } from "@/components/entities/candidateDetail/ImportedParticipations";

// Вкладка «Анкета» в панели кандидата: импортированные прохождения (ClickUp-архив)
// и ответы на анкеты Enceladus (вынесено из AllCandidatesPage, 20.10.2026).

export function AnketaTab({
  activeIndex,
  participations,
  nativeDispatches,
  onDispatchDeleted,
}: {
  activeIndex: number;
  participations: ReturnType<typeof readParticipations>;
  nativeDispatches: (FormDispatchInfo & {
    source_entity_id?: number;
    source_name?: string | null;
  })[];
  onDispatchDeleted?: (dispatchId: number) => void;
}) {
  // Чистый рендерер: фетч диспатчей + отметка «просмотрено» теперь в родителе
  // (там же, где строится ряд вкладок) — вкладке нужно только знать, какая
  // именно вкладка активна (участие 0..P-1, нативная — P).
  const hasNative = nativeDispatches.length > 0;
  const nativeTabIndex = participations.length;
  if (hasNative && activeIndex === nativeTabIndex) {
    return <AnketaResponses dispatches={nativeDispatches} onDeleted={onDispatchDeleted} />;
  }
  if (participations.length > 0) {
    const p = participations[Math.min(activeIndex, participations.length - 1)];
    return p ? <ImportedParticipations participations={[p]} /> : null;
  }
  // Ни прохождений, ни нативных анкет — пустое состояние.
  return <AnketaResponses dispatches={nativeDispatches} onDeleted={onDispatchDeleted} />;
}
