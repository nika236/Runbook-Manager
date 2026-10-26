"""File-based page store.

Reads Confluence-sourced page and blog post data from the git-versioned data/ directory.
This module never contacts Confluence -- it only reads local files.
"""

import json
import logging
from datetime import datetime, timedelta
from pathlib import Path
from collections import Counter

from app.services.exclusions import resolve_excluded_page_ids, get_exclusion_reason

logger = logging.getLogger(__name__)


class PageStore:
    """Reads page and blog post data exported from Confluence into the data/ directory."""

    def __init__(self, data_dir, stale_threshold_days=30, review_age_days=365):
        self.data_dir = Path(data_dir)
        self.spaces_dir = self.data_dir / 'spaces'
        self.stale_threshold_days = stale_threshold_days
        self.review_age_days = review_age_days
        self._index = {}
        self._trees = {}
        self._excluded = {}  # page_id -> exclusion_root_page_id
        self._stats_cache = None
        self._title_index = None  # lazily derived (space_key, title) -> page_id
        self._load_index()

    def invalidate_stats_cache(self):
        """Force the next get_stats() call to recompute rather than use the cache."""
        self._stats_cache = None

    def _load_index(self):
        """Build an in-memory index from page.json and post.json files on startup."""
        self._index = {}
        self._trees = {}
        self._title_index = None

        if not self.spaces_dir.exists():
            logger.info('No data/spaces directory found; index is empty.')
            return

        for space_dir in self.spaces_dir.iterdir():
            if not space_dir.is_dir():
                continue
            space_key = space_dir.name

            # Load pages
            pages_dir = space_dir / 'pages'
            if pages_dir.exists():
                for page_dir in pages_dir.iterdir():
                    if not page_dir.is_dir():
                        continue
                    page_json = page_dir / 'page.json'
                    if not page_json.exists():
                        continue
                    try:
                        data = json.loads(page_json.read_text(encoding='utf-8'))
                        if 'content_type' not in data:
                            data['content_type'] = 'page'
                        pid = str(data.get('confluence_page_id', page_dir.name))
                        self._index[pid] = data
                    except (json.JSONDecodeError, OSError) as e:
                        logger.warning('Failed to load page %s: %s', page_dir.name, e)

            # Load blog posts
            blogs_dir = space_dir / 'blogposts'
            if blogs_dir.exists():
                for blog_dir in blogs_dir.iterdir():
                    if not blog_dir.is_dir():
                        continue
                    post_json = blog_dir / 'post.json'
                    if not post_json.exists():
                        continue
                    try:
                        data = json.loads(post_json.read_text(encoding='utf-8'))
                        if 'content_type' not in data:
                            data['content_type'] = 'blogpost'
                        bid = str(data.get('confluence_page_id', blog_dir.name))
                        self._index[bid] = data
                    except (json.JSONDecodeError, OSError) as e:
                        logger.warning('Failed to load blog post %s: %s', blog_dir.name, e)

            # Load tree
            tree_path = space_dir / 'tree.json'
            if tree_path.exists():
                try:
                    self._trees[space_key] = json.loads(tree_path.read_text(encoding='utf-8'))
                except (json.JSONDecodeError, OSError) as e:
                    logger.warning('Failed to load tree.json for %s: %s', space_key, e)

        # Resolve excluded subtrees
        self._excluded = resolve_excluded_page_ids(self._index)
        logger.info('Loaded %d items into index from %s (%d excluded)',
                     len(self._index), self.spaces_dir, len(self._excluded))

    def reload(self):
        """Reload the in-memory index from disk."""
        self._load_index()

    def is_excluded(self, page_id):
        """Check if a page belongs to an excluded subtree."""
        return str(page_id) in self._excluded

    def get_excluded_ids(self):
        """Return the full excluded page_id -> root_page_id mapping."""
        return dict(self._excluded)

    def get_excluded_count(self):
        """Return the number of excluded pages."""
        return len(self._excluded)

    # ------------------------------------------------------------------
    # Space operations
    # ------------------------------------------------------------------

    def get_spaces(self):
        """List available spaces with page and blog counts."""
        spaces = []
        if not self.spaces_dir.exists():
            return spaces
        for space_dir in sorted(self.spaces_dir.iterdir()):
            if not space_dir.is_dir():
                continue
            space_key = space_dir.name
            space_json = space_dir / 'space.json'
            info = {'key': space_key, 'name': space_key}
            if space_json.exists():
                try:
                    info = json.loads(space_json.read_text(encoding='utf-8'))
                except (json.JSONDecodeError, OSError):
                    pass
            page_count = sum(1 for p in self._index.values()
                             if p.get('space_key') == space_key
                             and p.get('content_type') == 'page'
                             and str(p.get('confluence_page_id', '')) not in self._excluded)
            blog_count = sum(1 for p in self._index.values()
                             if p.get('space_key') == space_key
                             and p.get('content_type') == 'blogpost')
            info['page_count'] = page_count
            info['blog_count'] = blog_count
            spaces.append(info)
        return spaces

    def get_tree(self, space_key):
        """Return the pre-computed hierarchy tree for a space."""
        if space_key in self._trees:
            return self._trees[space_key]
        tree_path = self.spaces_dir / space_key / 'tree.json'
        if tree_path.exists():
            try:
                tree = json.loads(tree_path.read_text(encoding='utf-8'))
                self._trees[space_key] = tree
                return tree
            except (json.JSONDecodeError, OSError):
                pass
        return []

    # ------------------------------------------------------------------
    # Content operations
    # ------------------------------------------------------------------

    def get_all_pages(self, space_key=None, content_type=None, wl_filter=None,
                      metadata_store=None, include_excluded=False):
        """Return all indexed items, optionally filtered.

        By default, pages in excluded subtrees are omitted. Pass
        include_excluded=True to get the raw inventory.
        """
        items = list(self._index.values())
        if not include_excluded:
            items = [p for p in items
                     if str(p.get('confluence_page_id', '')) not in self._excluded]
        if space_key:
            items = [p for p in items if p.get('space_key') == space_key]
        if content_type:
            items = [p for p in items if p.get('content_type') == content_type]
        if wl_filter and metadata_store:
            filtered = []
            for p in items:
                pid = str(p.get('confluence_page_id', ''))
                sk = p.get('space_key', '')
                meta = metadata_store.get(sk, pid)
                if wl_filter == 'label_missing' and meta.get('flag_label_missing'):
                    filtered.append(p)
                elif wl_filter == 'taxonomy_unmapped' and meta.get('flag_taxonomy_unmapped'):
                    filtered.append(p)
                elif wl_filter == 'domain_missing' and meta.get('flag_domain_missing'):
                    filtered.append(p)
            items = filtered
        return items

    def get_blog_posts(self, space_key=None):
        """Return all blog posts, optionally filtered by space."""
        return self.get_all_pages(space_key=space_key, content_type='blogpost')

    def get_page(self, page_id):
        """Return page/post metadata from the index, or None."""
        return self._index.get(str(page_id))

    def find_page_by_title(self, space_key, title):
        """Return (space_key, page_id) for a mirrored title, or None.

        Used to rewrite internal Confluence links to the local mirror only when the
        target actually exists. Read-only: derived lazily from the existing index
        and reset whenever the index reloads.
        """
        if not title:
            return None
        if self._title_index is None:
            index = {}
            for item in self._index.values():
                item_title = (item.get('title') or '').strip().lower()
                if not item_title:
                    continue
                key = (item.get('space_key') or '', item_title)
                index.setdefault(key, str(item.get('confluence_page_id', '')))
            self._title_index = index

        normalized = title.strip().lower()
        if space_key:
            found = self._title_index.get((space_key, normalized))
            if found:
                return (space_key, found)
        # Fall back to any space: a title-only link still resolves if unambiguous.
        matches = [(sk, pid) for (sk, t), pid in self._title_index.items()
                   if t == normalized]
        if len(matches) == 1:
            return matches[0]
        return None

    def get_page_content(self, space_key, page_id):
        """Load full HTML content for a page or blog post from disk."""
        page_id = str(page_id)
        for subdir in ('pages', 'blogposts'):
            html_path = self.spaces_dir / space_key / subdir / page_id / 'content.html'
            if html_path.exists():
                try:
                    return html_path.read_text(encoding='utf-8')
                except OSError:
                    continue
        return None

    def get_page_text(self, space_key, page_id):
        """Load plain-text content for a page or blog post from disk."""
        page_id = str(page_id)
        for subdir in ('pages', 'blogposts'):
            txt_path = self.spaces_dir / space_key / subdir / page_id / 'content.txt'
            if txt_path.exists():
                try:
                    return txt_path.read_text(encoding='utf-8')
                except OSError:
                    continue
        return None

    def get_revisions(self, space_key, page_id):
        """Load revision history for a page."""
        rev_path = self.spaces_dir / space_key / 'pages' / str(page_id) / 'revisions.json'
        if rev_path.exists():
            try:
                return json.loads(rev_path.read_text(encoding='utf-8'))
            except (json.JSONDecodeError, OSError):
                return []
        return []

    # ------------------------------------------------------------------
    # Aggregations
    # ------------------------------------------------------------------

    def get_stale_pages(self, metadata_store=None):
        """Return pages not updated within the stale threshold."""
        cutoff = datetime.utcnow() - timedelta(days=self.stale_threshold_days)
        stale = []
        for page in self._index.values():
            if page.get('content_type') == 'blogpost':
                continue
            pid = str(page.get('confluence_page_id', ''))
            if pid in self._excluded:
                continue
            updated_str = page.get('updated_at')
            if not updated_str:
                continue
            try:
                updated = datetime.fromisoformat(updated_str.replace('Z', '+00:00'))
                updated = updated.replace(tzinfo=None)
            except (ValueError, TypeError):
                continue
            if updated < cutoff:
                entry = dict(page)
                if metadata_store:
                    meta = metadata_store.get(page.get('space_key', ''),
                                              str(page.get('confluence_page_id', '')))
                    if meta.get('local_status') == 'archived':
                        continue
                    entry.update(meta)
                stale.append(entry)
        stale.sort(key=lambda p: p.get('updated_at') or '')
        return stale

    def get_stats(self, metadata_store=None):
        """Compute dashboard statistics.

        Page-scoped metrics (total_pages, space_distribution, unowned_count,
        wl_count, stale_count) only count content_type == 'page'.
        Blog posts are counted separately in total_blogs.
        Uses cached result when metadata hasn't changed.
        """
        if (self._stats_cache is not None
                and metadata_store
                and not getattr(metadata_store, '_stats_dirty', True)):
            return self._stats_cache
        # Exclude postmortem subtree pages from stats
        all_items = [p for p in self._index.values()
                     if str(p.get('confluence_page_id', '')) not in self._excluded]
        now = datetime.utcnow()
        stale_cutoff = now - timedelta(days=self.stale_threshold_days)
        review_cutoff = now - timedelta(days=self.review_age_days)
        seven_days_ago = now - timedelta(days=7)

        priority_counter = Counter()
        category_counter = Counter()
        domain_counter = Counter()
        status_counter = Counter()
        space_counter = Counter()
        label_counter = Counter()
        team_counter = Counter()
        review_reason_counter = Counter()
        wl_count = 0
        stale_count = 0
        older_than_one_year = 0
        review_required_count = 0
        unowned_count = 0
        recently_updated = 0
        updated_at_unknown = 0
        total_pages = 0
        total_blogs = 0

        for item in all_items:
            pid = str(item.get('confluence_page_id', ''))
            sk = item.get('space_key', '')
            ct = item.get('content_type', 'page')
            meta = {}
            if metadata_store:
                meta = metadata_store.get(sk, pid)

            if meta.get('local_status') == 'archived':
                continue

            is_page = ct != 'blogpost'

            if is_page:
                total_pages += 1
                space_counter[sk] += 1
            else:
                total_blogs += 1

            if meta.get('priority'):
                priority_counter[meta['priority']] += 1
            if meta.get('category'):
                category_counter[meta['category']] += 1
            if meta.get('domain'):
                domain_counter[meta['domain']] += 1
            if meta.get('team'):
                team_counter[meta['team']] += 1
            for lbl in item.get('labels', []):
                label_counter[lbl] += 1

            if is_page:
                status_counter[meta.get('local_status', 'imported')] += 1
                if not meta.get('owner'):
                    unowned_count += 1
                if meta.get('flag_label_missing'):
                    wl_count += 1

            updated_str = item.get('updated_at')
            if updated_str:
                try:
                    updated = datetime.fromisoformat(updated_str.replace('Z', '+00:00'))
                    updated = updated.replace(tzinfo=None)
                    if is_page and updated < stale_cutoff:
                        stale_count += 1
                    if is_page and updated < review_cutoff:
                        older_than_one_year += 1
                    if updated > seven_days_ago:
                        recently_updated += 1
                except (ValueError, TypeError):
                    if is_page:
                        updated_at_unknown += 1
            elif is_page:
                updated_at_unknown += 1

            if is_page:
                reasons = meta.get('review_reasons') or []
                if reasons:
                    review_required_count += 1
                    for r in reasons:
                        review_reason_counter[r] += 1

        result = {
            'total_pages': total_pages,
            'total_runbooks': total_pages,
            'total_blogs': total_blogs,
            'space_distribution': dict(space_counter),
            'priority_distribution': dict(priority_counter),
            'category_distribution': dict(category_counter),
            'domain_distribution': dict(domain_counter),
            'status_distribution': dict(status_counter),
            'migration_distribution': dict(status_counter),
            'team_distribution': dict(team_counter),
            'label_distribution': dict(label_counter.most_common(30)),
            'review_reason_distribution': dict(review_reason_counter),
            'stale_count': stale_count,
            'older_than_one_year': older_than_one_year,
            'review_required_count': review_required_count,
            'unowned_count': unowned_count,
            'recently_updated': recently_updated,
            'updated_at_unknown': updated_at_unknown,
            'wl_count': wl_count,
        }
        self._stats_cache = result
        if metadata_store:
            metadata_store._stats_dirty = False
        return result
