"""Sync API -- triggers read-only pull from Confluence to local file store.

The sync service only issues GET requests to Confluence.
No POST, PUT, or DELETE operations are performed.
"""

from flask import Blueprint, jsonify, current_app

sync_bp = Blueprint('sync', __name__, url_prefix='/api/sync')


def _sync():
    return current_app.extensions['sync_service']


def _store():
    return current_app.extensions['page_store']


@sync_bp.route('/full', methods=['POST'])
def sync_full():
    """Trigger a full read-only sync from Confluence."""
    config = current_app.config

    if not config.get('CONFLUENCE_BASE_URL') or not config.get('CONFLUENCE_EMAIL') \
            or not config.get('CONFLUENCE_API_TOKEN'):
        return jsonify({
            'error': 'Confluence is not configured. '
                     'Set CONFLUENCE_BASE_URL, CONFLUENCE_EMAIL, and CONFLUENCE_API_TOKEN.',
        }), 400

    space_keys = config.get('CONFLUENCE_SPACE_KEYS', [])
    if not space_keys:
        return jsonify({'error': 'No CONFLUENCE_SPACE_KEYS configured.'}), 400

    try:
        results = _sync().sync_all(space_keys)
        _store().reload()
        total = sum(r.get('total_pages', 0) for r in results)

        return jsonify({
            'total': total,
            'spaces': results,
        })
    except Exception as e:
        return jsonify({'error': f'Sync failed: {str(e)}'}), 500


@sync_bp.route('/incremental', methods=['POST'])
def sync_incremental():
    """Trigger an incremental sync (only changed pages via CQL)."""
    config = current_app.config

    if not config.get('CONFLUENCE_BASE_URL') or not config.get('CONFLUENCE_EMAIL') \
            or not config.get('CONFLUENCE_API_TOKEN'):
        return jsonify({
            'error': 'Confluence is not configured.',
        }), 400

    space_keys = config.get('CONFLUENCE_SPACE_KEYS', [])
    if not space_keys:
        return jsonify({'error': 'No CONFLUENCE_SPACE_KEYS configured.'}), 400

    try:
        results = _sync().sync_incremental(space_keys)
        _store().reload()

        return jsonify({
            'total': sum(r.get('updated', r.get('total_pages', 0)) for r in results),
            'spaces': results,
        })
    except Exception as e:
        return jsonify({'error': f'Sync failed: {str(e)}'}), 500


@sync_bp.route('/status', methods=['GET'])
def sync_status():
    status = _sync().get_sync_status()
    return jsonify(status)


@sync_bp.route('/runs', methods=['GET'])
def sync_runs():
    status = _sync().get_sync_status()
    return jsonify({'runs': status.get('recent_runs', [])})


@sync_bp.route('/confluence', methods=['POST'])
def legacy_sync_confluence():
    """Legacy endpoint -- redirects to full sync."""
    return sync_full()
