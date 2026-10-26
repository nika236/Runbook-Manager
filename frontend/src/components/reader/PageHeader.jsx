import React from 'react';
import {
  ArrowTopRightOnSquareIcon, PencilSquareIcon,
} from '@heroicons/react/24/outline';
import ClassificationSummary from './ClassificationSummary';
import { formatDate, formatDateTime } from './classification';

/**
 * Compact page header: title, byline, classification, and actions.
 *
 * Deliberately short so the article itself starts inside the first desktop
 * viewport. Anything that is reference-only lives in the right rail instead.
 */
export default function PageHeader({
  page,
  confluenceUrl,
  onEditMetadata,
  canEditMetadata = false,
  children,
}) {
  const updated = formatDateTime(page.updated_at);
  const created = formatDate(page.created_at);
  const labels = Array.isArray(page.labels) ? page.labels : [];

  return (
    <header className="rd-header">
      {children}

      <h1 className="rd-title" id="page-title">{page.title}</h1>

      <div className="rd-byline">
        <span>{page.created_by || 'Author not recorded'}</span>
        <span className="rd-byline-sep" aria-hidden="true">·</span>
        {/* "Updated" is spelled out with a real date and time so it cannot be
            confused with the local import time. */}
        <span>{updated ? `Updated ${updated}` : 'Update date not recorded'}</span>
        <span className="rd-byline-sep" aria-hidden="true">·</span>
        <span>{`Version ${page.confluence_version || 1}`}</span>
        {created ? (
          <>
            <span className="rd-byline-sep" aria-hidden="true">·</span>
            <span>{`Created ${created}`}</span>
          </>
        ) : null}
      </div>

      <ClassificationSummary page={page} />

      {labels.length > 0 ? (
        <div className="rd-chips">
          <span className="rd-chip-key" style={{ fontSize: 'var(--rd-fs-meta)' }}>
            Confluence labels:
          </span>
          {labels.map((label) => (
            <span key={label} className="rd-chip rd-chip-info">{label}</span>
          ))}
        </div>
      ) : null}

      <div className="rd-actions">
        {confluenceUrl ? (
          <a
            className="btn-secondary"
            href={confluenceUrl}
            target="_blank"
            rel="noopener noreferrer"
          >
            <ArrowTopRightOnSquareIcon aria-hidden="true" className="h-4 w-4" />
            Open in Confluence
            <span className="rd-visually-hidden">(opens in a new tab)</span>
          </a>
        ) : null}

        {canEditMetadata ? (
          <button type="button" className="btn-ghost" onClick={onEditMetadata}>
            <PencilSquareIcon aria-hidden="true" className="h-4 w-4" />
            Edit local metadata
          </button>
        ) : null}
      </div>
    </header>
  );
}
