import React, { useCallback, useEffect, useState } from 'react';
import { useParams, Link } from 'react-router-dom';
import {
  ExclamationCircleIcon, ArrowPathIcon, ListBulletIcon, InformationCircleIcon,
} from '@heroicons/react/24/outline';
import ReaderBreadcrumbs from '../components/reader/ReaderBreadcrumbs';
import PageHeader from '../components/reader/PageHeader';
import PageDetails from '../components/reader/PageDetails';
import TableOfContents, { TocList, isTocUseful } from '../components/reader/TableOfContents';
import ConfluenceArticle from '../components/reader/ConfluenceArticle';
import RevisionHistory from '../components/reader/RevisionHistory';
import LocalMetadataForm from '../components/reader/LocalMetadataForm';
import Disclosure from '../components/reader/Disclosure';
import useSpaceNames from '../hooks/useSpaceNames';
import useContainerWidth from '../hooks/useContainerWidth';
import {
  getSpacePage, getPageRevisions, updatePageMetadata,
  getPublicConfig,
} from '../api/client';

/**
 * Shell width at which the right rail earns its keep: 720px article + 40px gap
 * + 280px rail. Below this the rail would squeeze the article under its 720px
 * floor, so the TOC and page details move into disclosures above/below instead.
 */
const RAIL_MIN_WIDTH = 1040;

