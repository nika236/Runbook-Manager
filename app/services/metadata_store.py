"""Application-owned metadata store.

Reads and writes local metadata (priority, owner, status, WL flags, etc.) to
durable JSON files in data/metadata/{space_key}/{page_id}.json.

This module never contacts Confluence.
All writes are local-only, atomic (temp file + rename), and logged to the audit trail.
"""

import json
import logging
import os
import tempfile
import threading
from datetime import datetime
from pathlib import Path

logger = logging.getLogger(__name__)

METADATA_FIELDS = {
    'category', 'domain', 'priority', 'owner', 'reviewer', 'team',
    'local_status', 'review_date', 'notes', 'related_pages', 'tags',
    'sync_status', 'wl_classification',
    'flag_label_missing', 'flag_domain_missing',
    'flag_taxonomy_unmapped', 'flag_classification_ambiguous',
    'review_reasons', 'review_term_matches',
    'detected_priorities', 'priority_conflict',
    'priority_source', 'priority_source_mismatch',
    'priority_manually_assigned', 'priority_matches',
    'domain_candidates', 'domain_conflict',
    'classification_version', 'classification_timestamp',
    # Team classification fields (v2.0)
    'classification_status', 'classification_reason',
    'previous_domain', 'previous_team',
    'detected_teams', 'team_detection_status',
    'classification_evidence',
    # Exclusion fields
    'exclusion_reason', 'exclusion_root_page_id',
}

DEFAULT_METADATA = {
    'category': None,
    'domain': None,
    'priority': None,
    'owner': None,
    'reviewer': None,
    'team': None,
    'local_status': 'imported',
    'review_date': None,
    'notes': None,
    'related_pages': [],
    'tags': [],
    'sync_status': 'synced',
    'wl_classification': None,
    'flag_label_missing': None,
    'flag_domain_missing': None,
    'flag_taxonomy_unmapped': None,
    'flag_classification_ambiguous': False,
    'review_reasons': [],
    'review_term_matches': [],
    'detected_priorities': [],
    'priority_conflict': False,
    'priority_source': None,
    'priority_source_mismatch': False,
    'priority_manually_assigned': False,
    'priority_matches': [],
    'domain_candidates': [],
    'domain_conflict': False,
    'classification_version': None,
    'classification_timestamp': None,
    # Team classification fields (v2.0)
    'classification_status': None,
    'classification_reason': None,
    'previous_domain': None,
    'previous_team': None,
    'detected_teams': [],
    'team_detection_status': None,
    'classification_evidence': [],
    # Exclusion fields
    'exclusion_reason': None,
    'exclusion_root_page_id': None,
}


def _atomic_write_json(path, data):
    """Write JSON to a file atomically using temp file + os.replace."""
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


