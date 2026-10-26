"""Tests for the Runbooks API endpoints.

Covers: page listing, filtering, pagination, sorting, page detail,
metadata CRUD, bulk updates, revisions, legacy endpoints,
error responses, and missing-page handling.
"""

import json
import pytest


# ===================================================================
# /api/spaces
# ===================================================================

class TestListSpaces:
    def test_success(self, client):
        resp = client.get('/api/spaces')
        assert resp.status_code == 200
        data = resp.get_json()
        assert 'spaces' in data
        assert len(data['spaces']) >= 1

    def test_contains_noc(self, client):
        data = client.get('/api/spaces').get_json()
        keys = [s['key'] for s in data['spaces']]
        assert 'NOC' in keys


class TestGetSpace:
    def test_found(self, client):
        resp = client.get('/api/spaces/NOC')
        assert resp.status_code == 200
        data = resp.get_json()
        assert data['key'] == 'NOC'

    def test_not_found(self, client):
        resp = client.get('/api/spaces/MISSING')
        assert resp.status_code == 404
        assert 'error' in resp.get_json()


class TestGetTree:
    def test_success(self, client):
        resp = client.get('/api/spaces/NOC/tree')
        assert resp.status_code == 200
        data = resp.get_json()
        assert 'tree' in data
        assert len(data['tree']) >= 1

    def test_missing_space(self, client):
        resp = client.get('/api/spaces/MISSING/tree')
        assert resp.status_code == 200
        assert resp.get_json()['tree'] == []


# ===================================================================
# /api/spaces/<key>/pages
# ===================================================================

class TestListPages:
    def test_success(self, client):
        resp = client.get('/api/spaces/NOC/pages')
        assert resp.status_code == 200
        data = resp.get_json()
        assert 'pages' in data
        assert 'total' in data
        assert data['total'] >= 1

    def test_pagination_fields(self, client):
        resp = client.get('/api/spaces/NOC/pages?page=1&per_page=1')
        data = resp.get_json()
        assert data['page'] == 1
        assert data['per_page'] == 1
        assert data['pages_count'] >= 1

    def test_search_filter(self, client):
        resp = client.get('/api/spaces/NOC/pages?search=Alert')
        data = resp.get_json()
        assert any('Alert' in p.get('title', '') for p in data['pages'])

    def test_search_case_insensitive(self, client):
        resp = client.get('/api/spaces/NOC/pages?search=alert')
        data = resp.get_json()
        assert any('Alert' in p.get('title', '') for p in data['pages'])

    def test_search_no_results(self, client):
        resp = client.get('/api/spaces/NOC/pages?search=zzz_nonexistent')
        data = resp.get_json()
        assert data['total'] == 0

    def test_sort_by_title(self, client):
        resp = client.get('/api/spaces/NOC/pages?sort_by=title&sort_order=asc')
        data = resp.get_json()
        titles = [p['title'] for p in data['pages']]
        assert titles == sorted(titles)

    def test_sort_desc(self, client):
        resp = client.get('/api/spaces/NOC/pages?sort_by=title&sort_order=desc')
        data = resp.get_json()
        titles = [p['title'] for p in data['pages']]
        assert titles == sorted(titles, reverse=True)

    def test_per_page_capped(self, client):
        resp = client.get('/api/spaces/NOC/pages?per_page=999')
        data = resp.get_json()
        assert data['per_page'] <= 200

    def test_archived_excluded_by_default(self, client, app):
        # Archive one page
        with app.app_context():
            meta = app.extensions['metadata_store']
            meta.update('NOC', '12346', {'local_status': 'archived'})
        resp = client.get('/api/spaces/NOC/pages')
        data = resp.get_json()
        ids = [p.get('confluence_page_id') for p in data['pages']]
        assert '12346' not in ids

    def test_archived_filter_shows_archived(self, client, app):
        with app.app_context():
            meta = app.extensions['metadata_store']
            meta.update('NOC', '12346', {'local_status': 'archived'})
        resp = client.get('/api/spaces/NOC/pages?local_status=archived')
        data = resp.get_json()
        assert any(p.get('confluence_page_id') == '12346' for p in data['pages'])

    def test_label_filter(self, client):
        resp = client.get('/api/spaces/NOC/pages?label=alert')
        data = resp.get_json()
        for p in data['pages']:
            assert 'alert' in (p.get('labels') or [])

    def test_empty_space(self, client):
        resp = client.get('/api/spaces/EMPTY/pages')
        data = resp.get_json()
        assert data['total'] == 0

    def test_enriched_with_metadata(self, client, app):
        with app.app_context():
            meta = app.extensions['metadata_store']
            meta.update('NOC', '12345', {'priority': 'P1', 'owner': 'alice'})
        resp = client.get('/api/spaces/NOC/pages')
        data = resp.get_json()
        page = next(p for p in data['pages'] if p['confluence_page_id'] == '12345')
        assert page['priority'] == 'P1'
        assert page['owner'] == 'alice'


# ===================================================================
# /api/spaces/<key>/pages/<id>
# ===================================================================

