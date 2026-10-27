import { useEffect, useRef, useCallback, useState } from 'react';
import {
  syncPrometheusStatuses,
  syncPrometheusStatusSingle,
} from '@/services/api';
import type {
  SyncStatusesResponse,
  SyncSingleStatusResponse,
  SyncStatusResult,
} from '@/services/api';

export interface UsePrometheusSyncReturn {
  /** Map of email → latest sync result */
  statusMap: Record<string, SyncStatusResult>;
  /** ISO timestamp of last successful sync */
  lastSyncedAt: string | null;
  /** Whether a sync is currently in-flight */
  isSyncing: boolean;
  /** Last sync error message (null if ok) */
  syncError: string | null;
  /** Trigger an immediate sync */
  syncNow: () => void;
}

/**
 * Hook: bulk-sync Prometheus statuses for a list of emails on mount.
 * No periodic polling — real-time updates arrive via WebSocket entity.updated.
 * Use syncNow() for manual refresh.
 *
 * Usage (InternsPage):
 *   const { statusMap } = usePrometheusBulkSync(visibleEmails);
 *   // statusMap['user@example.com'].hrStatus → "Принят"
 */
export function usePrometheusBulkSync(
  emails: string[],
  enabled = true,
): UsePrometheusSyncReturn {
  const [statusMap, setStatusMap] = useState<Record<string, SyncStatusResult>>({});
  const [lastSyncedAt, setLastSyncedAt] = useState<string | null>(null);
  const [isSyncing, setIsSyncing] = useState(false);
  const [syncError, setSyncError] = useState<string | null>(null);
  const mountedRef = useRef(true);

  const doSync = useCallback(async () => {
    if (!enabled || emails.length === 0) return;
    setIsSyncing(true);
    setSyncError(null);
    try {
      const resp: SyncStatusesResponse = await syncPrometheusStatuses(emails);
      if (!mountedRef.current) return;
      setLastSyncedAt(resp.syncedAt);
      if (resp.results) {
        setStatusMap((prev) => {
          const next = { ...prev };
          for (const r of resp.results) {
            if (r.email) {
              next[r.email.toLowerCase()] = r;
            }
          }
          return next;
        });
      }
      if (!resp.ok && resp.errors && resp.errors.length > 0) {
        setSyncError(resp.errors[0].message);
      }
    } catch (err) {
      if (!mountedRef.current) return;
      // Debounce errors are expected, ignore them silently
      const msg = err instanceof Error ? err.message : 'Sync failed';
      if (!msg.includes('debounced')) {
        setSyncError(msg);
      }
    } finally {
      if (mountedRef.current) setIsSyncing(false);
    }
  }, [emails, enabled]);

  // Initial sync on mount (no polling — updates arrive via WebSocket entity.updated)
  useEffect(() => {
    mountedRef.current = true;
    if (!enabled || emails.length === 0) return;

    doSync();

    return () => {
      mountedRef.current = false;
    };
  }, [doSync, enabled, emails.length]);

  return { statusMap, lastSyncedAt, isSyncing, syncError, syncNow: doSync };
}


export interface UsePrometheusSingleSyncReturn {
  /** Latest single status result */
  status: SyncSingleStatusResponse | null;
  lastSyncedAt: string | null;
  isSyncing: boolean;
  syncError: string | null;
  syncNow: () => void;
}

/**
 * Hook: sync a single intern's status from Prometheus on mount.
 * No periodic polling — real-time updates arrive via WebSocket entity.updated.
 * Use syncNow() for manual refresh.
 *
 * Usage (InternStatsPage):
 *   const { status } = usePrometheusSingleSync({ email: 'user@example.com' });
 */
export function usePrometheusSingleSync(
  params: { email?: string; internId?: string },
  enabled = true,
): UsePrometheusSingleSyncReturn {
  const [status, setStatus] = useState<SyncSingleStatusResponse | null>(null);
  const [lastSyncedAt, setLastSyncedAt] = useState<string | null>(null);
  const [isSyncing, setIsSyncing] = useState(false);
  const [syncError, setSyncError] = useState<string | null>(null);
  const mountedRef = useRef(true);

  const hasParams = !!(params.email || params.internId);

  const doSync = useCallback(async () => {
    if (!enabled || !hasParams) return;
    setIsSyncing(true);
    setSyncError(null);
    try {
      const resp: SyncSingleStatusResponse = await syncPrometheusStatusSingle(params);
      if (!mountedRef.current) return;
      setStatus(resp);
      setLastSyncedAt(resp.syncedAt);
      if (!resp.ok && resp.error) {
        setSyncError(resp.error);
      }
    } catch (err) {
      if (!mountedRef.current) return;
      const msg = err instanceof Error ? err.message : 'Sync failed';
      if (!msg.includes('debounced')) {
        setSyncError(msg);
      }
    } finally {
      if (mountedRef.current) setIsSyncing(false);
    }
  }, [params.email, params.internId, enabled, hasParams]);

  // Initial sync on mount (no polling — updates arrive via WebSocket entity.updated)
  useEffect(() => {
    mountedRef.current = true;
    if (!enabled || !hasParams) return;

    doSync();

    return () => {
      mountedRef.current = false;
    };
  }, [doSync, enabled, hasParams]);

  return { status, lastSyncedAt, isSyncing, syncError, syncNow: doSync };
}
