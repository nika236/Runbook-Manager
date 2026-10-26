import React, { useEffect, useState } from 'react';
import { Link } from 'react-router-dom';
import {
  BarChart, Bar, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer,
  PieChart, Pie, Cell,
} from 'recharts';
import {
  DocumentTextIcon,
  ExclamationTriangleIcon,
  UserIcon,
  ClockIcon,
  TagIcon,
  ArrowPathIcon,
  ArrowTrendingUpIcon,
  ChevronRightIcon,
} from '@heroicons/react/24/outline';
import { getDashboardStats, getSyncStatus } from '../api/client';
import useSpaceNames from '../hooks/useSpaceNames';

const CHART_COLORS = ['#6366f1', '#8b5cf6', '#06b6d4', '#10b981', '#f59e0b', '#ef4444', '#64748b'];
const PIE_COLORS = ['#ef4444', '#f97316', '#eab308', '#6366f1', '#10b981', '#94a3b8'];

function KpiCard({ title, value, description, icon: Icon, color = 'brand', href }) {
  const colorClasses = {
    brand: 'bg-brand-50 text-brand-600 dark:bg-brand-900/30 dark:text-brand-400',
    red: 'bg-red-50 text-red-600 dark:bg-red-900/30 dark:text-red-400',
    amber: 'bg-amber-50 text-amber-600 dark:bg-amber-900/30 dark:text-amber-400',
    emerald: 'bg-emerald-50 text-emerald-600 dark:bg-emerald-900/30 dark:text-emerald-400',
    slate: 'bg-slate-100 text-slate-600 dark:bg-slate-700 dark:text-slate-400',
  };

  const content = (
    <div className="kpi-card group relative">
      <div className="flex items-start justify-between">
        <div className="flex-1 min-w-0">
          <div className="text-sm font-medium text-slate-500 dark:text-slate-400">{title}</div>
          <div className="mt-1.5 text-3xl font-bold text-slate-900 dark:text-slate-100 tracking-tight tabular-nums">
            {value ?? <span className="loading-skeleton inline-block w-12 h-8" />}
          </div>
          {description && (
            <div className="mt-1.5 text-2xs text-slate-400 dark:text-slate-500">{description}</div>
          )}
        </div>
        <div className={`rounded-xl p-2.5 ${colorClasses[color] || colorClasses.brand}`}>
          <Icon className="h-5 w-5" />
        </div>
      </div>
      {href && (
        <ChevronRightIcon className="absolute top-5 right-3 h-3.5 w-3.5 text-slate-300 dark:text-slate-600 opacity-0 group-hover:opacity-100 transition-opacity" />
      )}
    </div>
  );

  if (href) {
    return <Link to={href} className="block hover:shadow-card-hover transition-shadow rounded-xl">{content}</Link>;
  }
  return content;
}

function ChartCard({ title, children, className = '' }) {
  return (
    <div className={`card p-5 ${className}`}>
      <h3 className="section-title mb-4">{title}</h3>
      {children}
    </div>
  );
}

function EmptyChart({ message, action }) {
  return (
    <div className="flex flex-col items-center justify-center h-48 text-center">
      <div className="w-12 h-12 rounded-full bg-slate-100 dark:bg-slate-700 flex items-center justify-center mb-3">
        <ArrowTrendingUpIcon className="h-5 w-5 text-slate-400" />
      </div>
      <div className="text-sm text-slate-500 dark:text-slate-400">{message}</div>
      {action && <div className="text-2xs text-slate-400 dark:text-slate-500 mt-1">{action}</div>}
    </div>
  );
}

function CustomTooltip({ active, payload, label }) {
  if (!active || !payload?.length) return null;
  return (
    <div className="bg-white dark:bg-slate-800 rounded-lg border border-slate-200 dark:border-slate-700 shadow-dropdown px-3 py-2 text-sm">
      {label && <div className="font-medium text-slate-700 dark:text-slate-200 mb-1">{label}</div>}
      {payload.map((p, i) => {
        const realValue = p.payload?.value ?? p.value;
        return (
          <div key={i} className="flex items-center gap-2 text-slate-600 dark:text-slate-400">
            <div className="w-2 h-2 rounded-full" style={{ backgroundColor: p.color || p.payload?.fill }} />
            <span>{p.name || p.payload?.name}: <strong>{realValue} pages</strong></span>
          </div>
        );
      })}
    </div>
  );
}

