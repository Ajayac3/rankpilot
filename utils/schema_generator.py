"""
RankPilot — JSON-LD Schema Generator + Validator
Generates structured data for NRI legal service pages.
2.5x higher AI Overview inclusion with proper schema (Search Engine Land, 2025).
Validates locally with jsonschema — no API calls needed.
"""
import os, sys, json
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from core.config import TARGET_DOMAIN, FIRM_NAME, FIRM_EMAIL, FIRM_PHONE

BASE_URL = f'https://{TARGET_DOMAIN}'

FIRM_INFO = {
    'name':        FIRM_NAME,
    'url':         BASE_URL,
    'logo':        f'{BASE_URL}/images/logo.png',
    'phone':       FIRM_PHONE,
    'email':       FIRM_EMAIL,
    'address': {
        'streetAddress': 'SCO 18-19, Sector 9D',
        'addressLocality': 'Delhi',
        'addressRegion':   'Delhi',
        'postalCode':      '160017',
        'addressCountry':  'IN',
    },
    'geo': {'latitude': 30.7333, 'longitude': 76.7794},
    'serviceAreas': ['India', 'USA', 'Canada', 'United Kingdom', 'UAE',
                     'Australia', 'Singapore', 'New Zealand'],
    'barCouncil': 'Punjab and Haryana Bar Council',
}

ADVOCATES = [
    {
        'name':        'Navkiran Singh',
        'url':         f'{BASE_URL}/navkiran-singh/',
        'description': 'Senior Advocate with 20+ years specialising in NRI legal matters',
        'credential':  'Advocate, Punjab and Haryana High Court',
    },
    {
        'name':        'Example Example',
        'url':         f'{BASE_URL}/Example-Example/',
        'description': 'Advocate specialising in NRI criminal law and FIR quashing',
        'credential':  'Advocate, Punjab and Haryana High Court',
    },
    {
        'name':        'Navpreet Kaur Dhaliwal',
        'url':         f'{BASE_URL}/navpreet-kaur-dhaliwal/',
        'description': 'Advocate specialising in NRI family law and matrimonial disputes',
        'credential':  'Advocate, Punjab and Haryana High Court',
    },
]

SERVICE_SCHEMA = [
    {'slug': 'nri-property-dispute-lawyer',
     'name': 'NRI Property Dispute Legal Services',
     'desc': 'Legal assistance for NRIs with property encroachment, possession delays, title disputes'},
    {'slug': '498a-against-nri-husband',
     'name': '498A NRI Husband Defence',
     'desc': 'Expert legal defence for NRI husbands facing 498A IPC false cases'},
    {'slug': 'nri-divorce-lawyer-india',
     'name': 'NRI Divorce Legal Services',
     'desc': 'Divorce proceedings and foreign decree recognition for NRIs'},
    {'slug': 'criminal-litigation',
     'name': 'NRI Criminal Law Services',
     'desc': 'Bail, anticipatory bail, FIR quashing and criminal defence for NRIs'},
    {'slug': 'power-of-attorney-nri-india',
     'name': 'NRI Power of Attorney Services',
     'desc': 'Drafting and registration of Power of Attorney for NRI property transactions'},
    {'slug': 'all-you-need-to-know-about-oci-card',
     'name': 'OCI Card Services',
     'desc': 'OCI card application, renewal and related services for overseas citizens of India'},
]

# ── Productization seam: the active site profile overrides the defaults above, so
# the engine carries no client-specific data in code (see PRODUCTIZATION.md). The
# NRI profile reproduces the values above; SITE_PROFILE=<other> swaps the tenant. ──
from core.profile import load_profile as _load_profile
_P = _load_profile()
TARGET_DOMAIN = _P.get('domain', TARGET_DOMAIN)
BASE_URL = f'https://{TARGET_DOMAIN}'
FIRM_INFO = dict(_P.get('firm_info') or FIRM_INFO)
FIRM_INFO.setdefault('url', BASE_URL)
FIRM_INFO.setdefault('logo', f'{BASE_URL}/images/logo.png')
ADVOCATES = _P.get('advocates', ADVOCATES)
SERVICE_SCHEMA = _P.get('services', SERVICE_SCHEMA)
KNOWS_ABOUT = _P.get('knows_about', ['NRI Property Law', 'NRI Criminal Law', 'NRI Family Law',
                                     'Power of Attorney', 'OCI Card', 'FIR Quashing', '498A Defence'])


