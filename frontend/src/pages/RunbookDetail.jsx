import React, { useEffect, useState } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import {
  ArrowLeftIcon,
  CheckCircleIcon,
  ExclamationCircleIcon,
  ArrowTopRightOnSquareIcon,
} from '@heroicons/react/24/outline';
import PriorityBadge from '../components/PriorityBadge';
import StatusBadge from '../components/StatusBadge';
import MigrationBadge from '../components/MigrationBadge';
import ConfluenceArticle from '../components/reader/ConfluenceArticle';
import { getRunbook, updateRunbook } from '../api/client';
import useSpaceNames from '../hooks/useSpaceNames';

const PRIORITIES = ['P0', 'P1', 'P2', 'P3', 'P4', 'P5'];
const STATUSES = ['active', 'stale', 'needs_review', 'archived'];
const MIGRATION_STATUSES = ['legacy', 'in_progress', 'migrated', 'verified'];

export default function RunbookDetail() {
  const { id } = useParams();
  const navigate = useNavigate();
  const { resolveSpace } = useSpaceNames();

  const [runbook, setRunbook] = useState(null);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [message, setMessage] = useState(null);

  const [formData, setFormData] = useState({
    priority: '', domain: '', team: '', owner: '',
    status: '', migration_status: '', tags: '', notes: '',
  });

  useEffect(() => {
    setLoading(true);
    getRunbook(id)
      .then((data) => {
        const rb = data.runbook || data;
        setRunbook(rb);
        setFormData({
          priority: rb.priority || '',
          domain: rb.domain || '',
          team: rb.team || '',
          owner: rb.owner || '',
          status: rb.status || '',
          migration_status: rb.migration_status || '',
          tags: Array.isArray(rb.tags) ? rb.tags.join(', ') : rb.tags || '',
          notes: rb.notes || '',
        });
      })
      .catch(() => {})
      .finally(() => setLoading(false));
  }, [id]);

  const handleSave = async () => {
    setSaving(true);
    setMessage(null);
    try {
      await updateRunbook(id, {
        ...formData,
        tags: formData.tags.split(',').map((t) => t.trim()).filter(Boolean),
      });
      setMessage({ type: 'success', text: 'Saved successfully.' });
    } catch {
      setMessage({ type: 'error', text: 'Failed to save changes.' });
    } finally {
      setSaving(false);
    }
  };

  const updateField = (field, value) => setFormData((prev) => ({ ...prev, [field]: value }));

  if (loading) {
    return (
      <div className="animate-fade-in max-w-4xl">
        <div className="loading-skeleton h-5 w-32 mb-4" />
        <div className="loading-skeleton h-8 w-64 mb-6" />
        <div className="card p-6"><div className="loading-skeleton h-48" /></div>
      </div>
    );
  }

  if (!runbook) {
    return (
      <div className="max-w-4xl">
        <button onClick={() => navigate('/runbooks')} className="btn-ghost mb-4">
          <ArrowLeftIcon className="h-4 w-4" /> Back
        </button>
        <div className="empty-state card py-12">
          <div className="text-sm text-slate-500">Page not found</div>
        </div>
      </div>
    );
  }

  return (
    <div className="animate-fade-in max-w-4xl">
      <button onClick={() => navigate('/runbooks')} className="btn-ghost mb-4">
        <ArrowLeftIcon className="h-4 w-4" /> Back to All Pages
      </button>

      {/* Header */}
      <div className="card p-5 mb-6">
        <div className="flex items-start justify-between gap-4">
          <div>
            <h1 className="text-xl font-bold text-slate-900 dark:text-slate-100">{runbook.title}</h1>
            {runbook.confluence_url && (
              <a href={runbook.confluence_url} target="_blank" rel="noopener noreferrer"
                    className="inline-flex items-center gap-1 mt-2 text-sm text-brand-600 dark:text-brand-400 hover:text-brand-700 dark:hover:text-brand-300">
                <ArrowTopRightOnSquareIcon className="h-4 w-4" />
                View in Confluence
              </a>
            )}
          </div>
          <div className="flex gap-2 flex-shrink-0">
            <PriorityBadge priority={formData.priority} />
            <StatusBadge status={formData.status} />
          </div>
        </div>
      </div>

      {/* Message */}
      {message && (
        <div className={`card p-3 mb-4 animate-slide-in ${
          message.type === 'success' ? 'bg-emerald-50 border-emerald-200' : 'bg-red-50 border-red-200'
        }`}>
          <div className={`flex items-center gap-2 text-sm ${
            message.type === 'success' ? 'text-emerald-700' : 'text-red-700'
          }`}>
            {message.type === 'success'
              ? <CheckCircleIcon className="h-4 w-4" />
              : <ExclamationCircleIcon className="h-4 w-4" />
            }
            {message.text}
          </div>
        </div>
      )}

      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
        {/* Edit form */}
        <div className="lg:col-span-2 space-y-6">
          <div className="card p-5">
            <h3 className="section-title mb-4">Details</h3>
            <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
              <FormField label="Priority">
                <select value={formData.priority} onChange={(e) => updateField('priority', e.target.value)} className="input-field">
                  <option value="">None</option>
                  {PRIORITIES.map((p) => <option key={p} value={p}>{p}</option>)}
                </select>
              </FormField>
              <FormField label="Status">
                <select value={formData.status} onChange={(e) => updateField('status', e.target.value)} className="input-field">
                  <option value="">None</option>
                  {STATUSES.map((s) => <option key={s} value={s}>{s.replace(/_/g, ' ')}</option>)}
                </select>
              </FormField>
              <FormField label="Migration Status">
                <select value={formData.migration_status} onChange={(e) => updateField('migration_status', e.target.value)} className="input-field">
                  <option value="">None</option>
                  {MIGRATION_STATUSES.map((m) => <option key={m} value={m}>{m.replace(/_/g, ' ')}</option>)}
                </select>
              </FormField>
              <FormField label="Domain">
                <input value={formData.domain} onChange={(e) => updateField('domain', e.target.value)}
                  className="input-field" placeholder="e.g. Infrastructure" />
              </FormField>
              <FormField label="Team">
                <input value={formData.team} onChange={(e) => updateField('team', e.target.value)}
                  className="input-field" placeholder="e.g. Platform" />
              </FormField>
              <FormField label="Owner">
                <input value={formData.owner} onChange={(e) => updateField('owner', e.target.value)}
                  className="input-field" placeholder="e.g. jane.doe" />
              </FormField>
              <div className="sm:col-span-2">
                <FormField label="Tags">
                  <input value={formData.tags} onChange={(e) => updateField('tags', e.target.value)}
                    className="input-field" placeholder="Comma-separated tags" />
                </FormField>
              </div>
              <div className="sm:col-span-2">
                <FormField label="Notes">
                  <textarea value={formData.notes} onChange={(e) => updateField('notes', e.target.value)}
                    className="input-field resize-y min-h-[100px]" rows={4} placeholder="Additional notes..." />
                </FormField>
              </div>
            </div>
            <div className="flex justify-end mt-5">
              <button onClick={handleSave} disabled={saving} className="btn-primary">
                {saving ? 'Saving...' : 'Save Changes'}
              </button>
            </div>
          </div>

          {runbook.content && (
            <div className="card p-5">
              <h3 className="section-title mb-4">Content Preview</h3>
              {/* Same renderer and allowlist as the reader route, so this
                  preview cannot drift from the real article. */}
              <ConfluenceArticle html={runbook.content} id="runbook-preview" />
            </div>
          )}
        </div>

        {/* Sidebar */}
        <div className="space-y-4">
          <div className="card p-4">
            <h3 className="section-title mb-3">Metadata</h3>
            <div className="space-y-2.5">
              {[
                ['Confluence ID', runbook.confluence_id],
                ['Space', resolveSpace(runbook.space_key)],
                ['Created', runbook.created_at ? new Date(runbook.created_at).toLocaleDateString() : null],
                ['Updated', runbook.updated_at ? new Date(runbook.updated_at).toLocaleDateString() : null],
                ['Synced', runbook.last_synced ? new Date(runbook.last_synced).toLocaleDateString() : null],
              ].map(([label, value]) => (
                <div key={label} className="flex items-baseline justify-between gap-2">
                  <span className="text-2xs text-slate-400 dark:text-slate-500">{label}</span>
                  <span className="text-sm text-slate-700 dark:text-slate-300 truncate">{value || '\u2014'}</span>
                </div>
              ))}
            </div>
          </div>

          <div className="card p-4">
            <h3 className="section-title mb-3">Change History</h3>
            {runbook.audit_log?.length > 0 ? (
              <div className="space-y-3">
                {runbook.audit_log.map((entry, idx) => (
                  <div key={idx} className="relative pl-4 pb-3 border-l-2 border-slate-100 dark:border-slate-700 last:pb-0">
                    <div className="absolute left-[-5px] top-1.5 w-2 h-2 rounded-full bg-slate-300 dark:bg-slate-600" />
                    <div className="text-2xs text-slate-400 dark:text-slate-500">
                      {entry.timestamp ? new Date(entry.timestamp).toLocaleString() : entry.date || '\u2014'}
                    </div>
                    <div className="text-sm font-medium text-slate-700 dark:text-slate-300 mt-0.5">
                      {entry.description || entry.change || '\u2014'}
                    </div>
                    {entry.user && <div className="text-2xs text-slate-400 dark:text-slate-500">by {entry.user}</div>}
                  </div>
                ))}
              </div>
            ) : (
              <div className="text-sm text-slate-400 dark:text-slate-500">No change history available</div>
            )}
          </div>
        </div>
      </div>
    </div>
  );
}

function FormField({ label, children }) {
  return (
    <div>
      <label className="label mb-1.5 block">{label}</label>
      {children}
    </div>
  );
}
