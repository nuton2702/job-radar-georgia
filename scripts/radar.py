"""Small, conservative public-source job monitor. Python standard library only."""
from __future__ import annotations
import argparse, copy, hashlib, html, json, os, re, tempfile, time, sys
from datetime import datetime, timezone, timedelta
from pathlib import Path
from urllib.request import Request, urlopen
from urllib.error import HTTPError
from urllib.parse import urlsplit, urlunsplit, parse_qsl, urlencode, urljoin
from urllib.robotparser import RobotFileParser

sys.modules.setdefault('radar',sys.modules[__name__])
ROOT = Path(__file__).resolve().parents[1]
UA = 'JobRadarGeorgia/0.3 (+https://github.com/nuton2702/job-radar-georgia)'

def now_iso(): return datetime.now(timezone.utc).isoformat(timespec='seconds')
def stamp(s): return datetime.fromisoformat(s.replace('Z','+00:00'))
def text(s): return re.sub(r'\s+', ' ', re.sub('<[^>]+>', ' ', html.unescape(html.unescape(str(s or ''))))).strip()
def canonical(url):
    p=urlsplit(url); q=[(k,v) for k,v in parse_qsl(p.query) if not k.startswith('utm_') and k not in ['source','gh_src','fbclid']]
    return urlunsplit(('https',p.netloc.lower(),p.path.rstrip('/'),urlencode(sorted(q)),''))
def title_key(s): return ' '.join(sorted(re.findall(r'\w+',s.lower())))
def uid(s): return hashlib.sha256(s.encode()).hexdigest()[:16]
def load(path): return json.loads(Path(path).read_text())
def atomic(path, value):
    path=Path(path);path.parent.mkdir(parents=True,exist_ok=True)
    with tempfile.NamedTemporaryFile('w',dir=path.parent,delete=False,encoding='utf-8') as f:
        json.dump(value,f,ensure_ascii=False,indent=2);f.write('\n');temp=f.name
    os.replace(temp,path)

class SourceError(Exception): pass
class HttpClient:
    def __init__(self, hosts=None): self.robots={};self.last={};self.hosts=set(hosts or ['careers.wolt.com','api.lever.co','boards-api.greenhouse.io'])
    def raw(self,url):
        p=urlsplit(url)
        if p.scheme!='https' or p.hostname not in self.hosts: raise SourceError('URL outside source allowlist')
        delay=1.1-(time.monotonic()-self.last.get(p.hostname,0))
        if delay>0: time.sleep(delay)
        self.last[p.hostname]=time.monotonic()
        try:
            with urlopen(Request(url,headers={'User-Agent':UA,'Accept':'application/json,text/html;q=0.9'}),timeout=25) as r:
                if urlsplit(r.url).hostname not in self.hosts:raise SourceError('Unexpected redirect')
                data=r.read(12_000_001)
                if len(data)>12_000_000: raise SourceError('Response exceeds safety limit')
                return r.status,data.decode('utf-8')
        except HTTPError as e: return e.code,''
        except (OSError,TimeoutError) as e: raise SourceError(type(e).__name__) from e
    def get(self,url):
        p=urlsplit(url);origin=f'{p.scheme}://{p.netloc}'
        if origin not in self.robots:
            status,body=self.raw(origin+'/robots.txt')
            if status==404:body='User-agent: *\nAllow: /'
            elif status!=200:raise SourceError(f'robots unavailable: HTTP {status}')
            rp=RobotFileParser();rp.parse(body.splitlines());self.robots[origin]=rp
        if not self.robots[origin].can_fetch(UA,url):raise SourceError('robots disallows retrieval')
        return self.raw(url)

def languages(s):
    return [code for code,term in {'RU':'russian','EN':'english','GE':'georgian'}.items() if re.search(r'\b'+term+r'\b',s,re.I)]
