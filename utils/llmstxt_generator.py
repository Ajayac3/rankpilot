"""
RankPilot — llms.txt Generator
Generates /llms.txt for the site — a plain-text map of key pages
that helps AI systems (ChatGPT, Perplexity, Gemini) correctly cite the site.
Output: complete_website/llms.txt
"""
import os, sys
from datetime import date
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from core.config import TARGET_DOMAIN, FIRM_NAME, FIRM_EMAIL, FIRM_PHONE

# Legal service pages with descriptions
SERVICE_PAGES = [
    ('/nri-property-dispute-lawyer/',
     'Property encroachment, possession delays, title fraud, co-owner disputes for NRIs'),
    ('/criminal-litigation/',
     'NRI criminal defense: anticipatory bail, FIR quashing, proclaimed offender relief'),
    ('/498a-against-nri-husband/',
     'Defense strategy for NRI husbands facing false 498A IPC domestic violence cases'),
    ('/498a-nri-husband-defense-guide-2026/',
     'Comprehensive 2026 guide for NRI husbands on 498A defense and legal options'),
    ('/nri-divorce-lawyer-india/',
     'NRI divorce proceedings in India: mutual consent, contested, foreign decree recognition'),
    ('/power-of-attorney-nri-india/',
     'Drafting, registration and revocation of Power of Attorney for NRI property transactions'),
    ('/anticipatory-bail-be-granted-to-an-nri/',
     'Anticipatory bail eligibility and process for NRIs facing arrest in India'),
    ('/fir-quashing-for-nri/',
     'Quashing of FIR under Section 528 BNSS: grounds, High Court procedure and fees'),
    ('/oci-card-guide-for-nris/',
     'OCI card meaning, eligibility, benefits, limitations and rejection remedies for overseas citizens of India'),
    ('/impounding-of-passport/',
     'What passport impounding means, who can impound a passport under the Passports Act 1967, and release remedies for NRIs'),
    ('/look-out-circular/',
     'What a Look Out Circular is, who can issue an LOC, and how an NRI can get an LOC withdrawn or quashed'),
    ('/land-kabza/',
     'What land kabza (illegal possession) means and the civil and criminal remedies available to NRI owners in Punjab'),
    ('/nri-has-been-declared-a-proclaimed-offender/',
     'What a proclaimed offender declaration means for an NRI and how to get it set aside'),
    ('/all-you-need-to-know-about-fir/',
     'How FIR works in India: registration, quashing, bail options for NRIs'),
    ('/challenges-faced-by-nris-in-india/',
     'Common legal challenges NRIs face: property fraud, family disputes, criminal cases'),
    ('/change-in-date-of-birth-in-the-passport/',
     'Passport correction procedure for NRIs: date of birth, name changes'),
    ('/blog/', 'NRI legal articles: property law, criminal law, family law, OCI/passport'),
    ('/about-us/', 'About Example Legal Firm — team of advocates specialising in NRI cases'),
    ('/contact-us/', 'Contact Example Legal Firm about NRI legal matters'),
]

ADVOCATE_PAGES = [
    ('/our-team/', 'Our Team — Adv. A. Example (Founder & Managing Partner) and Adv. B. Example (Partner), Punjab & Haryana High Court, Delhi'),
]

SITE_INFO = {
    'name':    FIRM_NAME,
    'tagline': 'Expert legal services for Non-Resident Indians — property, criminal, family law',
    'location': 'Delhi, India',
    'serving':  'NRIs in USA, Canada, UK, UAE, Australia, Singapore, New Zealand',
    'phone':   FIRM_PHONE,
    'email':   FIRM_EMAIL,
}


def generate_llmstxt(site_domain: str = TARGET_DOMAIN,
                     output_path: str = None) -> str:
    base = f'https://{site_domain}'

    lines = [
        f'# {SITE_INFO["name"]}',
        '',
        f'> {SITE_INFO["tagline"]}.',
        f'> Location: {SITE_INFO["location"]}.',
        f'> Serving: {SITE_INFO["serving"]}.',
        '',
        '## Legal Services',
        '',
    ]
    for path, desc in SERVICE_PAGES:
        lines.append(f'- [{desc.split(":")[0].strip()}]({base}{path}): {desc}')

    lines += ['', '## Our Advocates', '']
    for path, desc in ADVOCATE_PAGES:
        lines.append(f'- [{desc.split("—")[0].strip()}]({base}{path}): {desc}')

    lines += [
        '',
        '## Contact & Consultation',
        '',
        f'- Phone: {SITE_INFO["phone"]}',
        f'- Email: {SITE_INFO["email"]}',
        f'- [Contact]({base}/contact-us/)',
        '- [WhatsApp](https://wa.me/14155550100)',
        '',
        f'> Generated: {date.today().isoformat()} | Site: {base}',
    ]

    content = '\n'.join(lines)

    # Default output path
    if output_path is None:
        project_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
        output_path = os.path.join(project_root, 'complete_website', 'llms.txt')

    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    with open(output_path, 'w', encoding='utf-8') as f:
        f.write(content)
    print(f'  ✅ llms.txt written → {output_path}')
    return content


if __name__ == '__main__':
    print(generate_llmstxt())
