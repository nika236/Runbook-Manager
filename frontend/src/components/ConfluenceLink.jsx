import React, { useState, useEffect } from 'react';
import { ArrowTopRightOnSquareIcon } from '@heroicons/react/24/outline';
import { getPublicConfig } from '../api/client';

let _cachedBase = null;
let _fetchPromise = null;

function fetchBase() {
  if (!_fetchPromise) {
    _fetchPromise = getPublicConfig()
      .then((data) => {
        _cachedBase = data.confluence_site_base_url || '';
        return _cachedBase;
      })
      .catch(() => {
        _cachedBase = '';
        return '';
      });
  }
  return _fetchPromise;
}

export default function ConfluenceLink({ spaceKey, pageId, confluenceUrl, className = '' }) {
  const [base, setBase] = useState(_cachedBase ?? '');

  useEffect(() => {
    if (_cachedBase !== null) {
      setBase(_cachedBase);
      return;
    }
    fetchBase().then(setBase);
  }, []);

  const url = confluenceUrl || (base ? `${base}/spaces/${spaceKey}/pages/${pageId}` : '');

  if (!url) return null;

  return (
    <a
      href={url}
      target="_blank"
      rel="noopener noreferrer"
      className={`inline-flex items-center gap-1.5 text-sm text-slate-500 hover:text-brand-600 transition-colors ${className}`}
    >
      <ArrowTopRightOnSquareIcon className="h-4 w-4" />
      <span>View in Confluence</span>
    </a>
  );
}
