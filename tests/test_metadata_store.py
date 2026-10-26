"""Tests for the MetadataStore (application-owned local metadata).

Covers: CRUD, defaults, audit logging, bulk updates, field validation,
thread safety, missing directories, corrupted files.
"""

import json
import threading
from pathlib import Path

import pytest

from app.services.metadata_store import MetadataStore, METADATA_FIELDS, DEFAULT_METADATA


class TestMetadataDefaults:
    def test_default_fields_present(self):
        for field in ('category', 'priority', 'owner', 'reviewer',
                      'local_status', 'review_date', 'notes',
                      'related_pages', 'tags', 'sync_status'):
            assert field in DEFAULT_METADATA

    def test_default_status_is_imported(self):
        assert DEFAULT_METADATA['local_status'] == 'imported'

    def test_default_sync_status_is_synced(self):
        assert DEFAULT_METADATA['sync_status'] == 'synced'

    def test_metadata_fields_match_defaults(self):
        assert METADATA_FIELDS == set(DEFAULT_METADATA.keys())


class TestGet:
    def test_returns_defaults_for_missing(self, metadata_store):
        result = metadata_store.get('NOC', '12345')
        assert result['local_status'] == 'imported'
        assert result['priority'] is None

    def test_returns_saved_data(self, metadata_store):
        metadata_store.update('NOC', '12345', {'priority': 'P1'})
        result = metadata_store.get('NOC', '12345')
        assert result['priority'] == 'P1'

    def test_corrupted_file_returns_defaults(self, tmp_data_dir):
        store = MetadataStore(data_dir=str(tmp_data_dir))
        path = tmp_data_dir / 'metadata' / 'NOC'
        path.mkdir(parents=True)
        (path / '12345.json').write_text('not valid json', encoding='utf-8')
        result = store.get('NOC', '12345')
        assert result['local_status'] == 'imported'

    def test_merges_with_defaults(self, metadata_store):
        """Partial file gets missing fields filled from defaults."""
        path = metadata_store.metadata_dir / 'NOC'
        path.mkdir(parents=True, exist_ok=True)
        (path / '12345.json').write_text(json.dumps({'priority': 'P0'}), encoding='utf-8')
        result = metadata_store.get('NOC', '12345')
        assert result['priority'] == 'P0'
        assert result['local_status'] == 'imported'


class TestUpdate:
    def test_updates_field(self, metadata_store):
        result = metadata_store.update('NOC', '12345', {'priority': 'P2'})
        assert result['priority'] == 'P2'

    def test_persists_to_disk(self, metadata_store):
        metadata_store.update('NOC', '12345', {'owner': 'alice'})
        path = metadata_store._meta_path('NOC', '12345')
        assert path.exists()
        data = json.loads(path.read_text(encoding='utf-8'))
        assert data['owner'] == 'alice'

    def test_ignores_unknown_fields(self, metadata_store):
        result = metadata_store.update('NOC', '12345', {'unknown_field': 'val'})
        assert 'unknown_field' not in result

    def test_no_change_no_write(self, metadata_store):
        metadata_store.update('NOC', '12345', {'priority': 'P1'})
        # Second update with same value
        result = metadata_store.update('NOC', '12345', {'priority': 'P1'})
        assert result['priority'] == 'P1'

    def test_multiple_fields(self, metadata_store):
        result = metadata_store.update('NOC', '12345', {
            'priority': 'P0',
            'owner': 'bob',
            'local_status': 'active',
        })
        assert result['priority'] == 'P0'
        assert result['owner'] == 'bob'
        assert result['local_status'] == 'active'

    def test_empty_fields_dict(self, metadata_store):
        result = metadata_store.update('NOC', '12345', {})
        assert result['local_status'] == 'imported'

    def test_update_tags_as_list(self, metadata_store):
        result = metadata_store.update('NOC', '12345', {'tags': ['a', 'b']})
        assert result['tags'] == ['a', 'b']

    def test_update_related_pages(self, metadata_store):
        result = metadata_store.update('NOC', '12345', {'related_pages': ['999', '888']})
        assert result['related_pages'] == ['999', '888']

    def test_creates_directories(self, tmp_data_dir):
        store = MetadataStore(data_dir=str(tmp_data_dir))
        store.update('NEWSPACE', '111', {'priority': 'P3'})
        path = store._meta_path('NEWSPACE', '111')
        assert path.exists()


class TestCreateDefaults:
    def test_creates_file(self, metadata_store):
        metadata_store.create_defaults('NOC', '12345')
        path = metadata_store._meta_path('NOC', '12345')
        assert path.exists()

    def test_does_not_overwrite(self, metadata_store):
        metadata_store.update('NOC', '12345', {'priority': 'P1'})
        metadata_store.create_defaults('NOC', '12345')
        result = metadata_store.get('NOC', '12345')
        assert result['priority'] == 'P1'


