"""Load seed keywords from CSV into the database."""
import os, sys, csv
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from core.db import get_session, Keyword, Site
from core.config import TARGET_DOMAIN

CSV_PATH = os.path.join(os.path.dirname(__file__), '..', 'profiles', 'example-legal', 'seed_keywords.csv')

def load():
    with get_session() as s:
        site = s.query(Site).filter_by(domain=TARGET_DOMAIN).first()
        if not site:
            print(f'Site {TARGET_DOMAIN} not in DB. Run: python core/db.py first')
            return

        with open(CSV_PATH, encoding='utf-8') as f:
            reader = csv.DictReader(f)
            added = 0
            for row in reader:
                existing = s.query(Keyword).filter_by(
                    site_id=site.id, keyword=row['keyword'], country=row['country']
                ).first()
                if not existing:
                    s.add(Keyword(
                        site_id=site.id,
                        keyword=row['keyword'],
                        country=row['country'],
                        cluster=row.get('cluster', ''),
                        intent=row.get('intent', ''),
                        priority=int(row.get('priority', 2)),
                        is_seed=True
                    ))
                    added += 1
            s.commit()

        total = s.query(Keyword).filter_by(site_id=site.id).count()
    print(f'✅ Added {added} keywords. Total in DB: {total}')

if __name__ == '__main__':
    load()
