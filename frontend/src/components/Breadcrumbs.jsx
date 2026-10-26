import React from 'react';
import { Link } from 'react-router-dom';
import { ChevronRightIcon, FolderOpenIcon } from '@heroicons/react/24/outline';

const slugify = (text) =>
  (text || '').toLowerCase().replace(/[^a-z0-9]+/g, '-').replace(/(^-|-$)/g, '');

export default function Breadcrumbs({ ancestors = [], spaceKey, spaceName, currentTitle }) {
  return (
    <nav className="flex items-center gap-1.5 text-sm text-slate-500 flex-wrap" aria-label="Breadcrumb">
      <Link to="/spaces" className="hover:text-brand-600 transition-colors">
        <FolderOpenIcon className="h-4 w-4" />
      </Link>
      <ChevronRightIcon className="h-3 w-3 text-slate-300" />
      <Link to={`/spaces/${spaceKey}`} className="hover:text-brand-600 transition-colors">
        {spaceName || spaceKey}
      </Link>
      {ancestors.map((a) => (
        <React.Fragment key={a.id}>
          <ChevronRightIcon className="h-3 w-3 text-slate-300" />
          <Link
            to={`/spaces/${spaceKey}/pages/${a.id}/${slugify(a.title)}`}
            className="hover:text-brand-600 truncate max-w-[200px] transition-colors"
          >
            {a.title}
          </Link>
        </React.Fragment>
      ))}
      {currentTitle && (
        <>
          <ChevronRightIcon className="h-3 w-3 text-slate-300" />
          <span className="text-slate-800 font-medium truncate max-w-[300px]">{currentTitle}</span>
        </>
      )}
    </nav>
  );
}
