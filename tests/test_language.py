import unittest,sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
from radar import language_blocker
class LanguageRequirements(unittest.TestCase):
    cfg={'excluded_title_languages':['German','French','Italian','Spanish']}
    def check(self,body):return language_blocker({'title':'Customer Service Representative','description':body},self.cfg)
    def test_hidden_requirement(self):
        self.assertIsNotNone(self.check('Become a German-speaking Customer Support Specialist.'))
        self.assertIsNotNone(self.check('You can speak fluently in German, Italian, Spanish, or French (B2-C1 level).'))
    def test_optional_and_incidental(self):
        self.assertIsNone(self.check('German is not required. English fluency required.'))
        self.assertIsNone(self.check('German is a plus.'))
        self.assertIsNone(self.check('We are a German company. Fluent English required.'))
    def test_allowed_alternative(self):
        self.assertIsNone(self.check('Fluent English or German required.'))
    def test_both_languages_required(self):
        self.assertIsNotNone(self.check('Fluent German and English required.'))