function CustomPieLabel({ cx, cy, midAngle, outerRadius, name, percent }) {
  if (percent < 0.01) return null;
  const RADIAN = Math.PI / 180;
  const radius = outerRadius + 22;
  const x = cx + radius * Math.cos(-midAngle * RADIAN);
  const y = cy + radius * Math.sin(-midAngle * RADIAN);
  return (
    <text x={x} y={y} fill="currentColor" className="text-slate-500 dark:text-slate-400" textAnchor={x > cx ? 'start' : 'end'} dominantBaseline="central" fontSize={12}>
      {name}
    </text>
  );
}

function useIsDark() {
  const [dark, setDark] = useState(() => document.documentElement.classList.contains('dark'));
  useEffect(() => {
    const obs = new MutationObserver(() => setDark(document.documentElement.classList.contains('dark')));
    obs.observe(document.documentElement, { attributes: true, attributeFilter: ['class'] });
    return () => obs.disconnect();
  }, []);
  return dark;
}

export default function Dashboard() {
  const [stats, setStats] = useState(null);
  const [syncStatus, setSyncStatus] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const isDark = useIsDark();

  const axisColor = isDark ? '#64748b' : '#94a3b8';
  const gridColor = isDark ? '#334155' : '#f1f5f9';
  const cursorFill = isDark ? 'rgba(30,41,59,0.3)' : 'rgba(248,250,252,0.4)';

  const { resolveSpace } = useSpaceNames();

  useEffect(() => {
    Promise.all([
      getDashboardStats(),
      getSyncStatus().catch(() => null),
    ])
      .then(([statsData, syncData]) => {
        setStats(statsData);
        setSyncStatus(syncData);
      })
      .catch(() => setError('Failed to load dashboard data'))
      .finally(() => setLoading(false));
  }, []);

  if (loading) {
    return (
      <div className="animate-fade-in">
        <div className="loading-skeleton h-7 w-48 mb-6" />
        <div className="grid grid-cols-2 lg:grid-cols-5 gap-4 mb-6">
          {[...Array(5)].map((_, i) => (
            <div key={i} className="card p-5">
              <div className="loading-skeleton h-4 w-20 mb-3" />
              <div className="loading-skeleton h-8 w-16 mb-2" />
              <div className="loading-skeleton h-3 w-24" />
            </div>
          ))}
        </div>
        <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
          <div className="card p-5"><div className="loading-skeleton h-48" /></div>
          <div className="card p-5"><div className="loading-skeleton h-48" /></div>
        </div>
      </div>
    );
  }

  if (error) {
    return (
      <div className="empty-state">
        <div className="w-14 h-14 rounded-full bg-red-50 dark:bg-red-900/30 flex items-center justify-center mb-4">
          <ExclamationTriangleIcon className="h-6 w-6 text-red-500" />
        </div>
        <div className="text-sm font-medium text-slate-900 dark:text-slate-100 mb-1">Unable to load dashboard</div>
        <div className="text-sm text-slate-500 dark:text-slate-400">{error}</div>
      </div>
    );
  }

  const total = stats?.total_runbooks ?? stats?.total_pages ?? 0;
  const wl = stats?.wl_count ?? 0;
  const stale = stats?.stale_count ?? 0;
  const unowned = stats?.unowned_count ?? 0;
  const recent = stats?.recently_updated ?? 0;

  const spaceData = stats?.space_distribution
    ? Object.entries(stats.space_distribution).map(([key, count]) => ({
        name: resolveSpace(key),
        count,
      }))
    : [];

  const LABEL_FRIENDLY = {
    'moved-to-new-space':          'Moved to New Space',
    'kb-how-to-article':           'KB Article',
    'monitoring-core-splunk':      'Mon: Splunk',
    'monitoring-core-datadog':     'Mon: Datadog',
    'monitoring-core-standard':    'Mon: Standard',
    'monitoring-core-tbd':         'Mon: TBD',
    'monitoring-core-application-insights': 'Mon: App Insights',
    'monitoring-core-deployments': 'Mon: Deployments',
    'monitoring-core-general':     'Mon: General',
    'monitoring-core-pagerduty':   'Mon: PagerDuty',
    'monitoring-core-onboarding':  'Mon: Onboarding',
    'monitoring-core-splunk-synthetics': 'Mon: Synthetics',
    'monitoring-core-grafana':     'Mon: Grafana',
    'monitoring-core-splunk-apm':  'Mon: Splunk APM',
    'monitoring-core-stored-procedures': 'Mon: Stored Procs',
  };

  const formatLabel = (raw) =>
    LABEL_FRIENDLY[raw] || raw.replace(/[-_]/g, ' ').replace(/\b\w/g, (c) => c.toUpperCase());

  const labelData = stats?.label_distribution
    ? Object.entries(stats.label_distribution)
        .map(([name, count]) => ({ name: formatLabel(name), count }))
        .sort((a, b) => b.count - a.count)
        .slice(0, 8)
    : [];

  const priorityDataRaw = stats?.priority_distribution
    ? Object.entries(stats.priority_distribution).map(([name, value]) => ({ name, value }))
    : [];
  const priorityTotal = priorityDataRaw.reduce((s, d) => s + d.value, 0);
  const MIN_SLICE_PCT = 0.04;
  const priorityData = priorityDataRaw.map((d) => ({
    ...d,
    displayValue: d.value / priorityTotal < MIN_SLICE_PCT
      ? Math.ceil(priorityTotal * MIN_SLICE_PCT)
      : d.value,
  }));

  const domainEntries = stats?.domain_distribution
    ? Object.entries(stats.domain_distribution)
        .map(([name, count]) => ({ name, count }))
        .sort((a, b) => b.count - a.count)
    : [];
  const domainData = domainEntries;

  const REVIEW_REASON_LABELS = {
    older_than_one_year: 'Older than 1 year',
    contains_pagerduty: 'PagerDuty',
    contains_datadog: 'Datadog',
    contains_nagios: 'Nagios',
    contains_moving_on: 'Moving on',
  };

  const reviewData = stats?.review_reason_distribution
    ? Object.entries(stats.review_reason_distribution)
        .map(([key, count]) => ({ name: REVIEW_REASON_LABELS[key] || key, count }))
        .sort((a, b) => b.count - a.count)
    : [];

  const lastSync = syncStatus?.last_sync_time;

  return (
    <div className="animate-fade-in">
      <div className="flex items-center justify-between mb-6">
        <div>
          <h1 className="page-title">Overview</h1>
          <p className="caption mt-0.5">Documentation health and content summary</p>
        </div>
        {lastSync && (
          <div className="hidden sm:flex items-center gap-2 text-2xs text-slate-400 dark:text-slate-500">
            <ArrowPathIcon className="h-3.5 w-3.5" />
            Last synced {new Date(lastSync).toLocaleDateString()}
          </div>
        )}
      </div>

      {/* KPI Cards */}
      <div className="grid grid-cols-2 lg:grid-cols-5 gap-3 mb-6">
        <KpiCard title="Total Pages" value={total}
          description={`Across ${spaceData.length || '--'} spaces`}
          icon={DocumentTextIcon} color="brand" href="/runbooks" />
        <KpiCard title="Without Label" value={wl}
          description={wl > 0 ? `${((wl / Math.max(total, 1)) * 100).toFixed(0)}% of pages` : 'All pages classified'}
          icon={TagIcon} color={wl > 0 ? 'amber' : 'emerald'} href="/wl" />
        <KpiCard title="Needs Review" value={stale}
          description={stale > 0 ? 'Action required' : 'All current'}
          icon={ExclamationTriangleIcon} color={stale > 0 ? 'red' : 'emerald'} href="/stale" />
        <KpiCard title="Unowned" value={unowned}
          description={unowned > 0 ? 'Missing ownership' : 'All assigned'}
          icon={UserIcon} color={unowned > 0 ? 'amber' : 'emerald'} />
        <KpiCard title="Recently Updated" value={recent}
          description="In the last 7 days" icon={ClockIcon} color="slate" />
      </div>

      {/* Charts */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-4 mb-6">
        <ChartCard title="Pages by Space">
          {spaceData.length > 0 ? (
            <ResponsiveContainer width="100%" height={220}>
              <BarChart data={spaceData} barCategoryGap="35%">
                <CartesianGrid strokeDasharray="3 3" stroke={gridColor} vertical={false} />
                <XAxis dataKey="name" tick={{ fontSize: 12, fill: axisColor }} axisLine={false} tickLine={false} />
                <YAxis tick={{ fontSize: 12, fill: axisColor }} axisLine={false} tickLine={false} width={35} />
                <Tooltip content={<CustomTooltip />} cursor={{ fill: cursorFill }} />
                <Bar dataKey="count" radius={[6, 6, 0, 0]} maxBarSize={50}>
                  {spaceData.map((_, i) => <Cell key={i} fill={CHART_COLORS[i % CHART_COLORS.length]} />)}
                </Bar>
              </BarChart>
            </ResponsiveContainer>
          ) : <EmptyChart message="No spaces available" action="Run a sync to import content" />}
        </ChartCard>

        <ChartCard title="Top Labels">
          {labelData.length > 0 ? (
            <ResponsiveContainer width="100%" height={220}>
              <BarChart data={labelData} layout="vertical" barCategoryGap="30%">
                <CartesianGrid strokeDasharray="3 3" stroke={gridColor} horizontal={false} />
                <XAxis type="number" tick={{ fontSize: 12, fill: axisColor }} axisLine={false} tickLine={false} />
                <YAxis type="category" dataKey="name" tick={{ fontSize: 11, fill: axisColor }} axisLine={false} tickLine={false} width={140} />
                <Tooltip content={<CustomTooltip />} cursor={{ fill: cursorFill }} />
                <Bar dataKey="count" radius={[0, 6, 6, 0]} maxBarSize={24} fill="#8b5cf6" />
              </BarChart>
            </ResponsiveContainer>
          ) : <EmptyChart message="No labels found" action="Pages have not been labeled yet" />}
        </ChartCard>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-4 mb-6">
        <ChartCard title="Priority Distribution">
          {priorityData.length > 0 ? (
            <div>
              <ResponsiveContainer width="100%" height={180}>
                <PieChart>
                  <Pie data={priorityData} cx="50%" cy="50%" innerRadius={50} outerRadius={72}
                    paddingAngle={2} dataKey="displayValue" label={CustomPieLabel}>
                    {priorityData.map((_, i) => <Cell key={i} fill={PIE_COLORS[i % PIE_COLORS.length]} stroke="none" />)}
                  </Pie>
                  <Tooltip content={<CustomTooltip />} />
                </PieChart>
              </ResponsiveContainer>
            </div>
          ) : <EmptyChart message="No priorities assigned" action="Assign priorities from the content library" />}
        </ChartCard>

        <ChartCard title="Review Reasons">
          {reviewData.length > 0 ? (
            <ResponsiveContainer width="100%" height={220}>
              <BarChart data={reviewData} layout="vertical" barCategoryGap="30%">
                <CartesianGrid strokeDasharray="3 3" stroke={gridColor} horizontal={false} />
                <XAxis type="number" tick={{ fontSize: 12, fill: axisColor }} axisLine={false} tickLine={false} />
                <YAxis type="category" dataKey="name" tick={{ fontSize: 11, fill: axisColor }} axisLine={false} tickLine={false} width={120} />
                <Tooltip content={<CustomTooltip />} cursor={{ fill: cursorFill }} />
                <Bar dataKey="count" radius={[0, 6, 6, 0]} maxBarSize={24} fill="#ef4444" />
              </BarChart>
            </ResponsiveContainer>
          ) : <EmptyChart message="No review reasons detected" action="Run classification to detect review-required content" />}
        </ChartCard>
      </div>

      <ChartCard title="Pages by Domain">
        {domainData.length > 0 ? (
          <ResponsiveContainer width="100%" height={domainData.length * 36 + 30}>
            <BarChart data={domainData} layout="vertical" barCategoryGap="30%">
              <CartesianGrid strokeDasharray="3 3" stroke={gridColor} horizontal={false} />
              <XAxis type="number" tick={{ fontSize: 12, fill: axisColor }} axisLine={false} tickLine={false} />
              <YAxis type="category" dataKey="name" tick={{ fontSize: 11, fill: axisColor }} axisLine={false} tickLine={false} width={120} />
              <Tooltip content={<CustomTooltip />} cursor={{ fill: cursorFill }} />
              <Bar dataKey="count" radius={[0, 6, 6, 0]} maxBarSize={24}>
                {domainData.map((_, i) => (
                  <Cell key={i} fill={CHART_COLORS[i % CHART_COLORS.length]} />
                ))}
              </Bar>
            </BarChart>
          </ResponsiveContainer>
        ) : <EmptyChart message="No domains assigned" action="Run classification to detect domains" />}
      </ChartCard>
    </div>
  );
}
