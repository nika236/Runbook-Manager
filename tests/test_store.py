"""Tests for the file-based PageStore.

Covers: index loading, page retrieval, content reading,
revisions, space listing, hierarchy trees, stale detection, stats,
missing directories, corrupted files, reload behavior.
"""

import json
from datetime import datetime, timedelta
from pathlib import Path

import pytest

from app.services.store import PageStore
from app.services.metadata_store import MetadataStore


class TestPageStoreInit:
    def test_empty_data_dir(self, tmp_data_dir):
        store = PageStore(data_dir=str(tmp_data_dir))
        assert store.get_all_pages() == []

    def test_missing_spaces_dir(self, tmp_data_dir):
        store = PageStore(data_dir=str(tmp_data_dir / 'nonexistent'))
        assert store.get_all_pages() == []

    def test_loads_pages_on_init(self, populated_data_dir):
        store = PageStore(data_dir=str(populated_data_dir))
        pages = store.get_all_pages()
        assert len(pages) == 2

    def test_loads_tree_on_init(self, populated_data_dir):
        store = PageStore(data_dir=str(populated_data_dir))
        tree = store.get_tree('NOC')
        assert len(tree) >= 1

    def test_corrupted_page_json_skipped(self, tmp_data_dir):
        pages_dir = tmp_data_dir / 'spaces' / 'NOC' / 'pages' / '999'
        pages_dir.mkdir(parents=True)
        (pages_dir / 'page.json').write_text('not valid json', encoding='utf-8')
        store = PageStore(data_dir=str(tmp_data_dir))
        assert store.get_page('999') is None

    def test_non_directory_in_spaces_ignored(self, tmp_data_dir):
        spaces_dir = tmp_data_dir / 'spaces'
        spaces_dir.mkdir(parents=True)
        (spaces_dir / 'not_a_dir.txt').write_text('file', encoding='utf-8')
        store = PageStore(data_dir=str(tmp_data_dir))
        assert store.get_all_pages() == []

    def test_corrupted_tree_json_ignored(self, tmp_data_dir):
        space_dir = tmp_data_dir / 'spaces' / 'NOC'
        pages_dir = space_dir / 'pages'
        pages_dir.mkdir(parents=True)
        (space_dir / 'tree.json').write_text('bad json', encoding='utf-8')
        store = PageStore(data_dir=str(tmp_data_dir))
        tree = store.get_tree('NOC')
        assert tree == []


class TestReload:
    def test_reload_picks_up_new_pages(self, populated_data_dir):
        store = PageStore(data_dir=str(populated_data_dir))
        assert len(store.get_all_pages()) == 2

        # Add a new page
        new_dir = populated_data_dir / 'spaces' / 'NOC' / 'pages' / '99999'
        new_dir.mkdir(parents=True)
        doc = {
            'confluence_page_id': '99999',
            'space_key': 'NOC',
            'title': 'New Page',
        }
        (new_dir / 'page.json').write_text(json.dumps(doc), encoding='utf-8')

        store.reload()
        assert len(store.get_all_pages()) == 3


class TestGetSpaces:
    def test_returns_spaces(self, page_store):
        spaces = page_store.get_spaces()
        assert len(spaces) >= 1
        noc = next(s for s in spaces if s.get('key') == 'NOC')
        assert noc['page_count'] == 2

    def test_empty_store(self, tmp_data_dir):
        store = PageStore(data_dir=str(tmp_data_dir))
        assert store.get_spaces() == []

    def test_corrupted_space_json_fallback(self, populated_data_dir):
        (populated_data_dir / 'spaces' / 'NOC' / 'space.json').write_text('bad', encoding='utf-8')
        store = PageStore(data_dir=str(populated_data_dir))
        spaces = store.get_spaces()
        assert len(spaces) >= 1
        noc = next(s for s in spaces if s.get('key') == 'NOC')
        assert noc['key'] == 'NOC'


class TestGetTree:
    def test_returns_tree(self, page_store):
        tree = page_store.get_tree('NOC')
        assert len(tree) >= 1
        assert tree[0]['id'] == '12345'

    def test_missing_space(self, page_store):
        assert page_store.get_tree('MISSING') == []

    def test_tree_loaded_from_file(self, populated_data_dir):
        """Tree loaded from cache first, then from file on miss."""
        store = PageStore(data_dir=str(populated_data_dir))
        # Clear in-memory cache
        store._trees = {}
        tree = store.get_tree('NOC')
        assert len(tree) >= 1