class MetadataStore:
    """Manages application-owned page metadata in local JSON files."""

    def __init__(self, data_dir):
        self.data_dir = Path(data_dir)
        self.metadata_dir = self.data_dir / 'metadata'
        self.audit_path = self.data_dir / 'audit' / 'log.jsonl'
        self._lock = threading.Lock()
        self._cache = {}
        self._cache_loaded = False
        self._stats_dirty = True

    def _ensure_dirs(self, space_key):
        (self.metadata_dir / space_key).mkdir(parents=True, exist_ok=True)
        self.audit_path.parent.mkdir(parents=True, exist_ok=True)

    def _meta_path(self, space_key, page_id):
        return self.metadata_dir / space_key / f'{page_id}.json'

    def load_cache(self, force=False):
        """Pre-load all metadata files into memory.

        Called at startup and after external scripts modify files on disk.
        Pass force=True to reload even if already loaded.
        """
        if self._cache_loaded and not force:
            return
        self._cache.clear()
        count = 0
        if self.metadata_dir.exists():
            for space_dir in self.metadata_dir.iterdir():
                if not space_dir.is_dir():
                    continue
                sk = space_dir.name
                for meta_file in space_dir.glob('*.json'):
                    pid = meta_file.stem
                    try:
                        data = json.loads(meta_file.read_text(encoding='utf-8'))
                        merged = dict(DEFAULT_METADATA)
                        merged.update(data)
                        self._cache[(sk, pid)] = merged
                        count += 1
                    except (json.JSONDecodeError, OSError) as e:
                        logger.warning('Failed to cache metadata %s: %s', meta_file, e)
        self._cache_loaded = True
        self._stats_dirty = True
        logger.info('Metadata cache loaded: %d records', count)

    def get(self, space_key, page_id):
        """Load metadata for a page, returning defaults if not found."""
        key = (space_key, str(page_id))
        if self._cache_loaded:
            cached = self._cache.get(key)
            if cached is not None:
                return dict(cached)
            return dict(DEFAULT_METADATA)

        path = self._meta_path(space_key, page_id)
        if path.exists():
            try:
                data = json.loads(path.read_text(encoding='utf-8'))
                merged = dict(DEFAULT_METADATA)
                merged.update(data)
                return merged
            except (json.JSONDecodeError, OSError) as e:
                logger.warning('Failed to read metadata %s: %s', path, e)
        return dict(DEFAULT_METADATA)

    def update(self, space_key, page_id, fields, user=None):
        """Update metadata fields for a page. Only known fields are written.

        Returns the updated metadata dict.
        """
        with self._lock:
            current = self.get(space_key, page_id)
            changes = {}

            for field in METADATA_FIELDS:
                if field in fields and fields[field] != current.get(field):
                    changes[field] = {'old': current.get(field), 'new': fields[field]}
                    current[field] = fields[field]

            if not changes:
                return current

            self._ensure_dirs(space_key)
            _atomic_write_json(self._meta_path(space_key, page_id), current)
            self._cache[(space_key, str(page_id))] = dict(current)
            self._stats_dirty = True
            self._write_audit(space_key, page_id, 'metadata_update', changes, user)

        return current

    def create_defaults(self, space_key, page_id):
        """Create a default metadata file for a newly imported page."""
        path = self._meta_path(space_key, page_id)
        if path.exists():
            return
        self._ensure_dirs(space_key)
        _atomic_write_json(path, DEFAULT_METADATA)
        self._cache[(space_key, str(page_id))] = dict(DEFAULT_METADATA)
        self._stats_dirty = True

    def set_sync_status(self, space_key, page_id, status):
        """Update only the sync_status field."""
        self.update(space_key, page_id, {'sync_status': status}, user='sync_service')

    def set_wl_flags(self, space_key, page_id, flags, user='wl_classifier'):
        """Update WL classification flags without overwriting other metadata."""
        wl_fields = {}
        for key in ('flag_label_missing', 'flag_domain_missing',
                     'flag_taxonomy_unmapped', 'flag_classification_ambiguous',
                     'wl_classification'):
            if key in flags:
                wl_fields[key] = flags[key]
        if wl_fields:
            self.update(space_key, page_id, wl_fields, user=user)

    def bulk_update(self, items, fields, user=None):
        """Update metadata for multiple pages.

        Args:
            items: list of (space_key, page_id) tuples
            fields: dict of fields to update
            user: optional user identifier for audit

        Returns:
            dict with 'updated' and 'errors' lists
        """
        updated = []
        errors = []
        for space_key, page_id in items:
            try:
                self.update(space_key, page_id, fields, user=user)
                updated.append(page_id)
            except Exception as e:
                logger.error('Failed to update metadata for %s/%s: %s', space_key, page_id, e)
                errors.append({'page_id': page_id, 'error': str(e)})
        return {'updated': updated, 'errors': errors, 'updated_count': len(updated)}

    # ------------------------------------------------------------------
    # Audit log
    # ------------------------------------------------------------------

    def _write_audit(self, space_key, page_id, action, details, user=None):
        """Append an entry to the audit log (JSONL format)."""
        entry = {
            'timestamp': datetime.utcnow().isoformat() + 'Z',
            'space_key': space_key,
            'page_id': str(page_id),
            'action': action,
            'details': details,
            'user': user,
        }
        try:
            self.audit_path.parent.mkdir(parents=True, exist_ok=True)
            with open(self.audit_path, 'a', encoding='utf-8') as f:
                f.write(json.dumps(entry, default=str) + '\n')
        except OSError as e:
            logger.error('Failed to write audit log: %s', e)

    def get_recent_activity(self, limit=50):
        """Read the most recent audit log entries."""
        if not self.audit_path.exists():
            return []
        entries = []
        try:
            with open(self.audit_path, 'r', encoding='utf-8') as f:
                for line in f:
                    line = line.strip()
                    if line:
                        try:
                            entries.append(json.loads(line))
                        except json.JSONDecodeError:
                            continue
        except OSError:
            return []
        entries.sort(key=lambda e: e.get('timestamp', ''), reverse=True)
        return entries[:limit]
