import React, { useEffect, useState, useCallback } from 'react';
import { useNavigate, useSearchParams } from 'react-router-dom';
import {
  MagnifyingGlassIcon,
  ChevronLeftIcon,
  ChevronRightIcon,
  DocumentTextIcon,
  UserGroupIcon,
  BuildingOfficeIcon,
  ChevronUpIcon,
  ChevronDownIcon,
  XMarkIcon,
} from '@heroicons/react/24/outline';
import PriorityBadge from '../components/PriorityBadge';
import StatusBadge from '../components/StatusBadge';
import { getTeamsDomainsSummary, getTeamsDomainsPages } from '../api/client';
import useSpaceNames from '../hooks/useSpaceNames';

const slugify = (text) =>
  (text || '').toLowerCase().replace(/[^a-z0-9]+/g, '-').replace(/(^-|-$)/g, '');

const PAGE_SIZE = 25;

const CLS_STATUS_COLORS = {
  confirmed: 'bg-emerald-50 text-emerald-700 dark:bg-emerald-900/30 dark:text-emerald-300',
  changed: 'bg-blue-50 text-blue-700 dark:bg-blue-900/30 dark:text-blue-300',
  domain_only: 'bg-amber-50 text-amber-700 dark:bg-amber-900/30 dark:text-amber-300',
  ambiguous: 'bg-orange-50 text-orange-700 dark:bg-orange-900/30 dark:text-orange-300',
  conflict: 'bg-red-50 text-red-700 dark:bg-red-900/30 dark:text-red-300',
  unassigned: 'bg-slate-50 text-slate-500 dark:bg-slate-800 dark:text-slate-400',
  read_error: 'bg-red-50 text-red-700 dark:bg-red-900/30 dark:text-red-300',
};

function ClassificationBadge({ status }) {
  if (!status) return <span className="text-slate-300 dark:text-slate-600">&mdash;</span>;
  const cls = CLS_STATUS_COLORS[status] || CLS_STATUS_COLORS.unassigned;
  return (
    <span className={`inline-flex items-center px-1.5 py-0.5 rounded text-2xs font-medium ${cls}`}>
      {status.replace(/_/g, ' ')}
    </span>
  );
}

