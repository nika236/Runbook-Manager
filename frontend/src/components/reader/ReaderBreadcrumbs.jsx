import React from 'react';
import { Link } from 'react-router-dom';
import { ChevronRightIcon } from '@heroicons/react/24/outline';

const slugify = (text) =>
  (text || '').toLowerCase().replace(/[^a-z0-9]+/g, '-').replace(/(^-|-$)/g, '');

function Sep() {
  return <ChevronRightIcon aria-hidden="true" className="rd-breadcrumb-sep"
                           style={{ width: '0.875rem', height: '0.875rem' }} />;
}

/**
 * Breadcrumb trail for a mirrored page.
 *
 * Items are visually truncated but stay recoverable: every link carries the
 * untruncated text in `title`, and the current page is marked aria-current.
 */
export default function ReaderBreadcrumbs({
  ancestors = [], spaceKey, spaceName, currentTitle,
}) {
  return (
    <nav className="rd-breadcrumb" aria-label="Breadcrumb">
      <Link to="/spaces">Spaces</Link>
      <Sep />
      <Link to={`/spaces/${spaceKey}`} title={spaceName || spaceKey}>
        {spaceName || spaceKey}
      </Link>
      {ancestors.map((a) => (
        <React.Fragment key={a.id}>
          <Sep />
          <Link
            to={`/spaces/${spaceKey}/pages/${a.id}/${slugify(a.title)}`}
            title={a.title}
          >
            {a.title}
          </Link>
        </React.Fragment>
      ))}
      {currentTitle ? (
        <>
          <Sep />
          <span className="rd-breadcrumb-current" aria-current="page" title={currentTitle}>
            {currentTitle}
          </span>
        </>
      ) : null}
    </nav>
  );
}
