import { useState, useEffect, useCallback } from 'react';
import { motion } from 'framer-motion';
import { useNavigate } from 'react-router-dom';
import {
  Cloud,
  RefreshCw,
  Server,
  GitBranch,
  Globe,
  Clock,
  AlertCircle,
  CheckCircle2,
  ExternalLink,
  ChevronRight,
  Box,
} from 'lucide-react';
import {
  getSaturnProjects,
  getSaturnSyncStatus,
  triggerSaturnSync,
  getSaturnProject,
} from '@/services/api';
import type { SaturnProject, SaturnApplication, SaturnSyncStatus } from '@/services/api';
import { useAuthStore } from '@/stores/authStore';

function StatusBadge({ status }: { status?: string }) {
  if (!status) return <span className="text-xs text-dark-500">--</span>;

  const isHealthy = status.includes('healthy') || status.includes('running');
  const isExited = status.includes('exited') || status.includes('unhealthy');

  return (
    <span
      className={`inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-xs font-medium ${
        isHealthy
          ? 'bg-emerald-500/20 text-emerald-400'
          : isExited
          ? 'bg-red-500/20 text-red-400'
          : 'bg-amber-500/20 text-amber-400'
      }`}
    >
      <span className={`w-1.5 h-1.5 rounded-full ${isHealthy ? 'bg-emerald-400' : isExited ? 'bg-red-400' : 'bg-amber-400'}`} />
      {status}
    </span>
  );
}

function formatDate(dateStr?: string) {
  if (!dateStr) return '--';
  const d = new Date(dateStr);
  return d.toLocaleString('ru-RU', { day: '2-digit', month: '2-digit', year: 'numeric', hour: '2-digit', minute: '2-digit' });
}

