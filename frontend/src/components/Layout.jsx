import React, { useState, useEffect, useRef, useCallback } from 'react';
import { Link, Outlet, useLocation, useNavigate } from 'react-router-dom';
import {
  Squares2X2Icon,
  DocumentTextIcon,
  FolderOpenIcon,
  MagnifyingGlassIcon,
  UserGroupIcon,
  TagIcon,
  ExclamationTriangleIcon,
  ArrowPathIcon,
  Bars3Icon,
  XMarkIcon,
  CommandLineIcon,
  ChevronRightIcon,
  ChevronDoubleLeftIcon,
  ChevronDoubleRightIcon,
  SunIcon,
  MoonIcon,
} from '@heroicons/react/24/outline';
import { getRunbooks, getSyncStatus } from '../api/client';

const slugify = (text) =>
  (text || '').toLowerCase().replace(/[^a-z0-9]+/g, '-').replace(/(^-|-$)/g, '');

const NAV_SECTIONS = [
  {
    title: null,
    items: [
      { path: '/', label: 'Overview', icon: Squares2X2Icon },
    ],
  },
  {
    title: 'Content',
    items: [
      { path: '/spaces', label: 'Spaces', icon: FolderOpenIcon },
      { path: '/runbooks', label: 'All Pages', icon: DocumentTextIcon },
      { path: '/teams-domains', label: 'Teams & Domains', icon: UserGroupIcon },
    ],
  },
  {
    title: 'Classification',
    items: [
      { path: '/wl', label: 'Without Label', icon: TagIcon },
      { path: '/stale', label: 'Needs Review', icon: ExclamationTriangleIcon },
    ],
  },
  {
    title: 'System',
    items: [
      { path: '/sync', label: 'Synchronization', icon: ArrowPathIcon },
    ],
  },
];

function useTheme() {
  const [dark, setDark] = useState(() => document.documentElement.classList.contains('dark'));

  const toggle = useCallback(() => {
    const next = !dark;
    document.documentElement.classList.add('transitioning');
    document.documentElement.classList.toggle('dark', next);
    localStorage.setItem('theme', next ? 'dark' : 'light');
    setDark(next);
    setTimeout(() => document.documentElement.classList.remove('transitioning'), 250);
  }, [dark]);

  return { dark, toggle };
}

/* The expanded navigation is 240px wide. On a 1280px screen that leaves the
   reader ~976px, which is not enough for a 720-840px article plus the context
   rail, so the article would be squeezed instead. Collapsing to an icon rail
   below 1440px keeps the article at a comfortable width by default; an explicit
   user choice is remembered and always wins. */
const NAV_AUTO_EXPAND_WIDTH = 1440;

function useNavCollapsed() {
  const [collapsed, setCollapsed] = useState(() => {
    const stored = localStorage.getItem('nav-collapsed');
    if (stored === 'true') return true;
    if (stored === 'false') return false;
    return window.innerWidth < NAV_AUTO_EXPAND_WIDTH;
  });

  useEffect(() => {
    if (localStorage.getItem('nav-collapsed') !== null) return;
    const apply = () => setCollapsed(window.innerWidth < NAV_AUTO_EXPAND_WIDTH);
    window.addEventListener('resize', apply);
    return () => window.removeEventListener('resize', apply);
  }, []);

  const toggle = useCallback(() => {
    setCollapsed((prev) => {
      localStorage.setItem('nav-collapsed', String(!prev));
      return !prev;
    });
  }, []);

  return { collapsed, toggle };
}

