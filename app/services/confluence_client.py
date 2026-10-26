"""Read-only Confluence Cloud REST API client.

This module ONLY performs GET requests against Confluence.
No POST, PUT, or DELETE operations exist here by design.
"""

import re
import time
import logging
from concurrent.futures import ThreadPoolExecutor, as_completed

import requests

logger = logging.getLogger(__name__)

DEFAULT_PAGE_EXPAND = (
    'body.storage,version,ancestors,children.page,'
    'metadata.labels,history.lastUpdated,history.createdBy'
)


def strip_html(html):
    """Remove HTML tags and return plain text (full content, not truncated)."""
    if not html:
        return ''
    text = re.sub(r'<[^>]+>', ' ', html)
    text = re.sub(r'\s+', ' ', text).strip()
    return text


def parse_confluence_date(date_str):
    """Parse an ISO-8601 date string from Confluence."""
    if not date_str:
        return None
    if not isinstance(date_str, str):
        return None
    date_str = date_str.replace('Z', '+00:00')
    try:
        from datetime import datetime
        return datetime.fromisoformat(date_str)
    except (ValueError, TypeError):
        try:
            from datetime import datetime
            return datetime.strptime(date_str[:19], '%Y-%m-%dT%H:%M:%S')
        except (ValueError, TypeError):
            return None