export default function PageDetail() {
  const { spaceKey, pageId } = useParams();
  const { resolveSpace } = useSpaceNames();
  const [shellRef, shellWidth] = useContainerWidth();

  const [page, setPage] = useState(null);
  const [revisions, setRevisions] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [reloadKey, setReloadKey] = useState(0);

  const [headings, setHeadings] = useState([]);
  const [activeHeading, setActiveHeading] = useState(null);

  const [editing, setEditing] = useState(false);
  const [saving, setSaving] = useState(false);
  const [saveError, setSaveError] = useState(null);
  const [siteBase, setSiteBase] = useState('');

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    setError(null);
    setHeadings([]);
    setActiveHeading(null);

    Promise.all([
      getSpacePage(spaceKey, pageId),
      getPageRevisions(spaceKey, pageId).catch(() => ({ revisions: [] })),
    ]).then(([pageData, revData]) => {
      if (cancelled) return;
      setPage(pageData);
      setRevisions(revData.revisions || []);
    }).catch((err) => {
      if (cancelled) return;
      setError(err?.response?.status === 404 ? 'not-found' : 'load-failed');
    }).finally(() => {
      if (!cancelled) setLoading(false);
    });

    return () => { cancelled = true; };
  }, [spaceKey, pageId, reloadKey]);

  // Canonical Confluence base, used only when a page has no stored URL.
  useEffect(() => {
    getPublicConfig()
      .then((cfg) => setSiteBase(cfg.confluence_site_base_url || ''))
      .catch(() => setSiteBase(''));
  }, []);

  const handleHeadings = useCallback((found) => setHeadings(found), []);
  const handleActive = useCallback((id) => setActiveHeading(id), []);

  const handleSave = async (fields) => {
    setSaving(true);
    setSaveError(null);
    try {
      const updated = await updatePageMetadata(spaceKey, pageId, fields);
      setPage((prev) => ({ ...prev, ...updated }));
      setEditing(false);
    } catch {
      setSaveError('Could not save local metadata. The page in Confluence is unchanged.');
    } finally {
      setSaving(false);
    }
  };

  if (loading) {
    return (
      <div className="rd-shell animate-fade-in" aria-busy="true">
        <div className="loading-skeleton" style={{ height: '1rem', width: '18rem' }} />
        <div className="loading-skeleton" style={{ height: '2rem', width: '28rem', marginTop: '0.75rem' }} />
        <div className="loading-skeleton" style={{ height: '1.5rem', width: '32rem', marginTop: '0.875rem' }} />
        <div className="loading-skeleton" style={{ height: '2.5rem', width: '14rem', marginTop: '1rem' }} />
        {/* Same vertical rhythm as the loaded header, so content arriving does
            not shift the article down the page. */}
        <div className="loading-skeleton" style={{ height: '26rem', marginTop: '2.5rem', borderRadius: '0.5rem' }} />
        <span className="rd-visually-hidden" role="status">Loading page</span>
      </div>
    );
  }

  if (error || !page) {
    const notFound = error === 'not-found';
    return (
      <div className="rd-shell">
        <div className="rd-panel" style={{ padding: '2.5rem', textAlign: 'center' }}>
          <ExclamationCircleIcon
            aria-hidden="true"
            style={{ width: '2.25rem', height: '2.25rem', margin: '0 auto 0.875rem',
                     color: 'var(--rd-danger-border)' }}
          />
          <h1 style={{ margin: 0, fontSize: 'var(--rd-fs-subsection)',
                       lineHeight: 'var(--rd-lh-subsection)', fontWeight: 650,
                       color: 'var(--rd-text)' }}>
            {notFound ? 'Page not found in the local mirror' : 'Could not load this page'}
          </h1>
          <p style={{ margin: '0.5rem 0 1.25rem', fontSize: 'var(--rd-fs-meta)',
                      color: 'var(--rd-text-secondary)' }}>
            {notFound
              ? `No mirrored page with ID ${pageId} exists in space ${spaceKey}.`
              : 'The mirrored content could not be retrieved. This does not affect the page in Confluence.'}
          </p>
          <div className="rd-actions" style={{ justifyContent: 'center' }}>
            {!notFound ? (
              <button type="button" className="btn-primary"
                      onClick={() => setReloadKey((k) => k + 1)}>
                <ArrowPathIcon aria-hidden="true" className="h-4 w-4" />
                Try again
              </button>
            ) : null}
            <Link to={`/spaces/${spaceKey}`} className="btn-secondary">
              Back to space
            </Link>
          </div>
        </div>
      </div>
    );
  }

  const spaceName = resolveSpace(spaceKey);
  const confluenceUrl = page.confluence_url
    || (siteBase ? `${siteBase}/spaces/${spaceKey}/pages/${pageId}` : '');
  const showRail = shellWidth >= RAIL_MIN_WIDTH;
  const tocUseful = isTocUseful(headings);

  const railContent = (
    <>
      <TableOfContents headings={headings} activeId={activeHeading} />
      <PageDetails page={page} spaceKey={spaceKey} spaceName={spaceName} pageId={pageId} />
    </>
  );

  return (
    <div className="rd-shell animate-fade-in" ref={shellRef}>
      <PageHeader
        page={page}
        confluenceUrl={confluenceUrl}
        canEditMetadata
        onEditMetadata={() => { setEditing(true); setSaveError(null); }}
      >
        <ReaderBreadcrumbs
          ancestors={page.ancestors || []}
          spaceKey={spaceKey}
          spaceName={spaceName}
          currentTitle={page.title}
        />
      </PageHeader>

      {editing ? (
        <div style={{ marginBottom: '1.5rem' }}>
          <LocalMetadataForm
            page={page}
            saving={saving}
            error={saveError}
            onSave={handleSave}
            onCancel={() => { setEditing(false); setSaveError(null); }}
          />
        </div>
      ) : null}

      <div className="rd-layout" data-rail={showRail ? 'true' : 'false'}>
        <div className="rd-main">
          {/* Narrow layouts get the same navigation through a disclosure rather
              than a second column. */}
          {!showRail && tocUseful ? (
            <div style={{ marginBottom: '1.5rem' }}>
              <Disclosure title="On this page" count={headings.length} icon={ListBulletIcon}>
                <nav aria-label="On this page">
                  <TocList headings={headings} activeId={activeHeading} />
                </nav>
              </Disclosure>
            </div>
          ) : null}

          <article aria-labelledby="page-title">
            <ConfluenceArticle
              html={page.content}
              sourceWasEmpty={page.content_is_empty}
              onHeadingsChange={handleHeadings}
              onActiveHeadingChange={handleActive}
            />
          </article>

          <div style={{ display: 'grid', gap: '1rem', marginTop: '2.5rem' }}>
            <RevisionHistory revisions={revisions} confluenceUrl={confluenceUrl} />

            {!showRail ? (
              <Disclosure title="Page details" icon={InformationCircleIcon}>
                <PageDetails page={page} spaceKey={spaceKey} spaceName={spaceName}
                             pageId={pageId} flat />
              </Disclosure>
            ) : null}
          </div>
        </div>

        {showRail ? (
          <aside className="rd-rail" aria-label="Page context">
            {railContent}
          </aside>
        ) : null}
      </div>
    </div>
  );
}
