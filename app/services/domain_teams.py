"""Central domain-to-team mapping.

Single authoritative source for domain-team relationships used by:
- Classification logic
- Backend validation
- API responses
- UI filters
- Tests

Loads from app/config/domain_teams.json at import time.
"""

import json
import re
import logging
from pathlib import Path

logger = logging.getLogger(__name__)

_CONFIG_PATH = Path(__file__).resolve().parent.parent / 'config' / 'domain_teams.json'


def _load_config():
    """Load and parse domain_teams.json."""
    with open(_CONFIG_PATH, 'r', encoding='utf-8') as f:
        return json.load(f)


_CONFIG = _load_config()

# ---- Public constants derived from the config ----

DOMAIN_TEAMS = {}       # {domain_name: [team_name, ...]}
TEAM_TO_DOMAIN = {}     # {team_name: domain_name}
ACTIVE_DOMAINS = set()  # set of active domain names
RETIRED_DOMAINS = {}    # {domain_name: status_string}
ALL_TEAMS = set()       # set of all active team names

for domain_name, domain_info in _CONFIG.get('domains', {}).items():
    teams = domain_info.get('teams', [])
    DOMAIN_TEAMS[domain_name] = list(teams)
    ACTIVE_DOMAINS.add(domain_name)
    for team in teams:
        TEAM_TO_DOMAIN[team] = domain_name
        ALL_TEAMS.add(team)

for domain_name, status in _CONFIG.get('retired', {}).items():
    RETIRED_DOMAINS[domain_name] = status

# Slugified lookup tables for normalization
DOMAIN_SLUGS = {}  # {slug: display_name}
TEAM_SLUGS = {}    # {slug: display_name}


def _slugify(name):
    """Create a stable slug from a display name."""
    return re.sub(r'[^a-z0-9]+', '-', name.lower()).strip('-')


for d in ACTIVE_DOMAINS:
    DOMAIN_SLUGS[_slugify(d)] = d

for t in ALL_TEAMS:
    TEAM_SLUGS[_slugify(t)] = t


# ---- Validation functions ----

def is_valid_domain(domain):
    """Check if a domain name is an active domain."""
    return domain in ACTIVE_DOMAINS


def is_retired_domain(domain):
    """Check if a domain name is retired."""
    return domain in RETIRED_DOMAINS


def is_valid_team(team):
    """Check if a team name is a known active team."""
    return team in ALL_TEAMS


def get_domain_for_team(team):
    """Return the parent domain for a team, or None."""
    return TEAM_TO_DOMAIN.get(team)


def is_valid_domain_team_pair(domain, team):
    """Validate that a team belongs to the given domain.

    Returns True if:
    - team is None (domain-only assignment is valid)
    - team belongs to the given domain
    """
    if team is None:
        return True
    return TEAM_TO_DOMAIN.get(team) == domain


def get_teams_for_domain(domain):
    """Return list of teams for a domain, or empty list."""
    return list(DOMAIN_TEAMS.get(domain, []))


def get_domain_teams_config():
    """Return the full config dict for API responses."""
    return {
        'domains': {
            d: {'teams': DOMAIN_TEAMS[d]}
            for d in sorted(ACTIVE_DOMAINS)
        },
        'retired': dict(RETIRED_DOMAINS),
        'all_teams': sorted(ALL_TEAMS),
        'version': _CONFIG.get('version', 1),
    }


def validate_domain_team_update(domain, team):
    """Validate a domain/team assignment for metadata update.

    Returns (is_valid, error_message).
    """
    if domain is not None and not is_valid_domain(domain):
        if is_retired_domain(domain):
            return False, f'Domain "{domain}" is retired and cannot receive new assignments'
        return False, f'Unknown domain: "{domain}"'

    if team is not None:
        if not is_valid_team(team):
            return False, f'Unknown team: "{team}"'
        if domain is None:
            return False, 'Team cannot be set without a domain'
        if not is_valid_domain_team_pair(domain, team):
            expected = get_domain_for_team(team)
            return False, (f'Team "{team}" belongs to domain "{expected}", '
                           f'not "{domain}"')

    return True, None
