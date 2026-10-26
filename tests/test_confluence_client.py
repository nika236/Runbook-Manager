"""Tests for the Confluence REST API client (read-only).

Covers: authentication, rate limiting, retries, pagination, error handling,
history, restrictions, and crucially: proof that only GET requests are
issued (no POST/PUT/PATCH/DELETE).
"""

import time
from unittest.mock import MagicMock, patch, PropertyMock, call
import pytest
import requests

from app.services.confluence_client import (
    ConfluenceClient, strip_html, parse_confluence_date, DEFAULT_PAGE_EXPAND,
)
from tests.conftest import (
    make_confluence_page, make_pages_response, make_space_response,
)


# ===================================================================
# strip_html
# ===================================================================

class TestStripHtml:
    def test_basic_html(self):
        assert strip_html('<p>Hello <b>world</b></p>') == 'Hello world'

    def test_empty_string(self):
        assert strip_html('') == ''

    def test_none(self):
        assert strip_html(None) == ''

    def test_no_tags(self):
        assert strip_html('plain text') == 'plain text'

    def test_nested_tags(self):
        result = strip_html('<div><p><span>deep</span></p></div>')
        assert 'deep' in result

    def test_whitespace_normalization(self):
        result = strip_html('<p>foo</p>  <p>bar</p>')
        assert result == 'foo bar'

    def test_unicode_content(self):
        assert strip_html('<p>Ünïcödé 中文 العربية</p>') == 'Ünïcödé 中文 العربية'

    def test_special_characters(self):
        result = strip_html('<p>alert &amp; monitor &lt;system&gt;</p>')
        assert 'alert' in result
        assert '&amp;' in result or '&' in result

    def test_large_content(self):
        big = '<p>' + 'x' * 100000 + '</p>'
        result = strip_html(big)
        assert len(result) == 100000

    def test_self_closing_tags(self):
        result = strip_html('line1<br/>line2')
        assert 'line1' in result
        assert 'line2' in result

    def test_script_tags(self):
        result = strip_html('<script>alert("xss")</script>text')
        assert 'text' in result


# ===================================================================
# parse_confluence_date
# ===================================================================

class TestParseConfluenceDate:
    def test_iso_with_z(self):
        dt = parse_confluence_date('2024-06-15T10:00:00.000Z')
        assert dt is not None
        assert dt.year == 2024
        assert dt.month == 6
        assert dt.day == 15

    def test_iso_with_offset(self):
        dt = parse_confluence_date('2024-06-15T10:00:00.000+00:00')
        assert dt is not None

    def test_empty_string(self):
        assert parse_confluence_date('') is None

    def test_none(self):
        assert parse_confluence_date(None) is None

    def test_invalid_format(self):
        assert parse_confluence_date('not-a-date') is None

    def test_partial_iso(self):
        dt = parse_confluence_date('2024-06-15T10:00:00')
        assert dt is not None
        assert dt.year == 2024

    def test_integer_input(self):
        assert parse_confluence_date(12345) is None


# ===================================================================
# ConfluenceClient construction
# ===================================================================

class TestConfluenceClientInit:
    def test_trailing_slash_removed(self):
        c = ConfluenceClient('https://test.atlassian.net/', 'e@e.com', 'tok')
        assert c.base_url == 'https://test.atlassian.net'

    def test_session_auth_set(self):
        c = ConfluenceClient('https://test.atlassian.net', 'user@x.com', 'secret')
        assert c.session.auth == ('user@x.com', 'secret')

    def test_accept_header(self):
        c = ConfluenceClient('https://test.atlassian.net', 'u', 't')
        assert 'application/json' in c.session.headers.get('Accept', '')

    def test_user_agent_header(self):
        c = ConfluenceClient('https://test.atlassian.net', 'u', 't')
        assert 'runbooks-app' in c.session.headers.get('User-Agent', '')

    def test_rate_limit_zero(self):
        c = ConfluenceClient('https://test.atlassian.net', 'u', 't', rate_limit=0)
        assert c._min_interval == 0

    def test_rate_limit_positive(self):
        c = ConfluenceClient('https://test.atlassian.net', 'u', 't', rate_limit=10)
        assert abs(c._min_interval - 0.1) < 0.001

    def test_empty_base_url(self):
        c = ConfluenceClient('', 'u', 't')
        assert c.base_url == ''

    def test_missing_credentials(self):
        c = ConfluenceClient('https://test.atlassian.net', '', '')
        assert c.session.auth == ('', '')