class TestGetPage:
    def test_found(self, client):
        resp = client.get('/api/spaces/NOC/pages/12345')
        assert resp.status_code == 200
        data = resp.get_json()
        assert data['title'] == 'Alert Runbook'
        assert data['content'] is not None
        assert 'local_status' in data

    def test_not_found(self, client):
        resp = client.get('/api/spaces/NOC/pages/99999')
        assert resp.status_code == 404

    def test_includes_content(self, client):
        data = client.get('/api/spaces/NOC/pages/12345').get_json()
        assert '<p>' in data['content']


# ===================================================================
# /api/spaces/<key>/pages/<id>/revisions
# ===================================================================

class TestGetRevisions:
    def test_returns_revisions(self, client):
        resp = client.get('/api/spaces/NOC/pages/12345/revisions')
        assert resp.status_code == 200
        data = resp.get_json()
        assert 'revisions' in data
        assert len(data['revisions']) == 3

    def test_missing_page_returns_empty(self, client):
        resp = client.get('/api/spaces/NOC/pages/99999/revisions')
        data = resp.get_json()
        assert data['revisions'] == []


# ===================================================================
# /api/spaces/<key>/pages/<id>/metadata (GET and PUT)
# ===================================================================

class TestMetadataEndpoint:
    def test_get_defaults(self, client):
        resp = client.get('/api/spaces/NOC/pages/12345/metadata')
        assert resp.status_code == 200
        data = resp.get_json()
        assert data['local_status'] == 'imported'

    def test_update_metadata(self, client):
        resp = client.put('/api/spaces/NOC/pages/12345/metadata',
                          json={'priority': 'P0', 'owner': 'alice'})
        assert resp.status_code == 200
        data = resp.get_json()
        assert data['priority'] == 'P0'
        assert data['owner'] == 'alice'

    def test_update_nonexistent_page(self, client):
        resp = client.put('/api/spaces/NOC/pages/99999/metadata',
                          json={'priority': 'P1'})
        assert resp.status_code == 404

    def test_update_no_body(self, client):
        resp = client.put('/api/spaces/NOC/pages/12345/metadata',
                          content_type='application/json')
        assert resp.status_code == 400

    def test_update_unknown_fields_ignored(self, client):
        resp = client.put('/api/spaces/NOC/pages/12345/metadata',
                          json={'unknown_field': 'value', 'priority': 'P2'})
        assert resp.status_code == 200
        data = resp.get_json()
        assert data['priority'] == 'P2'
        assert 'unknown_field' not in data

    def test_update_preserves_other_fields(self, client):
        client.put('/api/spaces/NOC/pages/12345/metadata',
                   json={'priority': 'P1', 'owner': 'alice'})
        resp = client.put('/api/spaces/NOC/pages/12345/metadata',
                          json={'notes': 'important'})
        data = resp.get_json()
        assert data['priority'] == 'P1'
        assert data['owner'] == 'alice'
        assert data['notes'] == 'important'

    def test_empty_fields_returns_current(self, client):
        resp = client.put('/api/spaces/NOC/pages/12345/metadata',
                          json={'unrecognized': 'x'})
        assert resp.status_code == 200


# ===================================================================
# /api/pages/bulk-update
# ===================================================================

class TestBulkUpdate:
    def test_success(self, client):
        resp = client.post('/api/pages/bulk-update', json={
            'items': [
                {'space_key': 'NOC', 'page_id': '12345'},
                {'space_key': 'NOC', 'page_id': '12346'},
            ],
            'fields': {'priority': 'P3'},
        })
        assert resp.status_code == 200
        data = resp.get_json()
        assert data['updated_count'] == 2

    def test_string_items(self, client):
        resp = client.post('/api/pages/bulk-update', json={
            'items': ['NOC/12345'],
            'fields': {'priority': 'P1'},
        })
        assert resp.status_code == 200
        assert resp.get_json()['updated_count'] == 1

    def test_no_body(self, client):
        resp = client.post('/api/pages/bulk-update',
                           content_type='application/json')
        assert resp.status_code == 400

    def test_no_items(self, client):
        resp = client.post('/api/pages/bulk-update', json={
            'items': [],
            'fields': {'priority': 'P1'},
        })
        assert resp.status_code == 400

    def test_no_fields(self, client):
        resp = client.post('/api/pages/bulk-update', json={
            'items': [{'space_key': 'NOC', 'page_id': '12345'}],
            'fields': {},
        })
        assert resp.status_code == 400

    def test_updates_key(self, client):
        """Can also use 'updates' key instead of 'fields'."""
        resp = client.post('/api/pages/bulk-update', json={
            'items': [{'space_key': 'NOC', 'page_id': '12345'}],
            'updates': {'priority': 'P2'},
        })
        assert resp.status_code == 200


# ===================================================================
# Legacy endpoints
# ===================================================================