function CommandPalette({ open, onClose }) {
  const navigate = useNavigate();
  const inputRef = useRef(null);
  const [query, setQuery] = useState('');
  const [suggestions, setSuggestions] = useState([]);
  const [selectedIdx, setSelectedIdx] = useState(0);
  const [loading, setLoading] = useState(false);
  const debounceRef = useRef(null);
  const requestSeqRef = useRef(0);

  useEffect(() => {
    if (open) {
      setQuery('');
      setSuggestions([]);
      setSelectedIdx(0);
      setTimeout(() => inputRef.current?.focus(), 50);
    }
  }, [open]);

  useEffect(() => {
    if (!open) return;
    const handleEsc = (e) => {
      if (e.key === 'Escape') onClose();
    };
    document.addEventListener('keydown', handleEsc);
    return () => document.removeEventListener('keydown', handleEsc);
  }, [open, onClose]);

  const fetchSuggestions = useCallback((val) => {
    if (debounceRef.current) clearTimeout(debounceRef.current);
    if (val.length < 2) {
      setSuggestions([]);
      setLoading(false);
      return;
    }
    setLoading(true);
    const seq = ++requestSeqRef.current;
    debounceRef.current = setTimeout(async () => {
      try {
        const data = await getRunbooks({ search: val, per_page: 8 });
        if (seq !== requestSeqRef.current) return;
        const items = (data.runbooks || []).map((r) => ({
          ...r,
          confluence_page_id: r.id || r.confluence_page_id,
        }));
        setSuggestions(items);
      } catch {
        if (seq !== requestSeqRef.current) return;
        setSuggestions([]);
      } finally {
        if (seq === requestSeqRef.current) setLoading(false);
      }
    }, 200);
  }, []);

  const handleChange = (e) => {
    const val = e.target.value;
    setQuery(val);
    setSelectedIdx(0);
    fetchSuggestions(val);
  };

  const goToResult = (s) => {
    onClose();
    navigate(`/spaces/${s.space_key}/pages/${s.confluence_page_id}/${slugify(s.title)}`);
  };

  const handleKeyDown = (e) => {
    if (e.key === 'ArrowDown') {
      e.preventDefault();
      setSelectedIdx((i) => Math.min(i + 1, suggestions.length - 1));
    } else if (e.key === 'ArrowUp') {
      e.preventDefault();
      setSelectedIdx((i) => Math.max(i - 1, 0));
    } else if (e.key === 'Enter') {
      e.preventDefault();
      if (suggestions[selectedIdx]) {
        goToResult(suggestions[selectedIdx]);
      }
    }
  };

  if (!open) return null;

  const navResults = NAV_SECTIONS.flatMap((s) => s.items)
    .filter((item) => !query || item.label.toLowerCase().includes(query.toLowerCase()));

  return (
    <div className="cmd-backdrop" onClick={onClose}>
      <div
        className="fixed top-[15vh] left-1/2 -translate-x-1/2 w-full max-w-lg animate-slide-in"
        onClick={(e) => e.stopPropagation()}
      >
        <div className="bg-white dark:bg-slate-800 rounded-2xl shadow-dropdown border border-slate-200 dark:border-slate-700 overflow-hidden">
          <div className="flex items-center gap-3 px-4 border-b border-slate-100 dark:border-slate-700">
            <MagnifyingGlassIcon className="h-5 w-5 text-slate-400 flex-shrink-0" />
            <input
              ref={inputRef}
              type="text"
              value={query}
              onChange={handleChange}
              onKeyDown={handleKeyDown}
              placeholder="Search pages, navigate..."
              className="flex-1 py-3.5 text-sm bg-transparent border-none focus:outline-none focus:ring-0 placeholder-slate-400 dark:placeholder-slate-500 text-slate-800 dark:text-slate-200"
            />
            <kbd className="hidden sm:inline-flex items-center px-1.5 py-0.5 text-2xs font-medium text-slate-400 bg-slate-100 dark:bg-slate-700 dark:text-slate-500 rounded">
              ESC
            </kbd>
          </div>

          <div className="max-h-80 overflow-y-auto p-2">
            {loading && (
              <div className="flex items-center gap-2 px-3 py-2 text-sm text-slate-400">
                <div className="animate-spin h-3.5 w-3.5 border-2 border-slate-300 dark:border-slate-600 border-t-brand-500 rounded-full" />
                Searching...
              </div>
            )}

            {suggestions.length > 0 && (
              <div className="mb-1">
                <div className="label px-3 py-1.5">Pages</div>
                {suggestions.slice(0, 8).map((s, idx) => (
                  <button
                    key={s.confluence_page_id}
                    onClick={() => goToResult(s)}
                    className={`w-full flex items-center gap-3 px-3 py-2 rounded-lg text-sm text-left transition-colors ${
                      idx === selectedIdx
                        ? 'bg-brand-50 text-brand-700 dark:bg-brand-900/30 dark:text-brand-300'
                        : 'text-slate-700 dark:text-slate-300 hover:bg-slate-50 dark:hover:bg-slate-700/50'
                    }`}
                  >
                    <DocumentTextIcon className="h-4 w-4 flex-shrink-0 text-slate-400" />
                    <span className="flex-1 truncate font-medium">{s.title}</span>
                    <span className="text-2xs text-slate-400 dark:text-slate-500 flex-shrink-0">{s.space_key}</span>
                    <ChevronRightIcon className="h-3 w-3 text-slate-300 dark:text-slate-600" />
                  </button>
                ))}
              </div>
            )}

            {!query && (
              <div>
                <div className="label px-3 py-1.5">Quick navigation</div>
                {navResults.map((item) => (
                  <button
                    key={item.path}
                    onClick={() => { onClose(); navigate(item.path); }}
                    className="w-full flex items-center gap-3 px-3 py-2 rounded-lg text-sm text-slate-700 dark:text-slate-300 hover:bg-slate-50 dark:hover:bg-slate-700/50 text-left transition-colors"
                  >
                    <item.icon className="h-4 w-4 text-slate-400" />
                    <span className="font-medium">{item.label}</span>
                    <ChevronRightIcon className="h-3 w-3 text-slate-300 dark:text-slate-600 ml-auto" />
                  </button>
                ))}
              </div>
            )}

            {query && !loading && suggestions.length === 0 && (
              <div className="px-3 py-6 text-center text-sm text-slate-400">
                No results for &ldquo;{query}&rdquo;
              </div>
            )}
          </div>

          <div className="border-t border-slate-100 dark:border-slate-700 px-4 py-2 flex items-center justify-between text-2xs text-slate-400">
            <div className="flex items-center gap-3">
              <span><kbd className="font-mono">↑↓</kbd> navigate</span>
              <span><kbd className="font-mono">↵</kbd> select</span>
            </div>
            <span><kbd className="font-mono">esc</kbd> close</span>
          </div>
        </div>
      </div>
    </div>
  );
}

