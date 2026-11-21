"""Public source adapters: no authentication or private endpoints."""
import json,re,html
from urllib.parse import urljoin

def workable(src,client):
    from radar import SourceError,make_record,text
    code,body=client.get(src['url'])
    if code!=200:raise SourceError(f'HTTP {code}')
    data=json.loads(body)
    if not isinstance(data,dict) or not isinstance(data.get('jobs'),list) or not data['jobs']:
        raise SourceError('Empty or invalid public board; no closures inferred')
    out={}
    for row in data['jobs']:
        if not all(k in row for k in ['shortcode','title','url','country']):raise SourceError('Workable schema changed')
        loc=', '.join(str(row.get(k) or '') for k in ['city','state','country'])
        desc=text(row.get('description',''))
        employment=row.get('employment_type') or 'Уточнить'
        if employment not in ['Full-time','Part-time','Contract','Freelance','Task-based']:employment='Уточнить'
        r=make_record(src,row['shortcode'],row['title'],row['url'],loc,desc,employment,{'remote':'Remote','hybrid':'Hybrid','on_site':'Office'}.get(row.get('workplace_type'),'Remote' if row.get('telecommuting') else 'Unknown'),row.get('published_on'))
        r.update(kind='talent_pool' if re.search(r'talent pool|future opportunities|general application',r['title']+' '+desc,re.I) else 'job',evidence='Specific posting in official public Workable feed',experience=row.get('experience') or 'Уточнить')
        if r['external_id'] in out:out[r['external_id']]['geography']+='; '+loc
        else:out[r['external_id']]=r
    return list(out.values())

def bolt(src,client):
    from radar import SourceError,make_record
    code,body=client.get(src['url'])
    if code!=200:raise SourceError(f'HTTP {code}')
    streams=[]
    for raw in re.findall(r'self\.__next_f\.push\((\[.*?\])\)</script>',body,re.S):
        try:
            value=json.loads(raw)
            if len(value)>1 and isinstance(value[1],str):streams.append(value[1])
        except ValueError:continue
    stream=''.join(streams);out={};decoder=json.JSONDecoder()
    for m in re.finditer(r'\{"id":"[^"]+","header":\{"roleTitle":',stream):
        try:j,_=decoder.raw_decode(stream[m.start():])
        except ValueError:continue
        h=j['header'];b=j['body'];url=urljoin(src['url'],b['applyLinkProps']['href']);desc=b.get('description','')
        if desc.startswith('$'):desc='Описание доступно на странице работодателя.'
        title=h['roleTitle'];loc='; '.join(', '.join(x.get(k,'') for k in ['city','country']) for x in h['locations'])
        r=make_record(src,j['id'],title,url,loc,desc,'Part-time' if re.search(r'part[ -]time',title,re.I) else 'Уточнить','Unknown',b.get('jobPostedDate','').removeprefix('$D') or None)
        r.update(kind='job',evidence='Specific ID, role and location in official Bolt current list; format not inferred')
        out[r['external_id']]=r
    if not out:raise SourceError('Bolt public list schema changed or empty; no closures inferred')
    return list(out.values())

def telus(src,client):
    from radar import SourceError,make_record,text
    out={};queue=[src['url']];seen=set()
    while queue:
        url=queue.pop(0)
        if url in seen:continue
        if len(seen)>=12:raise SourceError('Pagination limit reached; incomplete list')
        seen.add(url);code,body=client.get(url)
        if code!=200:raise SourceError(f'HTTP {code}')
        cards=re.findall(r'<a[^>]*class="jobs-section__item\s[^"]*"[^>]*href="([^"]+)"[^>]*>(.*?)</a>',body,re.S)
        if not cards:raise SourceError('TELUS list empty or markup changed')
        for path,card in cards:
            title=re.search(r'<h4[^>]*>(.*?)</h4>',card,re.S);meta=re.search(r'<div class="paragraph-4"[^>]*>(.*?)</div>',card,re.S)
            if not title or not meta:raise SourceError('Missing listing metadata')
            title=text(title[1]);loc=text(meta[1]).split('•')[0].strip();alltext=text(card)
            r=make_record(src,path.split('/')[-1].split('-')[0],title,urljoin(src['url'],path),loc,alltext,'Part-time' if 'Part time' in alltext else ('Full-time' if 'Full time' in alltext else 'Уточнить'),'Remote' if re.search(r'\bRemote\b',alltext) else ('Office' if 'Onsite' in alltext else 'Unknown'))
            r.update(kind='job',evidence='Specific opening in official TELUS AI Community list; requirements must be reviewed')
            out[r['external_id']]=r
        for link in re.findall(r'href="([^"]*\?page=\d+[^"]*)"',body):
            link=urljoin(src['url'],html.unescape(link)).split('#')[0]
            # Both /jobs?page=N and /jobs/in?page=N occur in official pagination.
            if re.fullmatch(r'https://jobs\.telusdigital\.com/search/cfm5/ai-community/jobs(?:/in)?\?page=\d+',link):
                link=link.replace('/jobs/in?','/jobs?')
                if link not in seen and link not in queue:queue.append(link)
    return list(out.values())

def public_page(src,client):
    from radar import SourceError,text,uid
    code,body=client.get(src['url'])
    if code!=200:raise SourceError(f'HTTP {code}; public page not checked')
    clean=re.sub(r'<(script|style)\b[^>]*>.*?</\1>','',body,flags=re.S|re.I)
    title=re.search(r'<title[^>]*>(.*?)</title>',body,re.S|re.I)
    if not title or len(text(clean))<100:raise SourceError('No readable public content; projects not verified')
    src['_observation']={'page_title':text(title[1]),'content_hash':uid(text(clean)),'url':src['url'],'evidence':'Public page only; projects, country eligibility, rates and payouts NOT verified'}
    return []