def classify(item,cfg):
    title=item['title'].lower(); body=item.get('description','').lower();loc=item.get('geography','').lower()
    if item['company'].lower() in [x.lower() for x in cfg['excluded_employers']]:return None
    category=next((k for k,words in cfg['categories'].items() if k not in cfg.get('disabled_categories',[]) and any(w.lower() in title for w in words)),None)
    if category is None:return None
    # Location is structured source metadata, never an incidental mention in description.
    geo=any(re.search(r'\b'+re.escape(t.lower())+r'\b',loc) for t in cfg['geographic_terms'])
    if re.search(r'\b(atlanta|united states|usa|georgia,? us)\b',loc):geo=False
    worldwide=bool(re.search(r'\b(worldwide|global|anywhere)\b',loc))
    if not geo and not (worldwide and cfg.get('include_worldwide_leads',False)):return None
    for lang in cfg.get('excluded_title_languages',[]):
        if re.search(r'\b'+lang.lower()+r'\b',title):return None
    known=languages(title)
    if known and not set(known).intersection(cfg['languages']):return None
    senior=bool(re.search(r'\b(senior|lead|manager|head|director|principal)\b',title))
    if senior and cfg.get('exclude_senior_titles',True):return None
    fmt=item.get('work_format','Unknown')
    if fmt!='Unknown' and fmt not in cfg['formats']:return None
    employment=item.get('employment_type','Уточнить')
    if employment!='Уточнить' and employment not in cfg['employment']:return None
    item.update(category=category,georgia_eligible='location_supported' if geo else 'needs_review',languages=' + '.join(known) or 'Уточнить')
    priority=cfg['priority_rules']['russian_remote'] if 'RU' in known and fmt=='Remote' else cfg['priority_rules']['default']
    if 'GE' in known:priority=cfg['priority_rules']['georgian_required']
    item['priority']=priority;item['match_notes']=('Требуется грузинский: уровень кандидата средний, сверьте требования.' if 'GE' in known else 'Точные языковые требования, опыт и выплаты необходимо сверить.')
    if re.search(r'\b[2-9]\+? years?\b',body):item['priority']='C';item['match_notes']+=' Возможен обязательный профильный опыт.'
    return item

def make_record(src,id,title,url,location,description,employment='Уточнить',fmt='Unknown',published=None):
    return dict(source_id=src['id'],external_id=str(id),company=src['company'],title=title,url=url,geography=location,description=text(description),employment_type=employment,work_format=fmt,published_at=published,source=urlsplit(url).hostname)

def lever(src,client):
    status,body=client.get(src['url'])
    if status!=200:raise SourceError(f'HTTP {status}')
    try:rows=json.loads(body)
    except ValueError:raise SourceError('Invalid JSON')
    if not isinstance(rows,list) or not rows:raise SourceError('Empty or invalid job board; no closures inferred')
    out=[]
    for j in rows:
        if not all(k in j for k in ['id','text','hostedUrl','categories']):raise SourceError('Lever schema changed')
        cat=j['categories'];descr=' '.join([j.get('descriptionPlain',''),j.get('descriptionBodyPlain',''),j.get('additionalPlain','')]+[text(x.get('content','')) for x in j.get('lists',[])])
        loc='; '.join(cat.get('allLocations') or [cat.get('location','')])
        rec=make_record(src,j['id'],j['text'],j['hostedUrl'],loc,descr,cat.get('commitment','Уточнить'),{'remote':'Remote','hybrid':'Hybrid','on-site':'Office'}.get(j.get('workplaceType'),'Unknown'))
        if rec['employment_type'] not in ['Full-time','Part-time','Freelance','Contract','Task-based']:rec['employment_type']='Уточнить'
        rec['source_created_at']=datetime.fromtimestamp(j['createdAt']/1000,timezone.utc).isoformat() if j.get('createdAt') else None
        rec['kind']='talent_pool' if re.search(r'not an active job|talent (?:pool|hub|community)|general application|trainers network',j['text']+' '+descr+' '+cat.get('team',''),re.I) else 'job'
        rec['evidence']='Published official Lever posting; talent pool is not a paid project' if rec['kind']=='talent_pool' else 'Published official Lever posting'
        out.append(rec)
    return out

