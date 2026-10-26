import React, { useEffect, useState, useCallback } from 'react';
import { useNavigate, useSearchParams } from 'react-router-dom';
import {
  MagnifyingGlassIcon,
  ChevronUpIcon,
  ChevronDownIcon,
  ChevronLeftIcon,
  ChevronRightIcon,
  DocumentTextIcon,
  XMarkIcon,
  FunnelIcon,
} from '@heroicons/react/24/outline';
import PriorityBadge from '../components/PriorityBadge';
import StatusBadge from '../components/StatusBadge';
import WLBadge from '../components/WLBadge';
import { getRunbooks, bulkUpdateRunbooks, getFilterValues } from '../api/client';
import useSpaceNames from '../hooks/useSpaceNames';

const slugify = (text) =>
  (text || '').toLowerCase().replace(/[^a-z0-9]+/g, '-').replace(/(^-|-$)/g, '');

const STATUSES = ['imported', 'active', 'stale', 'needs_review', 'archived'];
const PAGE_SIZE = 25;

const REVIEW_REASON_LABELS = {
  older_than_one_year: 'Older Than 1 Year',
  contains_pagerduty: 'PagerDuty',
  contains_datadog: 'Datadog',
  contains_nagios: 'Nagios',
  contains_moving_on: 'Moving On',
};

