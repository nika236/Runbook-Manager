"""Dashboard API -- reads from file store and metadata store.

No requests are made to Confluence from this module.
"""

from flask import Blueprint, jsonify, current_app

dashboard_bp = Blueprint('dashboard', __name__, url_prefix='/api/dashboard')


def _store():
    return current_app.extensions['page_store']


def _meta():
    return current_app.extensions['metadata_store']


@dashboard_bp.route('/stats', methods=['GET'])
def stats():
    data = _store().get_stats(metadata_store=_meta())
    return jsonify(data)


@dashboard_bp.route('/reload-cache', methods=['POST'])
def reload_cache():
    """Force-reload metadata from disk and invalidate stats cache.

    Call after external scripts (assign_owners, apply_classification, etc.)
    modify metadata files outside the running Flask process.
    """
    meta = _meta()
    meta.load_cache(force=True)
    _store().invalidate_stats_cache()
    return jsonify({'status': 'ok', 'records': len(meta._cache)})


@dashboard_bp.route('/recent-activity', methods=['GET'])
def recent_activity():
    entries = _meta().get_recent_activity(limit=50)
    mapped = []
    for e in entries:
        details = e.get('details', {})
        desc_parts = []
        for field, change in details.items():
            if isinstance(change, dict):
                desc_parts.append(f'{field}: {change.get("old")} -> {change.get("new")}')
            else:
                desc_parts.append(f'{field}: {change}')
        mapped.append({
            'page_id': e.get('page_id'),
            'space_key': e.get('space_key'),
            'runbook_title': e.get('page_id'),
            'title': e.get('page_id'),
            'change_description': '; '.join(desc_parts) if desc_parts else e.get('action', ''),
            'description': '; '.join(desc_parts) if desc_parts else e.get('action', ''),
            'changed_by': e.get('user', ''),
            'user': e.get('user', ''),
            'changed_at': e.get('timestamp', ''),
            'date': e.get('timestamp', ''),
            'action': e.get('action', ''),
            'details': details,
        })
    return jsonify({'activity': mapped, 'activities': mapped})


@dashboard_bp.route('/stale', methods=['GET'])
def stale_runbooks():
    stale = _store().get_stale_pages(metadata_store=_meta())
    items = []
    for p in stale:
        entry = dict(p)
        entry['id'] = str(p.get('confluence_page_id', ''))
        entry['confluence_id'] = entry['id']
        entry['status'] = p.get('local_status', 'stale')
        items.append(entry)
    return jsonify({'runbooks': items, 'stale': items})
