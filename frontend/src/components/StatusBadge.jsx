import React from 'react';

const statusConfig = {
  active: { className: 'badge-green', label: 'Active', dot: 'bg-emerald-500' },
  imported: { className: 'badge-blue', label: 'Imported', dot: 'bg-blue-500' },
  stale: { className: 'badge-red', label: 'Stale', dot: 'bg-red-500' },
  needs_review: { className: 'badge-amber', label: 'Needs Review', dot: 'bg-amber-500' },
  archived: { className: 'badge-slate', label: 'Archived', dot: 'bg-slate-400' },
};

export default function StatusBadge({ status }) {
  const config = statusConfig[status];
  if (!config) return <span className="badge-slate">{status || 'Unknown'}</span>;
  return (
    <span className={config.className}>
      <span className={`dot mr-1.5 ${config.dot}`} />
      {config.label}
    </span>
  );
}
