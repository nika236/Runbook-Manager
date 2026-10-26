"""Security and reliability tests.

Covers: token leakage, injection, read-only enforcement,
invalid inputs, excessive payloads, and error information disclosure.
"""

import json
import inspect
import pytest

from app.services.confluence_client import ConfluenceClient
from app.services.sync_service import SyncService


class TestNoTokenLeakage:
    """API tokens and secrets must not appear in responses or logs."""

    def test_error_response_no_token(self, client, app):
        """Error responses must not include API credentials."""
        with app.app_context():
            app.config['CONFLUENCE_BASE_URL'] = ''
        resp = client.post('/api/sync/full')
        body = resp.get_data(as_text=True)
        assert 'test-token' not in body
        assert 'test@example.com' not in body.lower() or 'configured' in body.lower()

    def test_page_response_no_token(self, client):
        resp = client.get('/api/spaces/NOC/pages/12345')
        body = resp.get_data(as_text=True)
        assert 'test-token' not in body

    def test_stats_no_token(self, client):
        resp = client.get('/api/dashboard/stats')
        body = resp.get_data(as_text=True)
        assert 'test-token' not in body


class TestInvalidInputs:
    """Test handling of malicious/invalid inputs."""

    def test_xss_in_search(self, client):
        resp = client.get('/api/spaces/NOC/pages?search=<script>alert(1)</script>')
        assert resp.status_code == 200
        body = resp.get_data(as_text=True)
        # Should not reflect raw script tag
        assert '<script>alert(1)</script>' not in body

    def test_sql_injection_in_search(self, client):
        resp = client.get("/api/spaces/NOC/pages?search=' OR 1=1 --")
        assert resp.status_code == 200

    def test_very_long_search(self, client):
        resp = client.get(f'/api/spaces/NOC/pages?search={"x" * 10000}')
        assert resp.status_code in (200, 414)

    def test_negative_page(self, client):
        resp = client.get('/api/spaces/NOC/pages?page=-1')
        assert resp.status_code == 200

    def test_zero_per_page(self, client):
        resp = client.get('/api/spaces/NOC/pages?per_page=0')
        # Should not crash
        assert resp.status_code == 200

    def test_non_numeric_page(self, client):
        resp = client.get('/api/spaces/NOC/pages?page=abc')
        assert resp.status_code == 200

    def test_special_chars_in_space_key(self, client):
        resp = client.get('/api/spaces/%3Cscript%3E/pages')
        assert resp.status_code == 200
        assert resp.get_json()['total'] == 0

    def test_special_chars_in_page_id(self, client):
        resp = client.get('/api/spaces/NOC/pages/<script>')
        assert resp.status_code == 404

    def test_metadata_update_with_html(self, client):
        resp = client.put('/api/spaces/NOC/pages/12345/metadata',
                          json={'notes': '<script>alert(1)</script>'})
        assert resp.status_code == 200
        # The value is stored as-is (it's metadata, not rendered HTML)
        data = resp.get_json()
        assert data['notes'] == '<script>alert(1)</script>'


class TestReadOnlyConfluence:
    """Ensure the codebase has no methods that could write to Confluence."""

    def test_client_source_no_mutations(self):
        source = inspect.getsource(ConfluenceClient)
        for keyword in ['session.post', 'session.put', 'session.patch', 'session.delete']:
            assert keyword not in source, \
                f'Found {keyword} in ConfluenceClient source'

    def test_sync_source_no_mutations(self):
        source = inspect.getsource(SyncService)
        # SyncService should never call post/put/delete on the client
        for keyword in ['client.post', 'client.put', 'client.patch', 'client.delete',
                        '.post(', '.put(', '.patch(', '.delete(']:
            # Allow 'write_text' and similar local file operations
            if keyword in ('.post(', '.put(', '.patch(', '.delete('):
                # Check it's not on the session/client
                lines = source.split('\n')
                for line in lines:
                    if keyword in line:
                        # Must be local file operations, not HTTP
                        assert 'session' not in line and 'client' not in line, \
                            f'Found HTTP mutation in SyncService: {line.strip()}'


class TestBulkUpdateSecurity:
    def test_large_payload(self, client):
        items = [{'space_key': 'NOC', 'page_id': str(i)} for i in range(1000)]
        resp = client.post('/api/pages/bulk-update', json={
            'items': items,
            'fields': {'priority': 'P1'},
        })
        # Should handle (maybe slowly) without crashing
        assert resp.status_code == 200

    def test_empty_json_body(self, client):
        resp = client.post('/api/pages/bulk-update',
                           data='{}',
                           content_type='application/json')
        assert resp.status_code == 400

    def test_non_json_body(self, client):
        resp = client.post('/api/pages/bulk-update',
                           data='not json',
                           content_type='text/plain')
        assert resp.status_code in (400, 415)
