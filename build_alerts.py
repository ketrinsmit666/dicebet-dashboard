"""Run on DWH export host; outputs aggregates only."""
import argparse,csv,json
from collections import defaultdict
from datetime import date,timedelta
from pathlib import Path

def build(lifecycle,late,as_of,pulsation=None):
 groups={};cutoff=date.fromisoformat(as_of)-timedelta(days=1)
 def bucket(geo,dt):
  d=date.fromisoformat(dt[:10]);key=(geo,d.strftime('%Y-%m'),d.day)
  return groups.setdefault(key,defaultdict(float))
 if lifecycle and Path(lifecycle).exists():
  with open(lifecycle,encoding='utf-8-sig') as f:
   for r in csv.DictReader(f):
    if r['ftd_flag']!='1' or r['ftd_date'][:10]>cutoff.isoformat():continue
    v=bucket(r['geo_short'],r['ftd_date'])
    for d,key in [(3,'active_d1_3'),(7,'active_d4_7'),(14,'active_d8_14'),(30,'active_d15_30')]:
     if r[f'matured_d{d}']=='1':v[f'm{d}']+=1;v[f'a{d}']+=int(r[key])
    if r['matured_d30']=='1':v['ngr30']+=float(r['ngr_d0_30_usd'] or 0)
    if r['matured_d7']=='1':
     for n in [2,3,5,8]:v['d'+str(n)]+=int(float(r['deposit_count_d7'])>=n)
 if late and Path(late).exists():
  with open(late,encoding='utf-8-sig') as f:
   for r in csv.DictReader(f):
    if r['ftd_date'][:10]>cutoff.isoformat():continue
    v=bucket(r['geo_short'],r['ftd_date']);v['late']+=1
    if float(r['days_since_ftd'])>=7:
     v['late7']+=1;v['days7']+=float(r['active_days_d7'])
     for n in [2,3]:v['late_d'+str(n)]+=int(float(r['deposit_count_d7'])>=n)
 pulse_cutoff=None
 if pulsation and Path(pulsation).exists():
  with open(pulsation,encoding='utf-8-sig') as f:
   for r in csv.DictReader(f):
    dt=r['dt'][:10]
    if dt>cutoff.isoformat():continue
    pulse_cutoff=max(pulse_cutoff or dt,dt);v=bucket('ALL',dt)
    for key,value in r.items():
     if key!='dt':v['pulse_'+key]+=float(value or 0)
 return {'snapshot_date':as_of,'cutoffs':{**({'pulsation':pulse_cutoff} if pulse_cutoff else {}),**({'lifecycle':cutoff.isoformat()} if lifecycle else {}),**({'late':cutoff.isoformat()} if late else {})},'rows':[{'geo':g,'month':m,'day':d,'v':dict(v)} for (g,m,d),v in groups.items()]}
if __name__=='__main__':
 p=argparse.ArgumentParser();p.add_argument('--lifecycle');p.add_argument('--late');p.add_argument('--pulsation');p.add_argument('--as-of',required=True);p.add_argument('--output',default='data/alerts_cube.json');a=p.parse_args()
 Path(a.output).write_text(json.dumps(build(a.lifecycle,a.late,a.as_of,a.pulsation),ensure_ascii=False,separators=(',',':')))
