"""Synchronization service.

Pulls data from Confluence (read-only) and writes to the local file store.
Never sends POST/PUT/DELETE to Confluence.
"""

import json
import hashlib
import logging
import os
import tempfile
from datetime import datetime
from pathlib import Path

from app.services.confluence_client import ConfluenceClient, strip_html

logger = logging.getLogger(__name__)


def _escape_cql_string(value):
    """Escape a value for safe inclusion in a double-quoted CQL string literal."""
    return str(value).replace('\\', '\\\\').replace('"', '\\"')


def _atomic_write_json(path, data):
    """Write JSON atomically using temp file + os.replace."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp_path = tempfile.mkstemp(dir=str(path.parent), suffix='.tmp')
    try:
        with os.fdopen(fd, 'w', encoding='utf-8') as f:
            json.dump(data, f, indent=2, default=str)
        os.replace(tmp_path, str(path))
    except BaseException:
        try:
            os.unlink(tmp_path)
        except OSError:
            pass
        raise


def _atomic_write_text(path, text):
    """Write text atomically using temp file + os.replace."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp_path = tempfile.mkstemp(dir=str(path.parent), suffix='.tmp')
    try:
        with os.fdopen(fd, 'w', encoding='utf-8') as f:
            f.write(text)
        os.replace(tmp_path, str(path))
    except BaseException:
        try:
            os.unlink(tmp_path)
        except OSError:
            pass
        raise


