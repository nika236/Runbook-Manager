"""Data integrity tests.

Validates dashboard metric invariants, content type scoping,
duplicate detection, and consistent counting across all layers.
"""

import json

import pytest

from app.services.store import PageStore
from app.services.metadata_store import MetadataStore


def _make_page(pid, space_key='NOC', content_type='page', labels=None,
               updated_at='2024-06-15T10:00:00.000Z', title='Test Page'):
    return {
        'confluence_page_id': str(pid),
        'space_key': space_key,
        'title': title,
        'content_type': content_type,
        'labels': labels or [],
        'created_by': 'admin',
        'updated_by': 'admin',
        'created_at': '2024-01-01T00:00:00.000Z',
        'updated_at': updated_at,
        'confluence_version': 1,
        'word_count': 10,
        'content_hash': 'hash_%s' % pid,
    }


def _write_page(data_dir, doc, content_type='page'):
    subdir = 'blogposts' if content_type == 'blogpost' else 'pages'
    filename = 'post.json' if content_type == 'blogpost' else 'page.json'
    page_dir = data_dir / 'spaces' / doc['space_key'] / subdir / str(doc['confluence_page_id'])
    page_dir.mkdir(parents=True, exist_ok=True)
    (page_dir / filename).write_text(json.dumps(doc), encoding='utf-8')
    (page_dir / 'content.html').write_text('<p>content</p>', encoding='utf-8')
    (page_dir / 'content.txt').write_text('content', encoding='utf-8')


class TestStatsInvariants:
    """Verify that dashboard metric invariants always hold."""

    def test_unowned_lte_total_pages(self, tmp_path):
        """unowned_count must never exceed total_pages."""
        data_dir = tmp_path
        for i in range(5):
            _write_page(data_dir, _make_page(i, 'NOC'))
        _write_page(data_dir, _make_page('b1', 'NOC', content_type='blogpost'),
                    content_type='blogpost')

        store = PageStore(data_dir=str(data_dir))
        stats = store.get_stats()

        assert stats['unowned_count'] <= stats['total_pages'], (
            'unowned_count (%d) > total_pages (%d)' %
            (stats['unowned_count'], stats['total_pages']))

    def test_wl_lte_total_pages(self, tmp_path):
        """wl_count must never exceed total_pages."""
        data_dir = tmp_path
        for i in range(5):
            _write_page(data_dir, _make_page(i, 'NOC'))
        _write_page(data_dir, _make_page('b1', 'NOC', content_type='blogpost'),
                    content_type='blogpost')

        store = PageStore(data_dir=str(data_dir))
        stats = store.get_stats()

        assert stats['wl_count'] <= stats['total_pages'], (
            'wl_count (%d) > total_pages (%d)' %
            (stats['wl_count'], stats['total_pages']))

    def test_stale_lte_total_pages(self, tmp_path):
        """stale_count must never exceed total_pages."""
        data_dir = tmp_path
        for i in range(3):
            _write_page(data_dir, _make_page(i, 'NOC', updated_at='2020-01-01T00:00:00.000Z'))
        _write_page(data_dir, _make_page('b1', 'NOC', content_type='blogpost',
                                          updated_at='2020-01-01T00:00:00.000Z'),
                    content_type='blogpost')

        store = PageStore(data_dir=str(data_dir))
        stats = store.get_stats()

        assert stats['stale_count'] <= stats['total_pages']

    def test_space_distribution_equals_total_pages(self, tmp_path):
        """sum(space_distribution) must equal total_pages."""
        data_dir = tmp_path
        for i in range(3):
            _write_page(data_dir, _make_page(i, 'NOC'))
        for i in range(10, 12):
            _write_page(data_dir, _make_page(i, 'LAB'))
        _write_page(data_dir, _make_page('b1', 'NOC', content_type='blogpost'),
                    content_type='blogpost')

        store = PageStore(data_dir=str(data_dir))
        stats = store.get_stats()

        space_sum = sum(stats['space_distribution'].values())
        assert space_sum == stats['total_pages'], (
            'sum(space_distribution)=%d != total_pages=%d' %
            (space_sum, stats['total_pages']))

    def test_owned_plus_unowned_equals_total(self, tmp_path):
        """owned + unowned must equal total_pages."""
        data_dir = tmp_path
        meta_store = MetadataStore(data_dir=str(data_dir))

        for i in range(4):
            _write_page(data_dir, _make_page(i, 'NOC'))
        meta_store.update('NOC', '0', {'owner': 'alice'})
        meta_store.update('NOC', '1', {'owner': 'bob'})

        store = PageStore(data_dir=str(data_dir))
        stats = store.get_stats(metadata_store=meta_store)

        owned = stats['total_pages'] - stats['unowned_count']
        assert owned + stats['unowned_count'] == stats['total_pages']