def _organization_schema() -> dict:
    return {
        '@context': 'https://schema.org',
        '@type': ['LegalService', 'Organization'],
        'name':  FIRM_INFO['name'],
        'url':   FIRM_INFO['url'],
        'logo':  FIRM_INFO['logo'],
        'telephone': FIRM_INFO['phone'],
        'email':     FIRM_INFO['email'],
        'address': {
            '@type':          'PostalAddress',
            'streetAddress':  FIRM_INFO['address']['streetAddress'],
            'addressLocality': FIRM_INFO['address']['addressLocality'],
            'addressRegion':  FIRM_INFO['address']['addressRegion'],
            'postalCode':     FIRM_INFO['address']['postalCode'],
            'addressCountry': FIRM_INFO['address']['addressCountry'],
        },
        'geo': {
            '@type':     'GeoCoordinates',
            'latitude':  FIRM_INFO['geo']['latitude'],
            'longitude': FIRM_INFO['geo']['longitude'],
        },
        'areaServed': FIRM_INFO['serviceAreas'],
        'knowsAbout': KNOWS_ABOUT,
        'memberOf': {'@type': 'Organization', 'name': FIRM_INFO['barCouncil']},
        'employee': [{'@type': 'Person', 'name': a['name'], 'url': a['url'],
                      'description': a['description']} for a in ADVOCATES],
    }


def _localbusiness_schema() -> dict:
    return {
        '@context': 'https://schema.org',
        '@type': 'LegalService',
        'name':  FIRM_INFO['name'],
        'url':   FIRM_INFO['url'],
        'telephone': FIRM_INFO['phone'],
        'email':     FIRM_INFO['email'],
        'address': {
            '@type':          'PostalAddress',
            'streetAddress':  FIRM_INFO['address']['streetAddress'],
            'addressLocality': FIRM_INFO['address']['addressLocality'],
            'addressRegion':  FIRM_INFO['address']['addressRegion'],
            'postalCode':     FIRM_INFO['address']['postalCode'],
            'addressCountry': FIRM_INFO['address']['addressCountry'],
        },
        'geo': {
            '@type':     'GeoCoordinates',
            'latitude':  FIRM_INFO['geo']['latitude'],
            'longitude': FIRM_INFO['geo']['longitude'],
        },
        'openingHours': 'Mo-Sa 09:00-18:00',
        'priceRange': '$$',
        'currenciesAccepted': 'INR, USD, GBP, CAD, AED',
        'paymentAccepted': 'Cash, Bank Transfer, PayPal',
        'areaServed': FIRM_INFO['serviceAreas'],
    }


def _service_page_schema(service: dict) -> dict:
    return {
        '@context': 'https://schema.org',
        '@type': 'Service',
        'name': service['name'],
        'description': service['desc'],
        'url': f'{BASE_URL}/{service["slug"]}/',
        'provider': {
            '@type': 'LegalService',
            'name':  FIRM_INFO['name'],
            'url':   FIRM_INFO['url'],
        },
        'areaServed': FIRM_INFO['serviceAreas'],
        'audience': {
            '@type': 'Audience',
            'audienceType': 'Non-Resident Indians (NRIs)',
        },
    }


def _person_schema(advocate: dict) -> dict:
    return {
        '@context': 'https://schema.org',
        '@type': 'Person',
        'name':        advocate['name'],
        'url':         advocate['url'],
        'description': advocate['description'],
        'hasCredential': {
            '@type': 'EducationalOccupationalCredential',
            'credentialCategory': advocate['credential'],
        },
        'worksFor': {'@type': 'LegalService', 'name': FIRM_INFO['name'], 'url': FIRM_INFO['url']},
    }


def _validate_schema(schema_obj: dict) -> bool:
    """Validate JSON-LD structure locally using jsonschema."""
    try:
        import jsonschema
        # Minimal schema.org object validation
        minimal_schema = {
            'type': 'object',
            'required': ['@context', '@type'],
            'properties': {
                '@context': {'type': 'string'},
                '@type': {'oneOf': [{'type': 'string'}, {'type': 'array'}]},
            }
        }
        jsonschema.validate(instance=schema_obj, schema=minimal_schema)
        return True
    except Exception as e:
        print(f'  ⚠️ Schema validation failed: {e}')
        return False


def generate_all_schemas(output_dir: str = None) -> dict:
    """
    Generate all JSON-LD schemas and save to output_dir.
    Returns dict of {filename: schema_dict}.
    """
    if output_dir is None:
        output_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                                  'data', 'schema_output')
    os.makedirs(output_dir, exist_ok=True)

    schemas = {}

    # Core schemas
    schemas['organization.json'] = _organization_schema()
    schemas['localbusiness.json'] = _localbusiness_schema()

    # Per-advocate schemas
    for adv in ADVOCATES:
        key = f'person_{adv["name"].lower().replace(" ", "_")}.json'
        schemas[key] = _person_schema(adv)

    # Per-service schemas
    for svc in SERVICE_SCHEMA:
        key = f'service_{svc["slug"].replace("-", "_")}.json'
        schemas[key] = _service_page_schema(svc)

    # Validate and save
    passed = 0
    for filename, schema in schemas.items():
        valid = _validate_schema(schema)
        path = os.path.join(output_dir, filename)
        with open(path, 'w', encoding='utf-8') as f:
            json.dump(schema, f, indent=2, ensure_ascii=False)
        status = '✅' if valid else '⚠️'
        print(f'  {status} {filename}')
        if valid:
            passed += 1

    print(f'\n  Schema generation complete: {passed}/{len(schemas)} valid → {output_dir}')
    return schemas


if __name__ == '__main__':
    generate_all_schemas()
