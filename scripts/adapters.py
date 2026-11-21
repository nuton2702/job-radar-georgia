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
    if not title or text(title[1]) in ['{title}','Just a moment...','Access Denied'] or len(text(clean))<100:raise SourceError('No readable public content; projects not verified')
    src['_observation']={'page_title':text(title[1]),'content_hash':uid(text(clean)),'url':src['url'],'evidence':'Public page only; projects, country eligibility, rates and payouts NOT verified'}
    return []

def jobsge(src,client):
    from radar import SourceError,make_record,text
    from urllib.parse import parse_qs,urlsplit
    code,body=client.get(src['url'])
    if code!=200:raise SourceError(f'HTTP {code}')
    page_count=re.search(r'loaded_page\s*<\s*(\d+)',body)
    total=int(page_count[1]) if page_count else 1
    if total>30:raise SourceError('Jobs.ge pagination exceeds 30 pages; no closures inferred')
    pages=[body]
    for page in range(2,total+1):
        status,part=client.get(urljoin(src['url'],'?page='+str(page)))
        if status!=200:raise SourceError(f'Jobs.ge page {page}: HTTP {status}')
        if not re.search(r'view=jobs',part):raise SourceError(f'Jobs.ge page {page}: unreadable listing')
        pages.append(part)
    rows=re.findall(r'<tr\b[^>]*>(.*?)</tr>','\n'.join(pages),re.S)
    candidates={};existing=set(src.get('_existing_ids',[]))
    cfg=src.get('_config',{});words=[w.lower() for k,ws in cfg.get('categories',{}).items() if k not in cfg.get('disabled_categories',[]) for w in ws]
    parsed=0
    for row in rows:
        cells=re.findall(r'<td\b[^>]*>(.*?)</td>',row,re.S)
        if len(cells)<6:continue
        links=re.findall(r'<a[^>]*href=["\']([^"\']+)["\'][^>]*>(.*?)</a>',cells[1],re.S)
        target=next(((u,text(t)) for u,t in links if 'view=jobs' in html.unescape(u) and text(t)),None)
        if not target:continue
        url=urljoin(src['url'],html.unescape(target[0]));id=parse_qs(urlsplit(url).query).get('id',[''])[0]
        if not id:continue
        parsed+=1;title=target[1];company=text(cells[3])
        if company.lower() in [e.lower() for e in cfg.get('excluded_employers',[])]:continue
        if id not in existing and not any(w in title.lower() for w in words):continue
        candidates[id]=(title,company,url,text(cells[4]),text(cells[5]))
    if not parsed:raise SourceError('Jobs.ge list schema changed or empty')
    # Existing records first, then a bounded daily discovery pass.
    ordered=sorted(candidates,key=lambda id:(id not in existing,-int(id)))[:40]
    out=[];errors=[]
    src['_record_results']={}
    for id in existing-set(candidates):
        url=urljoin(src['url'],'?view=jobs&id='+id)
        try:
            status,detail=client.get(url)
            src['_record_results'][id]={'outcome':'missing' if status in (404,410) else 'unavailable','evidence':f'Absent from all {total} current listing pages; direct page HTTP {status}', 'url':url}
        except SourceError as e:
            src['_record_results'][id]={'outcome':'unavailable','evidence':str(e),'url':url}
    for id in ordered:
        title,company,url,published,deadline=candidates[id]
        try:
            status,detail=client.get(url)
            if status!=200:raise SourceError(f'Detail HTTP {status}')
            clean=text(re.sub(r'<(script|style)\b[^>]*>.*?</\1>','',detail,flags=re.S|re.I))
            if not all(x in clean for x in ['Ad title:','Provided By:','Deadline:']) or title.casefold() not in clean.casefold() or company.casefold() not in clean.casefold():
                raise SourceError('Detail identity not confirmed')
            if re.search(r'advertisement (?:has )?expired|vacancy (?:is )?closed',clean,re.I):raise SourceError('Explicit closure requires review')
            start=clean.find('Deadline:');description=clean[start:].split('⬅')[0]
            locmatch=re.search(r'(?:Location|Based in|Office location)\s*:\s*([^.;]{2,100})',description,re.I)
            loc=locmatch[1] if locmatch else ('Tbilisi, Georgia' if re.search(r'\bTbilisi\b',description,re.I) else '')
            fmt='Remote' if re.search(r'fully remote|100% remote|Location:\s*Remote',description,re.I) else ('Hybrid' if re.search(r'\bhybrid\b',description,re.I) else 'Unknown')
            employment='Part-time' if re.search(r'part[ -]time',title,re.I) else ('Full-time' if re.search(r'(?:job type|employment)\s*:\s*full[ -]time',description,re.I) else 'Уточнить')
            rec=make_record({**src,'company':company},id,title,url,loc,description,employment,fmt)
            rec.update(kind='job',source_published_label=published,source_deadline_label=deadline,evidence='Specific ID in current Jobs.ge list and matching title/employer in detail; source date lacks year and is not inferred')
            out.append(rec)
        except SourceError as e:
            errors.append({'url':url,'error':str(e)})
            src['_record_results'][id]={'outcome':'unavailable','evidence':str(e),'url':url}
    src['_detail_errors']=errors
    src['_discovery_counts']={'relevant_listings':len(candidates),'details_attempted':len(ordered),'daily_limit':40,'listing_pages':total}
    return out


