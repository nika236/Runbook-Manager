import React from 'react';
import { formatDate, formatDateTime, PRIORITY_VARIANT, STATUS_VARIANT } from './classification';

function Row({ term, value, mono = false }) {
  const missing = value === null || value === undefined || value === '';
  return (
    <>
      <dt>{term}</dt>
      <dd className={[missing ? 'rd-unset' : '', mono ? 'rd-mono' : ''].filter(Boolean).join(' ')}>
        {missing ? 'Not set' : value}
      </dd>
    </>
  );
}

/**
 * One metadata group. `flat` drops the panel chrome for cases where this is
 * already inside a disclosure panel, so no card sits inside another card.
 */
function Group({ id, heading, flat, children }) {
  if (flat) {
    return (
      <section aria-labelledby={id} style={{ marginBottom: '1rem' }}>
        <h3 id={id} style={{ margin: '0 0 0.5rem', fontSize: 'var(--rd-fs-meta)',
                             lineHeight: 'var(--rd-lh-meta)', fontWeight: 650,
                             color: 'var(--rd-text)' }}>
          {heading}
        </h3>
        {children}
      </section>
    );
  }
  return (
    <section className="rd-panel" aria-labelledby={id}>
      <h2 className="rd-panel-head" id={id}>{heading}</h2>
      <div className="rd-panel-body">{children}</div>
    </section>
  );
}

/**
 * Secondary page metadata, split into the two things it actually is: the
 * classification this application owns, and read-only facts about the
 * Confluence source.
 *
 * A semantic definition list, not a layout table — the nine-row Page Properties
 * table is what pushed the article below the fold in the previous design.
 */
export default function PageDetails({ page, spaceKey, spaceName, pageId, flat = false }) {
  const priority = PRIORITY_VARIANT[page.priority];
  const status = STATUS_VARIANT[page.local_status || 'imported'];

  return (
    <>
      <Group id="local-classification-heading" heading="Local classification" flat={flat}>
        <dl className="rd-dl">
          <Row term="Priority" value={priority ? priority.label : null} />
          <Row term="Domain" value={page.domain} />
          <Row term="Team" value={page.team} />
          <Row term="Owner" value={page.owner} />
          <Row term="Reviewer" value={page.reviewer} />
          <Row term="Status" value={status ? status.label : page.local_status} />
          <Row term="Notes" value={page.notes} />
        </dl>
        <p style={{ margin: '0.75rem 0 0', fontSize: 'var(--rd-fs-fine)',
                    color: 'var(--rd-text-muted)' }}>
          Stored in this application only. Editing these fields never changes the
          Confluence page.
        </p>
      </Group>

      <Group id="confluence-source-heading" heading="Confluence source" flat={flat}>
        <dl className="rd-dl">
          <Row term="Space" value={spaceName || spaceKey} />
          <Row term="Author" value={page.created_by} />
          <Row term="Created" value={formatDate(page.created_at)} />
          <Row term="Updated by" value={page.updated_by} />
          <Row term="Updated" value={formatDateTime(page.updated_at)} />
          <Row term="Version" value={page.confluence_version ? `v${page.confluence_version}` : null} />
        </dl>
      </Group>
    </>
  );
}
