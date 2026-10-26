import React, { useEffect, useMemo, useRef, useState } from 'react';
import { DocumentTextIcon } from '@heroicons/react/24/outline';
import sanitizeArticle from './sanitizeArticle';

/**
 * Renders imported Confluence article HTML.
 *
 * Everything is scoped under `.confluence-content` so application-level resets
 * cannot flatten the article and article styles cannot leak into app chrome.
 * The component adds only progressive enhancements the server cannot do:
 * heading discovery for the table of contents, and a copy action on code blocks.
 */
export default function ConfluenceArticle({
  html,
  sourceWasEmpty = false,
  onHeadingsChange,
  onActiveHeadingChange,
  id = 'article-content',
}) {
  const containerRef = useRef(null);
  const [copiedKey, setCopiedKey] = useState(null);

  const safeHtml = useMemo(() => sanitizeArticle(html), [html]);

  // -- Publish the headings that actually rendered, for the TOC ---------------
  useEffect(() => {
    if (!onHeadingsChange) return;
    const root = containerRef.current;
    if (!root) {
      onHeadingsChange([]);
      return;
    }
    const found = Array.from(root.querySelectorAll('h2[id], h3[id], h4[id]'))
      .map((el) => ({
        id: el.id,
        text: (el.textContent || '').trim(),
        depth: Number(el.tagName.slice(1)),
      }))
      .filter((h) => h.id && h.text);
    onHeadingsChange(found);
  }, [safeHtml, onHeadingsChange]);

  // -- Track the section currently in view -----------------------------------
  useEffect(() => {
    if (!onActiveHeadingChange) return undefined;
    const root = containerRef.current;
    if (!root) return undefined;

    const headings = Array.from(root.querySelectorAll('h2[id], h3[id], h4[id]'));
    if (!headings.length) {
      onActiveHeadingChange(null);
      return undefined;
    }

    // IntersectionObserver against the app shell's scroll container.
    const scroller = root.closest('main') || null;
    const visible = new Set();
    const observer = new IntersectionObserver(
      (entries) => {
        entries.forEach((entry) => {
          if (entry.isIntersecting) visible.add(entry.target.id);
          else visible.delete(entry.target.id);
        });
        const firstVisible = headings.find((h) => visible.has(h.id));
        if (firstVisible) {
          onActiveHeadingChange(firstVisible.id);
        }
      },
      { root: scroller, rootMargin: '-72px 0px -65% 0px', threshold: 0 },
    );

    headings.forEach((h) => observer.observe(h));
    return () => observer.disconnect();
  }, [safeHtml, onActiveHeadingChange]);

  // -- Copy action on code blocks --------------------------------------------
  // Added only because it can be done accessibly: a real <button> with an
  // accessible name, reachable by keyboard, with a text status message.
  useEffect(() => {
    const root = containerRef.current;
    if (!root) return undefined;
    if (!navigator.clipboard) return undefined;

    const blocks = Array.from(root.querySelectorAll('pre.cf-code'));
    const cleanups = [];

    blocks.forEach((pre, index) => {
      if (pre.parentElement?.classList.contains('cf-code-host')) return;

      const host = document.createElement('div');
      host.className = 'cf-code-host';
      pre.parentNode.insertBefore(host, pre);
      host.appendChild(pre);

      const button = document.createElement('button');
      button.type = 'button';
      button.className = 'cf-code-copy';
      button.textContent = 'Copy';
      button.setAttribute('aria-label', `Copy code block ${index + 1}`);

      const onClick = async () => {
        try {
          await navigator.clipboard.writeText(pre.innerText);
          button.textContent = 'Copied';
          setCopiedKey(`${index}:${Date.now()}`);
          window.setTimeout(() => { button.textContent = 'Copy'; }, 1800);
        } catch {
          button.textContent = 'Copy failed';
          window.setTimeout(() => { button.textContent = 'Copy'; }, 1800);
        }
      };
      button.addEventListener('click', onClick);
      host.appendChild(button);

      cleanups.push(() => button.removeEventListener('click', onClick));
    });

    return () => cleanups.forEach((fn) => fn());
  }, [safeHtml]);

  // A block that scrolls must be reachable by keyboard (WCAG 2.1.1). Only blocks
  // that genuinely overflow become tab stops, so a code-heavy page does not fill
  // the tab order with blocks that have nothing to scroll.
  useEffect(() => {
    const root = containerRef.current;
    if (!root) return undefined;

    const markScrollable = () => {
      root.querySelectorAll('pre.cf-code').forEach((pre) => {
        const scrolls = pre.scrollWidth > pre.clientWidth + 1;
        if (scrolls && !pre.hasAttribute('tabindex')) {
          pre.setAttribute('tabindex', '0');
          pre.setAttribute('role', 'region');
          pre.setAttribute('aria-label', 'Code block, scrollable');
        } else if (!scrolls && pre.getAttribute('role') === 'region') {
          pre.removeAttribute('tabindex');
          pre.removeAttribute('role');
          pre.removeAttribute('aria-label');
        }
      });
    };

    markScrollable();
    const observer = new ResizeObserver(markScrollable);
    observer.observe(root);
    return () => observer.disconnect();
  }, [safeHtml]);

  if (!safeHtml) {
    return (
      <div className="rd-panel" style={{ padding: '2rem', textAlign: 'center' }}>
        <DocumentTextIcon
          aria-hidden="true"
          style={{ width: '2rem', height: '2rem', margin: '0 auto 0.75rem',
                   color: 'var(--rd-text-muted)' }}
        />
        <p style={{ margin: 0, fontWeight: 600, color: 'var(--rd-text)' }}>
          {sourceWasEmpty ? 'This page has no content' : 'No readable content'}
        </p>
        <p style={{ margin: '0.375rem 0 0', fontSize: 'var(--rd-fs-meta)',
                    color: 'var(--rd-text-secondary)' }}>
          {sourceWasEmpty
            ? 'The mirrored Confluence page body is empty.'
            : 'The mirrored body could not be rendered as readable content.'}
        </p>
      </div>
    );
  }

  return (
    <>
      <div
        id={id}
        ref={containerRef}
        className="confluence-content"
        // Server-rendered then allowlist-sanitized in sanitizeArticle.js.
        dangerouslySetInnerHTML={{ __html: safeHtml }}
      />
      <div aria-live="polite" className="rd-visually-hidden">
        {copiedKey ? 'Code copied to clipboard' : ''}
      </div>
    </>
  );
}
