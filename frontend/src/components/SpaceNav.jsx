import React from 'react';
import { Link } from 'react-router-dom';
import { FolderOpenIcon } from '@heroicons/react/24/outline';

export default function SpaceNav({ spaces = [], activeSpace = '' }) {
  if (!spaces.length) return null;
  return (
    <nav className="space-y-0.5">
      <div className="label px-3 mb-2">Spaces</div>
      {spaces.map((s) => {
        const key = s.key || s.space_key;
        const active = activeSpace === key;
        return (
          <Link
            key={key}
            to={`/spaces/${key}`}
            className={`flex items-center justify-between px-3 py-2 rounded-lg text-sm transition-colors ${
              active
                ? 'bg-brand-50 text-brand-700 font-medium'
                : 'text-slate-600 hover:bg-slate-50'
            }`}
          >
            <span className="flex items-center gap-2.5 truncate">
              <FolderOpenIcon className={`h-4 w-4 flex-shrink-0 ${active ? 'text-brand-500' : 'text-slate-400'}`} />
              <span className="truncate">{s.name || key}</span>
            </span>
            <span className="text-2xs text-slate-400 tabular-nums flex-shrink-0">
              {s.page_count ?? 0}
            </span>
          </Link>
        );
      })}
    </nav>
  );
}