def pharmbills(src,client):
    from radar import SourceError,make_record,text
    code,body=client.get(src['url'])
    if code!=200:raise SourceError(f'HTTP {code}')
    links={}
    for path,label in re.findall(r'<a[^>]*href="([^"]+)"[^>]*>(.*?)</a>',body,re.S):
        title=text(label)
        if path.startswith('/openings/') and path.endswith('-georgia-remote') and title and title!='Learn More':
            links[urljoin(src['url'],path)]=title
    if not links:raise SourceError('Pharmbills Georgia board missing or changed')
    cfg=src.get('_config',{});words=[w.lower() for k,v in cfg.get('categories',{}).items() if k not in cfg.get('disabled_categories',[]) for w in v]
    out=[];errors=[]
    for url,title in links.items():
        key=url.rstrip('/').split('/')[-1]
        if not any(w in title.lower() for w in words) and key not in src.get('existing_slugs',[]):continue
        try:
            code,detail=client.get(url)
            if code!=200:raise SourceError(f'Detail HTTP {code}')
            h=re.search(r'<h1[^>]*>(.*?)</h1>',detail,re.S)
            if not h or title.casefold() not in text(h[1]).casefold():raise SourceError('Detail identity mismatch')
            apply_url='https://cooperation.pharmbills.com/apply/'+key
            if apply_url not in detail:raise SourceError('Specific application link missing')
            clean=text(re.sub(r'<(script|style)\b[^>]*>.*?</\1>','',detail,flags=re.S|re.I))
            if re.search(r'no longer accepting|position (?:is |has been )closed',clean,re.I):raise SourceError('Posting no longer accepting applications')
            rec=make_record(src,key,title,url,'Georgia',clean,'Уточнить','Remote')
            rec.update(kind='job',evidence='Specific opening on official Georgia board, matching detail heading and application link')
            out.append(rec)
        except SourceError as e:errors.append({'url':url,'error':str(e)})
    src['_detail_errors']=errors
    return out

def concentrix(src,client):
    from radar import SourceError,make_record
    code,body=client.get(src['url'])
    if code!=200:raise SourceError(f'HTTP {code}')
    block=re.search(r'<script[^>]*id="jobsData"[^>]*>(.*?)</script>',body,re.S)
    if not block:raise SourceError('Official jobsData missing')
    data=json.loads(block[1])
    if not data.get('ok') or not isinstance(data.get('data'),list) or not data['data']:raise SourceError('Official job list empty or invalid')
    out=[]
    src['_detail_errors']=[]
    for j in data['data']:
        if j.get('country')!='Georgia':continue
        if str(j.get('allow_applications')) not in ['1','True'] or str(j.get('publish_on_job_listing')) not in ['1','True']:continue
        if not all(j.get(k) for k in ['ats_external_id','job_title','long_description','apply_url']):
            src['_detail_errors'].append({'url':src['url'],'error':'Incomplete posting '+str(j.get('ats_external_id'))});continue
        id=j['ats_external_id'];url='https://jobs.concentrix.com/job/?id='+id
        rec=make_record(src,id,j['job_title'].strip(),url,', '.join([j.get('city',''),'Georgia']),j['long_description'],'Full-time' if j.get('job_type')=='full_time' else 'Уточнить','Unknown')
        rec.update(kind='job',evidence='Specific opening in official embedded jobsData for Georgia with application URL',application_url=j['apply_url'])
        out.append(rec)
    return out