def wolt(src,client):
    status,body=client.get(src['url'])
    if status!=200:raise SourceError(f'HTTP {status}')
    links={urljoin(src['url'],u):text(t) for u,t in re.findall(r'<a[^>]*href="(/en/jobs/\d+/\d+)"[^>]*>(.*?)</a>',body,re.S)}
    if not links:raise SourceError('Job-list markup changed or empty; no closures inferred')
    out=[]
    for url,label in links.items():
        # Discovery scope narrows downloads only; matching uses configuration later.
        title=label.split('SupportFull-time')[0]
        rec=make_record(src,url.rstrip('/').split('/')[-1],title,url,label,'')
        rec['kind']='job';out.append(rec)
    return out

def wolt_detail(rec,client):
    status,body=client.get(rec['url'])
    if status!=200:raise SourceError(f'Detail HTTP {status}')
    blobs=re.findall(r'<script[^>]*type="application/ld\+json"[^>]*>(.*?)</script>',body,re.S)
    for b in blobs:
        try:j=json.loads(b)
        except ValueError:continue
        if not isinstance(j,dict) or j.get('@type')!='JobPosting':continue
        title=j.get('title','');descr=text(j.get('description',''));loc=text(json.dumps(j.get('jobLocation',{}),ensure_ascii=False))
        if not title or not descr or 'wolt' not in json.dumps(j.get('hiringOrganization',{})).lower():raise SourceError('Missing job identity')
        fmt='Remote' if re.search(r'fully remote|\bremote\b',title,re.I) else ('Office' if re.search('onsite|on-site',title,re.I) else 'Unknown')
        employment='Part-time' if re.search('part.time',title,re.I) else ('Full-time' if re.search('full.time',title,re.I) else 'Уточнить')
        rec.update(title=title,description=descr,geography=loc,work_format=fmt,employment_type=employment,published_at=j.get('datePosted'),evidence='Specific ID in official current list and matching JobPosting detail')
        return rec
    raise SourceError('No valid JobPosting data')

def apply_result(record,outcome,at,evidence,url,history,min_hours=12):
    record['last_checked_at']=at
    if outcome=='verified':
        record.update(status='verified',last_verified_at=at,missing_since=None,missing_count=0)
    elif outcome=='missing':
        first=record.get('missing_since') or at
        count=record.get('missing_count',0)+1
        record.update(missing_since=first,missing_count=count)
        record['status']='closed' if count>=2 and stamp(at)-stamp(first)>=timedelta(hours=min_hours) else 'needs_review'
    elif outcome=='excluded':record['status']='archived'
    elif record.get('status') not in ['closed','archived']:record['status']='needs_review'
    event=dict(record_id=record['id'],checked_at=at,outcome=outcome,evidence=evidence,url=url)
    record['last_check_result']=event
    history.append(event)

