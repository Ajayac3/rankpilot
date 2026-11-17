"""RankPilot — per-tenant Site Profile + Compliance Ruleset loader.

This is the productization seam (see PRODUCTIZATION.md): everything site-specific
lives in profiles/<name>/site_profile.yaml and compliance/rulesets/<id>.yaml — NO
client data is hardcoded in the engine. Select the active profile with the
SITE_PROFILE env var (defaults to example-legal so existing runs are
unchanged).
"""
import os
from pathlib import Path
import yaml

BASE_DIR = Path(__file__).parent.parent


def active_profile_name() -> str:
    return os.environ.get('SITE_PROFILE', 'example-legal')


def load_profile(name: str | None = None) -> dict:
    name = name or active_profile_name()
    path = BASE_DIR / 'profiles' / name / 'site_profile.yaml'
    if not path.is_file():
        raise FileNotFoundError(f'Site profile not found: {path}')
    with open(path, encoding='utf-8') as f:
        data = yaml.safe_load(f) or {}
    data['_name'] = name
    domain = data.get('domain', '')
    fi = data.setdefault('firm_info', {})
    fi.setdefault('name', data.get('name', ''))
    fi.setdefault('url', f'https://{domain}' if domain else '')
    fi.setdefault('logo', f'https://{domain}/images/logo.png' if domain else '')
    return data


def load_ruleset(ruleset_id: str) -> dict:
    path = BASE_DIR / 'compliance' / 'rulesets' / f'{ruleset_id}.yaml'
    if not path.is_file():
        return {'prohibited': []}
    with open(path, encoding='utf-8') as f:
        return yaml.safe_load(f) or {'prohibited': []}


def compliance_scan(text: str, ruleset_id: str) -> list[str]:
    """Return prohibited phrases found in text under the given ruleset (empty = clean)."""
    rs = load_ruleset(ruleset_id)
    t = (text or '').lower()
    return [p for p in rs.get('prohibited', []) if p.lower() in t]
