import unittest,sys,json
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
from adapters import jobsge,pharmbills
from radar import HttpClient,SourceError
from test_adapters import Fake

class Reliability(unittest.TestCase):
    def test_jobsge_existing_listing_on_second_page(self):
        root='https://jobs.ge/en/'
        row='<tr><td>*</td><td><a href="?view=jobs&id=123">Customer Support</a></td><td></td><td>Example</td><td>21 November</td><td>21 December</td></tr>'
        src={'id':'jobsge','company':'Jobs.ge','url':root,'_existing_ids':['123'],'_config':{'categories':{}}}
        client=Fake({root:(200,'<script>loaded_page<2</script>'),root+'?page=2':(200,row),root+'?view=jobs&id=123':(200,'Ad title: Customer Support Provided By: Example Deadline: 21 December Location: Tbilisi.')})
        self.assertEqual(jobsge(src,client)[0]['external_id'],'123')
        self.assertEqual(src['_discovery_counts']['listing_pages'],2)
    def test_failed_page_cannot_establish_absence(self):
        src={'id':'jobsge','url':'https://jobs.ge/en/'}
        with self.assertRaises(SourceError):jobsge(src,Fake({src['url']:(200,'loaded_page<2'),src['url']+'?page=2':(503,'')}))
    def test_pharm_requires_application_link(self):
        root='https://cooperation.pharmbills.com/locations/georgia';path='/openings/data-entry-georgia-remote'
        src={'id':'pharmbills','company':'Pharmbills','url':root,'_config':{'categories':{'Other':['data entry']}}}
        client=Fake({root:(200,f'<a href="{path}">Data Entry</a>'),'https://cooperation.pharmbills.com'+path:(200,'<h1>Data Entry in Georgia, Remote</h1>')})
        self.assertEqual(pharmbills(src,client),[])
        client.pages['https://cooperation.pharmbills.com'+path]=(200,'<h1>Data Entry in Georgia, Remote</h1><a href="https://cooperation.pharmbills.com/apply/data-entry-georgia-remote">Apply Now</a>')
        self.assertEqual(pharmbills(src,client)[0]['work_format'],'Remote')
    def test_transient_retry_but_no_retry_access_denied(self):
        from unittest.mock import patch
        c=HttpClient()
        with patch.object(c,'_request',side_effect=[(503,''),(200,'ok')]) as request,patch('radar.time.sleep'):
            self.assertEqual(c.raw('x'),(200,'ok'));self.assertEqual(request.call_count,2)
        with patch.object(c,'_request',return_value=(403,'')) as request:
            self.assertEqual(c.raw('x'),(403,''));self.assertEqual(request.call_count,1)

    def test_concentrix_skips_disabled_and_incomplete(self):
        from adapters import concentrix
        row=dict(ats_external_id='GE-1',job_title='Customer Support',country='Georgia',city='Tbilisi',long_description='English support',apply_url='https://example.com/apply',allow_applications='1',publish_on_job_listing='1')
        rows=[row,{**row,'ats_external_id':'GE-2','allow_applications':'0'},{**row,'ats_external_id':'GE-3','long_description':''}]
        body='<script type="application/json" id="jobsData">'+json.dumps({'ok':True,'data':rows})+'</script>'
        src={'id':'concentrix','company':'Concentrix','url':'x'}
        result=concentrix(src,Fake({'x':(200,body)}))
        self.assertEqual([r['external_id'] for r in result],['GE-1'])
        self.assertEqual(len(src['_detail_errors']),1)
