import React, { useEffect, useState, useCallback } from 'react';
import { useNavigate } from 'react-router-dom';
import {
  TagIcon, ChevronLeftIcon, ChevronRightIcon, ExclamationCircleIcon,
  InformationCircleIcon, DocumentTextIcon,

} from '@heroicons/react/24/outline';
import { getWLPages } from '../api/client';
import useSpaceNames from '../hooks/useSpaceNames';

const slugify = (text) =>
  (text || '').toLowerCase().replace(/[^a-z0-9]+/g, '-').replace(/(^-|-$)/g, '');

const PAGE_SIZE = 30;

const WL_TYPES = [
  {
    value: 'label_missing',
    label: 'Without Label',
    shortLabel: 'No Labels',
    description: 'Pages with zero Confluence labels (Interpretation 1 — default WL rule)',
    color: 'brand',
  },
  {
    value: 'taxonomy_unmapped',
    label: 'Unmapped Taxonomy',
    shortLabel: 'Unmapped',
    description: 'Pages whose labels cannot be mapped to application taxonomy (Interpretation 4)',
    color: 'amber',
  },
  {
    value: 'domain_missing',
    label: 'No Domain',
    shortLabel: 'No Domain',
    description: 'Pages with no application domain assigned',
    color: 'slate',
  },
];