class TestLegacyEndpoints:
    def test_legacy_list(self, client):
        resp = client.get('/api/runbooks/')
        assert resp.status_code == 200
        data = resp.get_json()
        assert 'runbooks' in data
        assert data['total'] >= 1
        # Check legacy fields
        rb = data['runbooks'][0]
        assert 'id' in rb
        assert 'confluence_id' in rb

    def test_legacy_detail(self, client):
        resp = client.get('/api/runbooks/12345')
        assert resp.status_code == 200
        data = resp.get_json()
        assert data['id'] == '12345'
        assert data['confluence_id'] == '12345'
        assert 'content' in data

    def test_legacy_detail_not_found(self, client):
        resp = client.get('/api/runbooks/99999')
        assert resp.status_code == 404

    def test_legacy_search(self, client):
        resp = client.get('/api/runbooks/?search=Alert')
        data = resp.get_json()
        assert any('Alert' in r.get('title', '') for r in data['runbooks'])

    def test_legacy_pagination(self, client):
        resp = client.get('/api/runbooks/?page=1&per_page=1')
        data = resp.get_json()
        assert data['page'] == 1
        assert len(data['runbooks']) <= 1

    def test_legacy_archived_excluded(self, client, app):
        with app.app_context():
            meta = app.extensions['metadata_store']
            meta.update('NOC', '12346', {'local_status': 'archived'})
        resp = client.get('/api/runbooks/')
        data = resp.get_json()
        ids = [r.get('id') for r in data['runbooks']]
        assert '12346' not in ids

    def test_legacy_wl_filter_label_missing(self, client, app):
        with app.app_context():
            meta = app.extensions['metadata_store']
            meta.update('NOC', '12345', {'flag_label_missing': True})
        resp = client.get('/api/runbooks/?wl_filter=label_missing')
        assert resp.status_code == 200
        data = resp.get_json()
        ids = [r.get('id') for r in data['runbooks']]
        assert '12345' in ids
        assert '12346' not in ids

    def test_legacy_wl_filter_cleared_shows_all(self, client, app):
        with app.app_context():
            meta = app.extensions['metadata_store']
            meta.update('NOC', '12345', {'flag_label_missing': True})
        resp = client.get('/api/runbooks/')
        data = resp.get_json()
        ids = [r.get('id') for r in data['runbooks']]
        assert '12345' in ids
        assert '12346' in ids

    def test_legacy_wl_filter_invalid_value_ignored(self, client):
        """An unrecognized wl_filter value must not crash or hide everything."""
        resp = client.get('/api/runbooks/?wl_filter=not-a-real-filter')
        assert resp.status_code == 200
        data = resp.get_json()
        assert data['total'] >= 1


# ===================================================================
# Dashboard API
# ===================================================================

class TestDashboardAPI:
    def test_stats(self, client):
        resp = client.get('/api/dashboard/stats')
        assert resp.status_code == 200
        data = resp.get_json()
        assert 'total_pages' in data
        assert 'stale_count' in data
        assert 'unowned_count' in data

    def test_recent_activity(self, client):
        resp = client.get('/api/dashboard/recent-activity')
        assert resp.status_code == 200
        data = resp.get_json()
        assert 'activity' in data

    def test_stale(self, client):
        resp = client.get('/api/dashboard/stale')
        assert resp.status_code == 200
        data = resp.get_json()
        assert 'runbooks' in data


# ===================================================================
# Sync API
# ===================================================================

class TestSyncAPI:
    def test_status(self, client):
        resp = client.get('/api/sync/status')
        assert resp.status_code == 200
        data = resp.get_json()
        assert 'state' in data

    def test_runs(self, client):
        resp = client.get('/api/sync/runs')
        assert resp.status_code == 200
        data = resp.get_json()
        assert 'runs' in data

    def test_full_sync_missing_config(self, client, app):
        with app.app_context():
            app.config['CONFLUENCE_BASE_URL'] = ''
        resp = client.post('/api/sync/full')
        assert resp.status_code == 400
        assert 'error' in resp.get_json()

    def test_incremental_sync_missing_config(self, client, app):
        with app.app_context():
            app.config['CONFLUENCE_BASE_URL'] = ''
        resp = client.post('/api/sync/incremental')
        assert resp.status_code == 400

    def test_full_sync_no_spaces(self, client, app):
        with app.app_context():
            app.config['CONFLUENCE_SPACE_KEYS'] = []
        resp = client.post('/api/sync/full')
        assert resp.status_code == 400

    def test_legacy_sync_endpoint(self, client, app):
        """POST /api/sync/confluence should trigger full sync."""
        with app.app_context():
            app.config['CONFLUENCE_BASE_URL'] = ''
        resp = client.post('/api/sync/confluence')
        # Should fail same as full sync with missing config
        assert resp.status_code == 400


# ===================================================================
# Error responses and edge cases
# ===================================================================

class TestErrorResponses:
    def test_all_404s_have_error_key(self, client):
        paths = [
            '/api/spaces/MISSING',
            '/api/spaces/NOC/pages/99999',
        ]
        for path in paths:
            resp = client.get(path)
            if resp.status_code == 404:
                assert 'error' in resp.get_json(), f'Missing error key in 404 for {path}'

    def test_json_content_type(self, client):
        resp = client.get('/api/spaces')
        assert 'application/json' in resp.content_type

    def test_url_encoded_page_id(self, client):
        resp = client.get('/api/spaces/NOC/pages/12345')
        assert resp.status_code == 200
