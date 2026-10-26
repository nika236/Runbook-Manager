import React from 'react';

/**
 * Minimum eligible headings before a TOC is worth showing. Below this it is
 * noise: the whole structure is already visible in the article.
 */
export const TOC_MIN_HEADINGS = 3;

export function isTocUseful(headings) {
  return Array.isArray(headings) && headings.length >= TOC_MIN_HEADINGS;
}

/**
 * The link list itself, shared by the desktop rail and the narrow-screen
 * disclosure so both stay identical.
 *
 * Indentation is normalised against the shallowest heading present, so a page
 * that only uses h3/h4 still starts flush left. The current section is marked
 * with aria-current plus a weight and border change, never colour alone.
 */
export function TocList({ headings, activeId }) {
  const minDepth = Math.min(...headings.map((h) => h.depth));
  return (
    <ul className="rd-toc-list">
      {headings.map((h) => (
        <li key={h.id}>
          <a
            href={`#${h.id}`}
            className={`rd-toc-link rd-toc-depth-${h.depth - minDepth + 2}`}
            aria-current={activeId === h.id ? 'true' : undefined}
          >
            {h.text}
          </a>
        </li>
      ))}
    </ul>
  );
}

/** Rail form: a labelled navigation landmark wrapped in a panel. */
export default function TableOfContents({ headings, activeId, className = '' }) {
  if (!isTocUseful(headings)) return null;

  return (
    <nav aria-label="On this page" className={`rd-panel ${className}`}>
      <h2 className="rd-panel-head" id="toc-heading">On this page</h2>
      <div className="rd-panel-body">
        <TocList headings={headings} activeId={activeId} />
      </div>
    </nav>
  );
}
