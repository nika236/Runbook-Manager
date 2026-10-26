import React from 'react';
import { ClockIcon, TagIcon, ExclamationTriangleIcon } from '@heroicons/react/24/outline';
import { PRIORITY_VARIANT, STATUS_VARIANT, reviewReasonLabel } from './classification';

/**
 * A single classification chip. The visible text always states the value, so
 * colour is reinforcement and never the sole carrier of meaning.
 */
export function Chip({ label, value, variant = 'neutral', icon: Icon, unset = false }) {
  return (
    <span className={`rd-chip rd-chip-${variant}`}>
      {Icon ? <Icon aria-hidden="true" className="rd-chip-icon" /> : null}
      {label ? <span className="rd-chip-key">{label}:</span> : null}
      <span className={unset ? 'rd-chip-unset' : undefined}>{value}</span>
    </span>
  );
}

/**
 * What a NOC engineer needs before reading: urgency, ownership, and whether the
 * page can still be trusted.
 *
 * Missing values are stated explicitly ("Not set" / "Unassigned") rather than
 * hidden or inferred. Review flags are read straight from the metadata the
 * classification service already wrote — this component does not re-derive them.
 */
export default function ClassificationSummary({ page }) {
  const priority = PRIORITY_VARIANT[page.priority];
  const status = STATUS_VARIANT[page.local_status || 'imported'];
  const reviewReasons = Array.isArray(page.review_reasons) ? page.review_reasons : [];

  return (
    <div className="rd-chips">
      {priority
        ? <Chip label="Priority" value={priority.label} variant={priority.variant} />
        : <Chip label="Priority" value="Not set" unset />}

      {page.domain
        ? <Chip label="Domain" value={page.domain} variant="info" />
        : <Chip label="Domain" value="Not set" unset />}

      {page.team
        ? <Chip label="Team" value={page.team} />
        : <Chip label="Team" value="Unassigned" unset />}

      {page.owner
        ? <Chip label="Owner" value={page.owner} />
        : <Chip label="Owner" value="Unassigned" unset />}

      {status ? <Chip label="Status" value={status.label} variant={status.variant} /> : null}

      {reviewReasons.map((reason) => (
        <Chip
          key={reason}
          label="Review"
          value={reviewReasonLabel(reason)}
          variant="warning"
          icon={ClockIcon}
        />
      ))}

      {/* "WL" in the old UI. Spelled out, and neutral rather than error-red:
          a missing label is a gap in classification, not a page failure. */}
      {page.flag_label_missing ? (
        <Chip value="Without label" variant="neutral" icon={TagIcon} />
      ) : null}

      {page.flag_taxonomy_unmapped ? (
        <Chip value="Taxonomy unmapped" variant="neutral" icon={ExclamationTriangleIcon} />
      ) : null}
    </div>
  );
}
