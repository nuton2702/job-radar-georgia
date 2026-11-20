import openpyxl,json,pathlib,hashlib
root=pathlib.Path(__file__).resolve().parents[1]; uploads=root.parent/'upload'
def dump(name,data): (root/'dist/data'/name).write_text(json.dumps(data,ensure_ascii=False,indent=2))
def snapshot(w):
 return {s.title:[{'row':r[0].row,'cells':[{'column':c.column_letter,'value':c.value,'hyperlink':c.hyperlink.target if c.hyperlink else None} for c in r if c.value is not None]} for r in s if any(c.value is not None for c in r)] for s in w}
w=openpyxl.load_workbook(next(uploads.glob('vacancies*'))); dump('original-jobs.json',snapshot(w));jobs=[]
for s in list(w)[:5]:
 for row in list(s.values)[1:]:
  a,company,title,lang,exp,sched,pay,status,url,notes=row[:10]
  if not title:continue
  fmt='Unknown'
  if 'гибрид' in sched.lower():fmt='Hybrid'
  elif 'remote/офис' not in sched.lower() and ('100% remote' in sched.lower() or 'remote georgia' in sched.lower() or 'fully remote' in sched.lower() or 'удалённо' in sched.lower() or 'remote из' in sched.lower()):fmt='Remote'
  elif 'офис' in sched.lower() and 'не подтверждён' not in sched.lower():fmt='Office'
  if company=='Wolt' and 'Уточнить конкретный' in notes:fmt='Unknown'
  jobs.append(dict(id='job-'+hashlib.sha256((company+title+url).encode()).hexdigest()[:12],company=company,title=title,category='QA' if 'QA' in title else ('Другие направления' if 'Interpreter' in title or 'Operations' in title else 'Customer Support'),work_format=fmt,employment_type='Уточнить' if company in ['WayPoint B2B','Pharmbills'] or s.title.startswith('05') else ('Part-time' if s.title.startswith('02') else 'Full-time'),geography='Грузия / Тбилиси — по исходной таблице',georgia_eligible='needs_review',languages=lang,experience=exp,schedule=sched,salary=pay,source=url.split('/')[2],url=url,priority=a,notes=notes,status='needs_review',source_status=status,source_sheet=s.title,source_manual_checked_on='2026-11-21',first_seen_at=None,published_at=None,last_checked_at=None,last_verified_at=None,history=[]))
w=openpyxl.load_workbook(next(uploads.glob('Лист*')));dump('original-platforms.json',snapshot(w));platforms=[];excluded=[]
for r in w.active.values:
 if r[1] and r[0] not in ['Площадка']:
  name,url,category,work,entry,payout,reg,tests,notes=r
  platforms.append(dict(id='platform-'+hashlib.sha256(name.encode()).hexdigest()[:10],name=name,url='https://'+url,category=category,work=work,entry=entry,payout=payout,source_registration=reg,tests=tests,notes=notes,georgia_eligible='needs_review',kyc='Требования уточнить',projects_status='Не проверено',verified_rates=None,last_checked_at=None,last_verified_at=None))
 if r[0] and r[4] and not r[1] and r[0]!='Площадка / Вакансия':excluded.append(dict(name=r[0],reason=r[4],reason_status='Исходная причина; требует повторной оценки',auto_reinclude=False))
assert len(jobs)==19 and len(platforms)==13 and len(excluded)==6
for name,data in [('jobs.json',jobs),('platforms.json',platforms),('excluded-platforms.json',excluded),('projects.json',[]),('check-history.json',[]),('sources.json',[]),('update-status.json',dict(last_database_update=None,last_run_at=None,automation_enabled=False,source_manual_updated_on='2026-11-21',imported_jobs=len(jobs),imported_platforms=len(platforms))),('search-config.json',dict(timezone='Asia/Tbilisi',schedule_utc='0 6 * * *',countries=['Georgia'],languages=['RU','EN','GE'],excluded_employers=['5CA'],excluded_platforms=[x['name'] for x in excluded],categories={'Customer Support':['customer support','customer service','chat support','player support','technical support','customer success'],'QA':['game tester','game qa','manual qa','crowdtesting','software tester'],'AI':['ai trainer','response evaluator','content evaluator','data annotator','data labeling','search quality','ads quality','language contributor','data collection'],'Другие направления':['content moderator','community moderator','data entry','virtual assistant','transcription','localization reviewer']},formats=['Remote','Hybrid','Office'],employment=['Full-time','Part-time','Freelance','Contract','Task-based']))]:dump(name,data)
(root/'dist/data.js').write_text('window.RADAR_DATA='+json.dumps(dict(jobs=jobs,platforms=platforms,excluded=excluded),ensure_ascii=False)+';')
print('Imported 19 jobs, 13 platforms, 6 exclusions; original cells and notes preserved.')