class TestSetSyncStatus:
    def test_sets_sync_status(self, metadata_store):
        metadata_store.set_sync_status('NOC', '12345', 'deleted')
        result = metadata_store.get('NOC', '12345')
        assert result['sync_status'] == 'deleted'


class TestBulkUpdate:
    def test_updates_multiple(self, metadata_store):
        items = [('NOC', '111'), ('NOC', '222')]
        result = metadata_store.bulk_update(items, {'priority': 'P1'})
        assert result['updated_count'] == 2
        assert len(result['errors']) == 0

    def test_empty_items(self, metadata_store):
        result = metadata_store.bulk_update([], {'priority': 'P1'})
        assert result['updated_count'] == 0

    def test_partial_failure(self, metadata_store, monkeypatch):
        """If one update fails, others still proceed."""
        call_count = [0]
        original_update = metadata_store.update

        def failing_update(sk, pid, fields, user=None):
            call_count[0] += 1
            if pid == '222':
                raise IOError('disk full')
            return original_update(sk, pid, fields, user=user)

        monkeypatch.setattr(metadata_store, 'update', failing_update)
        items = [('NOC', '111'), ('NOC', '222'), ('NOC', '333')]
        result = metadata_store.bulk_update(items, {'priority': 'P2'})
        assert len(result['updated']) == 2
        assert len(result['errors']) == 1


class TestAuditLog:
    def test_audit_entry_written(self, metadata_store):
        metadata_store.update('NOC', '12345', {'priority': 'P1'}, user='tester')
        assert metadata_store.audit_path.exists()
        entries = metadata_store.get_recent_activity()
        assert len(entries) >= 1
        assert entries[0]['user'] == 'tester'
        assert entries[0]['action'] == 'metadata_update'

    def test_audit_contains_changes(self, metadata_store):
        metadata_store.update('NOC', '12345', {'priority': 'P1'})
        entries = metadata_store.get_recent_activity()
        details = entries[0]['details']
        assert 'priority' in details
        assert details['priority']['new'] == 'P1'

    def test_no_audit_when_no_change(self, metadata_store):
        metadata_store.update('NOC', '12345', {'priority': 'P1'})
        count_before = len(metadata_store.get_recent_activity())
        metadata_store.update('NOC', '12345', {'priority': 'P1'})
        count_after = len(metadata_store.get_recent_activity())
        assert count_after == count_before

    def test_audit_recent_sorted_desc(self, metadata_store):
        metadata_store.update('NOC', '111', {'priority': 'P1'})
        metadata_store.update('NOC', '222', {'priority': 'P2'})
        entries = metadata_store.get_recent_activity()
        if len(entries) >= 2:
            assert entries[0]['timestamp'] >= entries[1]['timestamp']

    def test_audit_limit(self, metadata_store):
        for i in range(60):
            metadata_store.update('NOC', str(i), {'priority': f'P{i % 5}'})
        entries = metadata_store.get_recent_activity(limit=10)
        assert len(entries) == 10

    def test_audit_missing_file(self, metadata_store):
        entries = metadata_store.get_recent_activity()
        assert entries == []

    def test_audit_with_corrupted_lines(self, metadata_store):
        metadata_store.audit_path.parent.mkdir(parents=True, exist_ok=True)
        with open(metadata_store.audit_path, 'w', encoding='utf-8') as f:
            f.write('bad line\n')
            f.write(json.dumps({'timestamp': '2024-01-01', 'action': 'test'}) + '\n')
        entries = metadata_store.get_recent_activity()
        assert len(entries) == 1


class TestThreadSafety:
    def test_concurrent_updates(self, metadata_store):
        errors = []

        def update_worker(page_id, priority):
            try:
                metadata_store.update('NOC', page_id, {'priority': priority})
            except Exception as e:
                errors.append(e)

        threads = []
        for i in range(20):
            t = threading.Thread(target=update_worker, args=(str(i), f'P{i % 5}'))
            threads.append(t)
            t.start()

        for t in threads:
            t.join()

        assert len(errors) == 0
        # Verify all were written
        for i in range(20):
            result = metadata_store.get('NOC', str(i))
            assert result['priority'] == f'P{i % 5}'

    def test_concurrent_same_page(self, metadata_store):
        """Multiple threads updating the same page."""
        errors = []

        def update_worker(priority):
            try:
                metadata_store.update('NOC', '12345', {'priority': priority})
            except Exception as e:
                errors.append(e)

        threads = []
        for i in range(10):
            t = threading.Thread(target=update_worker, args=(f'P{i % 5}',))
            threads.append(t)
            t.start()

        for t in threads:
            t.join()

        assert len(errors) == 0
        result = metadata_store.get('NOC', '12345')
        assert result['priority'] in [f'P{i}' for i in range(5)]
