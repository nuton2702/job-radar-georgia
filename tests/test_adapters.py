import unittest,json,sys,tempfile
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
from adapters import bolt,workable,telus,public_page
from radar import SourceError,run,ROOT

class Fake:
    def __init__(self,pages):self.pages=pages;self.calls=[]
    def get(self,url):self.calls.append(url);return self.pages[url]

class Adapters(unittest.TestCase):
    def test_bolt_public_data_and_unknown_format(self):
        j={'id':'abc','header':{'roleTitle':'Part Time Customer Support','locations':[{'city':'Tbilisi','country':'Georgia'}]},'body':{'description':'$ref','jobPostedDate':'$D2026-11-13T00:00:00Z','applyLinkProps':{'href':'/en/careers/positions/abc/'}}}
        body='<script>self.__next_f.push('+json.dumps([1,'1:'+json.dumps(j,separators=(',',':'))])+')</script>'
        r=bolt({'id':'bolt','company':'Bolt','url':'https://bolt.eu/list'},Fake({'https://bolt.eu/list':(200,body)}))[0]
        self.assertEqual(r['work_format'],'Unknown');self.assertEqual(r['employment_type'],'Part-time')
        self.assertEqual(r['published_at'],'2026-11-13T00:00:00Z')
    def test_bolt_empty_not_closure(self):
        with self.assertRaises(SourceError):bolt({'url':'x'},Fake({'x':(200,'<html>changed</html>')}))
    def test_workable_merges_locations_and_separates_talent_pool(self):
        rows=[dict(shortcode='x',title='Customer Support',url='https://apply.workable.com/j/x',country=c,city=city,telecommuting=True,published_on='2026-11-20') for c,city in [('Georgia','Tbilisi'),('Georgia','Batumi')]]
        rows.append(dict(shortcode='y',title='AI talent pool',url='https://apply.workable.com/j/y',country='Georgia'))
        r=workable({'id':'s','company':'Example','url':'x'},Fake({'x':(200,json.dumps({'jobs':rows}))}))
        self.assertEqual(len(r),2);self.assertIn('Batumi',r[0]['geography']);self.assertEqual(r[1]['kind'],'talent_pool')
    def test_telus_pagination_and_deduplication(self):
        root='https://jobs.telusdigital.com/search/cfm5/ai-community/jobs'
        card='<a class="jobs-section__item box" href="/jobs/123-title"><h4>Online Data Analyst</h4><div class="paragraph-4">Tbilisi, Georgia • English • Part time</div>Remote</a>'
        client=Fake({root:(200,card+'<a href="'+root+'?page=2">Next</a>'),root+'?page=2':(200,card)})
        rows=telus({'id':'telus','company':'TELUS','url':root},client)
        self.assertEqual(len(client.calls),2);self.assertEqual(len(rows),1);self.assertEqual(rows[0]['work_format'],'Remote')
    def test_public_page_never_verifies_jobs_or_projects(self):
        cfg=json.loads((ROOT/'dist/data/search-config.json').read_text())
        with tempfile.TemporaryDirectory() as tmp:
            d=Path(tmp);src={'id':'probe','company':'Example','platform_id':'p','adapter':'public_page','url':'x','enabled':True}
            data={'jobs.json':[{'id':'j','company':'Example','title':'Support','url':'x','status':'needs_review','last_verified_at':None}],'platforms.json':[{'id':'p','url':'x'}],'projects.json':[],'check-history.json':[],'search-config.json':cfg,'sources.json':[src],'update-status.json':{}}
            for name,value in data.items():(d/name).write_text(json.dumps(value))
            run(d,Fake({'x':(200,'<title>Example</title><p>'+'Public information '*20+'</p>')}),'2026-11-21T06:00:00Z')
            job=json.loads((d/'jobs.json').read_text())[0];p=json.loads((d/'platforms.json').read_text())[0]
            self.assertIsNone(job['last_verified_at']);self.assertNotIn('last_verified_at',p)
            self.assertEqual(p['availability_status'],'public_page_accessible')
            self.assertEqual(json.loads((d/'projects.json').read_text()),[])
    def test_source_error_does_not_abort_other_sources(self):
        with self.assertRaises(SourceError):workable({'url':'x'},Fake({'x':(403,'')}))
if __name__=='__main__':unittest.main()