# ===================================================================
# Rate limiting / throttle
# ===================================================================

class TestThrottle:
    def test_throttle_waits(self, confluence_client):
        confluence_client._min_interval = 0.5
        confluence_client._last_request_time = time.time()
        start = time.time()
        confluence_client._throttle()
        elapsed = time.time() - start
        # Should have waited close to 0.5s
        assert elapsed >= 0.3

    def test_no_throttle_when_interval_zero(self, confluence_client):
        confluence_client._min_interval = 0
        confluence_client._last_request_time = time.time()
        start = time.time()
        confluence_client._throttle()
        elapsed = time.time() - start
        assert elapsed < 0.1

    def test_no_throttle_after_long_pause(self, confluence_client):
        confluence_client._min_interval = 0.5
        confluence_client._last_request_time = time.time() - 10
        start = time.time()
        confluence_client._throttle()
        elapsed = time.time() - start
        assert elapsed < 0.1


# ===================================================================
# _get method
# ===================================================================

class TestGet:
    def _mock_response(self, json_data, status_code=200):
        resp = MagicMock()
        resp.status_code = status_code
        resp.json.return_value = json_data
        resp.raise_for_status.return_value = None
        return resp

    def test_successful_get(self, confluence_client):
        data = {'results': []}
        confluence_client.session.get.return_value = self._mock_response(data)
        result = confluence_client._get('/wiki/rest/api/content')
        assert result == data

    def test_get_builds_full_url(self, confluence_client):
        confluence_client.session.get.return_value = self._mock_response({})
        confluence_client._get('/wiki/rest/api/space')
        call_args = confluence_client.session.get.call_args
        assert call_args[0][0] == 'https://test.atlassian.net/wiki/rest/api/space'

    def test_get_passes_params(self, confluence_client):
        confluence_client.session.get.return_value = self._mock_response({})
        confluence_client._get('/path', params={'key': 'val'})
        call_args = confluence_client.session.get.call_args
        assert call_args[1]['params'] == {'key': 'val'}

    def test_get_passes_timeout(self, confluence_client):
        confluence_client.session.get.return_value = self._mock_response({})
        confluence_client._get('/path', timeout=60)
        call_args = confluence_client.session.get.call_args
        assert call_args[1]['timeout'] == 60

    def test_retry_on_failure(self, confluence_client):
        exc = requests.ConnectionError('connection failed')
        ok_resp = self._mock_response({'ok': True})
        confluence_client.session.get.side_effect = [exc, ok_resp]
        with patch('time.sleep'):
            result = confluence_client._get('/path', retries=2)
        assert result == {'ok': True}
        assert confluence_client.session.get.call_count == 2

    def test_all_retries_exhausted(self, confluence_client):
        exc = requests.ConnectionError('fail')
        confluence_client.session.get.side_effect = [exc, exc, exc]
        with patch('time.sleep'):
            with pytest.raises(requests.ConnectionError):
                confluence_client._get('/path', retries=3)

    def test_http_error_raised(self, confluence_client):
        resp = MagicMock()
        resp.status_code = 401
        resp.raise_for_status.side_effect = requests.HTTPError(response=resp)
        confluence_client.session.get.side_effect = [resp, resp, resp]
        with patch('time.sleep'):
            with pytest.raises(requests.HTTPError):
                confluence_client._get('/path', retries=3)

    def test_timeout_error(self, confluence_client):
        exc = requests.Timeout('timeout')
        confluence_client.session.get.side_effect = [exc, exc, exc]
        with patch('time.sleep'):
            with pytest.raises(requests.Timeout):
                confluence_client._get('/path', retries=3)

    def test_malformed_json(self, confluence_client):
        resp = MagicMock()
        resp.status_code = 200
        resp.raise_for_status.return_value = None
        resp.json.side_effect = ValueError('bad json')
        confluence_client.session.get.return_value = resp
        with pytest.raises(ValueError):
            confluence_client._get('/path')

    def test_absolute_url_not_prefixed(self, confluence_client):
        confluence_client.session.get.return_value = self._mock_response({})
        confluence_client._get('https://other.com/path')
        call_args = confluence_client.session.get.call_args
        assert call_args[0][0] == 'https://other.com/path'

    def test_exponential_backoff(self, confluence_client):
        exc = requests.ConnectionError('fail')
        ok_resp = self._mock_response({'ok': True})
        confluence_client.session.get.side_effect = [exc, exc, ok_resp]
        with patch('time.sleep') as mock_sleep:
            confluence_client._get('/path', retries=3)
        # First retry: 2^0=1, second retry: 2^1=2
        assert mock_sleep.call_args_list[0] == call(1)
        assert mock_sleep.call_args_list[1] == call(2)


