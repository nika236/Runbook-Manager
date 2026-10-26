"""Runbooks API -- reads from file store, writes metadata locally only.

No requests are made to Confluence from this module.
"""

from flask import Blueprint, request, jsonify, current_app
from app.services.confluence_renderer import RenderContext, storage_body_is_empty
from app.services.domain_teams import validate_domain_team_update, get_domain_teams_config

runbooks_bp = Blueprint('runbooks', __name__, url_prefix='/api')

UPDATABLE_FIELDS = {
    'category', 'domain', 'priority', 'owner', 'reviewer', 'team',
    'local_status', 'review_date', 'notes', 'related_pages', 'tags',
}


def _store():
    return current_app.extensions['page_store']


def _meta():
    return current_app.extensions['metadata_store']


def _render_context(space_key, page_id, page=None):
    """Build the renderer context for one page.

    Supplies a title resolver for internal links, and the canonical Confluence
    URL used by "Open in Confluence" fallbacks. No attachment data is mirrored,
    so referenced images render with the "not mirrored" fallback.
    """
    store = _store()
    page = page if page is not None else store.get_page(page_id)
    return RenderContext(
        space_key=space_key,
        page_id=str(page_id),
        page_url=(page or {}).get('confluence_url'),
        site_base_url=current_app.config.get('CONFLUENCE_SITE_BASE_URL', ''),
        resolve_page=store.find_page_by_title,
    )


# ------------------------------------------------------------------
# Public config (non-secret values only)
# ------------------------------------------------------------------

@runbooks_bp.route('/config/public', methods=['GET'])
def public_config():
    return jsonify({
        'confluence_site_base_url': current_app.config.get('CONFLUENCE_SITE_BASE_URL', ''),
    })


@runbooks_bp.route('/config/domain-teams', methods=['GET'])
def domain_teams_config():
    """Return the authoritative domain-to-team mapping."""
    return jsonify(get_domain_teams_config())


# ------------------------------------------------------------------
# Spaces
# ------------------------------------------------------------------

@runbooks_bp.route('/spaces', methods=['GET'])
def list_spaces():
    return jsonify({'spaces': _store().get_spaces()})


@runbooks_bp.route('/spaces/<space_key>', methods=['GET'])
def get_space(space_key):
    spaces = _store().get_spaces()
    for s in spaces:
        if s.get('key') == space_key:
            return jsonify(s)
    return jsonify({'error': 'Space not found'}), 404


@runbooks_bp.route('/spaces/<space_key>/tree', methods=['GET'])
def get_tree(space_key):
    return jsonify({'tree': _store().get_tree(space_key)})


# ------------------------------------------------------------------
# Pages (read from file store + local metadata)
# ------------------------------------------------------------------

@runbooks_bp.route('/spaces/<space_key>/pages', methods=['GET'])
def list_pages(space_key):
    content_type = request.args.get('content_type', 'page')
    wl_filter = request.args.get('wl_filter')
    meta_store = _meta()

    pages = _store().get_all_pages(
        space_key=space_key,
        content_type=content_type if content_type != 'all' else None,
        wl_filter=wl_filter,
        metadata_store=meta_store if wl_filter else None,
    )

    enriched = []
    for p in pages:
        pid = str(p.get('confluence_page_id', ''))
        entry = dict(p)
        entry.update(meta_store.get(space_key, pid))
        enriched.append(entry)

    # Status filter (accept both 'local_status' and 'status')
    status_filter = request.args.get('local_status') or request.args.get('status')
    if status_filter:
        if status_filter != 'archived':
            enriched = [r for r in enriched if r.get('local_status') != 'archived']
        enriched = [r for r in enriched if r.get('local_status') == status_filter]
    else:
        enriched = [r for r in enriched if r.get('local_status') != 'archived']

    for param in ('priority', 'category', 'domain', 'owner', 'team', 'sync_status'):
        value = request.args.get(param)
        if value:
            enriched = [r for r in enriched if r.get(param) == value]

    label = request.args.get('label')
    if label:
        enriched = [r for r in enriched if label in (r.get('labels') or [])]

    review_reason = request.args.get('review_reason')
    if review_reason:
        enriched = [r for r in enriched if review_reason in (r.get('review_reasons') or [])]

    search = request.args.get('search')
    if search:
        search_lower = search.lower()
        enriched = [r for r in enriched
                    if search_lower in (r.get('title') or '').lower()]

    # Accept both sort_order and sort_dir
    sort_by = request.args.get('sort_by', 'updated_at')
    sort_order = request.args.get('sort_order') or request.args.get('sort_dir', 'desc')
    reverse = sort_order == 'desc'
    enriched.sort(key=lambda r: r.get(sort_by) or '', reverse=reverse)

    page = request.args.get('page', 1, type=int)
    per_page = request.args.get('per_page', 50, type=int)
    per_page = min(per_page, 200)

    total = len(enriched)
    start = (page - 1) * per_page
    end = start + per_page
    page_items = enriched[start:end]
    pages_count = (total + per_page - 1) // per_page if per_page > 0 else 1

    return jsonify({
        'pages': page_items,
        'total': total,
        'page': page,
        'per_page': per_page,
        'pages_count': pages_count,
    })


