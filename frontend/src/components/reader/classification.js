/**
 * Presentation metadata for the local classification fields.
 *
 * These maps only *label* values that the classification service already
 * produced; none of them decide when a flag applies. Review-reason keys mirror
 * `detect_review_terms` / `classify_page` in app/services/classification_service.py.
 */

export const PRIORITY_VARIANT = {
  P0: { variant: 'danger', label: 'P0 Critical' },
  P1: { variant: 'warning', label: 'P1 High' },
  P2: { variant: 'warning', label: 'P2 Medium' },
  P3: { variant: 'info', label: 'P3 Normal' },
  P4: { variant: 'success', label: 'P4 Low' },
  P5: { variant: 'neutral', label: 'P5 Info' },
};

export const STATUS_VARIANT = {
  active: { variant: 'success', label: 'Active' },
  imported: { variant: 'info', label: 'Imported' },
  stale: { variant: 'warning', label: 'Stale' },
  needs_review: { variant: 'warning', label: 'Needs review' },
  archived: { variant: 'neutral', label: 'Archived' },
};

export const REVIEW_REASON_LABELS = {
  older_than_one_year: 'Not updated in over a year',
  contains_pagerduty: 'Mentions PagerDuty',
  contains_datadog: 'Mentions Datadog',
  contains_nagios: 'Mentions Nagios',
  contains_moving_on: 'Mentions Moving On',
};

export function reviewReasonLabel(reason) {
  return REVIEW_REASON_LABELS[reason]
    || String(reason || '').replace(/_/g, ' ').replace(/^\w/, (c) => c.toUpperCase());
}

export const PRIORITIES = ['P0', 'P1', 'P2', 'P3', 'P4', 'P5'];
export const LOCAL_STATUSES = ['imported', 'active', 'stale', 'needs_review', 'archived'];

/** Format an ISO timestamp for display, or return null when absent/invalid. */
export function formatDate(iso, opts = { dateStyle: 'medium' }) {
  if (!iso) return null;
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return null;
  return d.toLocaleDateString(undefined, opts);
}

/** Same, including time — used where "last updated" must be unambiguous. */
export function formatDateTime(iso) {
  if (!iso) return null;
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return null;
  return d.toLocaleString(undefined, { dateStyle: 'medium', timeStyle: 'short' });
}

export function formatBytes(bytes) {
  const n = Number(bytes);
  if (!n || Number.isNaN(n)) return null;
  const units = ['B', 'KB', 'MB', 'GB', 'TB'];
  const i = Math.min(Math.floor(Math.log(n) / Math.log(1024)), units.length - 1);
  return `${(n / 1024 ** i).toFixed(i > 0 ? 1 : 0)} ${units[i]}`;
}
