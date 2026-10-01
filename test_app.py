"""Run: python -m unittest test_app.py"""
import unittest
from analytics import compare
class AlertTests(unittest.TestCase):
 def test_rates_match_days_and_ignore_small_bases(self):
  c={'cutoffs':{'lifecycle':'2026-09-29'},'rows':[
   {'geo':'TR','month':m,'day':d,'v':{'m7':n,'d2':v}} for m,d,n,v in [('2026-09',1,100,30),('2026-08',1,100,60),('2026-08',25,100,0)]]}
  a,_=compare(c,'2026-09');a=next(x for x in a if x['metric']=='dep2')
  self.assertEqual(a['days'],22);self.assertEqual(a['previous'],60);self.assertEqual(a['current'],30)
  self.assertFalse(compare(c,'2026-10')[0]);self.assertFalse(compare(c,'2026-09',{'min_base':101})[0])
 def test_zero_baseline_and_zero_denominator(self):
  c={'cutoffs':{'late':'2026-09-29'},'rows':[{'geo':'TR','month':'2026-08','day':1,'v':{'late':0}},{'geo':'TR','month':'2026-09','day':1,'v':{'late':40}}]}
  a,_=compare(c,'2026-09');self.assertEqual(a[0]['relative'],None)
class AppTests(unittest.TestCase):
 def test_pages(self):
  from streamlit.testing.v1 import AppTest
  for p in ['home','late_ftd','retention','crm','reactivation','pulsation','projects']:
   app=AppTest.from_file('app.py',default_timeout=30)
   app.query_params['page']=p;app.run();self.assertFalse(list(app.exception),str(app.exception))
  app=AppTest.from_file('app.py',default_timeout=30);app.query_params.update(page='retention',month='2026-09',geo='TR',tab='2',alert='dep2');app.run();self.assertFalse(list(app.exception))
if __name__=='__main__':unittest.main()
