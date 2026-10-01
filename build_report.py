"""Streaming lifecycle aggregation; only aggregate counts are embedded in HTML."""
import csv,json,argparse
from pathlib import Path
from collections import defaultdict
from datetime import date,timedelta
DAYS=(3,7,14,30)
REGDAYS=(1,3,7,14,30)
WINDOWS=('active_d1_3','active_d4_7','active_d8_14','active_d15_30')
def aggregate(path,snapshot):
    groups={};seen=set();meta={'snapshot_date':snapshot,'rows':0,'first_registration':None,'last_registration':None}
    with Path(path).open(encoding='utf-8-sig',newline='') as file:
        reader=csv.DictReader(file)
        required={'ftd_date','max_active_day_after_ftd','client_hk','geo_short','registration_month','ftd_month','ftd_flag','registered_flag','registration_date','has_verified_contact_flag','has_partner_id_flag'}|{f'matured_d{d}' for d in DAYS}|{f'retained_d{d}_plus' for d in DAYS}|set(WINDOWS)|{f'deposit_{d}_flag' for d in (2,3,5,8)}|{f'registration_matured_d{d}' for d in REGDAYS}|{f'ftd_within_d{d}_flag' for d in REGDAYS}|{f'{m}_{s}_usd' for m in ('ggr','bonus','ngr') for s in ('total','d0_30')}
        if required-set(reader.fieldnames or []):raise ValueError('Missing lifecycle columns: '+str(required-set(reader.fieldnames or [])))
        for r in reader:
            uid=r['client_hk']
            if not uid or uid in seen:raise ValueError('Duplicate or empty client key')
            seen.add(uid)
            def flag(k):
                if r[k] not in ('0','1'):raise ValueError('Invalid binary flag: '+k)
                return int(r[k])
            ftd=flag('ftd_flag');geo=r['geo_short'].strip() or 'unknown';reg=r['registration_month'][:7];fm=r['ftd_month'][:7] if ftd else ''
            if ftd and not fm:raise ValueError('FTD flag without FTD month')
            key=(geo,reg,fm,flag('has_verified_contact_flag'),flag('has_partner_id_flag'))
            if key not in groups:groups[key]={'geo':geo,'reg':reg,'ftd_month':fm,'contact':key[3],'partner':key[4],'v':defaultdict(float)}
            v=groups[key]['v'];v['users']+=1;v['ftd']+=ftd;v['verified']+=key[3]
            if flag('registered_flag')!=1:raise ValueError('Row is not registered')
            for d in DAYS:
                mature=flag(f'matured_d{d}')
                if mature and not ftd:raise ValueError('Mature FTD window without FTD')
                v[f'm{d}']+=mature;v[f'r{d}']+=mature*flag(f'retained_d{d}_plus')
            if ftd and flag('matured_d30'):
                last=float(r['max_active_day_after_ftd'] or -1)
                recent=date.fromisoformat(r['ftd_date'][:10])>=date.fromisoformat(snapshot)-timedelta(days=89)
                v['curve_den']+=1;v['curve90_den']+=int(recent)
                for day in range(31):
                    returned=int(day==0 or last>=day)
                    v[f'curve_{day}']+=returned;v[f'curve90_{day}']+=returned*int(recent)
            for d,w in zip(DAYS,WINDOWS):v[w]+=flag(f'matured_d{d}')*flag(w)
            for d in (2,3,5,8):v[f'dep{d}']+=ftd*flag(f'deposit_{d}_flag')
            for d in REGDAYS:
                mature=flag(f'registration_matured_d{d}');v[f'regm{d}']+=mature;v[f'regf{d}']+=mature*flag(f'ftd_within_d{d}_flag')
            for suffix in ('total','d0_30'):
                include=ftd if suffix=='total' else flag('matured_d30')
                for metric in ('ggr','bonus','ngr'):v[f'{metric}_{suffix}']+=include*float(r[f'{metric}_{suffix}_usd'] or 0)
            meta['rows']+=1;dt=r['registration_date'][:10]
            meta['first_registration']=min(meta['first_registration'] or dt,dt);meta['last_registration']=max(meta['last_registration'] or dt,dt)
    if not groups:raise ValueError('Empty lifecycle CSV')
    rows=[]
    for g in groups.values():
        g['v']={k:round(v,2) for k,v in g['v'].items()};rows.append(g)
    return {'meta':meta,'rows':rows}
def write_report(cube,output):
    template=Path(__file__).with_name('template.html').read_text()
    Path(output).write_text(template.replace('__PAYLOAD__',json.dumps(cube,ensure_ascii=False,separators=(',',':')).replace('</','<\\/')))
if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--input',type=Path);p.add_argument('--cube',type=Path,required=True);p.add_argument('--output',type=Path,required=True);p.add_argument('--as-of',default=date.today().isoformat());a=p.parse_args()
    if a.input:
        data=aggregate(a.input,a.as_of);a.cube.write_text(json.dumps(data,ensure_ascii=False,separators=(',',':')))
    else:data=json.loads(a.cube.read_text())
    write_report(data,a.output);print('Retention:',data['meta']['rows'],'players,',len(data['rows']),'aggregate groups')