export default function TeamsDomains() {
  const navigate = useNavigate();
  const [searchParams, setSearchParams] = useSearchParams();

  const [view, setView] = useState(searchParams.get('view') || 'domains');
  const [summary, setSummary] = useState(null);
  const [loading, setLoading] = useState(true);

  // Selection state
  const [selectedDomain, setSelectedDomain] = useState(searchParams.get('domain') || '');
  const [selectedTeam, setSelectedTeam] = useState(searchParams.get('team') || '');

  // Pages state
  const [pages, setPages] = useState([]);
  const [totalPages, setTotalPages] = useState(0);
  const [pagesLoading, setPagesLoading] = useState(false);
  const [search, setSearch] = useState(searchParams.get('search') || '');
  const [page, setPage] = useState(parseInt(searchParams.get('page') || '1', 10));
  const [sortBy, setSortBy] = useState('title');
  const [sortDir, setSortDir] = useState('asc');

  const { resolveSpace } = useSpaceNames();

  // Load summary data
  useEffect(() => {
    setLoading(true);
    getTeamsDomainsSummary()
      .then(setSummary)
      .catch(() => {})
      .finally(() => setLoading(false));
  }, []);

  // Load pages when filters change
  const fetchPages = useCallback(async () => {
    if (!selectedDomain && !selectedTeam) {
      setPages([]);
      setTotalPages(0);
      return;
    }
    setPagesLoading(true);
    try {
      const params = { page, per_page: PAGE_SIZE, sort_by: sortBy, sort_dir: sortDir };
      if (selectedDomain) params.domain = selectedDomain;
      if (selectedTeam) params.team = selectedTeam;
      if (search) params.search = search;
      const data = await getTeamsDomainsPages(params);
      setPages(data.pages || []);
      setTotalPages(data.total || 0);
    } catch {
      setPages([]);
      setTotalPages(0);
    } finally {
      setPagesLoading(false);
    }
  }, [selectedDomain, selectedTeam, search, page, sortBy, sortDir]);

  useEffect(() => { fetchPages(); }, [fetchPages]);

  // Sync URL params
  useEffect(() => {
    const params = {};
    if (view !== 'domains') params.view = view;
    if (selectedDomain) params.domain = selectedDomain;
    if (selectedTeam) params.team = selectedTeam;
    if (search) params.search = search;
    if (page > 1) params.page = page;
    setSearchParams(params, { replace: true });
  }, [view, selectedDomain, selectedTeam, search, page, setSearchParams]);

  const handleDomainSelect = (domain) => {
    setSelectedDomain(domain);
    setSelectedTeam('');
    setPage(1);
  };

  const handleTeamSelect = (team, domain) => {
    if (view === 'teams' && domain) {
      setSelectedDomain(domain);
    }
    setSelectedTeam(team);
    setPage(1);
  };

  const clearSelection = () => {
    setSelectedDomain('');
    setSelectedTeam('');
    setSearch('');
    setPage(1);
  };

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

  const handleRowClick = (rb) => {
    const sk = rb.space_key;
    const pid = rb.id || rb.confluence_page_id;
    navigate(`/spaces/${sk}/pages/${pid}/${slugify(rb.title)}`);
  };

  const pageCount = Math.ceil(totalPages / PAGE_SIZE);

  // Get teams for selected domain
  const domainTeams = summary?.domains?.find((d) => d.name === selectedDomain)?.teams || [];

  if (loading) {
    return (
      <div className="animate-fade-in p-8">
        <div className="loading-skeleton h-7 w-48 mb-6" />
        <div className="loading-skeleton h-40 w-full" />
      </div>
    );
  }

  return (
    <div className="animate-fade-in">
      {/* Header */}
      <div className="flex items-center justify-between mb-6">
        <div>
          <h1 className="page-title">Teams & Domains</h1>
          <p className="caption mt-0.5">Browse runbooks by organizational hierarchy</p>
        </div>
        <div className="flex items-center gap-2">
          {summary && (
            <span className="badge-brand tabular-nums">
              {summary.total_classified} classified
            </span>
          )}
        </div>
      </div>

      {/* View selector */}
      <div className="card p-1 mb-4 inline-flex gap-1">
        <button
          onClick={() => { setView('domains'); clearSelection(); }}
          className={`px-4 py-2 rounded-lg text-sm font-medium transition-colors ${
            view === 'domains'
              ? 'bg-brand-600 text-white shadow-sm'
              : 'text-slate-600 dark:text-slate-400 hover:bg-slate-100 dark:hover:bg-slate-700'
          }`}
        >
          <BuildingOfficeIcon className="h-4 w-4 inline mr-1.5 -mt-0.5" />
          Domains
        </button>
        <button
          onClick={() => { setView('teams'); clearSelection(); }}
          className={`px-4 py-2 rounded-lg text-sm font-medium transition-colors ${
            view === 'teams'
              ? 'bg-brand-600 text-white shadow-sm'
              : 'text-slate-600 dark:text-slate-400 hover:bg-slate-100 dark:hover:bg-slate-700'
          }`}
        >
          <UserGroupIcon className="h-4 w-4 inline mr-1.5 -mt-0.5" />
          Teams
        </button>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-4 gap-4">
        {/* Left panel: Domain/Team list */}
        <div className="lg:col-span-1">
          {view === 'domains' ? (
            <DomainsList
              domains={summary?.domains || []}
              selectedDomain={selectedDomain}
              selectedTeam={selectedTeam}
              onDomainSelect={handleDomainSelect}
              onTeamSelect={handleTeamSelect}
              domainTeams={domainTeams}
            />
          ) : (
            <TeamsList
              teams={summary?.teams || []}
              selectedTeam={selectedTeam}
              onTeamSelect={handleTeamSelect}
            />
          )}
        </div>

        {/* Right panel: Runbook results */}
        <div className="lg:col-span-3">
          {(selectedDomain || selectedTeam) ? (
            <div>
              {/* Active selection header */}
              <div className="flex items-center gap-2 mb-3 flex-wrap">
                {selectedDomain && (
                  <span className="inline-flex items-center gap-1 px-2.5 py-1 rounded-full bg-brand-50 dark:bg-brand-900/30 text-brand-700 dark:text-brand-300 text-sm font-medium">
                    {selectedDomain}
                    <button onClick={() => handleDomainSelect('')} className="hover:text-brand-900 dark:hover:text-brand-100">
                      <XMarkIcon className="h-3.5 w-3.5" />
                    </button>
                  </span>
                )}
                {selectedTeam && (
                  <span className="inline-flex items-center gap-1 px-2.5 py-1 rounded-full bg-emerald-50 dark:bg-emerald-900/30 text-emerald-700 dark:text-emerald-300 text-sm font-medium">
                    {selectedTeam}
                    <button onClick={() => setSelectedTeam('')} className="hover:text-emerald-900 dark:hover:text-emerald-100">
                      <XMarkIcon className="h-3.5 w-3.5" />
                    </button>
                  </span>
                )}
                <span className="text-2xs text-slate-400 tabular-nums">{totalPages} pages</span>

                {/* Search within selection */}
                <div className="relative ml-auto">
                  <MagnifyingGlassIcon className="absolute left-2.5 top-2 h-4 w-4 text-slate-400" />
                  <input
                    type="text"
                    placeholder="Search..."
                    value={search}
                    onChange={(e) => { setSearch(e.target.value); setPage(1); }}
                    className="input-field pl-8 py-1.5 text-sm w-48"
                  />
                </div>
              </div>

              {/* Results table */}
              <div className="card overflow-hidden">
                {pagesLoading ? (
                  <div className="p-8 flex items-center justify-center">
                    <div className="animate-spin h-5 w-5 border-2 border-slate-200 border-t-brand-500 rounded-full" />
                  </div>
                ) : pages.length === 0 ? (
                  <div className="empty-state py-16">
                    <DocumentTextIcon className="h-8 w-8 text-slate-300 dark:text-slate-600 mb-3" />
                    <div className="text-sm text-slate-500 dark:text-slate-400">No runbooks found</div>
                  </div>
                ) : (
                  <>
                    <div className="overflow-x-auto">
                      <table className="w-full min-w-[800px]">
                        <thead>
                          <tr>
                            <th className="table-header cursor-pointer select-none" onClick={() => handleSort('title')}>
                              Title <SortIcon column="title" />
                            </th>
                            <th className="table-header w-24">Space</th>
                            <th className="table-header w-32">Domain</th>
                            <th className="table-header w-32">Team</th>
                            <th className="table-header w-20 cursor-pointer select-none" onClick={() => handleSort('priority')}>
                              Priority <SortIcon column="priority" />
                            </th>
                            <th className="table-header w-28">Status</th>
                            <th className="table-header w-24 text-right cursor-pointer select-none" onClick={() => handleSort('updated_at')}>
                              Updated <SortIcon column="updated_at" />
                            </th>
                          </tr>
                        </thead>
                        <tbody>
                          {pages.map((rb) => {
                            const pid = rb.id || rb.confluence_page_id;
                            return (
                              <tr key={pid} className="table-row-interactive" onClick={() => handleRowClick(rb)}>
                                <td className="table-cell font-medium text-slate-900 dark:text-slate-100 truncate max-w-[300px]">{rb.title}</td>
                                <td className="table-cell"><span className="badge-slate whitespace-nowrap truncate">{resolveSpace(rb.space_key) || '\u2014'}</span></td>
                                <td className="table-cell text-sm text-slate-600 dark:text-slate-400 truncate">{rb.domain || <span className="text-slate-300 dark:text-slate-600">&mdash;</span>}</td>
                                <td className="table-cell text-sm text-slate-600 dark:text-slate-400 truncate">{rb.team || <span className="text-slate-300 dark:text-slate-600">&mdash;</span>}</td>
                                <td className="table-cell"><PriorityBadge priority={rb.priority} /></td>
                                <td className="table-cell"><ClassificationBadge status={rb.classification_status} /></td>
                                <td className="table-cell text-right text-2xs text-slate-400 tabular-nums">
                                  {rb.updated_at ? new Date(rb.updated_at).toLocaleDateString() : '\u2014'}
                                </td>
                              </tr>
                            );
                          })}
                        </tbody>
                      </table>
                    </div>

                    {pageCount > 1 && (
                      <div className="flex items-center justify-between px-4 py-3 border-t border-slate-100 dark:border-slate-700">
                        <span className="text-2xs text-slate-400 tabular-nums">
                          Page {page} of {pageCount} ({totalPages} total)
                        </span>
                        <div className="flex gap-1.5">
                          <button className="btn-ghost" disabled={page <= 1}
                            onClick={() => setPage((p) => Math.max(1, p - 1))}>
                            <ChevronLeftIcon className="h-4 w-4" /> Prev
                          </button>
                          <button className="btn-ghost" disabled={page >= pageCount}
                            onClick={() => setPage((p) => Math.min(pageCount, p + 1))}>
                            Next <ChevronRightIcon className="h-4 w-4" />
                          </button>
                        </div>
                      </div>
                    )}
                  </>
                )}
              </div>
            </div>
          ) : (
            <div className="card">
              <div className="empty-state py-20">
                <BuildingOfficeIcon className="h-10 w-10 text-slate-300 dark:text-slate-600 mb-3" />
                <div className="text-sm text-slate-500 dark:text-slate-400">
                  Select a {view === 'domains' ? 'domain' : 'team'} to view its runbooks
                </div>
              </div>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}


function DomainsList({ domains, selectedDomain, selectedTeam, onDomainSelect, onTeamSelect, domainTeams }) {
  return (
    <div className="space-y-1">
      {domains.map((d) => (
        <div key={d.name}>
          <button
            onClick={() => onDomainSelect(d.name)}
            className={`w-full flex items-center justify-between px-3 py-2 rounded-lg text-sm text-left transition-colors ${
              selectedDomain === d.name
                ? 'bg-brand-50 dark:bg-brand-900/30 text-brand-700 dark:text-brand-300 font-medium'
                : 'text-slate-700 dark:text-slate-300 hover:bg-slate-100 dark:hover:bg-slate-800'
            }`}
          >
            <span className="truncate">{d.name}</span>
            <span className="text-2xs text-slate-400 tabular-nums ml-2 flex-shrink-0">{d.count}</span>
          </button>

          {/* Show teams under selected domain */}
          {selectedDomain === d.name && domainTeams.length > 0 && (
            <div className="ml-3 mt-0.5 mb-1 space-y-0.5 border-l-2 border-brand-200 dark:border-brand-800 pl-2">
              {domainTeams.map((t) => (
                <button
                  key={t.name}
                  onClick={() => onTeamSelect(t.name)}
                  className={`w-full flex items-center justify-between px-2.5 py-1.5 rounded-md text-sm text-left transition-colors ${
                    selectedTeam === t.name
                      ? 'bg-emerald-50 dark:bg-emerald-900/30 text-emerald-700 dark:text-emerald-300 font-medium'
                      : 'text-slate-600 dark:text-slate-400 hover:bg-slate-50 dark:hover:bg-slate-800'
                  }`}
                >
                  <span className="truncate">{t.name}</span>
                  <span className="text-2xs text-slate-400 tabular-nums ml-2 flex-shrink-0">{t.count}</span>
                </button>
              ))}
            </div>
          )}
        </div>
      ))}

      {domains.length === 0 && (
        <div className="text-sm text-slate-400 dark:text-slate-500 text-center py-8">
          No domains configured
        </div>
      )}
    </div>
  );
}


function TeamsList({ teams, selectedTeam, onTeamSelect }) {
  return (
    <div className="space-y-0.5">
      {teams.map((t) => (
        <button
          key={t.name}
          onClick={() => onTeamSelect(t.name, t.domain)}
          className={`w-full flex items-center justify-between px-3 py-2 rounded-lg text-sm text-left transition-colors ${
            selectedTeam === t.name
              ? 'bg-emerald-50 dark:bg-emerald-900/30 text-emerald-700 dark:text-emerald-300 font-medium'
              : 'text-slate-700 dark:text-slate-300 hover:bg-slate-100 dark:hover:bg-slate-800'
          }`}
        >
          <div className="min-w-0">
            <div className="truncate">{t.name}</div>
            <div className="text-2xs text-slate-400 dark:text-slate-500 truncate">{t.domain}</div>
          </div>
          <span className="text-2xs text-slate-400 tabular-nums ml-2 flex-shrink-0">{t.count}</span>
        </button>
      ))}

      {teams.length === 0 && (
        <div className="text-sm text-slate-400 dark:text-slate-500 text-center py-8">
          No teams configured
        </div>
      )}
    </div>
  );
}