@runbooks_bp.route('/spaces/<space_key>/pages/<page_id>', methods=['GET'])
def get_page(space_key, page_id):
    page = _store().get_page(page_id)
    if not page:
        return jsonify({'error': 'Page not found'}), 404

    data = dict(page)
    raw_content = _store().get_page_content(space_key, page_id)
    render = current_app.extensions.get('render_content')
    if render and raw_content:
        data['content'] = render(raw_content, _render_context(space_key, page_id, page))
    else:
        data['content'] = raw_content
    data['content_is_empty'] = storage_body_is_empty(raw_content)
    data.update(_meta().get(space_key, page_id))
    data['audit_logs'] = []
    return jsonify(data)


@runbooks_bp.route('/spaces/<space_key>/pages/<page_id>/content', methods=['GET'])
def get_page_content(space_key, page_id):
    """Return the rendered HTML body for a page."""
    content = _store().get_page_content(space_key, page_id)
    if content is None:
        return jsonify({'error': 'Content not found'}), 404
    fmt = request.args.get('format', 'html')
    if fmt == 'text':
        text = _store().get_page_text(space_key, page_id)
        return jsonify({'content': text or '', 'format': 'text'})
    render = current_app.extensions.get('render_content')
    if render and content:
        rendered = render(content, _render_context(space_key, page_id))
    else:
        rendered = content
    return jsonify({'content': rendered, 'format': 'html'})


@runbooks_bp.route('/spaces/<space_key>/pages/<page_id>/revisions', methods=['GET'])
def get_revisions(space_key, page_id):
    return jsonify({'revisions': _store().get_revisions(space_key, page_id)})


# ------------------------------------------------------------------
# Metadata (application-owned, local writes only)
# ------------------------------------------------------------------

@runbooks_bp.route('/spaces/<space_key>/pages/<page_id>/metadata', methods=['GET'])
def get_metadata(space_key, page_id):
    return jsonify(_meta().get(space_key, page_id))


@runbooks_bp.route('/spaces/<space_key>/pages/<page_id>/metadata', methods=['PUT'])
def update_metadata(space_key, page_id):
    """Update application-owned metadata. Writes to local JSON file only."""
    page = _store().get_page(page_id)
    if not page:
        return jsonify({'error': 'Page not found'}), 404

    data = request.get_json()
    if not data:
        return jsonify({'error': 'No JSON body provided'}), 400

    fields = {k: v for k, v in data.items() if k in UPDATABLE_FIELDS}
    if not fields:
        return jsonify(_meta().get(space_key, page_id))

    # Validate domain-team relationship
    new_domain = fields.get('domain', _meta().get(space_key, page_id).get('domain'))
    new_team = fields.get('team', _meta().get(space_key, page_id).get('team'))
    if 'domain' in fields or 'team' in fields:
        # If domain is being changed, clear incompatible team
        if 'domain' in fields and 'team' not in fields:
            current_team = _meta().get(space_key, page_id).get('team')
            if current_team:
                valid, _ = validate_domain_team_update(new_domain, current_team)
                if not valid:
                    fields['team'] = None
                    new_team = None
        valid, error = validate_domain_team_update(new_domain, new_team)
        if not valid:
            return jsonify({'error': error}), 400

    updated = _meta().update(space_key, page_id, fields)
    return jsonify(updated)


