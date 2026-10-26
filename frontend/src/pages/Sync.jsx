import React, { useEffect, useState } from 'react';
import {
  ArrowPathIcon,
  CheckCircleIcon,
  ExclamationCircleIcon,
  ClockIcon,
  BoltIcon,
  ServerIcon,
  DocumentTextIcon,
} from '@heroicons/react/24/outline';
import { triggerFullSync, triggerIncrementalSync, getSyncStatus, getSyncRuns } from '../api/client';
import useSpaceNames, { invalidateSpaceNamesCache } from '../hooks/useSpaceNames';

function StatusDot({ ok }) {
  return <span className={`dot ${ok ? 'bg-emerald-400' : 'bg-slate-300'}`} />;
}

export default function Sync() {
  const { resolveSpace } = useSpaceNames();
  const [syncStatus, setSyncStatus] = useState(null);
  const [runs, setRuns] = useState([]);
  const [syncing, setSyncing] = useState(false);
  const [result, setResult] = useState(null);
  const [error, setError] = useState(null);
  const [loading, setLoading] = useState(true);

  const refreshStatus = async () => {
    try {
      const [status, runsData] = await Promise.all([getSyncStatus(), getSyncRuns()]);
      setSyncStatus(status);
      setRuns(runsData.runs || []);
    } catch {
      /* silent */
    }
  };

  useEffect(() => {
    refreshStatus().finally(() => setLoading(false));
  }, []);

  const handleSync = async (type) => {
    setSyncing(true);
    setResult(null);
    setError(null);
    try {
      const data = type === 'incremental'
        ? await triggerIncrementalSync()
        : await triggerFullSync();
      setResult(data);
      invalidateSpaceNamesCache();
      await refreshStatus();
    } catch (err) {
      setError(err.response?.data?.error || 'Sync failed. Check Confluence credentials and try again.');
    } finally {
      setSyncing(false);
    }
  };

  const lastSync = syncStatus?.last_sync_time;
  const totalPages = syncStatus?.total_pages ?? syncStatus?.total_runbooks ?? 0;
  const totalBlogs = syncStatus?.total_blogs ?? 0;

  return (
    <div className="animate-fade-in max-w-4xl">
      <div className="flex items-center gap-3 mb-6">
        <div className="w-9 h-9 rounded-xl bg-brand-50 flex items-center justify-center">
          <ArrowPathIcon className="h-5 w-5 text-brand-600" />
        </div>
        <div>
          <h1 className="page-title">Synchronization</h1>
          <p className="caption">Pull content from Confluence using read-only GET requests</p>
        </div>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-4 mb-6">
        {/* Controls */}
        <div className="card p-5">
          <h3 className="section-title mb-1">Sync Controls</h3>
          <p className="text-2xs text-slate-400 mb-5">
            Full sync retrieves all content. Incremental sync updates only changed pages.
          </p>
          <div className="space-y-2.5">
            <button
              onClick={() => handleSync('full')}
              disabled={syncing}
              className="btn-primary w-full justify-center py-2.5"
            >
              {syncing ? (
                <div className="animate-spin h-4 w-4 border-2 border-white/30 border-t-white rounded-full" />
              ) : (
                <ArrowPathIcon className="h-4 w-4" />
              )}
              {syncing ? 'Syncing...' : 'Full Sync'}
            </button>
            <button
              onClick={() => handleSync('incremental')}
              disabled={syncing}
              className="btn-secondary w-full justify-center py-2.5"
            >
              <BoltIcon className="h-4 w-4" />
              Incremental Sync
            </button>
          </div>

          {syncing && (
            <div className="flex items-center gap-2 mt-4 text-sm text-slate-500">
              <div className="animate-spin h-4 w-4 border-2 border-slate-300 border-t-brand-500 rounded-full" />
              Retrieving content from Confluence...
            </div>
          )}
        </div>

        {/* Status */}
        <div className="card p-5">
          <h3 className="section-title mb-4">Current Status</h3>
          {loading ? (
            <div className="space-y-3">
              <div className="loading-skeleton h-4 w-32" />
              <div className="loading-skeleton h-8 w-24" />
            </div>
          ) : (
            <div className="space-y-4">
              <div>
                <div className="label mb-1">Last Synchronization</div>
                <div className="flex items-center gap-2">
                  <StatusDot ok={!!lastSync} />
                  <span className="text-sm font-medium text-slate-800">
                    {lastSync ? new Date(lastSync).toLocaleString() : 'Never synced'}
                  </span>
                </div>
              </div>
              <div className="grid grid-cols-2 gap-4">
                <div>
                  <div className="label mb-1">Pages</div>
                  <div className="flex items-center gap-2">
                    <DocumentTextIcon className="h-4 w-4 text-slate-400" />
                    <span className="text-lg font-bold text-slate-900 tabular-nums">{totalPages}</span>
                  </div>
                </div>
                <div>
                  <div className="label mb-1">Blog Posts</div>
                  <div className="flex items-center gap-2">
                    <DocumentTextIcon className="h-4 w-4 text-slate-400" />
                    <span className="text-lg font-bold text-slate-900 tabular-nums">{totalBlogs}</span>
                  </div>
                </div>
              </div>
              <div className="pt-3 border-t border-slate-100">
                <div className="flex items-center gap-2 text-2xs text-slate-400">
                  <ServerIcon className="h-3.5 w-3.5" />
                  Read-only Confluence integration
                </div>
              </div>
            </div>
          )}
        </div>
      </div>

      {/* Results */}
      {result && (
        <div className="card p-4 mb-4 bg-emerald-50 border-emerald-200 animate-slide-in">
          <div className="flex items-center gap-2 text-emerald-700 text-sm">
            <CheckCircleIcon className="h-5 w-5" />
            <span className="font-medium">Sync completed successfully</span>
            <span className="text-emerald-600">&mdash; {result.total ?? 0} pages processed</span>
          </div>
        </div>
      )}

      {error && (
        <div className="card p-4 mb-4 bg-red-50 border-red-200 animate-slide-in">
          <div className="flex items-center gap-2 text-red-700 text-sm">
            <ExclamationCircleIcon className="h-5 w-5 flex-shrink-0" />
            <span>{error}</span>
          </div>
        </div>
      )}

      {/* Run history */}
      {runs.length > 0 && (
        <div className="card overflow-hidden">
          <div className="px-5 py-3 border-b border-slate-100">
            <h3 className="section-title">Recent Sync Runs</h3>
          </div>
          <table className="w-full">
            <thead>
              <tr>
                <th className="table-header">Space</th>
                <th className="table-header w-20">Pages</th>
                <th className="table-header w-20">Imported</th>
                <th className="table-header w-20">Updated</th>
                <th className="table-header w-16">Errors</th>
                <th className="table-header w-20">Duration</th>
                <th className="table-header w-32 text-right">Date</th>
              </tr>
            </thead>
            <tbody>
              {runs.slice(0, 10).map((run, idx) => (
                <tr key={idx}>
                  <td className="table-cell font-medium text-slate-800">{run.space_key ? resolveSpace(run.space_key) : '\u2014'}</td>
                  <td className="table-cell tabular-nums">{run.total_pages ?? 0}</td>
                  <td className="table-cell tabular-nums">{run.pages_imported ?? 0}</td>
                  <td className="table-cell tabular-nums">{run.pages_updated ?? 0}</td>
                  <td className="table-cell">
                    {(run.errors || []).length > 0 ? (
                      <span className="badge-red">{(run.errors || []).length}</span>
                    ) : (
                      <span className="text-2xs text-emerald-500">0</span>
                    )}
                  </td>
                  <td className="table-cell text-2xs text-slate-500 tabular-nums">
                    {run.duration_seconds ? `${run.duration_seconds.toFixed(1)}s` : '\u2014'}
                  </td>
                  <td className="table-cell text-right text-2xs text-slate-400">
                    {run.started_at ? new Date(run.started_at).toLocaleString() : '\u2014'}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      {!loading && runs.length === 0 && !result && (
        <div className="card p-5">
          <div className="empty-state py-8">
            <ClockIcon className="h-8 w-8 text-slate-300 mb-3" />
            <div className="text-sm text-slate-500">No sync history</div>
            <div className="text-2xs text-slate-400 mt-1">Run a sync to import content from Confluence</div>
          </div>
        </div>
      )}
    </div>
  );
}
