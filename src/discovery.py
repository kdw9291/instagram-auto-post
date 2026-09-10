"""Persistent, deduplicated discovery queue. Unparsed news is never publishable."""
import hashlib
import json
import re
import sqlite3
from datetime import datetime, timedelta, timezone
from email.utils import parsedate_to_datetime
from pathlib import Path
from urllib.parse import urlsplit, urlunsplit, parse_qsl, urlencode

def canonical(url):
    p=urlsplit(url)
    if p.scheme!='https' or not p.hostname or p.username or p.password:raise ValueError('잘못된 후보 URL')
    query=sorted((k,v) for k,v in parse_qsl(p.query) if not k.lower().startswith('utm_'))
    return urlunsplit(('https',p.netloc.lower(),p.path,urlencode(query),''))

def sync(root,report,at=None):
    at=at or datetime.now(timezone.utc)
    path=Path(root)/'data/runtime/discovery.sqlite3';path.parent.mkdir(parents=True,exist_ok=True)
    db=sqlite3.connect(path);db.row_factory=sqlite3.Row
    registered={canonical(s['url']) for s in report.get('sources',[]) if s['id'] in ('apgroup-exhibition','hera-release','bgf-bakery')}
    checking={canonical(s['url']) for s in report.get('sources',[]) if s.get('adapter') in ('bgf-release','apgroup-release')}
    try:
        with db:
            db.execute('CREATE TABLE IF NOT EXISTS candidates(id TEXT PRIMARY KEY,url TEXT,title TEXT,category TEXT,published TEXT,expires TEXT,state TEXT,source_id TEXT)')
            for source in report.get('sources',[]):
                if source.get('status')!='ok':continue
                checked=datetime.fromisoformat(source['checked_at'])
                if checked.tzinfo is None or not timedelta(0)<=at-checked<timedelta(hours=12):continue
                for c in source.get('candidates',[]):
                    if c.get('category') not in ('place','beauty','food'):continue
                    try:url=canonical(c['url'])
                    except ValueError:continue
                    date=None
                    if c.get('published_at'):
                        try:date=parsedate_to_datetime(c['published_at'])
                        except (ValueError,TypeError):pass
                    if not date:
                        m=re.search(r'보도자료\s+(\d{2})\.(\d{2})\.(\d{2})',c['title'])
                        if m:
                            try:date=datetime(2000+int(m[1]),int(m[2]),int(m[3]),tzinfo=timezone(timedelta(hours=9)))
                            except ValueError:pass
                    if date and date.tzinfo is None:date=None
                    expires=date+timedelta(days=7) if date else None
                    state='needs_date' if not date else 'expired' if expires<=at or date>at else 'discovered'
                    if state=='discovered' and url in registered:state='registered'
                    elif state=='discovered' and url in checking:state='checking'
                    key=hashlib.sha256(url.encode()).hexdigest()
                    db.execute('INSERT INTO candidates VALUES(?,?,?,?,?,?,?,?) ON CONFLICT(id) DO UPDATE SET title=excluded.title,category=excluded.category,published=excluded.published,expires=excluded.expires,state=excluded.state',
                        (key,url,c['title'],c['category'],date.isoformat() if date else None,expires.isoformat() if expires else None,state,source['id']))
            db.execute("UPDATE candidates SET state='expired' WHERE expires IS NOT NULL AND julianday(expires)<=julianday(?)",(at.isoformat(),))
        candidates=[dict(r) for r in db.execute('SELECT * FROM candidates ORDER BY published DESC LIMIT 50')]
        from .news_links import official_drafts, match
        drafts=official_drafts(root)
        for c in candidates:
            if c['state']!='discovered':continue
            link=match(c,drafts)
            if link:c.update(state='linked',official=link)
        return candidates
    finally:db.close()
