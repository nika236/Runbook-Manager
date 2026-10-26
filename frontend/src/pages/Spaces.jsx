import React, { useEffect, useState } from 'react';
import { Link } from 'react-router-dom';
import {
  FolderOpenIcon,
  DocumentTextIcon,
  TagIcon,
  ExclamationCircleIcon,
  ChevronRightIcon,
} from '@heroicons/react/24/outline';
import { getSpaces } from '../api/client';

export default function Spaces() {
  const [spaces, setSpaces] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);

  useEffect(() => {
    getSpaces()
      .then((data) => setSpaces(data.spaces || []))
      .catch(() => setError('Failed to load spaces'))
      .finally(() => setLoading(false));
  }, []);

  if (loading) {
    return (
      <div className="animate-fade-in">
        <div className="loading-skeleton h-7 w-32 mb-6" />
        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-4">
          {[1, 2].map((i) => (
            <div key={i} className="card p-6">
              <div className="loading-skeleton h-10 w-10 rounded-xl mb-4" />
              <div className="loading-skeleton h-5 w-32 mb-2" />
              <div className="loading-skeleton h-3 w-48 mb-4" />
              <div className="flex gap-2">
                <div className="loading-skeleton h-5 w-16 rounded-full" />
                <div className="loading-skeleton h-5 w-16 rounded-full" />
              </div>
            </div>
          ))}
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
        <div className="text-sm font-medium text-slate-900 dark:text-slate-100 mb-1">Unable to load spaces</div>
        <div className="text-sm text-slate-500 dark:text-slate-400">{error}</div>
      </div>
    );
  }

  return (
    <div className="animate-fade-in">
      <div className="flex items-center justify-between mb-6">
        <div>
          <h1 className="page-title">Spaces</h1>
          <p className="caption mt-0.5">Confluence documentation spaces</p>
        </div>
        <span className="badge-slate">{spaces.length} space{spaces.length !== 1 ? 's' : ''}</span>
      </div>

      {spaces.length === 0 ? (
        <div className="empty-state card py-16">
          <div className="w-14 h-14 rounded-full bg-slate-100 dark:bg-slate-700 flex items-center justify-center mb-4">
            <FolderOpenIcon className="h-6 w-6 text-slate-400" />
          </div>
          <div className="text-sm font-medium text-slate-900 dark:text-slate-100 mb-1">No spaces found</div>
          <div className="text-sm text-slate-500 dark:text-slate-400">Run a synchronization to import content from Confluence</div>
          <Link to="/sync" className="btn-primary mt-4 text-sm">Go to Sync</Link>
        </div>
      ) : (
        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-4">
          {spaces.map((s) => (
            <Link key={s.key} to={`/spaces/${s.key}`} className="group">
              <div className="card-hover p-6 h-full">
                <div className="flex items-start gap-4">
                  <div className="w-10 h-10 rounded-xl bg-brand-50 dark:bg-brand-900/30 flex items-center justify-center flex-shrink-0 group-hover:bg-brand-100 dark:group-hover:bg-brand-900/50 transition-colors">
                    <FolderOpenIcon className="h-5 w-5 text-brand-600 dark:text-brand-400" />
                  </div>
                  <div className="flex-1 min-w-0">
                    <div className="flex items-center gap-2">
                      <h3 className="font-semibold text-slate-900 dark:text-slate-100 truncate">{s.name || s.key}</h3>
                      <ChevronRightIcon className="h-4 w-4 text-slate-300 dark:text-slate-600 opacity-0 group-hover:opacity-100 transition-opacity flex-shrink-0" />
                    </div>
                    <div className="text-2xs font-mono text-slate-400 dark:text-slate-500 mt-0.5">{s.key}</div>
                    {s.description && <p className="text-sm text-slate-500 dark:text-slate-400 mt-2 line-clamp-2">{s.description}</p>}
                    <div className="flex items-center gap-3 mt-3">
                      <div className="flex items-center gap-1.5 text-2xs text-slate-500 dark:text-slate-400">
                        <DocumentTextIcon className="h-3.5 w-3.5" />{s.page_count ?? 0} pages
                      </div>
                      {(s.blog_count ?? 0) > 0 && (
                        <div className="flex items-center gap-1.5 text-2xs text-slate-500 dark:text-slate-400">{s.blog_count} blogs</div>
                      )}
                      {(s.wl_count ?? 0) > 0 && (
                        <div className="flex items-center gap-1.5 text-2xs text-red-500 dark:text-red-400">
                          <TagIcon className="h-3.5 w-3.5" />{s.wl_count} WL
                        </div>
                      )}
                    </div>
                  </div>
                </div>
              </div>
            </Link>
          ))}
        </div>
      )}
    </div>
  );
}