export default function WLPages() {
  const navigate = useNavigate();
  const { resolveSpace } = useSpaceNames();

  const [wlType, setWlType] = useState('label_missing');
  const [pages, setPages] = useState([]);
  const [total, setTotal] = useState(0);
  const [page, setPage] = useState(1);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);

  const fetchWL = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const data = await getWLPages({ wl_type: wlType, page, per_page: PAGE_SIZE });
      setPages(data.pages || []);
      setTotal(data.total || 0);
    } catch {
      setError('Failed to load WL pages');
      setPages([]);
    } finally {
      setLoading(false);
    }
  }, [wlType, page]);

  useEffect(() => { fetchWL(); }, [fetchWL]);

  const totalPages = Math.ceil(total / PAGE_SIZE);
  const activeType = WL_TYPES.find((t) => t.value === wlType);

  return (
    <div className="animate-fade-in max-w-5xl">
      <div className="flex items-center gap-3 mb-2">
        <div className="w-9 h-9 rounded-xl bg-red-50 dark:bg-red-900/30 flex items-center justify-center">
          <TagIcon className="h-5 w-5 text-red-500 dark:text-red-400" />
        </div>
        <div>
          <h1 className="page-title">Without Label</h1>
          <p className="caption">Pages missing Confluence labels or application classification</p>
        </div>
      </div>

      {/* Explanation */}
      <div className="card p-4 mb-4 mt-4 bg-slate-50 dark:bg-slate-800/50 border-slate-200/60 dark:border-slate-700/60">
        <div className="flex gap-3">
          <InformationCircleIcon className="h-5 w-5 text-brand-500 flex-shrink-0 mt-0.5" />
          <div className="text-sm text-slate-600 dark:text-slate-400">
            <strong className="text-slate-800 dark:text-slate-200">WL (Without Label)</strong> is an application-only classification.
            It is never written to Confluence. The default rule (Interpretation 1) flags pages with zero native
            Confluence labels. Use the tabs below to switch between classification rules.
          </div>
        </div>
      </div>

      {/* Classification selector */}
      <div className="flex items-center gap-1.5 mb-4 border-b border-slate-200 dark:border-slate-700 overflow-x-auto">
        {WL_TYPES.map((t) => (
          <button
            key={t.value}
            onClick={() => { setWlType(t.value); setPage(1); }}
            className={`px-4 py-2.5 text-sm font-medium whitespace-nowrap border-b-2 transition-colors -mb-px ${
              wlType === t.value
                ? 'border-brand-600 text-brand-700 dark:text-brand-400 dark:border-brand-400'
                : 'border-transparent text-slate-500 dark:text-slate-400 hover:text-slate-700 dark:hover:text-slate-300 hover:border-slate-300 dark:hover:border-slate-600'
            }`}
          >
            {t.shortLabel}
          </button>
        ))}
      </div>

      {activeType && (
        <div className="flex items-center justify-between mb-3">
          <span className="text-sm text-slate-500 dark:text-slate-400">{activeType.description}</span>
          <span className="badge-brand tabular-nums">{total} pages</span>
        </div>
      )}

      {/* Table */}
      <div className="card overflow-x-auto">
        {loading ? (
          <div className="p-8 flex items-center justify-center">
            <div className="animate-spin h-5 w-5 border-2 border-slate-200 border-t-brand-500 rounded-full" />
          </div>
        ) : error ? (
          <div className="empty-state py-12">
            <ExclamationCircleIcon className="h-6 w-6 text-red-400 mb-2" />
            <div className="text-sm text-red-600">{error}</div>
          </div>
        ) : pages.length === 0 ? (
          <div className="empty-state py-16">
            <div className="w-12 h-12 rounded-full bg-emerald-50 dark:bg-emerald-900/30 flex items-center justify-center mb-3">
              <TagIcon className="h-5 w-5 text-emerald-500 dark:text-emerald-400" />
            </div>
            <div className="text-sm font-medium text-slate-700 dark:text-slate-300">No pages match this rule</div>
            <div className="text-2xs text-slate-400 dark:text-slate-500 mt-1">
              All pages are classified under the current criteria
            </div>
          </div>
        ) : (
          <>
            <table className="w-full table-fixed">
              <colgroup>
                <col className={wlType === 'label_missing' ? 'w-[45%]' : 'w-[55%]'} />
                <col className="w-[20%]" />
                {wlType === 'label_missing' && <col className="w-[12%]" />}
                <col className="w-[13%]" />
                <col className="w-[10%]" />
              </colgroup>
              <thead>
                <tr>
                  <th className="table-header">Title</th>
                  <th className="table-header">Space</th>
                  {wlType === 'label_missing' && <th className="table-header">Labels</th>}
                  <th className="table-header">Author</th>
                  <th className="table-header text-right">Updated</th>
                </tr>
              </thead>
              <tbody>
                {pages.map((p) => {
                  const pid = p.confluence_page_id || p.id;
                  const labels = p.labels || [];
                  return (
                    <tr
                      key={pid}
                      className="table-row-interactive"
                      onClick={() => navigate(`/spaces/${p.space_key}/pages/${pid}/${slugify(p.title)}`)}
                    >
                      <td className="table-cell truncate">
                        <div className="flex items-center gap-2 min-w-0">
                          <DocumentTextIcon className="h-4 w-4 text-slate-300 dark:text-slate-600 flex-shrink-0" />
                          <span className="font-medium text-slate-900 dark:text-slate-100 truncate">{p.title}</span>
                        </div>
                      </td>
                      <td className="table-cell truncate">
                        <span className="badge-slate truncate">{resolveSpace(p.space_key)}</span>
                      </td>
                      {wlType === 'label_missing' && (
                        <td className="table-cell">
                          <span className="badge-red text-2xs">None</span>
                        </td>
                      )}
                      <td className="table-cell text-sm text-slate-500 dark:text-slate-400 truncate">
                        {p.created_by || '\u2014'}
                      </td>
                      <td className="table-cell text-right text-2xs text-slate-400 dark:text-slate-500 tabular-nums whitespace-nowrap">
                        {p.updated_at ? new Date(p.updated_at).toLocaleDateString() : '\u2014'}
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>

            {totalPages > 1 && (
              <div className="flex items-center justify-between px-4 py-3 border-t border-slate-100 dark:border-slate-700">
                <span className="text-2xs text-slate-400 tabular-nums">
                  Page {page} of {totalPages} ({total} total)
                </span>
                <div className="flex gap-1.5">
                  <button className="btn-ghost" disabled={page <= 1}
                    onClick={() => setPage((p) => Math.max(1, p - 1))}>
                    <ChevronLeftIcon className="h-4 w-4" /> Prev
                  </button>
                  <button className="btn-ghost" disabled={page >= totalPages}
                    onClick={() => setPage((p) => Math.min(totalPages, p + 1))}>
                    Next <ChevronRightIcon className="h-4 w-4" />
                  </button>
                </div>
              </div>
            )}
          </>
        )}
      </div>
    </div>
  );
}