# ===================================================================
# Space operations
# ===================================================================

class TestListSpaces:
    def test_single_page(self, confluence_client):
        data = {
            'results': [{'key': 'NOC', 'name': 'NOC Ops'}],
            'size': 1,
        }
        confluence_client.session.get.return_value = MagicMock(
            status_code=200, json=MagicMock(return_value=data),
            raise_for_status=MagicMock(),
        )
        spaces = confluence_client.list_spaces()
        assert len(spaces) == 1
        assert spaces[0]['key'] == 'NOC'

    def test_empty_spaces(self, confluence_client):
        data = {'results': [], 'size': 0}
        confluence_client.session.get.return_value = MagicMock(
            status_code=200, json=MagicMock(return_value=data),
            raise_for_status=MagicMock(),
        )
        assert confluence_client.list_spaces() == []

    def test_pagination(self, confluence_client):
        page1 = {'results': [{'key': 'A'}] * 100, 'size': 100}
        page2 = {'results': [{'key': 'B'}], 'size': 1}
        resp1 = MagicMock(json=MagicMock(return_value=page1), raise_for_status=MagicMock())
        resp2 = MagicMock(json=MagicMock(return_value=page2), raise_for_status=MagicMock())
        confluence_client.session.get.side_effect = [resp1, resp2]
        spaces = confluence_client.list_spaces(limit=100)
        assert len(spaces) == 101


class TestGetSpace:
    def test_success(self, confluence_client):
        data = make_space_response()
        confluence_client.session.get.return_value = MagicMock(
            status_code=200, json=MagicMock(return_value=data),
            raise_for_status=MagicMock(),
        )
        result = confluence_client.get_space('NOC')
        assert result['key'] == 'NOC'


# ===================================================================
# Page operations
# ===================================================================

class TestGetPages:
    def test_success(self, confluence_client):
        data = make_pages_response([make_confluence_page()])
        confluence_client.session.get.return_value = MagicMock(
            status_code=200, json=MagicMock(return_value=data),
            raise_for_status=MagicMock(),
        )
        result = confluence_client.get_pages('NOC')
        assert len(result['results']) == 1

    def test_custom_expand(self, confluence_client):
        data = make_pages_response([])
        confluence_client.session.get.return_value = MagicMock(
            status_code=200, json=MagicMock(return_value=data),
            raise_for_status=MagicMock(),
        )
        confluence_client.get_pages('NOC', expand='body.storage')
        call_args = confluence_client.session.get.call_args
        assert call_args[1]['params']['expand'] == 'body.storage'


