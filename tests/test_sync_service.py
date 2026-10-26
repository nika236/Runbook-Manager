"""Tests for the SyncService (read-only pull from Confluence to local store).

Covers: full sync, incremental sync, idempotency, content hashing,
page document building, tree generation, revision writing,
deleted page flagging, sync state persistence, error handling.
"""

import json
from datetime import datetime
from pathlib import Path
from unittest.mock import MagicMock, patch, PropertyMock

import pytest
import requests

from app.services.sync_service import SyncService, _escape_cql_string
from app.services.confluence_client import ConfluenceClient
from tests.conftest import (
    make_confluence_page, make_pages_response, make_space_response,
)


def _setup_mock_sync(confluence_client, pages, space_key='NOC'):
    """Wire up the mocked client to return pages during sync."""
    # get_space
    confluence_client.get_space = MagicMock(return_value=make_space_response(key=space_key))

    # get_all_pages
    confluence_client.get_all_pages = MagicMock(return_value=pages)

    # get_all_blog_posts (empty by default)
    confluence_client.get_all_blog_posts = MagicMock(return_value=[])

    # get_pages (used by get_all_pages internally, but since get_all_pages is mocked
    # we don't need this for most tests)
    confluence_client.get_pages = MagicMock(
        return_value=make_pages_response(pages, size=len(pages)))

    # fetch_page_extras
    extras = {}
    for p in pages:
        pid = str(p['id'])
        extras[pid] = {
            'revisions': [{'number': 1, 'by': {'displayName': 'admin'}, 'when': '2024-01-01'}],
            'restrictions': None,
        }
    confluence_client.fetch_page_extras = MagicMock(return_value=extras)


# ===================================================================
# Building page documents
# ===================================================================

class TestBuildPageDoc:
    def test_basic_fields(self, sync_service):
        page = make_confluence_page(page_id='100', title='Test', space_key='NOC')
        doc = sync_service._build_content_doc(page, 'NOC')
        assert doc['confluence_page_id'] == '100'
        assert doc['title'] == 'Test'
        assert doc['space_key'] == 'NOC'

    def test_content_hash_computed(self, sync_service):
        page = make_confluence_page(body_html='<p>Hello</p>')
        doc = sync_service._build_content_doc(page, 'NOC')
        assert doc['content_hash'] is not None
        assert len(doc['content_hash']) == 64  # SHA-256 hex

    def test_same_content_same_hash(self, sync_service):
        page1 = make_confluence_page(body_html='<p>Same</p>')
        page2 = make_confluence_page(body_html='<p>Same</p>')
        doc1 = sync_service._build_content_doc(page1, 'NOC')
        doc2 = sync_service._build_content_doc(page2, 'NOC')
        assert doc1['content_hash'] == doc2['content_hash']

    def test_different_content_different_hash(self, sync_service):
        page1 = make_confluence_page(body_html='<p>A</p>')
        page2 = make_confluence_page(body_html='<p>B</p>')
        doc1 = sync_service._build_content_doc(page1, 'NOC')
        doc2 = sync_service._build_content_doc(page2, 'NOC')
        assert doc1['content_hash'] != doc2['content_hash']

    def test_ancestors_extracted(self, sync_service):
        page = make_confluence_page(ancestors=[
            {'id': '1', 'title': 'Root'},
            {'id': '2', 'title': 'Parent'},
        ])
        doc = sync_service._build_content_doc(page, 'NOC')
        assert len(doc['ancestors']) == 2
        assert doc['parent_page_id'] == '2'

    def test_no_ancestors(self, sync_service):
        page = make_confluence_page(ancestors=[])
        doc = sync_service._build_content_doc(page, 'NOC')
        assert doc['parent_page_id'] is None
        assert doc['ancestors'] == []

    def test_labels_extracted(self, sync_service):
        page = make_confluence_page(labels=['prod', 'alert'])
        doc = sync_service._build_content_doc(page, 'NOC')
        assert 'prod' in doc['labels']
        assert 'alert' in doc['labels']

    def test_empty_body(self, sync_service):
        page = make_confluence_page(body_html='')
        doc = sync_service._build_content_doc(page, 'NOC')
        assert doc['word_count'] == 0

    def test_unicode_title(self, sync_service):
        page = make_confluence_page(title='Ünïcödé Тест 中文')
        doc = sync_service._build_content_doc(page, 'NOC')
        assert doc['title'] == 'Ünïcödé Тест 中文'

    def test_confluence_url_built(self, sync_service):
        page = make_confluence_page()
        doc = sync_service._build_content_doc(page, 'NOC')
        assert 'https://test.atlassian.net/wiki' in doc['confluence_url']

    def test_missing_webui_link(self, sync_service):
        page = make_confluence_page()
        page['_links'] = {}
        doc = sync_service._build_content_doc(page, 'NOC')
        assert doc['confluence_url'] == ''

    def test_version_number(self, sync_service):
        page = make_confluence_page(version=5)
        doc = sync_service._build_content_doc(page, 'NOC')
        assert doc['confluence_version'] == 5


