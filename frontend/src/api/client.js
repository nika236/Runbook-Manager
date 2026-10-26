import axios from 'axios';

const api = axios.create({
  baseURL: '/api',
  headers: {
    'Content-Type': 'application/json',
  },
});

// Config
export const getPublicConfig = () => api.get('/config/public').then((r) => r.data);

// Dashboard
export const getDashboardStats = () => api.get('/dashboard/stats').then((r) => r.data);
export const getRecentActivity = () => api.get('/dashboard/recent-activity').then((r) => r.data);
export const getStaleRunbooks = () => api.get('/dashboard/stale').then((r) => r.data);

// Spaces
export const getSpaces = () => api.get('/spaces').then((r) => r.data);
export const getSpace = (spaceKey) => api.get(`/spaces/${spaceKey}`).then((r) => r.data);
export const getSpaceTree = (spaceKey) => api.get(`/spaces/${spaceKey}/tree`).then((r) => r.data);

// Pages (new space-based routes)
export const getSpacePages = (spaceKey, params) =>
  api.get(`/spaces/${spaceKey}/pages`, { params }).then((r) => r.data);
export const getSpacePage = (spaceKey, pageId) =>
  api.get(`/spaces/${spaceKey}/pages/${pageId}`).then((r) => r.data);
export const getPageContent = (spaceKey, pageId, format = 'html') =>
  api.get(`/spaces/${spaceKey}/pages/${pageId}/content`, { params: { format } }).then((r) => r.data);
export const getPageRevisions = (spaceKey, pageId) =>
  api.get(`/spaces/${spaceKey}/pages/${pageId}/revisions`).then((r) => r.data);

// Metadata (local-only writes)
export const getPageMetadata = (spaceKey, pageId) =>
  api.get(`/spaces/${spaceKey}/pages/${pageId}/metadata`).then((r) => r.data);
export const updatePageMetadata = (spaceKey, pageId, data) =>
  api.put(`/spaces/${spaceKey}/pages/${pageId}/metadata`, data).then((r) => r.data);
export const bulkUpdatePages = (data) =>
  api.post('/pages/bulk-update', data).then((r) => r.data);

// WL pages
export const getWLPages = (params) => api.get('/wl/pages', { params }).then((r) => r.data);

// Sync
export const triggerFullSync = () => api.post('/sync/full').then((r) => r.data);
export const triggerIncrementalSync = () => api.post('/sync/incremental').then((r) => r.data);
export const getSyncStatus = () => api.get('/sync/status').then((r) => r.data);
export const getSyncRuns = () => api.get('/sync/runs').then((r) => r.data);

// Filter values (dynamic dropdowns)
export const getFilterValues = () => api.get('/filter-values').then((r) => r.data);

// Teams & Domains
export const getDomainTeamsConfig = () => api.get('/config/domain-teams').then((r) => r.data);
export const getTeamsDomainsSummary = () => api.get('/teams-domains/summary').then((r) => r.data);
export const getTeamsDomainsPages = (params) =>
  api.get('/teams-domains/pages', { params }).then((r) => r.data);

// Legacy compat wrappers
export const getRunbooks = (params) => api.get('/runbooks/', { params }).then((r) => r.data);
export const getRunbook = (id) => api.get(`/runbooks/${id}`).then((r) => r.data);
export const updateRunbook = (id, data) => api.put(`/runbooks/${id}`, data).then((r) => r.data);
export const bulkUpdateRunbooks = (data) => api.post('/pages/bulk-update', data).then((r) => r.data);
export const syncConfluence = () => api.post('/sync/confluence').then((r) => r.data);

export default api;