class TestGetAllPages:
    def test_single_batch(self, confluence_client):
        page = make_confluence_page()
        data = make_pages_response([page], size=1)
        confluence_client.session.get.return_value = MagicMock(
            status_code=200, json=MagicMock(return_value=data),
            raise_for_status=MagicMock(),
        )
        result = confluence_client.get_all_pages('NOC')
        assert len(result) == 1

    def test_multi_page_pagination(self, confluence_client):
        pages_batch1 = [make_confluence_page(page_id=str(i)) for i in range(50)]
        pages_batch2 = [make_confluence_page(page_id=str(i)) for i in range(50, 60)]
        data1 = make_pages_response(pages_batch1, size=50, total=60)
        data2 = make_pages_response(pages_batch2, size=10, total=60)
        resp1 = MagicMock(json=MagicMock(return_value=data1), raise_for_status=MagicMock())
        resp2 = MagicMock(json=MagicMock(return_value=data2), raise_for_status=MagicMock())
        confluence_client.session.get.side_effect = [resp1, resp2]
        result = confluence_client.get_all_pages('NOC')
        assert len(result) == 60

    def test_empty_space(self, confluence_client):
        data = make_pages_response([], size=0)
        confluence_client.session.get.return_value = MagicMock(
            status_code=200, json=MagicMock(return_value=data),
            raise_for_status=MagicMock(),
        )
        result = confluence_client.get_all_pages('EMPTY')
        assert result == []

    def test_progress_callback(self, confluence_client):
        page = make_confluence_page()
        data = make_pages_response([page], size=1, total=1)
        confluence_client.session.get.return_value = MagicMock(
            status_code=200, json=MagicMock(return_value=data),
            raise_for_status=MagicMock(),
        )
        progress = []
        confluence_client.get_all_pages('NOC', on_progress=lambda f, t: progress.append((f, t)))
        assert len(progress) >= 1

    def test_duplicate_pages_preserved(self, confluence_client):
        """If API returns duplicates, they are passed through."""
        p = make_confluence_page(page_id='111')
        data = make_pages_response([p, p], size=2)
        confluence_client.session.get.return_value = MagicMock(
            status_code=200, json=MagicMock(return_value=data),
            raise_for_status=MagicMock(),
        )
        result = confluence_client.get_all_pages('NOC')
        assert len(result) == 2


class TestGetPage:
    def test_success(self, confluence_client):
        page = make_confluence_page(page_id='999')
        confluence_client.session.get.return_value = MagicMock(
            status_code=200, json=MagicMock(return_value=page),
            raise_for_status=MagicMock(),
        )
        result = confluence_client.get_page('999')
        assert result['id'] == '999'


# ===================================================================
# History and restrictions
# ===================================================================

class TestGetHistory:
    def test_success(self, confluence_client):
        data = {'lastUpdated': {'when': '2024-01-01'}}
        confluence_client.session.get.return_value = MagicMock(
            status_code=200, json=MagicMock(return_value=data),
            raise_for_status=MagicMock(),
        )
        result = confluence_client.get_history('12345')
        assert result == data

    def test_error_returns_none(self, confluence_client):
        confluence_client.session.get.side_effect = requests.ConnectionError('fail')
        result = confluence_client.get_history('12345')
        assert result is None


class TestGetVersions:
    def test_success(self, confluence_client):
        data = {'results': [{'number': 1}, {'number': 2}], 'size': 2}
        confluence_client.session.get.return_value = MagicMock(
            status_code=200, json=MagicMock(return_value=data),
            raise_for_status=MagicMock(),
        )
        result = confluence_client.get_versions('12345')
        assert len(result) == 2

    def test_error_returns_empty(self, confluence_client):
        confluence_client.session.get.side_effect = requests.ConnectionError('fail')
        result = confluence_client.get_versions('12345')
        assert result == []


