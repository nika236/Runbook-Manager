import React from 'react';

/**
 * Classification-gap badge.
 *
 * Previously rendered as a red "WL" lozenge, which read as a page-level error.
 * A page without a Confluence label is a gap in *our* classification, not a
 * failure of the page, so the label is spelled out and the treatment is neutral.
 * `short` keeps dense table rows compact while still exposing the full wording
 * to assistive technology and on hover.
 */
export default function WLBadge({ flagLabelMissing, flagTaxonomyUnmapped, short = false }) {
  if (flagLabelMissing) {
    return (
      <span className="badge-slate" title="Without label — no Confluence label is set on this page">
        {short ? (
          <>
            WL
            <span className="rd-visually-hidden"> (Without label)</span>
          </>
        ) : 'Without label'}
      </span>
    );
  }
  if (flagTaxonomyUnmapped) {
    return (
      <span className="badge-slate" title="This page's label does not map to a known domain">
        Taxonomy unmapped
      </span>
    );
  }
  return null;
}