# ===================================================================
# Sync state management
# ===================================================================

class TestSyncState:
    def test_empty_state(self, sync_service):
        state = sync_service._load_sync_state()
        assert state == {}

    def test_save_and_load(self, sync_service):
        sync_service._save_sync_state({'NOC': {'page_checksums': {'1': 'abc'}}})
        state = sync_service._load_sync_state()
        assert state['NOC']['page_checksums']['1'] == 'abc'

    def test_corrupted_state_returns_empty(self, sync_service):
        sync_service.sync_dir.mkdir(parents=True, exist_ok=True)
        (sync_service.sync_dir / 'state.json').write_text('bad', encoding='utf-8')
        state = sync_service._load_sync_state()
        assert state == {}


# ===================================================================
# Full sync
# ===================================================================

class TestSyncSpace:
    def test_initial_sync(self, sync_service, confluence_client):
        pages = [
            make_confluence_page(page_id='1', title='Page 1'),
            make_confluence_page(page_id='2', title='Page 2'),
        ]
        _setup_mock_sync(confluence_client, pages)

        result = sync_service.sync_space('NOC')
        assert result['pages_imported'] == 2
        assert result['pages_updated'] == 0
        assert result['pages_unchanged'] == 0
        assert result['total_pages'] == 2

    def test_files_written(self, sync_service, confluence_client):
        pages = [make_confluence_page(page_id='1', title='Page 1')]
        _setup_mock_sync(confluence_client, pages)

        sync_service.sync_space('NOC')
        page_dir = sync_service.spaces_dir / 'NOC' / 'pages' / '1'
        assert (page_dir / 'page.json').exists()
        assert (page_dir / 'content.html').exists()
        assert (page_dir / 'content.txt').exists()

    def test_space_json_written(self, sync_service, confluence_client):
        pages = [make_confluence_page()]
        _setup_mock_sync(confluence_client, pages)
        sync_service.sync_space('NOC')
        assert (sync_service.spaces_dir / 'NOC' / 'space.json').exists()

    def test_tree_json_written(self, sync_service, confluence_client):
        pages = [make_confluence_page()]
        _setup_mock_sync(confluence_client, pages)
        sync_service.sync_space('NOC')
        assert (sync_service.spaces_dir / 'NOC' / 'tree.json').exists()

    def test_sync_state_saved(self, sync_service, confluence_client):
        pages = [make_confluence_page(page_id='1')]
        _setup_mock_sync(confluence_client, pages)
        sync_service.sync_space('NOC')
        state = sync_service._load_sync_state()
        assert 'NOC' in state
        assert '1' in state['NOC']['page_checksums']

    def test_run_log_written(self, sync_service, confluence_client):
        pages = [make_confluence_page()]
        _setup_mock_sync(confluence_client, pages)
        sync_service.sync_space('NOC')
        runs_dir = sync_service.sync_dir / 'runs'
        assert runs_dir.exists()
        run_files = list(runs_dir.glob('*.json'))
        assert len(run_files) >= 1

    def test_metadata_defaults_created(self, sync_service, confluence_client):
        pages = [make_confluence_page(page_id='999')]
        _setup_mock_sync(confluence_client, pages)
        sync_service.sync_space('NOC')
        meta_path = sync_service.metadata_dir / 'NOC' / '999.json'
        assert meta_path.exists()

    def test_idempotent_sync(self, sync_service, confluence_client):
        """Running sync twice with same data produces unchanged on second run."""
        pages = [make_confluence_page(page_id='1', body_html='<p>same</p>')]
        _setup_mock_sync(confluence_client, pages)

        result1 = sync_service.sync_space('NOC')
        assert result1['pages_imported'] == 1

        result2 = sync_service.sync_space('NOC')
        assert result2['pages_imported'] == 0
        assert result2['pages_unchanged'] == 1

    def test_content_change_detected(self, sync_service, confluence_client):
        page_v1 = make_confluence_page(page_id='1', body_html='<p>v1</p>')
        _setup_mock_sync(confluence_client, [page_v1])
        sync_service.sync_space('NOC')

        page_v2 = make_confluence_page(page_id='1', body_html='<p>v2 changed</p>')
        _setup_mock_sync(confluence_client, [page_v2])
        result = sync_service.sync_space('NOC')
        assert result['pages_updated'] == 1

    def test_deleted_pages_flagged(self, sync_service, confluence_client):
        # First sync with two pages
        pages = [
            make_confluence_page(page_id='1'),
            make_confluence_page(page_id='2'),
        ]
        _setup_mock_sync(confluence_client, pages)
        sync_service.sync_space('NOC')

        # Create metadata for page 2
        meta_dir = sync_service.metadata_dir / 'NOC'
        meta_dir.mkdir(parents=True, exist_ok=True)
        (meta_dir / '2.json').write_text(json.dumps({'sync_status': 'synced'}), encoding='utf-8')

        # Second sync without page 2
        _setup_mock_sync(confluence_client, [make_confluence_page(page_id='1')])
        result = sync_service.sync_space('NOC')
        assert result['pages_flagged_deleted'] == 1

        # Check metadata updated
        meta = json.loads((meta_dir / '2.json').read_text(encoding='utf-8'))
        assert meta['sync_status'] == 'deleted'

    def test_empty_space(self, sync_service, confluence_client):
        _setup_mock_sync(confluence_client, [])
        result = sync_service.sync_space('EMPTY')
        assert result['total_pages'] == 0

    def test_page_processing_error_recorded(self, sync_service, confluence_client):
        """If a page fails to process, it's recorded but sync continues."""
        pages = [
            make_confluence_page(page_id='1'),
            make_confluence_page(page_id='2'),
        ]
        _setup_mock_sync(confluence_client, pages)

        # Make the second page cause an error during build
        original_build = sync_service._build_content_doc

        def failing_build(page, space_key, content_type='page'):
            if str(page.get('id', '')) == '2':
                raise ValueError('bad page')
            return original_build(page, space_key, content_type)

        sync_service._build_content_doc = failing_build
        result = sync_service.sync_space('NOC')
        assert len(result['errors']) == 1
        assert result['errors'][0]['content_id'] == '2'