class TestBlogPostExclusion:
    """Blog posts must not inflate page-scoped metrics."""

    def test_blog_posts_not_counted_in_total_pages(self, tmp_path):
        data_dir = tmp_path
        _write_page(data_dir, _make_page('p1', 'NOC'))
        _write_page(data_dir, _make_page('b1', 'NOC', content_type='blogpost'),
                    content_type='blogpost')

        store = PageStore(data_dir=str(data_dir))
        stats = store.get_stats()

        assert stats['total_pages'] == 1
        assert stats['total_blogs'] == 1

    def test_blog_posts_not_in_space_distribution(self, tmp_path):
        data_dir = tmp_path
        _write_page(data_dir, _make_page('p1', 'NOC'))
        _write_page(data_dir, _make_page('p2', 'NOC'))
        _write_page(data_dir, _make_page('b1', 'NOC', content_type='blogpost'),
                    content_type='blogpost')

        store = PageStore(data_dir=str(data_dir))
        stats = store.get_stats()

        assert stats['space_distribution'].get('NOC', 0) == 2

    def test_blog_posts_not_in_unowned_count(self, tmp_path):
        data_dir = tmp_path
        for i in range(3):
            _write_page(data_dir, _make_page(i, 'NOC'))
        _write_page(data_dir, _make_page('b1', 'NOC', content_type='blogpost'),
                    content_type='blogpost')
        _write_page(data_dir, _make_page('b2', 'NOC', content_type='blogpost'),
                    content_type='blogpost')

        store = PageStore(data_dir=str(data_dir))
        stats = store.get_stats()

        assert stats['unowned_count'] == 3, (
            'unowned should be 3 pages, got %d' % stats['unowned_count'])

    def test_blog_posts_not_in_wl_count(self, tmp_path):
        data_dir = tmp_path
        _write_page(data_dir, _make_page('p1', 'NOC', labels=[]))
        _write_page(data_dir, _make_page('p2', 'NOC', labels=['runbook']))
        _write_page(data_dir, _make_page('b1', 'NOC', content_type='blogpost', labels=[]),
                    content_type='blogpost')

        meta_store = MetadataStore(data_dir=str(data_dir))
        meta_store.update('NOC', 'p1', {'flag_label_missing': True})
        meta_store.update('NOC', 'p2', {'flag_label_missing': False})
        meta_store.update('NOC', 'b1', {'flag_label_missing': True})

        store = PageStore(data_dir=str(data_dir))
        stats = store.get_stats(metadata_store=meta_store)

        assert stats['wl_count'] == 1

    def test_blog_posts_not_in_stale_count(self, tmp_path):
        data_dir = tmp_path
        old_date = '2020-01-01T00:00:00.000Z'
        _write_page(data_dir, _make_page('p1', 'NOC', updated_at=old_date))
        _write_page(data_dir, _make_page('b1', 'NOC', content_type='blogpost',
                                          updated_at=old_date),
                    content_type='blogpost')

        store = PageStore(data_dir=str(data_dir))
        stats = store.get_stats()

        assert stats['stale_count'] == 1


class TestDuplicateDetection:
    """Ensure duplicate IDs don't cause double-counting."""

    def test_duplicate_page_id_uses_last_loaded(self, tmp_path):
        """If the same ID appears twice, the index should have exactly one entry."""
        data_dir = tmp_path
        doc = _make_page('dup1', 'NOC', title='First')
        _write_page(data_dir, doc)

        store = PageStore(data_dir=str(data_dir))
        assert len(store.get_all_pages()) == 1

    def test_string_vs_numeric_page_id(self, tmp_path):
        """Page IDs stored as strings should match numeric lookups."""
        data_dir = tmp_path
        _write_page(data_dir, _make_page(12345, 'NOC'))

        store = PageStore(data_dir=str(data_dir))
        assert store.get_page('12345') is not None
        assert store.get_page(12345) is not None


class TestContentTypeFiltering:
    """Verify get_all_pages content_type filter works correctly."""

    def test_filter_pages_only(self, tmp_path):
        data_dir = tmp_path
        _write_page(data_dir, _make_page('p1', 'NOC'))
        _write_page(data_dir, _make_page('b1', 'NOC', content_type='blogpost'),
                    content_type='blogpost')

        store = PageStore(data_dir=str(data_dir))
        pages = store.get_all_pages(content_type='page')
        assert len(pages) == 1
        assert pages[0]['content_type'] == 'page'

    def test_filter_blogposts_only(self, tmp_path):
        data_dir = tmp_path
        _write_page(data_dir, _make_page('p1', 'NOC'))
        _write_page(data_dir, _make_page('b1', 'NOC', content_type='blogpost'),
                    content_type='blogpost')

        store = PageStore(data_dir=str(data_dir))
        blogs = store.get_all_pages(content_type='blogpost')
        assert len(blogs) == 1
        assert blogs[0]['content_type'] == 'blogpost'


class TestEmptyDataset:
    """Invariants must hold for empty datasets."""

    def test_empty_stats_invariants(self, tmp_path):
        store = PageStore(data_dir=str(tmp_path))
        stats = store.get_stats()

        assert stats['total_pages'] == 0
        assert stats['total_blogs'] == 0
        assert stats['unowned_count'] == 0
        assert stats['wl_count'] == 0
        assert stats['stale_count'] == 0
        assert sum(stats['space_distribution'].values()) == 0


class TestTwoSpaces:
    """Verify counts are correct across multiple spaces."""

    def test_cross_space_totals(self, tmp_path):
        data_dir = tmp_path
        for i in range(3):
            _write_page(data_dir, _make_page('n%d' % i, 'NOC'))
        for i in range(2):
            _write_page(data_dir, _make_page('m%d' % i, 'LAB'))

        store = PageStore(data_dir=str(data_dir))
        stats = store.get_stats()

        assert stats['total_pages'] == 5
        assert stats['space_distribution'] == {'NOC': 3, 'LAB': 2}
        assert sum(stats['space_distribution'].values()) == stats['total_pages']