@runbooks_bp.route('/pages/bulk-update', methods=['POST'])
def bulk_update():
    """Bulk update metadata for multiple pages. Local writes only."""
    data = request.get_json()
    if not data:
        return jsonify({'error': 'No JSON body provided'}), 400

    # Accept both formats: {items:[...], fields:{...}} or {ids:[...], updates:{...}}
    items = data.get('items', [])
    fields = data.get('fields') or data.get('updates', {})

    if not items and 'ids' in data:
        items = data['ids']

    if not items:
        return jsonify({'error': 'No items provided'}), 400
    if not fields:
        return jsonify({'error': 'No fields to update'}), 400

    fields = {k: v for k, v in fields.items() if k in UPDATABLE_FIELDS}

    tuples = []
    for item in items:
        if isinstance(item, dict):
            tuples.append((item.get('space_key', ''), str(item.get('page_id', ''))))
        elif isinstance(item, str):
            parts = item.split('/', 1)
            if len(parts) == 2:
                tuples.append((parts[0], parts[1]))
            else:
                page = _store().get_page(item)
                if page:
                    tuples.append((page.get('space_key', ''), item))

    result = _meta().bulk_update(tuples, fields)
    return jsonify(result)


# ------------------------------------------------------------------
# WL pages endpoint
# ------------------------------------------------------------------

@runbooks_bp.route('/wl/pages', methods=['GET'])
def wl_pages():
    """List WL-classified pages (Without Label)."""
    meta_store = _meta()
    wl_type = request.args.get('wl_type', 'label_missing')
    space_key = request.args.get('space_key')

    pages = _store().get_all_pages(
        space_key=space_key,
        content_type='page',
        wl_filter=wl_type,
        metadata_store=meta_store,
    )

    enriched = []
    for p in pages:
        pid = str(p.get('confluence_page_id', ''))
        sk = p.get('space_key', '')
        entry = dict(p)
        entry.update(meta_store.get(sk, pid))
        entry['id'] = pid
        enriched.append(entry)

    sort_by = request.args.get('sort_by', 'title')
    sort_order = request.args.get('sort_order') or request.args.get('sort_dir', 'asc')
    enriched.sort(key=lambda r: r.get(sort_by) or '', reverse=(sort_order == 'desc'))

    page = request.args.get('page', 1, type=int)
    per_page = min(request.args.get('per_page', 50, type=int), 200)
    total = len(enriched)
    start = (page - 1) * per_page
    page_items = enriched[start:start + per_page]

    return jsonify({
        'pages': page_items,
        'total': total,
        'page': page,
        'per_page': per_page,
        'pages_count': (total + per_page - 1) // per_page if per_page > 0 else 1,
        'wl_type': wl_type,
    })


# ------------------------------------------------------------------
# Teams & Domains browsing
# ------------------------------------------------------------------

@runbooks_bp.route('/teams-domains/summary', methods=['GET'])
def teams_domains_summary():
    """Return domain and team counts for the Teams & Domains page."""
    store = _store()
    meta_store = _meta()
    config = get_domain_teams_config()
    pages = store.get_all_pages(content_type='page')

    from collections import Counter
    domain_counts = Counter()
    team_counts = Counter()
    status_counts = Counter()

    for p in pages:
        pid = str(p.get('confluence_page_id', ''))
        sk = p.get('space_key', '')
        meta = meta_store.get(sk, pid)
        if meta.get('local_status') == 'archived':
            continue
        d = meta.get('domain')
        t = meta.get('team')
        cs = meta.get('classification_status')
        if d:
            domain_counts[d] += 1
        if t:
            team_counts[t] += 1
        if cs:
            status_counts[cs] += 1

    domains_list = []
    for domain_name in sorted(config['domains'].keys()):
        teams_info = []
        for team_name in config['domains'][domain_name]['teams']:
            teams_info.append({
                'name': team_name,
                'count': team_counts.get(team_name, 0),
            })
        domains_list.append({
            'name': domain_name,
            'count': domain_counts.get(domain_name, 0),
            'teams': teams_info,
        })

    teams_list = []
    for team_name in sorted(config.get('all_teams', [])):
        from app.services.domain_teams import TEAM_TO_DOMAIN
        parent = TEAM_TO_DOMAIN.get(team_name, '')
        teams_list.append({
            'name': team_name,
            'domain': parent,
            'count': team_counts.get(team_name, 0),
        })

    return jsonify({
        'domains': domains_list,
        'teams': teams_list,
        'classification_status_counts': dict(status_counts),
        'total_classified': sum(domain_counts.values()),
        'total_unassigned': len(pages) - sum(1 for p in pages
            if meta_store.get(p.get('space_key', ''),
                              str(p.get('confluence_page_id', ''))).get('domain')),
    })