# ===================================================================
# Revision, restriction writing
# ===================================================================

class TestWriteRevisions:
    def test_writes_revisions(self, sync_service):
        versions = [
            {'number': 1, 'by': {'displayName': 'alice'}, 'when': '2024-01-01', 'message': 'init'},
            {'number': 2, 'by': {'displayName': 'bob'}, 'when': '2024-02-01', 'message': 'edit'},
        ]
        sync_service._ensure_dirs('NOC', '12345')
        sync_service._write_revisions('NOC', '12345', versions)
        rev_path = sync_service.spaces_dir / 'NOC' / 'pages' / '12345' / 'revisions.json'
        assert rev_path.exists()
        data = json.loads(rev_path.read_text(encoding='utf-8'))
        assert len(data) == 2
        assert data[0]['version'] == 1


class TestWriteRestrictions:
    def test_writes_restrictions(self, sync_service):
        sync_service._ensure_dirs('NOC', '12345')
        sync_service._write_restrictions('NOC', '12345', {'read': {'users': []}})
        path = sync_service.spaces_dir / 'NOC' / 'pages' / '12345' / 'restrictions.json'
        assert path.exists()

    def test_none_restrictions(self, sync_service):
        sync_service._ensure_dirs('NOC', '12345')
        sync_service._write_restrictions('NOC', '12345', None)
        path = sync_service.spaces_dir / 'NOC' / 'pages' / '12345' / 'restrictions.json'
        data = json.loads(path.read_text(encoding='utf-8'))
        assert data == {'accessible': False}


# ===================================================================
# Tree building
# ===================================================================

class TestBuildTree:
    def test_simple_tree(self, sync_service):
        pages = [
            {'confluence_page_id': '1', 'title': 'Root', 'parent_page_id': None},
            {'confluence_page_id': '2', 'title': 'Child', 'parent_page_id': '1'},
        ]
        tree = sync_service._build_tree(pages)
        assert len(tree) == 1
        assert tree[0]['id'] == '1'
        assert len(tree[0]['children']) == 1
        assert tree[0]['children'][0]['id'] == '2'

    def test_multiple_roots(self, sync_service):
        pages = [
            {'confluence_page_id': '1', 'title': 'A', 'parent_page_id': None},
            {'confluence_page_id': '2', 'title': 'B', 'parent_page_id': None},
        ]
        tree = sync_service._build_tree(pages)
        assert len(tree) == 2

    def test_orphan_becomes_root(self, sync_service):
        """Page whose parent isn't in the set becomes a root."""
        pages = [
            {'confluence_page_id': '1', 'title': 'Orphan', 'parent_page_id': '999'},
        ]
        tree = sync_service._build_tree(pages)
        assert len(tree) == 1

    def test_empty_pages(self, sync_service):
        tree = sync_service._build_tree([])
        assert tree == []

    def test_sorted_by_title(self, sync_service):
        pages = [
            {'confluence_page_id': '1', 'title': 'Zebra', 'parent_page_id': None},
            {'confluence_page_id': '2', 'title': 'Apple', 'parent_page_id': None},
        ]
        tree = sync_service._build_tree(pages)
        assert tree[0]['title'] == 'Apple'


