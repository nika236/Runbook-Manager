import React, { useEffect, useState, useCallback } from 'react';
import { useParams, useNavigate, Link } from 'react-router-dom';
import {
  MagnifyingGlassIcon, ChevronLeftIcon, ChevronRightIcon, ExclamationCircleIcon,
  FolderOpenIcon, DocumentTextIcon,
} from '@heroicons/react/24/outline';
import PageTree from '../components/PageTree';
import WLBadge from '../components/WLBadge';
import PriorityBadge from '../components/PriorityBadge';
import StatusBadge from '../components/StatusBadge';
import { getSpace, getSpaceTree, getSpacePages } from '../api/client';

const slugify = (text) =>
  (text || '').toLowerCase().replace(/[^a-z0-9]+/g, '-').replace(/(^-|-$)/g, '');

const PAGE_SIZE = 30;
const STATUSES = ['imported', 'active', 'stale', 'needs_review', 'archived'];
const PRIORITIES = ['P0', 'P1', 'P2', 'P3', 'P4', 'P5'];

export default function SpaceView() {
  const { spaceKey } = useParams();
  const navigate = useNavigate();

  const [space, setSpace] = useState(null);
  const [tree, setTree] = useState([]);
  const [pages, setPages] = useState([]);
  const [total, setTotal] = useState(0);
  const [loading, setLoading] = useState(true);
  const [pagesLoading, setPagesLoading] = useState(false);
  const [error, setError] = useState(null);
  const [search, setSearch] = useState('');
  const [status, setStatus] = useState('');
  const [priority, setPriority] = useState('');
  const [page, setPage] = useState(1);

  useEffect(() => {
    setLoading(true);
    setError(null);
    Promise.all([
      getSpace(spaceKey).catch(() => ({ key: spaceKey, name: spaceKey })),
      getSpaceTree(spaceKey).catch(() => ({ tree: [] })),
    ]).then(([spaceData, treeData]) => {
      setSpace(spaceData);
      setTree(treeData.tree || []);
    }).catch(() => setError('Failed to load space'))
      .finally(() => setLoading(false));
  }, [spaceKey]);

  const fetchPages = useCallback(async () => {
    setPagesLoading(true);
    try {
      const params = { page, per_page: PAGE_SIZE, sort_by: 'title', sort_dir: 'asc' };
      if (search) params.search = search;
      if (status) params.status = status;
      if (priority) params.priority = priority;
      const data = await getSpacePages(spaceKey, params);
      setPages(data.pages || []);
      setTotal(data.total || 0);
    } catch {
      setPages([]);
    } finally {
      setPagesLoading(false);
    }
  }, [spaceKey, page, search, status, priority]);

  useEffect(() => { fetchPages(); }, [fetchPages]);

  const totalPages = Math.ceil(total / PAGE_SIZE);

  if (loading) {
    return (
      <div className="animate-fade-in flex gap-6">
        <div className="w-72 hidden lg:block">
          <div className="card p-4"><div className="loading-skeleton h-64" /></div>
        </div>
        <div className="flex-1">
          <div className="loading-skeleton h-7 w-48 mb-6" />
          <div className="card p-4"><div className="loading-skeleton h-12 mb-4" /><div className="loading-skeleton h-64" /></div>
        </div>
      </div>
    );
  }

  if (error) {
    return (
      <div className="empty-state">
        <div className="w-14 h-14 rounded-full bg-red-50 dark:bg-red-900/30 flex items-center justify-center mb-4">
          <ExclamationCircleIcon className="h-6 w-6 text-red-500" />
        </div>
        <div className="text-sm font-medium text-slate-900 dark:text-slate-100">{error}</div>
      </div>
    );
  }

  const activeFilters = [search, status, priority].filter(Boolean).length;

  return (
    <div className="animate-fade-in flex gap-6">
      {/* Tree sidebar */}
      <aside className="w-72 flex-shrink-0 hidden lg:block">
        <div className="card max-h-[calc(100vh-120px)] overflow-y-auto sticky top-6 p-3">
          <div className="flex items-center gap-2 px-2 pb-3 mb-2 border-b border-slate-100 dark:border-slate-700/50">
            <FolderOpenIcon className="h-4 w-4 text-brand-500 dark:text-brand-400" />
            <span className="font-semibold text-sm text-slate-800 dark:text-slate-200 truncate">{space?.name || spaceKey}</span>
          </div>
          <PageTree tree={tree} spaceKey={spaceKey} />
        </div>
      </aside>

      <div className="flex-1 min-w-0">
        <div className="flex items-center justify-between mb-6">
          <div>
            <div className="flex items-center gap-2">
              <Link to="/spaces" className="text-sm text-slate-400 dark:text-slate-500 hover:text-brand-600 dark:hover:text-brand-400 transition-colors">Spaces</Link>
              <ChevronRightIcon className="h-3 w-3 text-slate-300 dark:text-slate-600" />
              <h1 className="page-title">{space?.name || spaceKey}</h1>
            </div>
            {space?.description && (
              <p className="caption mt-1">{space.description}</p>
            )}
          </div>
          <span className="badge-brand tabular-nums">{total} pages</span>
        </div>

        {/* Filters */}
        <div className="card p-3 mb-4">
          <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-2.5">
            <div className="relative lg:col-span-2">
              <MagnifyingGlassIcon className="absolute left-3 top-2.5 h-4 w-4 text-slate-400" />
              <input
                type="text"
                placeholder="Search in this space..."
                value={search}
                onChange={(e) => { setSearch(e.target.value); setPage(1); }}
                className="input-field pl-9"
              />
            </div>
            <select
              value={priority}
              onChange={(e) => { setPriority(e.target.value); setPage(1); }}
              className="input-field"
            >
              <option value="">All Priorities</option>
              {PRIORITIES.map((p) => <option key={p} value={p}>{p}</option>)}
            </select>
            <select
              value={status}
              onChange={(e) => { setStatus(e.target.value); setPage(1); }}
              className="input-field"
            >
              <option value="">All Statuses</option>
              {STATUSES.map((s) => <option key={s} value={s}>{s.replace(/_/g, ' ')}</option>)}
            </select>
          </div>
          {activeFilters > 0 && (
            <div className="flex items-center gap-2 mt-2 pt-2 border-t border-slate-100 dark:border-slate-700/50">
              <span className="text-2xs text-slate-400 dark:text-slate-500">{activeFilters} filter{activeFilters > 1 ? 's' : ''} active</span>
              <button
                onClick={() => { setSearch(''); setStatus(''); setPriority(''); setPage(1); }}
                className="text-2xs text-brand-600 dark:text-brand-400 hover:text-brand-700 dark:hover:text-brand-300 font-medium"
              >
                Clear all
              </button>
            </div>
          )}
        </div>

        {/* Table */}
        <div className="card overflow-hidden">
          {pagesLoading ? (
            <div className="p-8 flex items-center justify-center">
              <div className="animate-spin h-5 w-5 border-2 border-slate-200 dark:border-slate-600 border-t-brand-500 rounded-full" />
            </div>
          ) : pages.length === 0 ? (
            <div className="empty-state py-16">
              <DocumentTextIcon className="h-8 w-8 text-slate-300 dark:text-slate-600 mb-3" />
              <div className="text-sm text-slate-500 dark:text-slate-400">No pages found</div>
              {activeFilters > 0 && (
                <button onClick={() => { setSearch(''); setStatus(''); setPriority(''); setPage(1); }}
                  className="text-sm text-brand-600 dark:text-brand-400 hover:text-brand-700 dark:hover:text-brand-300 mt-2 font-medium">
                  Clear filters
                </button>
              )}
            </div>
          ) : (
            <>
              <table className="w-full">
                <thead>
                  <tr>
                    <th className="table-header">Title</th>
                    <th className="table-header w-24">Priority</th>
                    <th className="table-header w-28">Status</th>
                    <th className="table-header w-28">Owner</th>
                    <th className="table-header w-16">WL</th>
                    <th className="table-header w-28 text-right">Updated</th>
                  </tr>
                </thead>
                <tbody>
                  {pages.map((p) => {
                    const pid = p.confluence_page_id || p.id;
                    return (
                      <tr
                        key={pid}
                        className="table-row-interactive"
                        onClick={() => navigate(`/spaces/${spaceKey}/pages/${pid}/${slugify(p.title)}`)}
                      >
                        <td className="table-cell font-medium text-slate-900 dark:text-slate-100">{p.title}</td>
                        <td className="table-cell"><PriorityBadge priority={p.priority} /></td>
                        <td className="table-cell"><StatusBadge status={p.local_status || p.status} /></td>
                        <td className="table-cell text-slate-500 dark:text-slate-400">{p.owner || <span className="text-slate-300 dark:text-slate-600">&mdash;</span>}</td>
                        <td className="table-cell">
                          <WLBadge flagLabelMissing={p.flag_label_missing} flagTaxonomyUnmapped={p.flag_taxonomy_unmapped} />
                        </td>
                        <td className="table-cell text-right text-2xs text-slate-400 tabular-nums">
                          {p.updated_at ? new Date(p.updated_at).toLocaleDateString() : '\u2014'}
                        </td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>

              {totalPages > 1 && (
                <div className="flex items-center justify-between px-4 py-3 border-t border-slate-100 dark:border-slate-700/50">
                  <span className="text-2xs text-slate-400 dark:text-slate-500 tabular-nums">
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
    </div>
  );
}