function SyncIndicator() {
  const [status, setStatus] = useState(null);

  useEffect(() => {
    getSyncStatus()
      .then(setStatus)
      .catch(() => {});
  }, []);

  const lastSync = status?.last_sync_time;
  const totalPages = status?.total_pages ?? status?.total_runbooks ?? 0;

  return (
    <div className="px-4 py-3">
      <div className="flex items-center gap-2">
        <div className={`dot ${lastSync ? 'bg-emerald-400' : 'bg-slate-500'}`} />
        <span className="text-2xs text-sidebar-text truncate">
          {lastSync ? `Synced ${new Date(lastSync).toLocaleDateString()}` : 'Not synced'}
        </span>
      </div>
      {totalPages > 0 && (
        <div className="text-2xs text-sidebar-text mt-1 pl-3.5">
          {totalPages} pages indexed
        </div>
      )}
    </div>
  );
}

export default function Layout() {
  const location = useLocation();
  const [cmdOpen, setCmdOpen] = useState(false);
  const [mobileOpen, setMobileOpen] = useState(false);
  const { dark, toggle: toggleTheme } = useTheme();
  const { collapsed: navCollapsed, toggle: toggleNav } = useNavCollapsed();

  useEffect(() => {
    const handleKey = (e) => {
      if ((e.metaKey || e.ctrlKey) && e.key === 'k') {
        e.preventDefault();
        setCmdOpen(true);
      }
    };
    document.addEventListener('keydown', handleKey);
    return () => document.removeEventListener('keydown', handleKey);
  }, []);

  useEffect(() => {
    setMobileOpen(false);
  }, [location.pathname]);

  const isActive = (path) =>
    path === '/'
      ? location.pathname === '/'
      : location.pathname === path || location.pathname.startsWith(path + '/');

  const renderSidebar = (collapsed) => (
    <>
      <div className={`py-4 flex items-center gap-3 ${collapsed ? 'px-3 flex-col' : 'px-4'}`}>
        <div className="w-8 h-8 rounded-lg bg-brand-600 flex items-center justify-center flex-shrink-0">
          <CommandLineIcon className="h-4.5 w-4.5 text-white" />
        </div>
        {!collapsed && (
          <div className="flex-1 min-w-0">
            <div className="font-semibold text-white text-sm tracking-tight">Runbook Manager</div>
            {/* The sidebar is dark in both themes, so it cannot rely on `dark:`
                variants for contrast; it uses the sidebar tokens directly. */}
            <div className="text-2xs text-sidebar-text">Documentation Platform</div>
          </div>
        )}
        <button
          type="button"
          onClick={toggleTheme}
          title={dark ? 'Switch to light mode' : 'Switch to dark mode'}
          aria-label={dark ? 'Switch to light mode' : 'Switch to dark mode'}
          className="p-1.5 rounded-lg text-sidebar-text hover:text-white hover:bg-sidebar-hover transition-colors"
        >
          {dark ? <SunIcon aria-hidden="true" className="h-5 w-5" />
                : <MoonIcon aria-hidden="true" className="h-5 w-5" />}
        </button>
      </div>

      <div className={collapsed ? 'px-3 mb-2' : 'px-3 mb-2'}>
        <button
          type="button"
          onClick={() => setCmdOpen(true)}
          title={collapsed ? 'Search (Ctrl K)' : undefined}
          aria-label={collapsed ? 'Search' : undefined}
          className={`w-full flex items-center gap-2 py-2 rounded-lg text-[13px]
                     text-sidebar-text bg-sidebar-hover border border-slate-700/50
                     hover:border-slate-600 hover:text-sidebar-text-active transition-all duration-150
                     ${collapsed ? 'justify-center px-2' : 'px-3'}`}
        >
          <MagnifyingGlassIcon aria-hidden="true" className="h-4 w-4" />
          {!collapsed && (
            <>
              <span className="flex-1 text-left">Search...</span>
              <kbd className="hidden sm:inline text-2xs font-mono text-sidebar-text bg-slate-800 px-1.5 py-0.5 rounded">
                Ctrl K
              </kbd>
            </>
          )}
        </button>
      </div>

      {/* A plain div: the enclosing element is already the navigation landmark,
          and a nested <nav> would add a second, unnamed one. */}
      <div className="flex-1 px-3 py-1 overflow-y-auto space-y-4">
        {NAV_SECTIONS.map((section, sIdx) => (
          <div key={sIdx}>
            {/* Not `.label`: that utility resolves to a slate tone that fails AA
                on the dark sidebar. `sidebar-text` is the accessible token. */}
            {section.title && !collapsed && (
              <div className="px-3 mb-1 text-2xs font-medium uppercase tracking-wider
                              text-sidebar-text">
                {section.title}
              </div>
            )}
            {section.title && collapsed && sIdx > 0 && (
              <div className="mx-2 mb-2 border-t border-sidebar-border" role="presentation" />
            )}
            <div className="space-y-0.5">
              {section.items.map((item) => (
                <Link
                  key={item.path}
                  to={item.path}
                  title={collapsed ? item.label : undefined}
                  aria-current={isActive(item.path) ? 'page' : undefined}
                  className={`sidebar-link ${isActive(item.path) ? 'sidebar-link-active' : ''} ${
                    collapsed ? 'justify-center' : ''
                  }`}
                >
                  <item.icon aria-hidden="true" className="h-[18px] w-[18px] flex-shrink-0" />
                  <span className={collapsed ? 'rd-visually-hidden' : undefined}>{item.label}</span>
                </Link>
              ))}
            </div>
          </div>
        ))}
      </div>

      {!collapsed && (
        <div className="border-t border-sidebar-border">
          <SyncIndicator />
        </div>
      )}
    </>
  );

  return (
    <div className="flex h-screen bg-surface-50 dark:bg-slate-900">
      {/* Bypass block: hidden until focused, first control in tab order. */}
      <a href="#main-content" className="rd-skip-link">Skip to main content</a>

      {/* Desktop sidebar */}
      <nav id="app-navigation"
           className={`hidden lg:flex flex-col bg-sidebar-bg flex-shrink-0 transition-[width] duration-150
                       ${navCollapsed ? 'w-16' : 'w-60'}`}
           aria-label="Main navigation">
        {renderSidebar(navCollapsed)}
        <div className={`border-t border-sidebar-border p-2 ${navCollapsed ? '' : 'px-3'}`}>
          <button
            type="button"
            onClick={toggleNav}
            aria-expanded={!navCollapsed}
            aria-controls="app-navigation"
            title={navCollapsed ? 'Expand navigation' : 'Collapse navigation'}
            className={`w-full flex items-center gap-2 px-2 py-2 rounded-lg text-[13px]
                        text-sidebar-text hover:text-white hover:bg-sidebar-hover transition-colors
                        ${navCollapsed ? 'justify-center' : ''}`}
          >
            {navCollapsed
              ? <ChevronDoubleRightIcon aria-hidden="true" className="h-4 w-4" />
              : <ChevronDoubleLeftIcon aria-hidden="true" className="h-4 w-4" />}
            <span className={navCollapsed ? 'rd-visually-hidden' : undefined}>
              {navCollapsed ? 'Expand navigation' : 'Collapse navigation'}
            </span>
          </button>
        </div>
      </nav>

      {/* Mobile overlay */}
      {mobileOpen && (
        <div className="fixed inset-0 z-40 lg:hidden">
          <div className="fixed inset-0 bg-slate-900/50 backdrop-blur-sm" onClick={() => setMobileOpen(false)} />
          <nav aria-label="Main navigation"
               className="fixed inset-y-0 left-0 w-60 flex flex-col bg-sidebar-bg z-50 animate-slide-in">
            <button
              type="button"
              onClick={() => setMobileOpen(false)}
              aria-label="Close navigation"
              className="absolute top-4 right-3 p-1 rounded-lg text-slate-400 hover:text-white hover:bg-sidebar-hover"
            >
              <XMarkIcon aria-hidden="true" className="h-5 w-5" />
            </button>
            {renderSidebar(false)}
          </nav>
        </div>
      )}

      {/* Main content */}
      <div className="flex-1 flex flex-col min-w-0">
        {/* Top bar for mobile */}
        <header className="lg:hidden flex items-center gap-3 px-4 py-3 bg-white dark:bg-slate-800 border-b border-slate-200 dark:border-slate-700">
          <button
            type="button"
            onClick={() => setMobileOpen(true)}
            aria-label="Open navigation"
            className="p-1.5 rounded-lg text-slate-600 dark:text-slate-400 hover:bg-slate-100 dark:hover:bg-slate-700"
          >
            <Bars3Icon aria-hidden="true" className="h-5 w-5" />
          </button>
          <div className="font-semibold text-slate-800 dark:text-slate-200 text-sm">Runbook Manager</div>
          <div className="ml-auto flex items-center gap-1">
            <button
              type="button"
              onClick={toggleTheme}
              aria-label={dark ? 'Switch to light mode' : 'Switch to dark mode'}
              className="p-1.5 rounded-lg text-slate-400 hover:bg-slate-100 dark:hover:bg-slate-700 hover:text-slate-600 dark:hover:text-slate-300"
            >
              {dark ? <SunIcon aria-hidden="true" className="h-5 w-5" />
                    : <MoonIcon aria-hidden="true" className="h-5 w-5" />}
            </button>
            <button
              type="button"
              onClick={() => setCmdOpen(true)}
              aria-label="Search"
              className="p-1.5 rounded-lg text-slate-400 hover:bg-slate-100 dark:hover:bg-slate-700 hover:text-slate-600 dark:hover:text-slate-300"
            >
              <MagnifyingGlassIcon aria-hidden="true" className="h-5 w-5" />
            </button>
          </div>
        </header>

        {/* The single primary landmark, and the app's only scroll container. */}
        <main id="main-content" tabIndex={-1} className="flex-1 overflow-y-auto">
          <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-6">
            <Outlet />
          </div>
        </main>
      </div>

      <CommandPalette open={cmdOpen} onClose={() => setCmdOpen(false)} />
    </div>
  );
}