@runbooks_bp.route('/teams-domains/pages', methods=['GET'])
def teams_domains_pages():
    """List pages filtered by domain and/or team."""
    store = _store()
    meta_store = _meta()
    pages = store.get_all_pages(content_type='page')

    domain_filter = request.args.get('domain')
    team_filter = request.args.get('team')
    cls_status_filter = request.args.get('classification_status')

    enriched = []
    for p in pages:
        pid = str(p.get('confluence_page_id', ''))
        sk = p.get('space_key', '')
        meta = meta_store.get(sk, pid)
        if meta.get('local_status') == 'archived':
            continue

        if domain_filter and meta.get('domain') != domain_filter:
            continue
        if team_filter and meta.get('team') != team_filter:
            continue
        if cls_status_filter and meta.get('classification_status') != cls_status_filter:
            continue

        entry = dict(p)
        entry.update(meta)
        entry['id'] = pid
        enriched.append(entry)

    search = request.args.get('search')
    if search:
        search_lower = search.lower()
        enriched = [r for r in enriched
                    if search_lower in (r.get('title') or '').lower()]

    sort_by = request.args.get('sort_by', 'title')
    sort_order = request.args.get('sort_order') or request.args.get('sort_dir', 'asc')
    enriched.sort(key=lambda r: r.get(sort_by) or '', reverse=sort_order == 'desc')

    page_num = request.args.get('page', 1, type=int)
    per_page = min(request.args.get('per_page', 25, type=int), 200)
    total = len(enriched)
    start = (page_num - 1) * per_page
    page_items = enriched[start:start + per_page]

    return jsonify({
        'pages': page_items,
        'total': total,
        'page': page_num,
        'per_page': per_page,
        'pages_count': (total + per_page - 1) // per_page if per_page > 0 else 1,
    })


# ------------------------------------------------------------------
# Filter values -- dynamic dropdowns for the content library
# ------------------------------------------------------------------

@runbooks_bp.route('/filter-values', methods=['GET'])
def filter_values():
    """Return distinct values for each filterable field across all pages."""
    store = _store()
    meta_store = _meta()
    pages = store.get_all_pages(content_type='page')

    domains = set()
    priorities = set()
    owners = set()
    teams = set()
    labels = set()
    review_reasons = set()

    for p in pages:
        pid = str(p.get('confluence_page_id', ''))
        sk = p.get('space_key', '')
        meta = meta_store.get(sk, pid)

        if meta.get('domain'):
            domains.add(meta['domain'])
        if meta.get('priority'):
            priorities.add(meta['priority'])
        if meta.get('owner'):
            owners.add(meta['owner'])
        if meta.get('team'):
            teams.add(meta['team'])
        for lbl in p.get('labels', []):
            labels.add(lbl)
        for reason in (meta.get('review_reasons') or []):
            review_reasons.add(reason)

    return jsonify({
        'domains': sorted(domains),
        'priorities': sorted(priorities),
        'owners': sorted(owners),
        'teams': sorted(teams),
        'labels': sorted(labels)[:100],
        'review_reasons': sorted(review_reasons),
    })


# ------------------------------------------------------------------
# Legacy compatibility routes
# ------------------------------------------------------------------