# ===================================================================
# sync_all
# ===================================================================

class TestSyncAll:
    def test_syncs_multiple_spaces(self, sync_service, confluence_client):
        pages_noc = [make_confluence_page(page_id='1')]
        pages_nocmon = [make_confluence_page(page_id='2')]

        call_count = [0]
        def mock_sync_space(space_key, **kwargs):
            call_count[0] += 1
            return {'space_key': space_key, 'total_pages': 1}

        sync_service.sync_space = mock_sync_space
        results = sync_service.sync_all(['DEMO', 'LAB'])
        assert len(results) == 2
        assert call_count[0] == 2

    def test_one_space_fails(self, sync_service):
        call_count = [0]

        def mock_sync_space(space_key, **kwargs):
            call_count[0] += 1
            if space_key == 'BAD':
                raise ConnectionError('offline')
            return {'space_key': space_key, 'total_pages': 1}

        sync_service.sync_space = mock_sync_space
        results = sync_service.sync_all(['NOC', 'BAD'])
        assert len(results) == 2
        assert results[1].get('error') is not None


# ===================================================================
# get_sync_status
# ===================================================================

class TestGetSyncStatus:
    def test_empty(self, sync_service):
        status = sync_service.get_sync_status()
        assert status['state'] == {}
        assert status['recent_runs'] == []

    def test_after_sync(self, sync_service, confluence_client):
        pages = [make_confluence_page()]
        _setup_mock_sync(confluence_client, pages)
        sync_service.sync_space('NOC')
        status = sync_service.get_sync_status()
        assert 'NOC' in status['state']
        assert len(status['recent_runs']) >= 1


# ===================================================================
# READ-ONLY PROOF: sync_service never sends mutations via client
# ===================================================================

class TestSyncReadOnly:
    def test_sync_only_calls_get_methods(self, sync_service, confluence_client):
        """Track all method calls on the client during sync."""
        pages = [make_confluence_page()]
        _setup_mock_sync(confluence_client, pages)
        sync_service.sync_space('NOC')

        # The client should only have been called with read methods
        safe_methods = {
            'get_space', 'get_all_pages', 'get_all_blog_posts', 'get_pages',
            'get_blog_posts', 'fetch_page_extras',
            'get_versions', 'get_restrictions', 'get_history',
            'get_page', 'list_spaces',
            'search_cql', 'search_cql_all', 'get_space_labels',
        }
        for attr_name in dir(confluence_client):
            attr = getattr(confluence_client, attr_name)
            if isinstance(attr, MagicMock) and attr.called:
                if not attr_name.startswith('_'):
                    assert attr_name in safe_methods, \
                        f'Unexpected client method called during sync: {attr_name}'


# ===================================================================
# CQL string escaping (incremental sync query construction)
# ===================================================================

class TestCQLEscaping:
    def test_escape_helper_quotes(self):
        assert _escape_cql_string('normal') == 'normal'
        assert _escape_cql_string('has "quotes"') == 'has \\"quotes\\"'
        assert _escape_cql_string('back\\slash') == 'back\\\\slash'
        assert _escape_cql_string('inject" OR space = "OTHER') == \
            'inject\\" OR space = \\"OTHER'

    def test_incremental_sync_escapes_since_timestamp(self, sync_service, confluence_client):
        """A timestamp containing a quote must not break out of its CQL literal."""
        confluence_client.search_cql_all = MagicMock(return_value=[])
        malicious_ts = '2024-01-01" OR space = "EVIL'

        sync_service.sync_incremental(['NOC'], since_timestamp=malicious_ts)

        assert confluence_client.search_cql_all.called
        cql = confluence_client.search_cql_all.call_args[0][0]
        # The escaped literal must appear intact...
        assert 'lastmodified >= "2024-01-01\\" OR space = \\"EVIL"' in cql
        # ...and the raw unescaped injection must not appear as a second clause.
        assert 'OR space = "EVIL" AND type' not in cql

    def test_incremental_sync_escapes_space_keys(self, sync_service, confluence_client):
        confluence_client.search_cql_all = MagicMock(return_value=[])

        sync_service.sync_incremental(['NOC"] OR space = "EVIL'],
                                       since_timestamp='2024-01-01')

        cql = confluence_client.search_cql_all.call_args[0][0]
        assert '\\"' in cql
        assert 'space IN ("NOC\\"] OR space = \\"EVIL")' in cql