class TestGetAllPages:
    def test_all_pages(self, page_store):
        pages = page_store.get_all_pages()
        assert len(pages) == 2

    def test_filter_by_space(self, page_store):
        pages = page_store.get_all_pages(space_key='NOC')
        assert len(pages) == 2

    def test_filter_missing_space(self, page_store):
        pages = page_store.get_all_pages(space_key='MISSING')
        assert pages == []


class TestGetPage:
    def test_existing_page(self, page_store):
        page = page_store.get_page('12345')
        assert page is not None
        assert page['title'] == 'Alert Runbook'

    def test_missing_page(self, page_store):
        assert page_store.get_page('99999') is None

    def test_page_id_as_int(self, page_store):
        """PageStore should accept numeric page IDs."""
        page = page_store.get_page(12345)
        assert page is not None


class TestGetPageContent:
    def test_html_content(self, page_store):
        content = page_store.get_page_content('NOC', '12345')
        assert '<p>' in content

    def test_missing_content(self, page_store):
        assert page_store.get_page_content('NOC', '99999') is None

    def test_wrong_space(self, page_store):
        assert page_store.get_page_content('MISSING', '12345') is None


class TestGetPageText:
    def test_text_content(self, page_store):
        text = page_store.get_page_text('NOC', '12345')
        assert 'Alert' in text

    def test_missing(self, page_store):
        assert page_store.get_page_text('NOC', '99999') is None


class TestGetRevisions:
    def test_returns_revisions(self, page_store):
        revs = page_store.get_revisions('NOC', '12345')
        assert len(revs) == 3

    def test_missing_revisions(self, page_store):
        revs = page_store.get_revisions('NOC', '12346')
        assert revs == []

    def test_corrupted_revisions(self, populated_data_dir):
        rev_path = populated_data_dir / 'spaces' / 'NOC' / 'pages' / '12345' / 'revisions.json'
        rev_path.write_text('bad json', encoding='utf-8')
        store = PageStore(data_dir=str(populated_data_dir))
        assert store.get_revisions('NOC', '12345') == []


class TestGetStalePages:
    def test_finds_stale(self, page_store):
        stale = page_store.get_stale_pages()
        # Page 12346 has updated_at from 2023-06-01, well past 30 days
        assert any(p['confluence_page_id'] == '12346' for p in stale)

    def test_excludes_archived(self, page_store, metadata_store):
        metadata_store.update('NOC', '12346', {'local_status': 'archived'})
        stale = page_store.get_stale_pages(metadata_store=metadata_store)
        assert not any(p['confluence_page_id'] == '12346' for p in stale)

    def test_sorted_by_updated_at(self, page_store):
        stale = page_store.get_stale_pages()
        dates = [p.get('updated_at', '') for p in stale]
        assert dates == sorted(dates)


class TestGetStats:
    def test_basic_stats(self, page_store):
        stats = page_store.get_stats()
        assert stats['total_pages'] == 2
        assert 'NOC' in stats['space_distribution']

    def test_stats_with_metadata(self, page_store, metadata_store):
        metadata_store.update('NOC', '12345', {'priority': 'P1', 'owner': 'alice'})
        stats = page_store.get_stats(metadata_store=metadata_store)
        assert stats['priority_distribution'].get('P1', 0) >= 1
        # One page still unowned (12346)
        assert stats['unowned_count'] >= 1

    def test_stale_count(self, page_store):
        stats = page_store.get_stats()
        # At least page 12346 is stale
        assert stats['stale_count'] >= 1

    def test_archived_excluded_from_total(self, page_store, metadata_store):
        metadata_store.update('NOC', '12346', {'local_status': 'archived'})
        stats = page_store.get_stats(metadata_store=metadata_store)
        assert stats['total_pages'] == 1

    def test_label_distribution(self, page_store):
        stats = page_store.get_stats()
        label_dict = dict(stats['label_distribution'])
        assert 'alert' in label_dict or 'production' in label_dict
