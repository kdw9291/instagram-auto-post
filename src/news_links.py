"""Link discovery metadata to freshly verified official drafts, never copy news claims."""
import re
from .editorial import editorial_adapters, EvidenceError


def normalized(value):
    return re.sub(r'[^가-힣a-z0-9]', '', value.lower())


def named_in_title(name,title):
    pattern=r'\s*'.join(re.escape(ch) for ch in normalized(name))
    # Do not associate a base product with a Plus/Pro or numbered variant.
    return re.search(pattern+r"(?=$|[\s'’\"”·,.!?…]|(?:을|를|은|는)(?:\s|$))",title.lower()) is not None


def official_drafts(root):
    drafts=[]
    for key,maker in editorial_adapters(root):
        try:
            content,receipt=maker(root)
            if receipt.get('status')!='verified':continue
            names=[c['value'] for c in receipt.get('claims',[]) if c.get('field') in ('product','program','event_title') and isinstance(c.get('value'),str)]
            drafts.append({'source_id':key,'category':content['category'],'names':names,'urls':content['sources']})
        except (EvidenceError,ValueError,OSError):continue
    return drafts


def match(candidate,drafts):
    title=normalized(candidate['title']);matches=[]
    for draft in drafts:
        if candidate['category']!=draft['category']:continue
        # A long exact name is required: category/brand similarity alone is insufficient.
        names=[n for n in draft['names'] if len(normalized(n))>=8 and named_in_title(n,candidate['title'])]
        if names:matches.append((draft,names[0]))
    if len(matches)!=1:return None
    draft,name=matches[0]
    return {'source_id':draft['source_id'],'url':draft['urls'][0],'name':name,'reason':'공식 근거의 제품·행사명 일치; 원고는 공식 자료로만 작성'}