export default function SaturnPage() {
  const [projects, setProjects] = useState<SaturnProject[]>([]);
  const [syncStatus, setSyncStatus] = useState<SaturnSyncStatus | null>(null);
  const [expandedProject, setExpandedProject] = useState<string | null>(null);
  const [projectApps, setProjectApps] = useState<Record<string, SaturnApplication[]>>({});
  const [loading, setLoading] = useState(true);
  const [syncing, setSyncing] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const { user } = useAuthStore();
  const navigate = useNavigate();
  const isSuperadmin = user?.role === 'superadmin';

  const fetchData = useCallback(async () => {
    try {
      setLoading(true);
      setError(null);
      const [p, s] = await Promise.all([getSaturnProjects(), getSaturnSyncStatus()]);
      setProjects(p);
      setSyncStatus(s);
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Failed to load Saturn data');
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    fetchData();
  }, [fetchData]);

  const handleSync = async () => {
    try {
      setSyncing(true);
      setError(null);
      await triggerSaturnSync();
      await fetchData();
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Sync failed');
    } finally {
      setSyncing(false);
    }
  };

  const toggleProject = async (uuid: string) => {
    if (expandedProject === uuid) {
      setExpandedProject(null);
      return;
    }
    setExpandedProject(uuid);
    if (!projectApps[uuid]) {
      try {
        const detail = await getSaturnProject(uuid);
        setProjectApps((prev) => ({ ...prev, [uuid]: detail.applications }));
      } catch {
        // If fetch fails, just expand with empty
        setProjectApps((prev) => ({ ...prev, [uuid]: [] }));
      }
    }
  };

  return (
    <div className="p-6 max-w-6xl mx-auto space-y-6">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-3">
          <div className="w-10 h-10 rounded-xl bg-gradient-to-br from-orange-500/20 to-amber-500/20 flex items-center justify-center">
            <Cloud className="w-5 h-5 text-orange-400" />
          </div>
          <div>
            <h1 className="text-xl font-bold text-white">Saturn</h1>
            <p className="text-sm text-dark-400">Deployment platform integration</p>
          </div>
        </div>
        {isSuperadmin && (
          <button
            onClick={handleSync}
            disabled={syncing}
            className="flex items-center gap-2 px-4 py-2 rounded-lg bg-accent-500/20 text-accent-400 hover:bg-accent-500/30 transition-colors disabled:opacity-50"
          >
            <RefreshCw className={`w-4 h-4 ${syncing ? 'animate-spin' : ''}`} />
            {syncing ? 'Syncing...' : 'Sync Now'}
          </button>
        )}
      </div>

      {/* Error */}
      {error && (
        <div className="flex items-center gap-2 p-3 rounded-lg bg-red-500/10 border border-red-500/20 text-red-400 text-sm">
          <AlertCircle className="w-4 h-4 shrink-0" />
          {error}
        </div>
      )}

      {/* Sync Status Cards */}
      <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
        <motion.div
          initial={{ opacity: 0, y: 10 }}
          animate={{ opacity: 1, y: 0 }}
          className="rounded-xl bg-dark-800/50 border border-dark-700/50 p-4"
        >
          <div className="flex items-center gap-2 mb-2">
            <Server className="w-4 h-4 text-blue-400" />
            <span className="text-sm text-dark-400">Projects</span>
          </div>
          <div className="text-2xl font-bold text-white">
            {syncStatus?.total_saturn_projects ?? '--'}
          </div>
        </motion.div>

        <motion.div
          initial={{ opacity: 0, y: 10 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ delay: 0.05 }}
          className="rounded-xl bg-dark-800/50 border border-dark-700/50 p-4"
        >
          <div className="flex items-center gap-2 mb-2">
            <Box className="w-4 h-4 text-emerald-400" />
            <span className="text-sm text-dark-400">Applications</span>
          </div>
          <div className="text-2xl font-bold text-white">
            {syncStatus?.total_saturn_apps ?? '--'}
          </div>
        </motion.div>

        <motion.div
          initial={{ opacity: 0, y: 10 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ delay: 0.1 }}
          className="rounded-xl bg-dark-800/50 border border-dark-700/50 p-4"
        >
          <div className="flex items-center gap-2 mb-2">
            <Clock className="w-4 h-4 text-amber-400" />
            <span className="text-sm text-dark-400">Last Sync</span>
          </div>
          <div className="text-sm font-medium text-white">
            {syncStatus?.last_sync ? formatDate(syncStatus.last_sync.at) : 'Never'}
          </div>
          {syncStatus?.last_sync && (
            <div className="flex items-center gap-1 mt-1">
              <CheckCircle2 className="w-3 h-3 text-emerald-400" />
              <span className="text-xs text-dark-400">
                {syncStatus.last_sync.projects_synced} projects, {syncStatus.last_sync.apps_synced} apps
              </span>
            </div>
          )}
        </motion.div>
      </div>

      {/* Projects List */}
      <div className="space-y-2">
        <h2 className="text-lg font-semibold text-white">Saturn Projects</h2>

        {loading ? (
          <div className="flex items-center justify-center py-12">
            <div className="w-6 h-6 border-2 border-accent-500 border-t-transparent rounded-full animate-spin" />
          </div>
        ) : projects.length === 0 ? (
          <div className="text-center py-12 text-dark-400">
            <Cloud className="w-12 h-12 mx-auto mb-3 opacity-30" />
            <p>No Saturn projects synced yet.</p>
            {isSuperadmin && <p className="text-sm mt-1">Click "Sync Now" to import projects from Saturn.</p>}
          </div>
        ) : (
          <div className="space-y-2">
            {projects.map((proj) => (
              <motion.div
                key={proj.saturn_uuid}
                initial={{ opacity: 0 }}
                animate={{ opacity: 1 }}
                className="rounded-xl bg-dark-800/50 border border-dark-700/50 overflow-hidden"
              >
                {/* Project header */}
                <button
                  onClick={() => toggleProject(proj.saturn_uuid)}
                  className="w-full flex items-center gap-3 p-4 hover:bg-dark-700/30 transition-colors text-left"
                >
                  <ChevronRight
                    className={`w-4 h-4 text-dark-400 transition-transform ${
                      expandedProject === proj.saturn_uuid ? 'rotate-90' : ''
                    }`}
                  />
                  <div className="flex-1 min-w-0">
                    <div className="flex items-center gap-2">
                      <span className="font-medium text-white truncate">{proj.name}</span>
                      {proj.is_archived && (
                        <span className="px-1.5 py-0.5 rounded text-[10px] bg-dark-600 text-dark-400">archived</span>
                      )}
                    </div>
                    {proj.description && (
                      <p className="text-xs text-dark-400 truncate mt-0.5">{proj.description}</p>
                    )}
                  </div>
                  <div className="flex items-center gap-3 shrink-0">
                    {proj.enceladus_project_id && (
                      <button
                        onClick={(e) => {
                          e.stopPropagation();
                          navigate(`/projects/${proj.enceladus_project_id}`);
                        }}
                        className="flex items-center gap-1 px-2 py-1 rounded-md bg-blue-500/10 text-blue-400 text-xs hover:bg-blue-500/20 transition-colors"
                      >
                        <ExternalLink className="w-3 h-3" />
                        Enceladus
                      </button>
                    )}
                    <span className="text-xs text-dark-500">
                      {formatDate(proj.last_synced_at)}
                    </span>
                  </div>
                </button>

                {/* Expanded: applications */}
                {expandedProject === proj.saturn_uuid && (
                  <div className="border-t border-dark-700/50 px-4 py-3 space-y-2">
                    {!projectApps[proj.saturn_uuid] ? (
                      <div className="flex items-center justify-center py-4">
                        <div className="w-4 h-4 border-2 border-accent-500 border-t-transparent rounded-full animate-spin" />
                      </div>
                    ) : projectApps[proj.saturn_uuid].length === 0 ? (
                      <p className="text-sm text-dark-400 py-2">No applications in this project.</p>
                    ) : (
                      projectApps[proj.saturn_uuid].map((app) => (
                        <div
                          key={app.saturn_uuid}
                          className="flex items-center gap-3 p-3 rounded-lg bg-dark-700/30"
                        >
                          <Box className="w-4 h-4 text-dark-400 shrink-0" />
                          <div className="flex-1 min-w-0">
                            <div className="flex items-center gap-2">
                              <span className="text-sm font-medium text-white truncate">{app.name}</span>
                              <StatusBadge status={app.status} />
                            </div>
                            <div className="flex items-center gap-4 mt-1">
                              {app.fqdn && (
                                <span className="flex items-center gap-1 text-xs text-dark-400">
                                  <Globe className="w-3 h-3" />
                                  <a
                                    href={app.fqdn.startsWith('http') ? app.fqdn : `https://${app.fqdn}`}
                                    target="_blank"
                                    rel="noopener noreferrer"
                                    className="hover:text-blue-400 transition-colors"
                                    onClick={(e) => e.stopPropagation()}
                                  >
                                    {app.fqdn}
                                  </a>
                                </span>
                              )}
                              {app.git_repository && (
                                <span className="flex items-center gap-1 text-xs text-dark-400">
                                  <GitBranch className="w-3 h-3" />
                                  {app.git_branch || 'main'}
                                </span>
                              )}
                              {app.build_pack && (
                                <span className="text-xs text-dark-500">{app.build_pack}</span>
                              )}
                              {app.environment_name && (
                                <span className="px-1.5 py-0.5 rounded text-[10px] bg-dark-600 text-dark-400">
                                  {app.environment_name}
                                </span>
                              )}
                            </div>
                          </div>
                        </div>
                      ))
                    )}
                  </div>
                )}
              </motion.div>
            ))}
          </div>
        )}
      </div>
    </div>
  );
}
