import React from 'react';

const migrationConfig = {
  legacy: { className: 'badge-red', label: 'Legacy' },
  in_progress: { className: 'badge-amber', label: 'In Progress' },
  migrated: { className: 'badge-blue', label: 'Migrated' },
  verified: { className: 'badge-green', label: 'Verified' },
};

export default function MigrationBadge({ status }) {
  const config = migrationConfig[status];
  if (!config) return <span className="badge-slate">{status || 'Unknown'}</span>;
  return <span className={config.className}>{config.label}</span>;
}
