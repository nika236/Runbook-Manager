"""Shared fixtures for the runbooks-app test suite."""

import json
import os
import shutil
import tempfile
from pathlib import Path
from unittest.mock import MagicMock

import pytest

# Force test configuration before any app imports
os.environ.setdefault('CONFLUENCE_BASE_URL', 'https://test.atlassian.net')
os.environ.setdefault('CONFLUENCE_EMAIL', 'test@example.com')
os.environ.setdefault('CONFLUENCE_API_TOKEN', 'test-token-secret')
os.environ.setdefault('CONFLUENCE_SPACE_KEYS', 'DEMO,LAB')
os.environ.setdefault('SECRET_KEY', 'test-secret-key')
os.environ.setdefault('STALE_THRESHOLD_DAYS', '30')

from app import create_app
from app.services.confluence_client import ConfluenceClient
from app.services.store import PageStore
from app.services.metadata_store import MetadataStore
from app.services.sync_service import SyncService


# ---------------------------------------------------------------------------
# Sample Confluence API responses
# ---------------------------------------------------------------------------

def make_confluence_page(page_id='12345', title='Test Page', space_key='NOC',
                         body_html='<p>Hello world</p>', version=1,
                         labels=None, ancestors=None, children=None,
                         created_by='admin', updated_at='2024-06-15T10:00:00.000Z'):
    """Build a realistic Confluence REST API page response."""
    return {
        'id': str(page_id),
        'type': 'page',
        'status': 'current',
        'title': title,
        'body': {'storage': {'value': body_html, 'representation': 'storage'}},
        'version': {
            'number': version,
            'by': {'displayName': 'Updater', 'username': 'updater'},
            'when': updated_at,
        },
        'ancestors': ancestors or [],
        'children': {'page': {'results': children or []}},
        'metadata': {
            'labels': {
                'results': [{'name': lbl} for lbl in (labels or [])],
            },
        },
        'history': {
            'createdBy': {'displayName': created_by, 'username': created_by},
            'createdDate': '2024-01-01T00:00:00.000Z',
            'lastUpdated': {'when': updated_at},
        },
        '_links': {
            'webui': f'/spaces/{space_key}/pages/{page_id}/{title.replace(" ", "+")}',
        },
    }


def make_pages_response(pages, total=None, size=None, limit=50, start=0):
    """Build a paginated Confluence content response."""
    return {
        'results': pages,
        'start': start,
        'limit': limit,
        'size': size if size is not None else len(pages),
        'totalSize': total if total is not None else len(pages),
    }


def make_space_response(key='NOC', name='Demo Space'):
    return {
        'key': key,
        'name': name,
        'description': {'plain': {'value': 'Test space'}},
        'homepage': {'id': '10001'},
    }


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def tmp_data_dir(tmp_path):
    """Provide a temporary data directory for tests."""
    return tmp_path