export default function Runbooks() {
  const navigate = useNavigate();
  const [searchParams, setSearchParams] = useSearchParams();

  const [runbooks, setRunbooks] = useState([]);
  const [total, setTotal] = useState(0);
  const [loading, setLoading] = useState(true);
  const [selected, setSelected] = useState(new Set());
  const [filterValues, setFilterValues] = useState(null);

  const [search, setSearch] = useState(searchParams.get('search') || '');
  const [priority, setPriority] = useState(searchParams.get('priority') || '');
  const [status, setStatus] = useState(searchParams.get('status') || '');
  const [domain, setDomain] = useState(searchParams.get('domain') || '');
  const [owner, setOwner] = useState(searchParams.get('owner') || '');
  const [label, setLabel] = useState(searchParams.get('label') || '');
  const [reviewReason, setReviewReason] = useState(searchParams.get('review_reason') || '');
  const [page, setPage] = useState(parseInt(searchParams.get('page') || '1', 10));
  const [sortBy, setSortBy] = useState('title');
  const [sortDir, setSortDir] = useState('asc');

  const { resolveSpace } = useSpaceNames();
  const [bulkPriority, setBulkPriority] = useState('');
  const [bulkStatus, setBulkStatus] = useState('');
  const [bulkOwner, setBulkOwner] = useState('');

  useEffect(() => {
    getFilterValues().then(setFilterValues).catch(() => {});
  }, []);

  const fetchRunbooks = useCallback(async () => {
    setLoading(true);
    try {
      const params = { page, per_page: PAGE_SIZE, sort_by: sortBy, sort_dir: sortDir };
      if (search) params.search = search;
      if (priority) params.priority = priority;
      if (status) params.status = status;
      if (domain) params.domain = domain;
      if (owner) params.owner = owner;
      if (label) params.label = label;
      if (reviewReason) params.review_reason = reviewReason;
      const data = await getRunbooks(params);
      setRunbooks(data.runbooks || data.items || []);
      setTotal(data.total || 0);
    } catch {
      setRunbooks([]);
    } finally {
      setLoading(false);
      setSelected(new Set());
    }
  }, [page, sortBy, sortDir, search, priority, status, domain, owner, label, reviewReason]);

  useEffect(() => { fetchRunbooks(); }, [fetchRunbooks]);

  useEffect(() => {
    const params = {};
    if (search) params.search = search;
    if (priority) params.priority = priority;
    if (status) params.status = status;
    if (domain) params.domain = domain;
    if (owner) params.owner = owner;
    if (label) params.label = label;
    if (reviewReason) params.review_reason = reviewReason;
    if (page > 1) params.page = page;
    setSearchParams(params, { replace: true });
  }, [search, priority, status, domain, owner, label, reviewReason, page, setSearchParams]);

  const handleSort = (column) => {
    if (sortBy === column) {
      setSortDir((d) => (d === 'asc' ? 'desc' : 'asc'));
    } else {
      setSortBy(column);
      setSortDir('asc');
    }
    setPage(1);
  };

  const SortIcon = ({ column }) => {
    if (sortBy !== column) return null;
    return sortDir === 'asc'
      ? <ChevronUpIcon className="h-3 w-3 inline ml-0.5" />
      : <ChevronDownIcon className="h-3 w-3 inline ml-0.5" />;
  };

  const toggleSelect = (id) => {
    setSelected((prev) => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id); else next.add(id);
      return next;
    });
  };

  const toggleSelectAll = () => {
    if (selected.size === runbooks.length) {
      setSelected(new Set());
    } else {
      setSelected(new Set(runbooks.map((r) => r.id || r.confluence_page_id)));
    }
  };

  const handleBulkUpdate = async () => {
    if (selected.size === 0) return;
    const updates = {};
    if (bulkPriority) updates.priority = bulkPriority;
    if (bulkStatus) updates.local_status = bulkStatus;
    if (bulkOwner) updates.owner = bulkOwner;
    if (Object.keys(updates).length === 0) return;
    try {
      await bulkUpdateRunbooks({ ids: [...selected], updates });
      fetchRunbooks();
      setBulkPriority('');
      setBulkStatus('');
      setBulkOwner('');
    } catch { /* silent */ }
  };

  const clearAllFilters = () => {
    setSearch(''); setPriority(''); setStatus(''); setDomain('');
    setOwner(''); setLabel(''); setReviewReason(''); setPage(1);
  };

  const activeFilters = [
    search && { key: 'search', label: `"${search}"`, clear: () => setSearch('') },
    priority && { key: 'priority', label: priority, clear: () => setPriority('') },
    status && { key: 'status', label: status.replace(/_/g, ' '), clear: () => setStatus('') },
    domain && { key: 'domain', label: domain, clear: () => setDomain('') },
    owner && { key: 'owner', label: owner, clear: () => setOwner('') },
    label && { key: 'label', label: label, clear: () => setLabel('') },
    reviewReason && { key: 'review_reason', label: REVIEW_REASON_LABELS[reviewReason] || reviewReason, clear: () => setReviewReason('') },
  ].filter(Boolean);

  const totalPages = Math.ceil(total / PAGE_SIZE);

  const handleRowClick = (rb) => {
    const sk = rb.space_key;
    const pid = rb.id || rb.confluence_page_id;
    navigate(sk ? `/spaces/${sk}/pages/${pid}/${slugify(rb.title)}` : `/runbooks/${pid}`);
  };

  return (
    <div className="animate-fade-in">
      <div className="flex items-center justify-between mb-6">
        <div>
          <h1 className="page-title">All Pages</h1>
          <p className="caption mt-0.5">Browse and manage all imported content</p>
        </div>
        <span className="badge-brand tabular-nums">{total} pages</span>
      </div>

      {/* Filters */}
      <div className="card p-3 mb-4">
        <div className="flex items-center gap-2 mb-2.5">
          <FunnelIcon className="h-4 w-4 text-slate-400" />
          <span className="text-xs font-medium text-slate-500">Filters</span>
        </div>
        <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-4 gap-2.5">
          <div className="relative col-span-2 sm:col-span-3 lg:col-span-4">
            <MagnifyingGlassIcon className="absolute left-3 top-2.5 h-4 w-4 text-slate-400" />
            <input type="text" placeholder="Search pages by title..." value={search}
              onChange={(e) => { setSearch(e.target.value); setPage(1); }}
              className="input-field pl-9" />
          </div>

          <select value={domain} onChange={(e) => { setDomain(e.target.value); setPage(1); }}
            className="input-field">
            <option value="">All Domains</option>
            {(filterValues?.domains || []).map((d) => <option key={d} value={d}>{d}</option>)}
          </select>

          <select value={priority} onChange={(e) => { setPriority(e.target.value); setPage(1); }}
            className="input-field">
            <option value="">All Priorities</option>
            {(filterValues?.priorities || []).map((p) => <option key={p} value={p}>{p}</option>)}
          </select>

          <select value={owner} onChange={(e) => { setOwner(e.target.value); setPage(1); }}
            className="input-field">
            <option value="">All Owners</option>
            {(filterValues?.owners || []).map((o) => <option key={o} value={o}>{o}</option>)}
          </select>

          <select value={reviewReason} onChange={(e) => { setReviewReason(e.target.value); setPage(1); }}
            className="input-field">
            <option value="">All Review Reasons</option>
            {(filterValues?.review_reasons || []).map((r) => (
              <option key={r} value={r}>{REVIEW_REASON_LABELS[r] || r}</option>
            ))}
          </select>

          <select value={label} onChange={(e) => { setLabel(e.target.value); setPage(1); }}
            className="input-field">
            <option value="">All Labels</option>
            {(filterValues?.labels || []).map((l) => <option key={l} value={l}>{l}</option>)}
          </select>

          <select value={status} onChange={(e) => { setStatus(e.target.value); setPage(1); }}
            className="input-field">
            <option value="">All Statuses</option>
            {STATUSES.map((s) => <option key={s} value={s}>{s.replace(/_/g, ' ')}</option>)}
          </select>
        </div>

        {/* Active filter chips */}
        {activeFilters.length > 0 && (
          <div className="flex items-center gap-2 mt-2.5 pt-2.5 border-t border-slate-100 dark:border-slate-700 flex-wrap">
            {activeFilters.map((f) => (
              <span key={f.key} className="inline-flex items-center gap-1 px-2 py-0.5 rounded-full bg-brand-50 dark:bg-brand-900/30 text-brand-700 dark:text-brand-300 text-2xs font-medium">
                {f.label}
                <button onClick={() => { f.clear(); setPage(1); }} className="hover:text-brand-900 dark:hover:text-brand-100">
                  <XMarkIcon className="h-3 w-3" />
                </button>
              </span>
            ))}
            <button onClick={clearAllFilters}
              className="text-2xs text-slate-500 hover:text-slate-700 dark:text-slate-400 dark:hover:text-slate-200 font-medium ml-1">
              Clear all
            </button>
          </div>
        )}
      </div>

      {/* Bulk actions */}
      {selected.size > 0 && (
        <div className="card p-3 mb-4 bg-brand-50 dark:bg-brand-900/20 border-brand-200 dark:border-brand-800 animate-slide-in">
          <div className="flex items-center gap-3 flex-wrap">
            <span className="text-sm font-medium text-brand-800 dark:text-brand-200">{selected.size} selected</span>
            <div className="flex items-center gap-2 flex-1 flex-wrap">
              <select value={bulkPriority} onChange={(e) => setBulkPriority(e.target.value)}
                className="input-field w-auto min-w-[120px]">
                <option value="">Set Priority</option>
                {(filterValues?.priorities || ['P1','P2','P3','P4','P5']).map((p) => <option key={p} value={p}>{p}</option>)}
              </select>
              <select value={bulkStatus} onChange={(e) => setBulkStatus(e.target.value)}
                className="input-field w-auto min-w-[120px]">
                <option value="">Set Status</option>
                {STATUSES.map((s) => <option key={s} value={s}>{s.replace(/_/g, ' ')}</option>)}
              </select>
              <input placeholder="Set Owner" value={bulkOwner}
                onChange={(e) => setBulkOwner(e.target.value)}
                className="input-field w-auto min-w-[120px]" />
              <button onClick={handleBulkUpdate} className="btn-primary text-sm py-1.5">Apply</button>
            </div>
          </div>
        </div>
      )}

      {/* Table */}
      <div className="card overflow-hidden">
        {loading ? (
          <div className="p-8 flex items-center justify-center">
            <div className="animate-spin h-5 w-5 border-2 border-slate-200 border-t-brand-500 rounded-full" />
          </div>
        ) : runbooks.length === 0 ? (
          <div className="empty-state py-16">
            <DocumentTextIcon className="h-8 w-8 text-slate-300 dark:text-slate-600 mb-3" />
            <div className="text-sm text-slate-500 dark:text-slate-400">No pages found</div>
            {activeFilters.length > 0 && (
              <button onClick={clearAllFilters}
                className="text-sm text-brand-600 mt-2 font-medium">Clear filters</button>
            )}
          </div>
        ) : (
          <>
            <div className="overflow-x-auto">
              <table className="w-full min-w-[900px]">
                <thead>
                  <tr>
                    <th className="table-header w-10">
                      <input type="checkbox"
                        checked={runbooks.length > 0 && selected.size === runbooks.length}
                        onChange={toggleSelectAll}
                        className="rounded border-slate-300 text-brand-600 focus:ring-brand-500/30" />
                    </th>
                    <th className="table-header cursor-pointer select-none" onClick={() => handleSort('title')}>
                      Title <SortIcon column="title" />
                    </th>
                    <th className="table-header w-32">Space</th>
                    <th className="table-header w-32">Domain</th>
                    <th className="table-header w-20 cursor-pointer select-none" onClick={() => handleSort('priority')}>
                      Priority <SortIcon column="priority" />
                    </th>
                    <th className="table-header w-28">Owner</th>
                    <th className="table-header w-24">Status</th>
                    <th className="table-header w-14">WL</th>
                    <th className="table-header w-24 text-right cursor-pointer select-none" onClick={() => handleSort('updated_at')}>
                      Updated <SortIcon column="updated_at" />
                    </th>
                  </tr>
                </thead>
                <tbody>
                  {runbooks.map((rb) => {
                    const pid = rb.id || rb.confluence_page_id;
                    return (
                      <tr key={pid} className="table-row-interactive" onClick={() => handleRowClick(rb)}>
                        <td className="table-cell" onClick={(e) => e.stopPropagation()}>
                          <input type="checkbox" checked={selected.has(pid)}
                            onChange={() => toggleSelect(pid)}
                            className="rounded border-slate-300 text-brand-600 focus:ring-brand-500/30" />
                        </td>
                        <td className="table-cell font-medium text-slate-900 dark:text-slate-100 truncate max-w-[300px]">{rb.title}</td>
                        <td className="table-cell"><span className="badge-slate whitespace-nowrap truncate">{resolveSpace(rb.space_key) || '\u2014'}</span></td>
                        <td className="table-cell text-sm text-slate-600 dark:text-slate-400 truncate">{rb.domain || <span className="text-slate-300 dark:text-slate-600">&mdash;</span>}</td>
                        <td className="table-cell"><PriorityBadge priority={rb.priority} /></td>
                        <td className="table-cell text-sm text-slate-500 dark:text-slate-400 truncate">{rb.owner || <span className="text-slate-300 dark:text-slate-600">&mdash;</span>}</td>
                        <td className="table-cell"><StatusBadge status={rb.status || rb.local_status} /></td>
                        <td className="table-cell">
                          <WLBadge flagLabelMissing={rb.flag_label_missing} flagTaxonomyUnmapped={rb.flag_taxonomy_unmapped} />
                        </td>
                        <td className="table-cell text-right text-2xs text-slate-400 tabular-nums">
                          {rb.updated_at ? new Date(rb.updated_at).toLocaleDateString() : '\u2014'}
                        </td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>

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
