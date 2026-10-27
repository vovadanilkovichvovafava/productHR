import { ArrowLeft } from "lucide-react";

// «← К списку» над карточкой — только на телефоне (класс прячет на широком
// экране, см. useMobileMasterDetail).
export function MobileBackToList({ onClick }: { onClick: () => void }) {
  return (
    <button type="button" onClick={onClick} className="hf-mobile-back-to-list">
      <ArrowLeft className="h-4 w-4" aria-hidden="true" />
      К списку
    </button>
  );
}