def run(data_dir, client=None, at=None):
    d=Path(data_dir);at=at or now_iso()
    jobs=load(d/'jobs.json');platforms=load(d/'platforms.json');projects=load(d/'projects.json');history=load(d/'check-history.json');cfg=load(d/'search-config.json');sources=load(d/'sources.json');status=load(d/'update-status.json')
    from adapters import bolt,workable,telus,public_page
    client=client or HttpClient({urlsplit(s['url']).hostname for s in sources if s.get('enabled')})
    status.update(last_run_at=at,last_run_outcome='running');atomic(d/'update-status.json',status)
    reports=[];found=[];success=set();before=len(jobs);source_by_id={s['id']:s for s in sources}
    for src in sources:
        if not src.get('enabled'):continue
        try:
            records={'lever':lever,'wolt':wolt,'bolt':bolt,'workable':workable,'telus':telus,'public_page':public_page}[src['adapter']](src,client)
            success.add(src['id']);reports.append(dict(source_id=src['id'],status='ok',returned=len(records),name=src.get('company',src['id']),scope=src.get('scope',''),observation=src.get('_observation')))
            if src['adapter']=='wolt':
                for rec in records:
                    # Fetch only relevant titles or existing IDs; no broad scraping.
                    if not any(w.lower() in rec['title'].lower() for words in cfg['categories'].values() for w in words) and not any(rec['external_id'] in j['url'] for j in jobs):continue
                    try:found.append(wolt_detail(rec,client))
                    except SourceError as e:reports.append(dict(source_id=src['id'],status='detail_error',url=rec['url'],error=str(e)))
            else:found.extend(records)
        except (SourceError,KeyError,ValueError,TypeError) as e:reports.append(dict(source_id=src['id'],status='error',name=src.get('company',src['id']),scope=src.get('scope',''),error=str(e)))
    updated=set();seen=set()
    for rec in found:
        match=classify(copy.deepcopy(rec),cfg)
        # Existing records still get availability checks even when preferences change.
        existing=next((j for j in jobs if (j.get('source_id')==rec['source_id'] and j.get('external_id')==rec['external_id']) or canonical(j['url'])==canonical(rec['url']) or (j['company']==rec['company'] and re.search(r'/jobs/\d+/'+re.escape(rec['external_id'])+r'/?$',urlsplit(j['url']).path))),None)
        alias=cfg.get('source_aliases',{}).get(rec['source_id']+':'+rec['external_id'])
        if existing is None and alias:existing=next((j for j in jobs if j['id']==alias),None)
        if not match and not existing:continue
        key=rec['source_id']+':'+rec['external_id']
        if key in seen:continue
        seen.add(key)
        if rec.get('kind')=='talent_pool':
            pool=next((p for p in projects if p.get('source_id')==rec['source_id'] and p.get('external_id')==rec['external_id']),None)
            if pool is None:
                pool=dict(id='project-'+uid(key),first_seen_at=at);projects.append(pool)
            pool.update(match or rec);pool.update(last_checked_at=at,last_verified_at=at,status='talent_pool',paid_project_confirmed=False)
            history.append(dict(record_id=pool['id'],checked_at=at,outcome='talent_pool',evidence=rec['evidence'],url=rec['url']))
            continue
        if existing is None:
            existing=dict(id='job-'+uid(key),first_seen_at=at,source_manual_checked_on=None,source_status=None,source_sheet=None,salary='Не указана',experience='Смотрите требования источника',schedule='Смотрите описание источника',notes='Обнаружено автоматически. Выплаты и право на оформление требуют подтверждения.',history=[])
            jobs.append(existing)
        # Original spreadsheet fields stay unchanged; current source facts are separate.
        if existing.get('source_manual_checked_on'):
            existing['current_source']=rec
            existing.setdefault('original_url',existing['url'])
            existing['source_id']=rec['source_id'];existing['external_id']=rec['external_id']
            existing['current_url']=rec['url'];existing['georgia_eligible']=(match or {}).get('georgia_eligible','needs_review')
            existing['match_notes']=(match or {}).get('match_notes','Соответствие изменённым критериям требует оценки.')
            if not existing.get('published_at'):existing['published_at']=rec.get('published_at')
        else:existing.update(match or rec)
        existing['payment_eligibility']='needs_review';existing['match_status']='matched' if match else 'outside_current_config'
        apply_result(existing,'verified',at,rec['evidence'],rec['url'],history);updated.add(existing['id'])
    for job in jobs:
        if job['company'].lower() in [x.lower() for x in cfg['excluded_employers']]:
            apply_result(job,'excluded',at,'Employer excluded by configuration',job['url'],history);continue
        if job['id'] in updated:continue
        src=source_by_id.get(job.get('source_id'))
        if src is None and job['company']=='Wolt' and re.search(r'/en/jobs/\d+/\d+/?$',urlsplit(job['url']).path):
            src=source_by_id.get('wolt');job['source_id']='wolt';job['external_id']=job['url'].rstrip('/').split('/')[-1]
        if src and src['id'] in success and src['adapter'] in ['lever','workable'] and src.get('complete_list',src['adapter']=='lever'):
            # Full successfully parsed API list can establish repeated absence.
            apply_result(job,'missing',at,'Not in complete official published list',src['url'],history,cfg['closure_min_hours'])
        elif src and src['id'] in success and src['adapter']=='wolt' and job.get('external_id') and not any(r['external_id']==job['external_id'] for r in found):
            try:
                code,_=client.get(job.get('current_url') or job['url'])
                apply_result(job,'missing' if code in [404,410] else 'unavailable',at,f'Absent from list; direct page HTTP {code}',job['url'],history,cfg['closure_min_hours'])
            except SourceError as e:apply_result(job,'unavailable',at,str(e),job['url'],history)
        else:
            apply_result(job,'unavailable',at,'No supported successful verification for this record; not evidence of closure',job['url'],history)
    for pool in projects:
        if pool.get('last_checked_at')==at:continue
        pool['last_checked_at']=at;pool['status']='needs_review';pool['paid_project_confirmed']=False
        history.append(dict(record_id=pool['id'],checked_at=at,outcome='unavailable',evidence='Pool not reconfirmed in this run',url=pool['url']))
    for p in platforms:
        src=next((s for s in sources if s.get('platform_id')==p['id']),None)
        if src:
            p['last_checked_at']=at
            if src['id'] in success:
                p['availability_status']='public_page_accessible' if src['adapter']=='public_page' else 'official_board_accessible'
                p['public_page_checked_at']=at
                p['projects_status']='Проверена только публичная страница; проекты и выплаты не подтверждены' if src['adapter']=='public_page' else 'Проверен публичный список; доступность конкретных проектов для вас не гарантирована'
                if src['adapter']!='public_page':p['last_verified_at']=at
                p['public_observation']=src.get('_observation')
            else:p['availability_status']='needs_review';p['projects_status']='Источник недоступен для проверки'
        else:p['availability_status']='needs_review';p['projects_status']='Автопроверка не подключена'
        p['payment_verification_status']='needs_review'
        history.append(dict(record_id=p['id'],checked_at=at,outcome=p['availability_status'],evidence=p['projects_status'],url=src['url'] if src else p['url']))
    status.update(last_run_outcome='success' if success and all(r['status']=='ok' for r in reports) else ('partial' if success else 'failed'),source_results=reports,new_jobs=len(jobs)-before,checked_jobs=len(jobs),verified_jobs=sum(j['status']=='verified' for j in jobs),total_jobs=len(jobs),coverage_note='Поиск: '+', '.join(s['company'] for s in sources if s.get('enabled') and s['adapter']!='public_page')+'. Общие страницы платформ не подтверждают проекты. Ограничения и ошибки — в результатах источников.',automation_enabled=bool(status.get('automation_enabled') or os.environ.get('GITHUB_ACTIONS')=='true'),schedule_configured=bool(status.get('schedule_configured') or os.environ.get('GITHUB_ACTIONS')=='true'),scheduled_run_confirmed=bool(status.get('scheduled_run_confirmed') or os.environ.get('GITHUB_EVENT_NAME')=='schedule'))
    # Successful save means persisted result, not verification of every record.
    for name,items in [('jobs.json',jobs),('platforms.json',platforms),('projects.json',projects),('check-history.json',history)]:atomic(d/name,items)
    status['last_database_update']=now_iso();atomic(d/'update-status.json',status)
    return status

if __name__=='__main__':
    ap=argparse.ArgumentParser();ap.add_argument('--data-dir',default=str(ROOT/'dist/data'));args=ap.parse_args()
    try:
        result=run(args.data_dir);print(json.dumps(result,ensure_ascii=False,indent=2))
        raise SystemExit(1 if result['last_run_outcome']=='failed' else 0)
    except Exception as e:
        p=Path(args.data_dir)/'update-status.json';s=load(p);s.update(last_run_outcome='failed',error=type(e).__name__);atomic(p,s);raise
