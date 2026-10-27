import { useEffect, useState } from "react";
import { Loader2, Bell } from "lucide-react";
import { getNotifications } from "@/services/api/notifications";

/** События: те же уведомления, что и в вебе — заявки, выдачи, напоминания. */
export default function Notifications() {
  const [items, setItems] = useState<any[]>([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    getNotifications()
      .then((d) => setItems(Array.isArray(d) ? d : []))
      .catch(() => setItems([]))
      .finally(() => setLoading(false));
  }, []);

  if (loading) return <div className="hf-ma-loading"><Loader2 className="animate-spin" size={24} /></div>;
  if (!items.length) {
    return <div className="hf-ma-empty"><Bell size={28} /><p>Пока ничего нового</p></div>;
  }

  return (
    <div className="hf-ma-page">
      <h1 className="hf-ma-title">События</h1>
      {items.map((n) => (
        <div key={n.id} className={`hf-ma-notif${n.is_read ? "" : " hf-ma-notif-new"}`}>
          <div className="hf-ma-notif-title">{n.title}</div>
          {n.message && <div className="hf-ma-notif-msg">{n.message}</div>}
        </div>
      ))}
    </div>
  );
}