class ConfluenceClient:
    """Read-only client for Confluence Cloud REST API v1 and v2.

    Every method in this class issues only HTTP GET requests.
    """

    def __init__(self, base_url, email, api_token, rate_limit=8):
        self.base_url = base_url.rstrip('/')
        self.rate_limit = rate_limit
        self._min_interval = 1.0 / rate_limit if rate_limit > 0 else 0
        self._last_request_time = 0

        self.session = requests.Session()
        self.session.auth = (email, api_token)
        self.session.headers.update({
            'Accept': 'application/json',
            'User-Agent': 'runbooks-app/1.0 (read-only sync)',
        })

    def _throttle(self):
        """Enforce rate limiting between requests."""
        if self._min_interval > 0:
            elapsed = time.time() - self._last_request_time
            if elapsed < self._min_interval:
                time.sleep(self._min_interval - elapsed)
        self._last_request_time = time.time()

    def _get(self, path, params=None, timeout=30, retries=3):
        """Issue a GET request with retry and rate limiting."""
        url = f'{self.base_url}{path}' if path.startswith('/') else path
        for attempt in range(retries):
            self._throttle()
            try:
                resp = self.session.get(url, params=params, timeout=timeout)
                resp.raise_for_status()
                return resp.json()
            except requests.RequestException as e:
                if attempt == retries - 1:
                    raise
                wait = 2 ** attempt
                logger.warning('Request failed (attempt %d/%d), retrying in %ds: %s',
                               attempt + 1, retries, wait, e)
                time.sleep(wait)

    # ------------------------------------------------------------------
    # Space operations
    # ------------------------------------------------------------------

    def list_spaces(self, limit=100):
        """List all accessible Confluence spaces."""
        spaces = []
        start = 0
        while True:
            data = self._get('/wiki/rest/api/space', params={
                'limit': limit,
                'start': start,
                'expand': 'description.plain,homepage',
            })
            results = data.get('results', [])
            if not results:
                break
            spaces.extend(results)
            if data.get('size', 0) < limit:
                break
            start += limit
        return spaces

    def get_space(self, space_key):
        """Get a single space by key."""
        return self._get(f'/wiki/rest/api/space/{space_key}', params={
            'expand': 'description.plain,homepage',
        })

    def get_space_labels(self, space_id, limit=200):
        """Fetch all labels for a space via the v2 API."""
        labels = []
        cursor = None
        while True:
            params = {'limit': limit}
            if cursor:
                params['cursor'] = cursor
            data = self._get(f'/wiki/api/v2/spaces/{space_id}/labels', params=params)
            results = data.get('results', [])
            if not results:
                break
            labels.extend(results)
            cursor = data.get('_links', {}).get('next')
            if not cursor:
                break
        return labels

    # ------------------------------------------------------------------
    # Page operations
    # ------------------------------------------------------------------

    def get_pages(self, space_key, limit=50, start=0, expand=None):
        """Fetch a page of results from a space."""
        return self._get('/wiki/rest/api/content', params={
            'spaceKey': space_key,
            'type': 'page',
            'expand': expand or DEFAULT_PAGE_EXPAND,
            'limit': limit,
            'start': start,
        })

    def get_all_pages(self, space_key, expand=None, on_progress=None):
        """Paginate through all pages in a space."""
        return self._get_all_content(space_key, 'page', expand=expand,
                                     on_progress=on_progress)

    def get_page(self, page_id, expand=None):
        """Fetch a single page by ID."""
        return self._get(f'/wiki/rest/api/content/{page_id}', params={
            'expand': expand or DEFAULT_PAGE_EXPAND,
        })

    # ------------------------------------------------------------------
    # Blog post operations
    # ------------------------------------------------------------------

    def get_blog_posts(self, space_key, limit=50, start=0, expand=None):
        """Fetch a page of blog post results from a space."""
        return self._get('/wiki/rest/api/content', params={
            'spaceKey': space_key,
            'type': 'blogpost',
            'expand': expand or DEFAULT_PAGE_EXPAND,
            'limit': limit,
            'start': start,
        })

    def get_all_blog_posts(self, space_key, expand=None, on_progress=None):
        """Paginate through all blog posts in a space."""
        return self._get_all_content(space_key, 'blogpost', expand=expand,
                                     on_progress=on_progress)

    # ------------------------------------------------------------------
    # Generic content fetcher
    # ------------------------------------------------------------------

    def _get_all_content(self, space_key, content_type='page', expand=None,
                         on_progress=None):
        """Paginate through all content of a given type in a space."""
        all_items = []
        start = 0
        limit = 50
        total_estimate = None

        while True:
            data = self._get('/wiki/rest/api/content', params={
                'spaceKey': space_key,
                'type': content_type,
                'expand': expand or DEFAULT_PAGE_EXPAND,
                'limit': limit,
                'start': start,
            })
            results = data.get('results', [])
            if total_estimate is None:
                total_estimate = data.get('totalSize') or data.get('size', 0)
            if not results:
                break
            all_items.extend(results)
            if on_progress:
                on_progress(len(all_items), total_estimate)
            if data.get('size', 0) < limit:
                break
            start += limit

        return all_items

    # ------------------------------------------------------------------
    # CQL search (read-only)
    # ------------------------------------------------------------------

    def search_cql(self, cql, limit=50, start=0, expand=None):
        """Execute a CQL search query. Returns the raw search response."""
        params = {'cql': cql, 'limit': limit, 'start': start}
        if expand:
            params['expand'] = expand
        return self._get('/wiki/rest/api/search', params=params)

    def search_cql_all(self, cql, expand=None, on_progress=None):
        """Paginate through all CQL search results with safe termination.

        Guards against Confluence CQL pagination bugs where the API keeps
        returning full batches of duplicate results past totalSize.
        Deduplicates by content ID and stops when:
        - an empty batch is received;
        - a batch shorter than limit is received;
        - totalSize distinct IDs have been collected;
        - an entire batch contains only already-seen IDs.
        """
        seen_ids = set()
        all_results = []
        start = 0
        limit = 250
        total_estimate = None

        while True:
            data = self.search_cql(cql, limit=limit, start=start, expand=expand)
            results = data.get('results', [])
            if total_estimate is None:
                total_estimate = data.get('totalSize', 0)
            if not results:
                break

            new_in_batch = 0
            for item in results:
                content = item.get('content', item)
                cid = str(content.get('id', ''))
                if cid and cid not in seen_ids:
                    seen_ids.add(cid)
                    all_results.append(item)
                    new_in_batch += 1

            if on_progress:
                on_progress(len(all_results), total_estimate)

            if new_in_batch == 0:
                logger.warning(
                    'CQL pagination: batch at start=%d had no new IDs; '
                    'stopping with %d unique of %d reported.',
                    start, len(all_results), total_estimate or 0)
                break
            if len(results) < limit:
                break
            if total_estimate and len(all_results) >= total_estimate:
                break
            start += limit

        return all_results

    # ------------------------------------------------------------------
    # History and restrictions
    # ------------------------------------------------------------------

    def get_history(self, page_id):
        """Fetch version history for a page."""
        try:
            return self._get(f'/wiki/rest/api/content/{page_id}/history', params={
                'expand': 'lastUpdated,previousVersion',
            })
        except requests.RequestException:
            return None

    def get_versions(self, page_id, limit=50):
        """Fetch all versions of a page (for revision list)."""
        versions = []
        start = 0
        while True:
            try:
                data = self._get(f'/wiki/rest/api/content/{page_id}/version', params={
                    'limit': limit,
                    'start': start,
                    'expand': 'content',
                })
            except requests.RequestException:
                break
            results = data.get('results', [])
            if not results:
                break
            versions.extend(results)
            if data.get('size', 0) < limit:
                break
            start += limit
        return versions

    def get_restrictions(self, page_id):
        """Fetch page-level restrictions. Returns None if not accessible."""
        try:
            return self._get(f'/wiki/rest/api/content/{page_id}/restriction')
        except requests.HTTPError as e:
            if e.response is not None and e.response.status_code in (403, 404):
                return None
            raise
        except requests.RequestException:
            return None

    # ------------------------------------------------------------------
    # Parallel fetch helpers
    # ------------------------------------------------------------------

    def fetch_page_extras(self, pages,
                          fetch_revisions=True, fetch_restrictions=True,
                          max_workers=5, on_progress=None):
        """Fetch revisions and restrictions for a list of pages.

        Returns a dict keyed by page_id with sub-keys:
            'revisions', 'restrictions'
        """
        extras = {}
        total = len(pages)
        done = 0

        def fetch_one(page):
            pid = str(page.get('id', ''))
            result = {'revisions': [], 'restrictions': None}
            if fetch_revisions:
                try:
                    result['revisions'] = self.get_versions(pid)
                except Exception as e:
                    logger.warning('Failed to fetch revisions for page %s: %s', pid, e)
            if fetch_restrictions:
                try:
                    result['restrictions'] = self.get_restrictions(pid)
                except Exception as e:
                    logger.warning('Failed to fetch restrictions for page %s: %s', pid, e)
            return pid, result

        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            futures = {executor.submit(fetch_one, p): p for p in pages}
            for future in as_completed(futures):
                try:
                    pid, result = future.result()
                    extras[pid] = result
                except Exception as e:
                    logger.warning('Failed to fetch extras: %s', e)
                done += 1
                if on_progress:
                    on_progress(done, total)

        return extras
