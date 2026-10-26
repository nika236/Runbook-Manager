"""API contract tests for the page-detail reader.

Verifies the shape the reader depends on, the deliberate error/empty states, and
that nothing on this path can write to Confluence.
"""
import json

import pytest


class TestPageDetailPayload:
    """The reader renders from one payload; these are the fields it needs."""

    def test_page_payload_has_everything_the_header_shows(self, client):
        resp = client.get('/api/spaces/NOC/pages/12345')
        assert resp.status_code == 200
        data = resp.get_json()

        for field in ('title', 'created_by', 'updated_at', 'confluence_version',
                      'word_count', 'confluence_url', 'ancestors', 'labels',
                      'content', 'content_is_empty', 'local_status'):
            assert field in data, f'{field} missing from the page payload'

    def test_content_is_rendered_not_raw_storage_format(self, client):
        resp = client.get('/api/spaces/NOC/pages/12345')
        content = resp.get_json()['content']
        assert '<ac:' not in content
        assert '<ri:' not in content

    def test_content_is_empty_flag_distinguishes_empty_from_failed(self, client):
        data = client.get('/api/spaces/NOC/pages/12345').get_json()
        assert data['content_is_empty'] is False

    def test_ancestors_carry_id_and_title_for_breadcrumbs(self, client):
        data = client.get('/api/spaces/NOC/pages/12346').get_json()
        assert data['ancestors']
        assert set(data['ancestors'][0]) >= {'id', 'title'}

    def test_missing_metadata_is_null_not_invented(self, client):
        """The reader shows "Not set"; the API must not guess a value."""
        data = client.get('/api/spaces/NOC/pages/12345').get_json()
        assert data.get('priority') is None
        assert data.get('owner') is None
        assert data.get('team') is None

    def test_review_reasons_are_exposed_for_the_review_chips(self, client):
        data = client.get('/api/spaces/NOC/pages/12345').get_json()
        assert 'review_reasons' in data
        assert isinstance(data['review_reasons'], list)

    def test_content_endpoint_renders_the_same_way(self, client):
        page = client.get('/api/spaces/NOC/pages/12345').get_json()
        standalone = client.get('/api/spaces/NOC/pages/12345/content').get_json()
        assert standalone['format'] == 'html'
        assert standalone['content'] == page['content']


class TestDeliberateStates:

    def test_unknown_page_returns_404(self, client):
        resp = client.get('/api/spaces/NOC/pages/does-not-exist')
        assert resp.status_code == 404
        assert 'error' in resp.get_json()

    def test_unknown_page_content_returns_404(self, client):
        resp = client.get('/api/spaces/NOC/pages/does-not-exist/content')
        assert resp.status_code == 404

    def test_page_without_revisions_returns_an_empty_list(self, client):
        resp = client.get('/api/spaces/NOC/pages/12346/revisions')
        assert resp.status_code == 200
        assert resp.get_json()['revisions'] == []

    def test_revisions_carry_version_author_date(self, client):
        revisions = client.get('/api/spaces/NOC/pages/12345/revisions').get_json()['revisions']
        assert revisions
        assert set(revisions[0]) >= {'version', 'by', 'when'}


class TestConfluenceStaysReadOnly:

    def test_page_routes_reject_writes(self, client):
        for method in ('post', 'put', 'patch', 'delete'):
            resp = getattr(client, method)('/api/spaces/NOC/pages/12345')
            assert resp.status_code == 405, f'{method.upper()} should not be allowed'

    def test_content_route_rejects_writes(self, client):
        for method in ('post', 'put', 'patch', 'delete'):
            resp = getattr(client, method)('/api/spaces/NOC/pages/12345/content')
            assert resp.status_code == 405

    def test_metadata_write_is_local_only(self, client, populated_data_dir):
        """A metadata save must land in data/metadata and nowhere else."""
        resp = client.put(
            '/api/spaces/NOC/pages/12345/metadata',
            data=json.dumps({'priority': 'P1', 'owner': 'dana'}),
            content_type='application/json',
        )
        assert resp.status_code == 200
        body = resp.get_json()
        assert body['priority'] == 'P1'
        assert body['owner'] == 'dana'

        stored = populated_data_dir / 'metadata' / 'NOC' / '12345.json'
        assert stored.is_file()
        assert json.loads(stored.read_text(encoding='utf-8'))['priority'] == 'P1'

    def test_metadata_write_does_not_touch_the_mirrored_source(self, client,
                                                               populated_data_dir):
        source = populated_data_dir / 'spaces' / 'NOC' / 'pages' / '12345'
        before = {
            p.name: p.read_bytes()
            for p in source.iterdir() if p.is_file()
        }
        client.put(
            '/api/spaces/NOC/pages/12345/metadata',
            data=json.dumps({'priority': 'P0', 'notes': 'checked'}),
            content_type='application/json',
        )
        after = {
            p.name: p.read_bytes()
            for p in source.iterdir() if p.is_file()
        }
        assert before == after, 'a local metadata write modified the mirrored page'

    def test_metadata_write_rejects_unknown_fields(self, client):
        resp = client.put(
            '/api/spaces/NOC/pages/12345/metadata',
            data=json.dumps({'title': 'Renamed in Confluence',
                             'content': '<p>overwritten</p>'}),
            content_type='application/json',
        )
        assert resp.status_code == 200
        body = resp.get_json()
        assert body.get('title') != 'Renamed in Confluence'
        assert 'content' not in body or body.get('content') != '<p>overwritten</p>'

    def test_metadata_write_on_unknown_page_is_rejected(self, client):
        resp = client.put(
            '/api/spaces/NOC/pages/99999/metadata',
            data=json.dumps({'priority': 'P1'}),
            content_type='application/json',
        )
        assert resp.status_code == 404


class TestRenderingNeedsNoLiveConfluence:

    def test_page_renders_with_the_confluence_client_removed(self, app):
        """A mirrored page must render with no network available at all."""
        app.extensions.pop('confluence_client', None)
        with app.test_client() as client:
            resp = client.get('/api/spaces/NOC/pages/12345')
            assert resp.status_code == 200
            assert 'Alert procedure content' in resp.get_json()['content']
