import React, { useEffect, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import {
  ExclamationTriangleIcon, ClockIcon, DocumentTextIcon,
} from '@heroicons/react/24/outline';
import PriorityBadge from '../components/PriorityBadge';
import StatusBadge from '../components/StatusBadge';
import { getStaleRunbooks } from '../api/client';

const slugify = (text) =>
  (text || '').toLowerCase().replace(/[^a-z0-9]+/g, '-').replace(/(^-|-$)/g, '');

function daysSince(dateStr) {
  if (!dateStr) return null;
  return Math.floor((Date.now() - new Date(dateStr).getTime()) / (1000 * 60 * 60 * 24));
}

function DaysIndicator({ days }) {
  if (days === null) return <span className="text-slate-300">&mdash;</span>;
  const color = days > 90 ? 'text-red-600' : days > 30 ? 'text-amber-600' : 'text-yellow-600';
  return <span className={`text-sm font-semibold tabular-nums ${color}`}>{days}d</span>;
}

export default function StaleRunbooks() {
  const navigate = useNavigate();
  const [runbooks, setRunbooks] = useState([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    getStaleRunbooks()
      .then((data) => setRunbooks(data.runbooks || data.items || data || []))
      .catch(() => setRunbooks([]))
      .finally(() => setLoading(false));
  }, []);

  return (
    <div className="animate-fade-in max-w-5xl">
      <div className="flex items-center gap-3 mb-2">
        <div className="w-9 h-9 rounded-xl bg-amber-50 flex items-center justify-center">
          <ExclamationTriangleIcon className="h-5 w-5 text-amber-500" />
        </div>
        <div>
          <h1 className="page-title">Needs Review</h1>
          <p className="caption">Pages that have not been updated recently and may contain outdated information</p>
        </div>
      </div>

      <div className="card overflow-hidden mt-4">
        {loading ? (
          <div className="p-8 flex items-center justify-center">
            <div className="animate-spin h-5 w-5 border-2 border-slate-200 border-t-brand-500 rounded-full" />
          </div>
        ) : runbooks.length === 0 ? (
          <div className="empty-state py-16">
            <div className="w-12 h-12 rounded-full bg-emerald-50 flex items-center justify-center mb-3">
              <ClockIcon className="h-5 w-5 text-emerald-500" />
            </div>
            <div className="text-sm font-medium text-slate-700">All up to date</div>
            <div className="text-2xs text-slate-400 mt-1">No stale pages require review at this time</div>
          </div>
        ) : (
          <>
            <div className="px-5 py-3 border-b border-slate-100 flex items-center justify-between">
              <span className="text-sm text-slate-500">{runbooks.length} page{runbooks.length !== 1 ? 's' : ''} need review</span>
            </div>
            <table className="w-full">
              <thead>
                <tr>
                  <th className="table-header">Title</th>
                  <th className="table-header w-24">Priority</th>
                  <th className="table-header w-28">Owner</th>
                  <th className="table-header w-28">Status</th>
                  <th className="table-header w-20 text-right">Age</th>
                </tr>
              </thead>
              <tbody>
                {runbooks.map((rb) => {
                  const pid = rb.id || rb.confluence_page_id;
                  const days = daysSince(rb.updated_at);
                  return (
                    <tr key={pid} className="table-row-interactive"
                      onClick={() => {
                        const sk = rb.space_key;
                        navigate(sk ? `/spaces/${sk}/pages/${pid}/${slugify(rb.title)}` : `/runbooks/${pid}`);
                      }}>
                      <td className="table-cell">
                        <div className="flex items-center gap-2">
                          <DocumentTextIcon className="h-4 w-4 text-slate-300 flex-shrink-0" />
                          <span className="font-medium text-slate-900 truncate">{rb.title}</span>
                        </div>
                      </td>
                      <td className="table-cell"><PriorityBadge priority={rb.priority} /></td>
                      <td className="table-cell text-slate-500">{rb.owner || <span className="text-slate-300">&mdash;</span>}</td>
                      <td className="table-cell"><StatusBadge status={rb.status || rb.local_status} /></td>
                      <td className="table-cell text-right"><DaysIndicator days={days} /></td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </>
        )}
      </div>
    </div>
  );
}
