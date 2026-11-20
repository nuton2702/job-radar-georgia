import unittest,sys,json,tempfile,copy
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
from radar import apply_result,classify,canonical,lever,SourceError,run,ROOT

class Rules(unittest.TestCase):
 def setUp(self):
  self.cfg=json.loads((ROOT/'dist/data/search-config.json').read_text());self.r={'id':'j','status':'verified','last_verified_at':'2026-11-20T06:00:00Z'};self.h=[]
 def test_error_does_not_verify_or_close(self):
  apply_result(self.r,'unavailable','2026-11-21T06:00:00Z','timeout','https://example.com',self.h)
  self.assertEqual(self.r['last_verified_at'],'2026-11-20T06:00:00Z');self.assertEqual(self.r['status'],'needs_review')
 def test_two_absences_need_time(self):
  for at in ['2026-11-21T06:00:00Z','2026-11-21T06:01:00Z']:apply_result(self.r,'missing',at,'404','https://example.com',self.h)
  self.assertEqual(self.r['status'],'needs_review')
  apply_result(self.r,'missing','2026-11-22T06:00:00Z','404','https://example.com',self.h);self.assertEqual(self.r['status'],'closed')
 def test_reopen_resets_absence(self):
  self.r.update(status='closed',missing_count=3,missing_since='2026-11-19T06:00:00Z')
  apply_result(self.r,'verified','2026-11-21T06:00:00Z','published list','https://example.com',self.h)
  self.assertEqual(self.r['status'],'verified');self.assertEqual(self.r['missing_count'],0)
 def rec(self,**kw):
  return dict(company='Example',title='Russian Customer Support',description='',geography='Tbilisi, Georgia',work_format='Remote',employment_type='Full-time',**kw)
 def test_georgia_not_us(self):
  r=self.rec();r['geography']='Atlanta, Georgia, United States';self.assertIsNone(classify(r,self.cfg))
 def test_exclusion(self):
  r=self.rec();r['company']='5CA';self.assertIsNone(classify(r,self.cfg))
 def test_configuration_changes_search(self):
  r=self.rec();self.assertIsNotNone(classify(copy.deepcopy(r),self.cfg));self.cfg['disabled_categories']=['Customer Support'];self.assertIsNone(classify(r,self.cfg))
 def test_language_and_format_changes_search(self):
  r=self.rec();self.cfg['languages']=['EN'];self.assertIsNone(classify(copy.deepcopy(r),self.cfg));self.cfg['languages']=['RU'];self.cfg['formats']=['Office'];self.assertIsNone(classify(r,self.cfg))
 def test_no_unknown_worldwide_assumption(self):
  r=self.rec();r['geography']='Worldwide';self.assertIsNone(classify(r,self.cfg))
 def test_canonical_removes_tracking_preserves_id(self):
  self.assertEqual(canonical('https://jobs.ge/en/?id=12&utm_source=x'),canonical('https://jobs.ge/en?id=12'))
  self.assertNotEqual(canonical('https://jobs.ge/en?id=12'),canonical('https://jobs.ge/en?id=13'))
 def test_talent_pool_not_job(self):
  class C:
   def get(self,u):return 200,json.dumps([{'id':'p','text':'AI Trainers Network - Russian','hostedUrl':'https://jobs.lever.co/x/p','categories':{'location':'Georgia'},'descriptionPlain':'This is not an active job opening.'}])
  self.assertEqual(lever({'id':'welo','company':'Welo','url':'https://api.lever.co/v0/postings/x'},C())[0]['kind'],'talent_pool')
 def test_empty_api_not_closure(self):
  class C:
   def get(self,u):return 200,'[]'
  with self.assertRaises(SourceError):lever({'url':'https://api.lever.co/v0/postings/x'},C())
 def test_end_to_end_new_duplicate_dates_and_failure(self):
  class C:
   def get(self,u):return 200,json.dumps([{'id':'a','text':'Russian Customer Support','hostedUrl':'https://jobs.lever.co/x/a','categories':{'location':'Georgia','commitment':'Full-time'},'workplaceType':'remote','createdAt':1700000000000}]*2)
  class Bad:
   def get(self,u):raise SourceError('timeout')
  with tempfile.TemporaryDirectory() as tmp:
   d=Path(tmp)
   for name,value in {'jobs.json':[],'platforms.json':[],'projects.json':[],'check-history.json':[],'search-config.json':self.cfg,'sources.json':[{'id':'test','company':'Example','adapter':'lever','url':'https://api.lever.co/v0/postings/x','enabled':True}],'update-status.json':{'last_database_update':None,'scheduled_run_confirmed':False}}.items():(d/name).write_text(json.dumps(value))
   run(d,C(),'2026-11-21T06:00:00Z');jobs=json.loads((d/'jobs.json').read_text());self.assertEqual(len(jobs),1);self.assertEqual(jobs[0]['status'],'verified');self.assertIsNone(jobs[0]['published_at'])
   run(d,C(),'2026-11-22T06:00:00Z');jobs=json.loads((d/'jobs.json').read_text());self.assertEqual(len(jobs),1);self.assertEqual(jobs[0]['first_seen_at'],'2026-11-21T06:00:00Z')
   result=run(d,Bad(),'2026-11-23T06:00:00Z');jobs=json.loads((d/'jobs.json').read_text());self.assertEqual(result['last_run_outcome'],'failed');self.assertEqual(jobs[0]['last_verified_at'],'2026-11-22T06:00:00Z');self.assertEqual(jobs[0]['status'],'needs_review');self.assertEqual(len(json.loads((d/'check-history.json').read_text())),3)
if __name__=='__main__':unittest.main()