@pytest.fixture
def populated_data_dir(tmp_data_dir):
    """A data directory pre-populated with sample page data."""
    space_key = 'NOC'
    pages_dir = tmp_data_dir / 'spaces' / space_key / 'pages'

    # Page 1 - normal
    p1_dir = pages_dir / '12345'
    p1_dir.mkdir(parents=True)
    page1_doc = {
        'confluence_page_id': '12345',
        'space_key': space_key,
        'title': 'Alert Runbook',
        'content_type': 'page',
        'parent_page_id': None,
        'ancestors': [],
        'children_ids': ['12346'],
        'labels': ['alert', 'production'],
        'created_by': 'admin',
        'created_at': '2024-01-01T00:00:00.000Z',
        'updated_by': 'editor',
        'updated_at': '2024-06-15T10:00:00.000Z',
        'confluence_version': 3,
        'confluence_url': 'https://test.atlassian.net/wiki/spaces/NOC/pages/12345',
        'word_count': 50,
        'content_hash': 'abc123',
    }
    (p1_dir / 'page.json').write_text(json.dumps(page1_doc), encoding='utf-8')
    (p1_dir / 'content.html').write_text('<p>Alert procedure content</p>', encoding='utf-8')
    (p1_dir / 'content.txt').write_text('Alert procedure content', encoding='utf-8')
    (p1_dir / 'revisions.json').write_text(json.dumps([
        {'version': 1, 'by': 'admin', 'when': '2024-01-01T00:00:00.000Z', 'message': 'Created'},
        {'version': 2, 'by': 'editor', 'when': '2024-03-01T00:00:00.000Z', 'message': 'Updated'},
        {'version': 3, 'by': 'editor', 'when': '2024-06-15T10:00:00.000Z', 'message': 'Refresh'},
    ]), encoding='utf-8')
    # Page 2 - child, stale (old updated_at)
    p2_dir = pages_dir / '12346'
    p2_dir.mkdir(parents=True)
    page2_doc = {
        'confluence_page_id': '12346',
        'space_key': space_key,
        'title': 'Stale Procedure',
        'content_type': 'page',
        'parent_page_id': '12345',
        'ancestors': [{'id': '12345', 'title': 'Alert Runbook'}],
        'children_ids': [],
        'labels': ['stale'],
        'created_by': 'admin',
        'created_at': '2023-01-01T00:00:00.000Z',
        'updated_by': 'admin',
        'updated_at': '2023-06-01T00:00:00.000Z',
        'confluence_version': 1,
        'confluence_url': 'https://test.atlassian.net/wiki/spaces/NOC/pages/12346',
        'word_count': 10,
        'content_hash': 'def456',
    }
    (p2_dir / 'page.json').write_text(json.dumps(page2_doc), encoding='utf-8')
    (p2_dir / 'content.html').write_text('<p>Old content</p>', encoding='utf-8')
    (p2_dir / 'content.txt').write_text('Old content', encoding='utf-8')

    # space.json
    space_dir = tmp_data_dir / 'spaces' / space_key
    (space_dir / 'space.json').write_text(json.dumps({
        'key': 'NOC', 'name': 'Demo Space',
        'description': 'Test space', 'homepage_id': '12345',
    }), encoding='utf-8')

    # tree.json
    tree = [
        {
            'id': '12345',
            'title': 'Alert Runbook',
            'children': [
                {'id': '12346', 'title': 'Stale Procedure', 'children': []},
            ],
        },
    ]
    (space_dir / 'tree.json').write_text(json.dumps(tree), encoding='utf-8')

    return tmp_data_dir


@pytest.fixture
def page_store(populated_data_dir):
    """PageStore backed by the populated test data."""
    return PageStore(data_dir=str(populated_data_dir), stale_threshold_days=30)


@pytest.fixture
def metadata_store(tmp_data_dir):
    """MetadataStore backed by a clean temp directory."""
    return MetadataStore(data_dir=str(tmp_data_dir))


@pytest.fixture
def confluence_client():
    """ConfluenceClient with a mocked session (no real HTTP)."""
    client = ConfluenceClient(
        base_url='https://test.atlassian.net',
        email='test@example.com',
        api_token='test-token',
        rate_limit=100,  # fast for tests
    )
    client.session = MagicMock()
    client._min_interval = 0  # disable throttle in tests
    return client


@pytest.fixture
def sync_service(confluence_client, tmp_data_dir):
    """SyncService with mocked Confluence client."""
    return SyncService(
        confluence_client=confluence_client,
        data_dir=str(tmp_data_dir),
        stale_threshold_days=30,
    )


@pytest.fixture
def app(populated_data_dir):
    """Flask test application with populated data."""
    os.environ['DATA_DIR'] = str(populated_data_dir)
    os.environ['CONFLUENCE_BASE_URL'] = 'https://test.atlassian.net'
    os.environ['CONFLUENCE_EMAIL'] = 'test@example.com'
    os.environ['CONFLUENCE_API_TOKEN'] = 'test-token'
    os.environ['CONFLUENCE_SPACE_KEYS'] = 'DEMO,LAB'

    application = create_app()
    application.config['TESTING'] = True
    application.config['DATA_DIR'] = str(populated_data_dir)

    # Re-initialize stores with the correct data directory so tests use
    # the populated fixture data, not whatever DATA_DIR pointed to at
    # module-import time.
    data_dir = str(populated_data_dir)
    application.extensions['page_store'] = PageStore(
        data_dir=data_dir,
        stale_threshold_days=application.config['STALE_THRESHOLD_DAYS'],
    )
    application.extensions['metadata_store'] = MetadataStore(data_dir=data_dir)

    return application


@pytest.fixture
def client(app):
    """Flask test client."""
    return app.test_client()
