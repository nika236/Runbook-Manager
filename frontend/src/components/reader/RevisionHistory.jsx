import React from 'react';
import { ClockIcon } from '@heroicons/react/24/outline';
import Disclosure from './Disclosure';
import { formatDateTime } from './classification';

/**
 * Confluence version history for the page, collapsed by default.
 *
 * The mirror stores version metadata only (`version`, `by`, `when`, `message`) —
 * no historical bodies — so there is nothing to lazy-load and no diff to offer.
 * Saying so is better than a comparison button that cannot work.
 */
export default function RevisionHistory({ revisions = [], confluenceUrl }) {
  if (!revisions.length) return null;

  return (
    <Disclosure title="Revision history" count={revisions.length} icon={ClockIcon}>
      <ul style={{ listStyle: 'none', margin: 0, padding: 0 }}>
        {revisions.map((rev, index) => (
          <li key={rev.version ?? index} className="rd-revision">
            <span className="rd-revision-version">{`v${rev.version ?? '?'}`}</span>
            <span className="rd-revision-author">{rev.by || 'Author not recorded'}</span>
            <span className="rd-revision-date">
              {formatDateTime(rev.when) || 'Date not recorded'}
            </span>
            {rev.message ? (
              <span className="rd-revision-message" style={{ flexBasis: '100%' }}>
                {rev.message}
              </span>
            ) : null}
          </li>
        ))}
      </ul>
      <p style={{ margin: '0.75rem 0 0', fontSize: 'var(--rd-fs-fine)',
                  color: 'var(--rd-text-muted)' }}>
        Version metadata only. Historical page bodies are not mirrored locally,
        so previous versions cannot be viewed or compared here.
        {confluenceUrl ? ' Use Confluence to see earlier versions.' : ''}
      </p>
    </Disclosure>
  );
}
