"""Build in a temporary directory, validate, then publish output files locally."""
from pathlib import Path
import argparse,tempfile,shutil
from build_data import build
from render_html import render
ROOT=Path(__file__).resolve().parent
if __name__=='__main__':
 p=argparse.ArgumentParser();p.add_argument('--users',required=True);p.add_argument('--metrics',required=True);p.add_argument('--bonuses',required=True);p.add_argument('--registry');p.add_argument('--as-of',required=True);p.add_argument('--users-complete',action='store_true');a=p.parse_args()
 with tempfile.TemporaryDirectory() as tmp:
  temp=Path(tmp)
  for f in ['targets.csv','manual_facts.csv','dashboard.css','dashboard.js']:shutil.copyfile(ROOT/f,temp/f)
  build(a.users,a.metrics,a.bonuses,a.registry,temp,a.as_of,a.users_complete);render(temp)
  for f in ['dashboard_data.json','index.html','retention.html','pulsation.html','late_ftd.html','reactivation.html']:
   target=ROOT/f;staged=target.with_suffix(target.suffix+'.tmp');shutil.copyfile(temp/f,staged);staged.replace(target)
 print('Updated locally. Publish validated output files in one Git commit/deployment.')