@runbooks_bp.route('/runbooks/', methods=['GET'])
def legacy_list_runbooks():
    """Legacy endpoint kept for frontend compatibility during migration."""
    store = _store()
    meta_store = _meta()
    pages = store.get_all_pages(content_type='page')

    enriched = []
    for p in pages:
        pid = str(p.get('confluence_page_id', ''))
        sk = p.get('space_key', '')
        entry = dict(p)
        meta = meta_store.get(sk, pid)
        entry.update(meta)
        entry['id'] = pid
        entry['confluence_id'] = pid
        entry['status'] = meta.get('local_status', 'imported')
        entry['domain'] = meta.get('domain') or meta.get('category')
        entry['team'] = meta.get('team') or meta.get('category')
        entry['content_preview'] = (p.get('title', '') + ' ')[:200]
        entry['migration_status'] = meta.get('local_status', 'imported')
        entry['is_stale'] = False
        enriched.append(entry)

    # Status filter (accept both 'status' and 'local_status')
    status_filter = request.args.get('status') or request.args.get('local_status')
    if status_filter:
        if status_filter != 'archived':
            enriched = [r for r in enriched if r.get('local_status') != 'archived']
        enriched = [r for r in enriched if r.get('local_status') == status_filter]
    else:
        enriched = [r for r in enriched if r.get('local_status') != 'archived']

    for param in ('priority', 'domain', 'team', 'owner'):
        value = request.args.get(param)
        if value:
            enriched = [r for r in enriched if r.get(param) == value]

    label = request.args.get('label')
    if label:
        enriched = [r for r in enriched if label in (r.get('labels') or [])]

    review_reason = request.args.get('review_reason')
    if review_reason:
        enriched = [r for r in enriched if review_reason in (r.get('review_reasons') or [])]

    wl_filter = request.args.get('wl_filter')
    if wl_filter == 'label_missing':
        enriched = [r for r in enriched if r.get('flag_label_missing')]
    elif wl_filter == 'taxonomy_unmapped':
        enriched = [r for r in enriched if r.get('flag_taxonomy_unmapped')]
    elif wl_filter == 'domain_missing':
        enriched = [r for r in enriched if r.get('flag_domain_missing')]

    search = request.args.get('search')
    if search:
        search_lower = search.lower()
        enriched = [r for r in enriched
                    if search_lower in (r.get('title') or '').lower()]

    sort_by = request.args.get('sort_by', 'updated_at')
    sort_order = request.args.get('sort_order') or request.args.get('sort_dir', 'desc')
    enriched.sort(key=lambda r: r.get(sort_by) or '', reverse=sort_order == 'desc')

    page_num = request.args.get('page', 1, type=int)
    per_page = min(request.args.get('per_page', 50, type=int), 200)
    total = len(enriched)
    start = (page_num - 1) * per_page
    page_items = enriched[start:start + per_page]

    return jsonify({
        'runbooks': page_items,
        'total': total,
        'page': page_num,
        'per_page': per_page,
        'pages': (total + per_page - 1) // per_page if per_page > 0 else 1,
    })


@runbooks_bp.route('/runbooks/<runbook_id>', methods=['GET'])
def legacy_get_runbook(runbook_id):
    """Legacy endpoint for single runbook."""
    store = _store()
    page = store.get_page(runbook_id)
    if not page:
        return jsonify({'error': 'Runbook not found'}), 404

    sk = page.get('space_key', '')
    meta = _meta().get(sk, runbook_id)
    data = dict(page)
    data.update(meta)
    data['id'] = runbook_id
    data['confluence_id'] = runbook_id
    data['content_preview'] = ''
    raw_content = store.get_page_content(sk, runbook_id)
    render = current_app.extensions.get('render_content')
    if render and raw_content:
        data['content'] = render(raw_content, _render_context(sk, runbook_id, page))
    else:
        data['content'] = raw_content
    data['content_is_empty'] = storage_body_is_empty(raw_content)
    data['audit_logs'] = []
    data['status'] = meta.get('local_status', 'imported')
    data['domain'] = meta.get('domain') or meta.get('category')
    data['team'] = meta.get('team')
    data['migration_status'] = meta.get('local_status', 'imported')
    return jsonify(data)


@runbooks_bp.route('/runbooks/<runbook_id>', methods=['PUT'])
def legacy_update_runbook(runbook_id):
    """Legacy PUT endpoint -- updates local metadata only."""
    page = _store().get_page(runbook_id)
    if not page:
        return jsonify({'error': 'Runbook not found'}), 404

    sk = page.get('space_key', '')
    data = request.get_json()
    if not data:
        return jsonify({'error': 'No JSON body provided'}), 400

    fields = {k: v for k, v in data.items() if k in UPDATABLE_FIELDS}

    if 'status' in data and 'local_status' not in data:
        fields['local_status'] = data['status']

    # Validate domain-team relationship (same rule as the modern metadata endpoint)
    if 'domain' in fields or 'team' in fields:
        current_meta = _meta().get(sk, runbook_id)
        new_domain = fields.get('domain', current_meta.get('domain'))
        new_team = fields.get('team', current_meta.get('team'))
        if 'domain' in fields and 'team' not in fields:
            current_team = current_meta.get('team')
            if current_team:
                valid, _ = validate_domain_team_update(new_domain, current_team)
                if not valid:
                    fields['team'] = None
                    new_team = None
        valid, error = validate_domain_team_update(new_domain, new_team)
        if not valid:
            return jsonify({'error': error}), 400

    if fields:
        _meta().update(sk, runbook_id, fields)

    meta = _meta().get(sk, runbook_id)
    result = dict(page)
    result.update(meta)
    result['id'] = runbook_id
    result['status'] = meta.get('local_status', 'imported')
    return jsonify(result)
