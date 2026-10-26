import React, { Suspense, lazy } from 'react';
import { Routes, Route, Navigate, useParams } from 'react-router-dom';
import Layout from './components/Layout';

const Dashboard = lazy(() => import('./pages/Dashboard'));
const Spaces = lazy(() => import('./pages/Spaces'));
const SpaceView = lazy(() => import('./pages/SpaceView'));
const PageDetail = lazy(() => import('./pages/PageDetail'));
const Runbooks = lazy(() => import('./pages/Runbooks'));
const RunbookDetail = lazy(() => import('./pages/RunbookDetail'));
const WLPages = lazy(() => import('./pages/WLPages'));
const StaleRunbooks = lazy(() => import('./pages/StaleRunbooks'));
const Sync = lazy(() => import('./pages/Sync'));
const TeamsDomains = lazy(() => import('./pages/TeamsDomains'));

function RunbookRedirect() {
  const { id } = useParams();
  return <Navigate to={`/runbooks/${id}`} replace />;
}

function PageFallback() {
  return (
    <div className="animate-fade-in p-8">
      <div className="loading-skeleton h-7 w-48 mb-6" />
      <div className="loading-skeleton h-40 w-full" />
    </div>
  );
}

export default function App() {
  return (
    <Suspense fallback={<PageFallback />}>
      <Routes>
        <Route element={<Layout />}>
          <Route path="/" element={<Dashboard />} />
          <Route path="/spaces" element={<Spaces />} />
          <Route path="/spaces/:spaceKey" element={<SpaceView />} />
          <Route path="/spaces/:spaceKey/pages/:pageId" element={<PageDetail />} />
          <Route path="/spaces/:spaceKey/pages/:pageId/:slug" element={<PageDetail />} />
          <Route path="/wl" element={<WLPages />} />
          <Route path="/teams-domains" element={<TeamsDomains />} />
          <Route path="/runbooks" element={<Runbooks />} />
          <Route path="/runbooks/:id" element={<RunbookDetail />} />
          <Route path="/stale" element={<StaleRunbooks />} />
          <Route path="/sync" element={<Sync />} />
        </Route>
      </Routes>
    </Suspense>
  );
}