class SyncService:
    """Orchestrates read-only sync from Confluence to local file store."""

    def __init__(self, confluence_client: ConfluenceClient, data_dir: str,
                 stale_threshold_days: int = 30):
        self.client = confluence_client
        self.data_dir = Path(data_dir)
        self.spaces_dir = self.data_dir / 'spaces'
        self.sync_dir = self.data_dir / 'sync'
        self.metadata_dir = self.data_dir / 'metadata'
        self.other_content_dir = self.data_dir / 'other-content'
        self.stale_threshold_days = stale_threshold_days

    def _ensure_dirs(self, space_key, page_id=None):
        (self.spaces_dir / space_key / 'pages').mkdir(parents=True, exist_ok=True)
        (self.spaces_dir / space_key / 'blogposts').mkdir(parents=True, exist_ok=True)
        (self.sync_dir / 'runs').mkdir(parents=True, exist_ok=True)
        (self.metadata_dir / space_key).mkdir(parents=True, exist_ok=True)
        (self.other_content_dir / space_key).mkdir(parents=True, exist_ok=True)
        if page_id:
            (self.spaces_dir / space_key / 'pages' / str(page_id)).mkdir(
                parents=True, exist_ok=True)

    def _load_sync_state(self):
        state_path = self.sync_dir / 'state.json'
        if state_path.exists():
            try:
                return json.loads(state_path.read_text(encoding='utf-8'))
            except (json.JSONDecodeError, OSError):
                pass
        return {}

    def _save_sync_state(self, state):
        self.sync_dir.mkdir(parents=True, exist_ok=True)
        _atomic_write_json(self.sync_dir / 'state.json', state)

    def _content_hash(self, html):
        return hashlib.sha256((html or '').encode('utf-8')).hexdigest()

    def _build_content_doc(self, item, space_key, content_type='page'):
        """Build a document from a Confluence API response (page or blogpost)."""
        pid = str(item.get('id', ''))
        title = item.get('title', 'Untitled')
        body_html = item.get('body', {}).get('storage', {}).get('value', '')
        body_text = strip_html(body_html)

        ancestors = []
        for a in item.get('ancestors', []):
            ancestors.append({'id': str(a.get('id', '')), 'title': a.get('title', '')})
        parent_page_id = ancestors[-1]['id'] if ancestors else None

        children_ids = []
        children_data = item.get('children', {}).get('page', {})
        for child in children_data.get('results', []):
            children_ids.append(str(child.get('id', '')))

        labels = []
        labels_data = item.get('metadata', {}).get('labels', {})
        for lbl in labels_data.get('results', []):
            labels.append(lbl.get('name', ''))

        version_info = item.get('version', {})
        history_info = item.get('history', {})

        created_by = history_info.get('createdBy', {}).get('displayName') or \
                     history_info.get('createdBy', {}).get('username', '')
        created_at = history_info.get('createdDate')

        updated_by = version_info.get('by', {}).get('displayName') or \
                     version_info.get('by', {}).get('username', '')
        updated_at = (history_info.get('lastUpdated', {}).get('when')
                      or version_info.get('when'))

        confluence_version = version_info.get('number', 1)

        web_link = item.get('_links', {}).get('webui', '')
        base_url = self.client.base_url
        confluence_url = f'{base_url}/wiki{web_link}' if web_link else ''

        word_count = len(body_text.split()) if body_text else 0

        return {
            'confluence_page_id': pid,
            'space_key': space_key,
            'title': title,
            'content_type': content_type,
            'parent_page_id': parent_page_id,
            'ancestors': ancestors,
            'children_ids': children_ids,
            'labels': labels,
            'created_by': created_by,
            'created_at': created_at,
            'updated_by': updated_by,
            'updated_at': updated_at,
            'confluence_version': confluence_version,
            'confluence_url': confluence_url,
            'word_count': word_count,
            'content_hash': self._content_hash(body_html),
        }

    def _compute_wl_flags(self, doc, existing_meta=None):
        """Compute WL classification flags for a document."""
        labels = doc.get('labels', [])
        domain = (existing_meta or {}).get('domain')

        label_missing = len(labels) == 0
        domain_missing = domain is None or domain == ''

        # Interpretation 4: labels exist but none map to known app taxonomy
        # For now we have no taxonomy defined, so all labeled pages are unmapped
        # This will be refined once the taxonomy is established
        taxonomy_unmapped = True  # default until taxonomy is defined

        wl_class = 'wl' if label_missing else None

        return {
            'flag_label_missing': label_missing,
            'flag_domain_missing': domain_missing,
            'flag_taxonomy_unmapped': taxonomy_unmapped,
            'flag_classification_ambiguous': False,
            'wl_classification': wl_class,
        }

    def _write_content(self, doc, body_html, body_text, space_key, content_id,
                       content_type='page'):
        """Write content data files to disk."""
        if content_type == 'blogpost':
            content_dir = self.spaces_dir / space_key / 'blogposts' / str(content_id)
        else:
            content_dir = self.spaces_dir / space_key / 'pages' / str(content_id)
        content_dir.mkdir(parents=True, exist_ok=True)

        doc_filename = 'post.json' if content_type == 'blogpost' else 'page.json'
        _atomic_write_json(content_dir / doc_filename, doc)
        _atomic_write_text(content_dir / 'content.html', body_html or '')
        _atomic_write_text(content_dir / 'content.txt', body_text or '')

    def _write_revisions(self, space_key, page_id, versions):
        """Write revision history to disk."""
        revisions = []
        for v in versions:
            revisions.append({
                'version': v.get('number'),
                'by': v.get('by', {}).get('displayName', ''),
                'when': v.get('when'),
                'message': v.get('message', ''),
            })
        rev_path = self.spaces_dir / space_key / 'pages' / str(page_id) / 'revisions.json'
        _atomic_write_json(rev_path, revisions)

    def _write_restrictions(self, space_key, page_id, restrictions):
        """Write restriction data to disk."""
        path = self.spaces_dir / space_key / 'pages' / str(page_id) / 'restrictions.json'
        data = restrictions if restrictions is not None else {'accessible': False}
        _atomic_write_json(path, data)

    def _create_or_update_metadata(self, space_key, page_id, doc):
        """Create default metadata or update WL flags for a page."""
        from app.services.metadata_store import DEFAULT_METADATA
        meta_path = self.metadata_dir / space_key / f'{page_id}.json'
        meta_path.parent.mkdir(parents=True, exist_ok=True)

        existing_meta = None
        if meta_path.exists():
            try:
                existing_meta = json.loads(meta_path.read_text(encoding='utf-8'))
            except (json.JSONDecodeError, OSError):
                existing_meta = None

        wl_flags = self._compute_wl_flags(doc, existing_meta)

        if existing_meta is None:
            meta = dict(DEFAULT_METADATA)
            meta.update(wl_flags)
            _atomic_write_json(meta_path, meta)
        else:
            changed = False
            for k, v in wl_flags.items():
                if existing_meta.get(k) != v:
                    existing_meta[k] = v
                    changed = True
            if changed:
                _atomic_write_json(meta_path, existing_meta)

    def _build_tree(self, docs):
        """Build a hierarchy tree from content documents."""
        by_id = {d['confluence_page_id']: d for d in docs}
        children_map = {}
        roots = []

        for d in docs:
            pid = d['confluence_page_id']
            parent = d.get('parent_page_id')
            if parent and parent in by_id:
                children_map.setdefault(parent, []).append(pid)
            else:
                roots.append(pid)

        def build_node(pid):
            d = by_id.get(pid, {})
            node = {
                'id': pid,
                'title': d.get('title', ''),
                'children': [],
            }
            for child_id in sorted(children_map.get(pid, []),
                                   key=lambda c: by_id.get(c, {}).get('title', '')):
                node['children'].append(build_node(child_id))
            return node

        tree = []
        for rid in sorted(roots, key=lambda r: by_id.get(r, {}).get('title', '')):
            tree.append(build_node(rid))
        return tree

    def _write_space_info(self, space_key):
        """Write space.json from Confluence."""
        try:
            space_data = self.client.get_space(space_key)
            info = {
                'key': space_data.get('key', space_key),
                'name': space_data.get('name', space_key),
                'description': space_data.get('description', {}).get('plain', {}).get('value', ''),
                'homepage_id': str(space_data.get('homepage', {}).get('id', '')),
            }
        except Exception as e:
            logger.warning('Could not fetch space info for %s: %s', space_key, e)
            info = {'key': space_key, 'name': space_key}

        space_dir = self.spaces_dir / space_key
        space_dir.mkdir(parents=True, exist_ok=True)
        _atomic_write_json(space_dir / 'space.json', info)

    # ------------------------------------------------------------------
    # Content sync (pages + blog posts)
    # ------------------------------------------------------------------

    def _sync_content_type(self, space_key, content_type, old_checksums,
                           fetch_revisions, fetch_restrictions,
                           on_progress):
        """Sync all content of a specific type for a space. Returns (docs, new_checksums, stats)."""
        if content_type == 'blogpost':
            raw_items = self.client.get_all_blog_posts(space_key, on_progress=on_progress)
        else:
            raw_items = self.client.get_all_pages(space_key, on_progress=on_progress)

        logger.info('Fetched %d %ss from %s', len(raw_items), content_type, space_key)

        new_checksums = {}
        docs = []
        imported = 0
        updated = 0
        unchanged = 0
        errors = []

        for raw_item in raw_items:
            cid = str(raw_item.get('id', ''))
            try:
                body_html = raw_item.get('body', {}).get('storage', {}).get('value', '')
                body_text = strip_html(body_html)
                doc = self._build_content_doc(raw_item, space_key, content_type)
                new_hash = doc['content_hash']
                new_checksums[cid] = new_hash

                if cid not in old_checksums:
                    self._write_content(doc, body_html, body_text, space_key, cid, content_type)
                    self._create_or_update_metadata(space_key, cid, doc)
                    imported += 1
                elif old_checksums.get(cid) != new_hash:
                    self._write_content(doc, body_html, body_text, space_key, cid, content_type)
                    self._create_or_update_metadata(space_key, cid, doc)
                    updated += 1
                else:
                    unchanged += 1

                docs.append(doc)
            except Exception as e:
                logger.error('Error processing %s %s: %s', content_type, cid, e)
                errors.append({'content_id': cid, 'error': str(e)})

        if content_type == 'page' and (fetch_revisions or fetch_restrictions):
            pages_needing_extras = [p for p in raw_items
                                    if str(p.get('id', '')) in new_checksums
                                    and (str(p.get('id', '')) not in old_checksums
                                         or old_checksums.get(str(p.get('id', '')))
                                         != new_checksums.get(str(p.get('id', ''))))]
            if pages_needing_extras:
                logger.info('Fetching extras for %d changed pages...', len(pages_needing_extras))
                extras = self.client.fetch_page_extras(
                    pages_needing_extras,
                    fetch_revisions=fetch_revisions,
                    fetch_restrictions=fetch_restrictions,
                    max_workers=3,
                )
                for pid, extra in extras.items():
                    try:
                        if fetch_revisions and extra.get('revisions'):
                            self._write_revisions(space_key, pid, extra['revisions'])
                        if fetch_restrictions:
                            self._write_restrictions(space_key, pid, extra.get('restrictions'))
                    except Exception as e:
                        logger.error('Error writing extras for %s %s: %s', content_type, pid, e)

        stats = {
            'imported': imported,
            'updated': updated,
            'unchanged': unchanged,
            'errors': errors,
            'total': len(docs),
        }
        return docs, new_checksums, stats

    # ------------------------------------------------------------------
    # Public sync methods
    # ------------------------------------------------------------------

    def sync_space(self, space_key,
                   fetch_revisions=True, fetch_restrictions=True,
                   on_progress=None):
        """Full sync of a single space (pages + blog posts). Read-only from Confluence."""
        start_time = datetime.utcnow()
        state = self._load_sync_state()
        space_state = state.get(space_key, {})
        old_page_checksums = space_state.get('page_checksums', {})
        old_blog_checksums = space_state.get('blog_checksums', {})

        self._ensure_dirs(space_key)
        self._write_space_info(space_key)

        logger.info('Syncing pages from space %s...', space_key)
        page_docs, new_page_checksums, page_stats = self._sync_content_type(
            space_key, 'page', old_page_checksums,
            fetch_revisions, fetch_restrictions,
            on_progress,
        )

        logger.info('Syncing blog posts from space %s...', space_key)
        blog_docs, new_blog_checksums, blog_stats = self._sync_content_type(
            space_key, 'blogpost', old_blog_checksums,
            fetch_revisions=False, fetch_restrictions=False,
            on_progress=None,
        )

        # Flag deleted pages
        flagged_page_ids = set(old_page_checksums.keys()) - set(new_page_checksums.keys())
        for pid in flagged_page_ids:
            meta_path = self.metadata_dir / space_key / f'{pid}.json'
            if meta_path.exists():
                try:
                    meta = json.loads(meta_path.read_text(encoding='utf-8'))
                    meta['sync_status'] = 'deleted'
                    _atomic_write_json(meta_path, meta)
                except (json.JSONDecodeError, OSError):
                    pass

        flagged_blog_ids = set(old_blog_checksums.keys()) - set(new_blog_checksums.keys())
        for bid in flagged_blog_ids:
            meta_path = self.metadata_dir / space_key / f'{bid}.json'
            if meta_path.exists():
                try:
                    meta = json.loads(meta_path.read_text(encoding='utf-8'))
                    meta['sync_status'] = 'deleted'
                    _atomic_write_json(meta_path, meta)
                except (json.JSONDecodeError, OSError):
                    pass

        # Build and write hierarchy tree (pages only)
        tree = self._build_tree(page_docs)
        _atomic_write_json(self.spaces_dir / space_key / 'tree.json', tree)

        # Update sync state
        state[space_key] = {
            'last_full_sync': start_time.isoformat() + 'Z',
            'page_checksums': new_page_checksums,
            'blog_checksums': new_blog_checksums,
        }
        self._save_sync_state(state)

        end_time = datetime.utcnow()
        duration = (end_time - start_time).total_seconds()

        run_log = {
            'space_key': space_key,
            'started_at': start_time.isoformat() + 'Z',
            'completed_at': end_time.isoformat() + 'Z',
            'duration_seconds': duration,
            'pages_imported': page_stats['imported'],
            'pages_updated': page_stats['updated'],
            'pages_unchanged': page_stats['unchanged'],
            'pages_flagged_deleted': len(flagged_page_ids),
            'blogs_imported': blog_stats['imported'],
            'blogs_updated': blog_stats['updated'],
            'blogs_total': blog_stats['total'],
            'errors': page_stats['errors'] + blog_stats['errors'],
            'total_pages': page_stats['total'],
            'total_blogs': blog_stats['total'],
        }
        run_path = (self.sync_dir / 'runs' /
                    f'{start_time.strftime("%Y%m%dT%H%M%S")}_{space_key}.json')
        run_path.parent.mkdir(parents=True, exist_ok=True)
        _atomic_write_json(run_path, run_log)

        logger.info('Sync complete for %s: %d pages (%d imported, %d updated), '
                     '%d blogs, %d flagged deleted, %d errors in %.1fs',
                     space_key, page_stats['total'], page_stats['imported'],
                     page_stats['updated'], blog_stats['total'],
                     len(flagged_page_ids), len(page_stats['errors'] + blog_stats['errors']),
                     duration)

        return run_log

    def sync_incremental(self, space_keys, since_timestamp=None):
        """Incremental sync using CQL lastmodified query.

        Falls back to full sync if no timestamp is available.
        """
        state = self._load_sync_state()

        if since_timestamp is None:
            timestamps = []
            for sk in space_keys:
                ts = state.get(sk, {}).get('last_full_sync')
                if ts:
                    timestamps.append(ts)
            if timestamps:
                since_timestamp = min(timestamps)

        if not since_timestamp:
            logger.info('No previous sync timestamp; falling back to full sync.')
            return self.sync_all(space_keys)

        space_list = ','.join(f'"{_escape_cql_string(sk)}"' for sk in space_keys)
        cql = (f'space IN ({space_list}) AND lastmodified >= "{_escape_cql_string(since_timestamp)}" '
               f'AND type IN ("page","blogpost")')

        logger.info('Incremental sync with CQL: %s', cql)
        try:
            results = self.client.search_cql_all(cql)
        except Exception as e:
            logger.error('CQL search failed, falling back to full sync: %s', e)
            return self.sync_all(space_keys)

        updated_count = 0
        errors = []
        for result in results:
            content = result.get('content', result)
            cid = str(content.get('id', ''))
            space_key = content.get('space', {}).get('key', '')
            if not space_key or not cid:
                continue

            try:
                page_data = self.client.get_page(cid)
                content_type = page_data.get('type', 'page')
                body_html = page_data.get('body', {}).get('storage', {}).get('value', '')
                body_text = strip_html(body_html)
                doc = self._build_content_doc(page_data, space_key, content_type)
                self._write_content(doc, body_html, body_text, space_key, cid, content_type)
                self._create_or_update_metadata(space_key, cid, doc)

                ck_key = 'blog_checksums' if content_type == 'blogpost' else 'page_checksums'
                if space_key not in state:
                    state[space_key] = {}
                if ck_key not in state[space_key]:
                    state[space_key][ck_key] = {}
                state[space_key][ck_key][cid] = doc['content_hash']

                updated_count += 1
            except Exception as e:
                logger.error('Failed to sync content %s: %s', cid, e)
                errors.append({'content_id': cid, 'error': str(e)})

        now = datetime.utcnow().isoformat() + 'Z'
        for sk in space_keys:
            if sk in state:
                state[sk]['last_incremental_sync'] = now
        self._save_sync_state(state)

        return [{
            'type': 'incremental',
            'updated': updated_count,
            'errors': errors,
            'since': since_timestamp,
        }]

    def sync_all(self, space_keys, **kwargs):
        """Sync all configured spaces. Returns list of run logs."""
        results = []
        for space_key in space_keys:
            try:
                result = self.sync_space(space_key, **kwargs)
                results.append(result)
            except Exception as e:
                logger.error('Failed to sync space %s: %s', space_key, e)
                results.append({
                    'space_key': space_key,
                    'error': str(e),
                    'total_pages': 0,
                    'total_blogs': 0,
                })
        return results

    def get_sync_status(self):
        """Return current sync state and recent runs."""
        state = self._load_sync_state()
        runs_dir = self.sync_dir / 'runs'
        recent_runs = []
        if runs_dir.exists():
            run_files = sorted(runs_dir.glob('*.json'), reverse=True)[:10]
            for rf in run_files:
                try:
                    recent_runs.append(json.loads(rf.read_text(encoding='utf-8')))
                except (json.JSONDecodeError, OSError):
                    pass

        last_sync_time = None
        total_pages = 0
        total_blogs = 0
        for sk, sk_state in state.items():
            ts = sk_state.get('last_full_sync')
            if ts and (last_sync_time is None or ts > last_sync_time):
                last_sync_time = ts
            total_pages += len(sk_state.get('page_checksums', {}))
            total_blogs += len(sk_state.get('blog_checksums', {}))

        return {
            'state': state,
            'recent_runs': recent_runs,
            'last_sync_time': last_sync_time,
            'total_runbooks': total_pages,
            'total_pages': total_pages,
            'total_blogs': total_blogs,
        }