class TestGetRestrictions:
    def test_success(self, confluence_client):
        data = {'read': {'restrictions': {'user': []}}}
        confluence_client.session.get.return_value = MagicMock(
            status_code=200, json=MagicMock(return_value=data),
            raise_for_status=MagicMock(),
        )
        result = confluence_client.get_restrictions('12345')
        assert result is not None

    def test_403_returns_none(self, confluence_client):
        resp = MagicMock()
        resp.status_code = 403
        exc = requests.HTTPError(response=resp)
        confluence_client.session.get.return_value = MagicMock(
            raise_for_status=MagicMock(side_effect=exc),
        )
        result = confluence_client.get_restrictions('12345')
        assert result is None

    def test_404_returns_none(self, confluence_client):
        resp = MagicMock()
        resp.status_code = 404
        exc = requests.HTTPError(response=resp)
        confluence_client.session.get.return_value = MagicMock(
            raise_for_status=MagicMock(side_effect=exc),
        )
        result = confluence_client.get_restrictions('12345')
        assert result is None

    def test_connection_error_returns_none(self, confluence_client):
        confluence_client.session.get.side_effect = requests.ConnectionError('fail')
        result = confluence_client.get_restrictions('12345')
        assert result is None


# ===================================================================
# fetch_page_extras
# ===================================================================

class TestFetchPageExtras:
    def test_fetches_all_extras(self, confluence_client):
        page = make_confluence_page()
        ver_data = {'results': [{'number': 1}], 'size': 1}
        restr_data = {'read': {}}

        def mock_get(url, **kwargs):
            resp = MagicMock()
            resp.raise_for_status.return_value = None
            if '/version' in url:
                resp.json.return_value = ver_data
            elif '/restriction' in url:
                resp.json.return_value = restr_data
            else:
                resp.json.return_value = {}
            return resp

        confluence_client.session.get.side_effect = mock_get
        result = confluence_client.fetch_page_extras([page], max_workers=1)
        assert '12345' in result
        assert len(result['12345']['revisions']) == 1

    def test_empty_pages_list(self, confluence_client):
        result = confluence_client.fetch_page_extras([])
        assert result == {}

    def test_partial_failure_continues(self, confluence_client):
        page = make_confluence_page()

        call_count = [0]
        def mock_get(url, **kwargs):
            call_count[0] += 1
            resp = MagicMock()
            if '/version' in url:
                resp.raise_for_status.side_effect = requests.ConnectionError('fail')
                raise requests.ConnectionError('fail')
            resp.raise_for_status.return_value = None
            if '/restriction' in url:
                resp.json.return_value = {}
            else:
                resp.json.return_value = {'results': [], 'size': 0}
            return resp

        confluence_client.session.get.side_effect = mock_get
        result = confluence_client.fetch_page_extras([page], max_workers=1)
        # Should still return result despite the version-fetch failure
        assert '12345' in result


# ===================================================================
# READ-ONLY PROOF: No POST/PUT/PATCH/DELETE
# ===================================================================

class TestReadOnlyContract:
    """Verify the client never issues mutating HTTP methods."""

    def test_session_has_no_post_method_calls(self, confluence_client):
        """Scan all public methods and ensure none call session.post/put/patch/delete."""
        import inspect
        source = inspect.getsource(ConfluenceClient)
        for method in ('post', 'put', 'patch', 'delete'):
            assert f'.{method}(' not in source, \
                f'ConfluenceClient source contains .{method}() call'

    def test_session_post_not_called_during_get_all_pages(self, confluence_client):
        data = make_pages_response([make_confluence_page()], size=1)
        confluence_client.session.get.return_value = MagicMock(
            json=MagicMock(return_value=data), raise_for_status=MagicMock(),
        )
        confluence_client.get_all_pages('NOC')
        confluence_client.session.post.assert_not_called()
        confluence_client.session.put.assert_not_called()
        confluence_client.session.delete.assert_not_called()

    def test_session_post_not_called_during_extras(self, confluence_client):
        page = make_confluence_page()

        def mock_get(url, **kwargs):
            resp = MagicMock()
            resp.raise_for_status.return_value = None
            resp.json.return_value = {'results': [], 'size': 0}
            resp.content = b''
            return resp

        confluence_client.session.get.side_effect = mock_get
        confluence_client.fetch_page_extras([page], max_workers=1)
        confluence_client.session.post.assert_not_called()
        confluence_client.session.put.assert_not_called()
        confluence_client.session.delete.assert_not_called()
