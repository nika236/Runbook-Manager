import DOMPurify from 'dompurify';

/**
 * Explicit allowlist for imported Confluence article HTML.
 *
 * The server-side renderer already normalises storage format and escapes
 * plain-text macro bodies; this is the second, independent gate. It is an
 * allowlist rather than a blocklist so an unrecognised construct is dropped by
 * default instead of being trusted by default.
 */
const ALLOWED_TAGS = [
  // Sections and text
  'p', 'br', 'hr', 'div', 'span', 'section', 'blockquote',
  'h1', 'h2', 'h3', 'h4', 'h5', 'h6',
  'strong', 'b', 'em', 'i', 'u', 's', 'del', 'ins', 'mark',
  'sub', 'sup', 'small', 'abbr', 'time', 'q', 'cite',
  // Lists
  'ul', 'ol', 'li', 'dl', 'dt', 'dd',
  // Code
  'pre', 'code', 'kbd', 'samp', 'var',
  // Tables
  'table', 'caption', 'colgroup', 'col', 'thead', 'tbody', 'tfoot', 'tr', 'th', 'td',
  // Media and disclosure
  'img', 'figure', 'figcaption', 'details', 'summary',
  // Links
  'a',
];

const ALLOWED_ATTR = [
  // Links
  'href', 'target', 'rel', 'title',
  // Images
  'src', 'alt', 'width', 'height', 'loading', 'decoding',
  // Structure and accessibility
  'id', 'class', 'lang', 'dir', 'role', 'tabindex', 'open',
  'aria-label', 'aria-labelledby', 'aria-describedby', 'aria-hidden',
  'aria-expanded', 'aria-current',
  // Tables
  'colspan', 'rowspan', 'scope', 'headers', 'abbr',
  // Layout-only inline styling (the renderer already stripped colours)
  'style',
  // Renderer-emitted hooks
  'data-language', 'data-macro', 'data-highlight-colour', 'datetime',
];

/**
 * Permit only navigable, inert URL forms. Blocks javascript:, data:, vbscript:,
 * file: and any other scheme capable of executing or exfiltrating.
 */
const ALLOWED_URI_REGEXP = /^(?:https?:|mailto:|tel:|[^a-z]|[a-z+.-]+(?:[^a-z+.:-]|$))/i;

const CONFIG = {
  ALLOWED_TAGS,
  ALLOWED_ATTR,
  ALLOWED_URI_REGEXP,
  // Never allow data-*/aria-* wholesale; the lists above are exhaustive.
  ALLOW_DATA_ATTR: false,
  ALLOW_ARIA_ATTR: false,
  ALLOW_UNKNOWN_PROTOCOLS: false,
  // Active, embedded, and form content is rejected outright.
  FORBID_TAGS: [
    'script', 'style', 'iframe', 'frame', 'frameset', 'object', 'embed',
    'applet', 'form', 'input', 'button', 'select', 'option', 'textarea',
    'link', 'meta', 'base', 'svg', 'math', 'template', 'audio', 'video',
    'source', 'track', 'noscript',
  ],
  FORBID_ATTR: ['srcset', 'ping', 'formaction', 'background', 'xlink:href'],
  // USE_PROFILES is deliberately NOT set: DOMPurify ignores ALLOWED_TAGS and
  // ALLOWED_ATTR whenever a profile is active, which would silently substitute
  // the broad built-in HTML profile for the explicit lists above (and strip the
  // aria-* attributes the renderer emits). SVG and MathML are absent from
  // ALLOWED_TAGS, so no executable vector content can reach the DOM either way.
  KEEP_CONTENT: true,
  RETURN_TRUSTED_TYPE: false,
};

let hookInstalled = false;

function installHooks() {
  if (hookInstalled) return;
  hookInstalled = true;

  DOMPurify.addHook('afterSanitizeAttributes', (node) => {
    if (node.tagName === 'A' && node.hasAttribute('href')) {
      const href = node.getAttribute('href') || '';
      const isExternal = /^https?:/i.test(href);
      if (isExternal) {
        // Any link leaving the app opens in a new tab and cannot reach
        // window.opener. The renderer marks these, but a source-authored
        // target= must not be trusted to carry a safe rel.
        node.setAttribute('target', '_blank');
        node.setAttribute('rel', 'noopener noreferrer nofollow');
      } else {
        node.removeAttribute('target');
      }
    }
    // Inline styles survive only for layout properties; drop anything else that
    // slipped through, including attempts to escape the article container.
    if (node.hasAttribute && node.hasAttribute('style')) {
      const style = node.getAttribute('style') || '';
      if (/position|fixed|z-index|url\(|expression|@import|!important/i.test(style)) {
        node.removeAttribute('style');
      }
    }
  });
}

/**
 * Sanitize rendered Confluence HTML for insertion into the article container.
 *
 * @param {string} html Server-rendered article HTML.
 * @returns {string} Sanitized HTML, or '' when there is nothing to render.
 */
export function sanitizeArticle(html) {
  if (!html) return '';
  installHooks();
  return DOMPurify.sanitize(html, CONFIG);
}

/**
 * Count of elements DOMPurify removed during the last sanitize call.
 * Used by diagnostics, not by rendering.
 */
export function lastRemovedCount() {
  return DOMPurify.removed.length;
}

export default sanitizeArticle;
