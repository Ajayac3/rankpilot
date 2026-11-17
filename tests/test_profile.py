#!/usr/bin/env python3
"""Proves the productization seam: the same engine produces tenant-specific output
driven only by the active site profile, with no NRI/legal data hardcoded.
Run from rankpilot/: python3 tests/test_profile.py
"""
import os, sys, json, importlib
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

pass_ = fail = 0
def ok(c, l):
    global pass_, fail
    print(('  ✅ ' if c else '  ❌ ') + l)
    pass_ += 1 if c else 0
    fail += 0 if c else 1

def schema_for(profile):
    os.environ['SITE_PROFILE'] = profile
    import core.profile, utils.schema_generator
    importlib.reload(core.profile)
    importlib.reload(utils.schema_generator)
    return utils.schema_generator

print("PROFILE LOADER")
from core.profile import load_profile, compliance_scan
nri = load_profile('example-legal')
den = load_profile('example-dental')
ok(nri['firm_info']['name'] == 'Example Legal Firm', 'NRI profile loads')
ok(den['firm_info']['name'] == 'BrightSmile Dental Studio', 'dental profile loads')
ok(nri['compliance_ruleset'] == 'legal-in-bci-rule36', 'NRI selects the Rule 36 ruleset')

print("SCHEMA GENERATOR — NRI tenant")
sg = schema_for('example-legal')
org = sg._organization_schema()
ok(org['name'] == 'Example Legal Firm', 'NRI org schema carries the NRI firm')
ok(any('NRI' in k for k in org['knowsAbout']), 'NRI knowsAbout present')
ok(len(org['employee']) >= 2, 'NRI advocates present in schema')

print("SCHEMA GENERATOR — different vertical (genericity proof)")
sg = schema_for('example-dental')
org = sg._organization_schema()
blob = json.dumps(org)
ok(org['name'] == 'BrightSmile Dental Studio', 'dental org schema carries the dental firm')
ok('NRI' not in blob and '498A' not in blob and 'Punjab' not in blob, 'NO NRI/legal data leaks into dental output')
ok('Dental' in blob or 'Implant' in blob, 'dental topics present in schema')

print("COMPLIANCE RULESETS")
ok(compliance_scan('we are the best lawyer in town', 'legal-in-bci-rule36') == ['best lawyer'], 'legal ruleset catches "best lawyer"')
ok(compliance_scan('we are the best lawyer in town', 'generic') == [], 'generic ruleset does not over-block')
ok(compliance_scan('guaranteed results every time', 'generic') == ['guaranteed results'], 'generic ruleset catches "guaranteed results"')

print(f"\n{pass_} passed, {fail} failed")
sys.exit(1 if fail else 0)
