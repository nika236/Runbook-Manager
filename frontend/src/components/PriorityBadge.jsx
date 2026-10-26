import React from 'react';

const priorityConfig = {
  P0: { className: 'badge-red', label: 'P0 Critical' },
  P1: { className: 'bg-orange-50 text-orange-700 ring-1 ring-inset ring-orange-600/10', label: 'P1 High' },
  P2: { className: 'badge-amber', label: 'P2 Medium' },
  P3: { className: 'badge-blue', label: 'P3 Normal' },
  P4: { className: 'badge-green', label: 'P4 Low' },
  P5: { className: 'badge-slate', label: 'P5 Info' },
};

export default function PriorityBadge({ priority }) {
  const config = priorityConfig[priority];
  if (!config) return <span className="text-2xs text-slate-400">&mdash;</span>;
  return <span className={`badge ${config.className}`}>{config.label}</span>;
}
