"""Subtree-based page exclusions.

Identifies pages that exist in the source inventory but are not eligible
runbooks (e.g. post-mortem records, templates, incident histories).

Exclusion is based on stable Confluence page IDs and ancestor relationships,
not page titles or content patterns.  The root page ID for each excluded
subtree is stored in app/config/exclusions.json.

This module never contacts Confluence and never modifies source content.
"""

import json
import logging
from pathlib import Path

logger = logging.getLogger(__name__)

_CONFIG_PATH = Path(__file__).resolve().parent.parent / 'config' / 'exclusions.json'


def _load_config():
    with open(_CONFIG_PATH, 'r', encoding='utf-8') as f:
        return json.load(f)


_CONFIG = _load_config()

# Set of root page IDs for excluded subtrees
EXCLUSION_ROOTS = {
    str(e['root_page_id'])
    for e in _CONFIG.get('subtree_exclusions', [])
}

# Map root_page_id -> exclusion metadata
EXCLUSION_INFO = {
    str(e['root_page_id']): e
    for e in _CONFIG.get('subtree_exclusions', [])
}


def get_exclusion_roots():
    """Return the set of root page IDs for all excluded subtrees."""
    return set(EXCLUSION_ROOTS)


def get_exclusion_info(root_page_id):
    """Return exclusion metadata for a given root page ID."""
    return EXCLUSION_INFO.get(str(root_page_id))


def resolve_excluded_page_ids(page_index):
    """Resolve all page IDs that belong to an excluded subtree.

    Uses the ancestors array stored in each page's page.json to determine
    membership.  A page is excluded if:
    - Its own page ID is an exclusion root, OR
    - Any of its ancestors' IDs is an exclusion root.

    Args:
        page_index: dict of {page_id: page_doc} from PageStore._index

    Returns:
        dict of {page_id: exclusion_root_page_id} for every excluded page.
    """
    excluded = {}  # page_id -> root_page_id

    for pid, doc in page_index.items():
        pid_str = str(pid)

        # Is this page itself an exclusion root?
        if pid_str in EXCLUSION_ROOTS:
            excluded[pid_str] = pid_str
            continue

        # Check ancestors
        for ancestor in (doc.get('ancestors') or []):
            ancestor_id = str(ancestor.get('id', ''))
            if ancestor_id in EXCLUSION_ROOTS:
                excluded[pid_str] = ancestor_id
                break

    return excluded


def is_excluded(page_id, excluded_set):
    """Check if a page ID is in the excluded set."""
    return str(page_id) in excluded_set


def get_exclusion_reason(page_id, excluded_set):
    """Return the exclusion reason and root page ID for an excluded page.

    Returns (reason, root_page_id) or (None, None) if not excluded.
    """
    pid = str(page_id)
    if pid not in excluded_set:
        return None, None
    root_id = excluded_set[pid]
    info = EXCLUSION_INFO.get(root_id, {})
    return info.get('reason', 'subtree_exclusion'), root_id
