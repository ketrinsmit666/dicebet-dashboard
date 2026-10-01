"""Aggregate DWH exports locally. No player IDs are published. See README.md."""
import argparse,json,shutil
from pathlib import Path
import numpy as np
import pandas as pd
BUCKETS=[(1,7,'1–7 дней'),(8,14,'8–14 дней'),(15,30,'15–30 дней'),(31,60,'1–2 мес.'),(61,90,'2–3 мес.'),(91,180,'3–6 мес.'),(181,100000,'6 мес.+')]
PRIMARY=['TR','AR','CO','IN']
def records(df):
 return json.loads(df.to_json(orient='records',date_format='iso'))
def build(users,metrics,bonuses,registry,output,as_of,users_complete=False):
 out=Path(output);out.mkdir(parents=True,exist_ok=True)
 end=pd.Timestamp(as_of)-pd.Timedelta(days=1)
 u=pd.read_csv(users);m=pd.read_csv(metrics)
 assert not u.player_id.duplicated().any(),'Duplicate users'
 assert not m.duplicated(['player_id','activity_date']).any(),'Duplicate player/day'
 u['registration_date']=pd.to_datetime(u.registration_date);u['ftd_date']=pd.to_datetime(u.ftd_date)
 m['activity_date']=pd.to_datetime(m.activity_date)
 m=m[m.activity_date<=end].copy();start=m.activity_date.min();end=min(end,m.activity_date.max())
 # Missing bonus-only profiles can be shown as UNKNOWN; missing active profiles block retention.
 unknown_profiles=int(m.loc[~m.player_id.isin(u.player_id),'player_id'].nunique())
 registry_note='Только users: полная база регистраций не подтверждена; конверсия выборки.'
 full_from=start.strftime('%Y-%m') if users_complete else None
 if users_complete:registry_note='Полная выгрузка users; регистрационные когорты ограничены окном activity_start — as_of. Верификация отражает состояние контактов на дату выгрузки.'
 if registry:
  o=pd.read_csv(registry,usecols=['player_id','geo_short','registration_date','ftd_date','email_verified_flag','sms_verified_flag','deposit_count_total']).rename(columns={'geo_short':'geo'})
  o.registration_date=pd.to_datetime(o.registration_date);o.ftd_date=pd.to_datetime(o.ftd_date)
  missing=o[~o.player_id.isin(u.player_id)].copy()
  assert missing.ftd_date.isna().all(),'Old registry has FTD absent in users; reconcile exports first'
  u=pd.concat([u,missing],ignore_index=True);full_from=o.registration_date.min().strftime('%Y-%m')
  registry_note='Реестр регистраций 01.10.2026 дополнен users; отсутствующие в users игроки без FTD сохранены. Контакты — состояние выгрузки, не на дату регистрации.'
 u=u[u.registration_date<=end].copy();u.loc[u.ftd_date>end,'ftd_date']=pd.NaT
 u['reg_month']=u.registration_date.dt.strftime('%Y-%m');u['ftd_month']=u.ftd_date.dt.strftime('%Y-%m')
 u['verified']=((u.email_verified_flag==1)|(u.sms_verified_flag==1)).astype(int)
 u['ftd']=u.ftd_date.notna().astype(int);u['lag']=(u.ftd_date-u.registration_date).dt.days
 u['late']=u.ftd_date.notna()&(u.ftd_month>u.reg_month)
 u['age']=(end-u.ftd_date).dt.days
 # Day-grain money is authoritative; source nulls are tracked, never silently turned into known zero.
 fin=['deposit_cnt','deposit_sum_usd','bet_cnt','turnover_usd','win_amount_usd','ggr_usd','bonus_transferred_cnt','bonus_cost_usd','ngr_usd']
 m=m.merge(u[['player_id','geo','registration_date','ftd_date','reg_month','ftd_month']],on='player_id',how='left',validate='many_to_one')
 missing_active=m.geo.isna()&((m.bet_cnt>0)|(m.deposit_cnt>0))
 assert not missing_active.any(),'Missing profiles for active players'
 unknown_profiles=int(m.loc[m.geo.isna(),'player_id'].nunique())
 m.geo=m.geo.fillna('UNKNOWN')
 active=m[(m.deposit_cnt>0)|(m.bet_cnt>0)].sort_values(['player_id','activity_date']).copy()
 active['prev']=active.groupby('player_id').activity_date.shift()
 seed_count=0
 if 'previous_active_date' in active:
  supplied=pd.to_datetime(active.previous_active_date)
  assert not (active.prev.notna()&(supplied!=active.prev)).any(),'LAG does not match active history'
  assert not ((supplied>=active.activity_date)&supplied.notna()).any(),'LAG must precede activity'
  assert not (supplied.notna()&((active.activity_date-supplied).dt.days!=active.days_since_previous_active_day)).any(),'LAG day difference mismatch'
  seed_count=int((active.prev.isna()&supplied.notna()).sum())
  active['prev']=supplied
 active['idle']=(active.activity_date-active.prev).dt.days-1
 active['first_seen']=active.prev.isna().astype(int)
 first=active.groupby('player_id').activity_date.min()
 u['first_seen']=u.player_id.map(first)
 active['new_reg']=(active.registration_date==active.activity_date).astype(int)
 active['return_short']=active.idle.between(1,7).astype(int);active['reactivated']=(active.idle>=8).astype(int)
 active['continuing']=(active.idle==0).astype(int)
 agg=m.groupby(['activity_date','geo'])[fin].sum(min_count=1)
 bad=m.assign(financial_missing=m[['turnover_usd','ggr_usd','bonus_cost_usd','ngr_usd']].isna().any(axis=1).astype(int)).groupby(['activity_date','geo']).financial_missing.sum()
 counts=active.groupby(['activity_date','geo']).agg(active=('player_id','size'),new_reg=('new_reg','sum'),first_seen=('first_seen','sum'),return_short=('return_short','sum'),reactivated=('reactivated','sum'),continuing=('continuing','sum'))
 dep=m[m.deposit_cnt>0].groupby(['activity_date','geo']).size().rename('depositors')
 bettors=m[m.bet_cnt>0].groupby(['activity_date','geo']).size().rename('casino_players')
 regs=u.groupby(['registration_date','geo']).size().rename('registrations');regs.index.names=['activity_date','geo']
 ftd=u[u.ftd==1].groupby(['ftd_date','geo']).size().rename('ftd');ftd.index.names=['activity_date','geo']
 geos=sorted(set(u.geo.unique())|set(m.geo.unique()));dates=pd.date_range(start,end)
 ix=pd.MultiIndex.from_product([dates,geos],names=['activity_date','geo'])
 daily=agg.reindex(ix).fillna(0).join([counts,dep,bettors,bad,regs,ftd]).fillna(0)
 # Stocks are intervals, no daily player Cartesian product. Opening idle = d - previous_active - 1.
 react=[]
 active['next']=active.groupby('player_id').activity_date.shift(-1)
 for geo,g in active.groupby('geo'):
  last=g.activity_date.to_numpy(dtype='datetime64[D]').astype('int64');nxt=g.next.fillna(end+pd.Timedelta(days=1)).to_numpy(dtype='datetime64[D]').astype('int64')
  seeds=g[g.prev.notna()&(g.prev<start)]
  if len(seeds):
   last=np.concatenate([last,seeds.prev.to_numpy(dtype='datetime64[D]').astype('int64')]);nxt=np.concatenate([nxt,seeds.activity_date.to_numpy(dtype='datetime64[D]').astype('int64')])
  origin=np.datetime64(start.date(),'D').astype('int64');N=len(dates)
  ev=g[['activity_date','idle']].copy();ev['idx']=(ev.activity_date-start).dt.days
  for bi,(lo,hi,label) in enumerate(BUCKETS):
   a=np.maximum(last+lo+1,origin)-origin;b=np.minimum(np.minimum(last+hi+1,nxt),origin+N)-origin
   good=(a<=b)&(a<=N)&(b>=0);a=a[good].astype(int);b=b[good].astype(int)
   diff=np.zeros(N+2,dtype=np.int64);np.add.at(diff,a,1);np.add.at(diff,b+1,-1);stock=diff.cumsum()[:N+1]
   returned=np.zeros(N,dtype=np.int64);sel=ev[ev.idle.between(lo,hi)];np.add.at(returned,sel.idx.to_numpy(dtype=int),1)
   assert (returned<=stock[:N]).all(),'Return denominator mismatch'
   for i,d in enumerate(dates):
    react.append({'date':d.strftime('%Y-%m-%d'),'geo':geo,'bucket':bi,'base':int(stock[i]),'returned':int(returned[i]),'closing':int(stock[i+1])})
 r=pd.DataFrame(react)
 churn=r[r.bucket>=1].groupby(['date','geo']).agg(churn_open=('base','sum'),churn_close=('closing','sum'))
 churn.index=pd.MultiIndex.from_arrays([pd.to_datetime(churn.index.get_level_values(0)),churn.index.get_level_values(1)],names=ix.names)
 daily=daily.join(churn).fillna(0).reset_index();daily['date']=daily.activity_date.dt.strftime('%Y-%m-%d');daily=daily.drop(columns='activity_date')
 # Cohorts / FTD windows. Retention computed only where complete history of the window exists.
 am=active[['player_id','activity_date']].merge(u[['player_id','ftd_date']],on='player_id');am['day']=(am.activity_date-am.ftd_date).dt.days
 dm=m[['player_id','activity_date','deposit_cnt','ggr_usd','bonus_cost_usd','ngr_usd']].copy();dm['day']=(dm.activity_date-m.ftd_date).dt.days
 lastafter=am[am.day>=0].groupby('player_id').day.max();u['last_after']=u.player_id.map(lastafter).fillna(-1)
 observed_deps=m.groupby('player_id').deposit_cnt.sum();u['dep_observed']=u.player_id.map(observed_deps).fillna(0)
 # Lifetime counts are a snapshot and may include October 1; fixed windows are cut off at September 30.
 for w in [7,30]:
  z=dm[dm.day.between(0,w)].groupby('player_id').deposit_cnt.sum();u[f'dep{w}']=u.player_id.map(z).fillna(0)
  a=am[am.day.between(0,w)].groupby('player_id').size();u[f'ad{w}']=u.player_id.map(a).fillna(0)
 for lo,hi in [(1,3),(4,7),(8,14),(15,30)]:
  ids=am[am.day.between(lo,hi)].player_id.unique();u[f'r{hi}']=u.player_id.isin(ids).astype(int)
  u[f'b{hi}']=((u.age>=hi)&(u.ftd_date>=start)).astype(int);u[f'r{hi}']*=u[f'b{hi}']
 for w in [3,7,14,30]:u[f'roll{w}']=((u.last_after>=w)&(u.age>=w)&(u.ftd_date>=start)).astype(int)
 for key in ['ggr_usd','bonus_cost_usd','ngr_usd']:
  s=dm[dm.day.between(0,30)].groupby('player_id')[key].sum(min_count=1);u[key]=u.player_id.map(s).fillna(0)
 cohort=[]
 cohort_users=u[u.registration_date>=start]
 for dims,g in cohort_users.groupby(['reg_month','geo'],dropna=False):
  row={'month':dims[0],'geo':dims[1],'regs':len(g),'ftd':int(g.ftd.sum()),'verified':int(g.verified.sum()),'email':int(g.email_verified_flag.sum()),'sms':int(g.sms_verified_flag.sum()),'late':int(g.late.sum())}
  for w in [3,7,14,30]:row.update({f'b{w}':int(g[f'b{w}'].sum()),f'r{w}':int(g[f'r{w}'].sum()),f'roll{w}':int(g[f'roll{w}'].sum())})
  cohort.append(row)
 # Curve anchored on first observed bet only for registrations inside metrics coverage.
 bet=m[m.bet_cnt>0];firstbet=bet.groupby('player_id').activity_date.min();lastbet=bet.groupby('player_id').activity_date.max()
 curve=[]
 for anchor in ['ftd','bet']:
  anchor_date=u.ftd_date if anchor=='ftd' else u.player_id.map(firstbet)
  cu=u[['player_id','geo','reg_month','registration_date']].copy();cu['anchor']=anchor_date
  cu=cu[cu.anchor.notna()&(cu.anchor>=start)]
  if anchor=='bet':cu=cu[cu.registration_date>=start]
  cu['anchor_month']=cu.anchor.dt.strftime('%Y-%m');cu['age']=(end-cu.anchor).dt.days
  lastdates=active.groupby('player_id').activity_date.max() if anchor=='ftd' else lastbet
  cu['last']=(cu.player_id.map(lastdates)-cu.anchor).dt.days
  events=active[['player_id','activity_date']] if anchor=='ftd' else bet[['player_id','activity_date']]
  ce=events.merge(cu[['player_id','anchor']],on='player_id');ce['day']=(ce.activity_date-ce.anchor).dt.days
  exact={int(d):set(g.player_id) for d,g in ce[ce.day.between(0,30)].groupby('day')}
  for mode in ['mature_day','mature30']:
   for d in range(31):
    eligible=cu[cu.age>= (d if mode=='mature_day' else 30)].copy()
    eligible['rolling']=(eligible['last']>=d).astype(int);eligible['exact']=eligible.player_id.isin(exact.get(d,set())).astype(int)
    z=eligible.groupby(['geo','anchor_month','reg_month']).agg(base=('player_id','size'),rolling=('rolling','sum'),exact=('exact','sum')).reset_index()
    z['anchor']=anchor;z['mode']=mode;z['day']=d;curve+=records(z)
 # FTD cohorts and late FTD drilldown, with fixed-window funnel to avoid snapshot look-ahead.
 funnel=[];late=[]
 for onlylate,target in [(False,funnel),(True,late)]:
  sub=u[(u.ftd==1)&(u.ftd_date>=start)]
  if onlylate:sub=sub[sub.late]
  for (month,geo,reg),g in sub.groupby(['ftd_month','geo','reg_month']):
   row={'month':month,'geo':geo,'reg_month':reg,'n':len(g),'delay_sum':float(g.lag.sum()),'ftd_sum':float(g.ftd_amount_usd.sum())}
   for w in [7,30]:
    e=g[g.age>=w];row[f'base{w}']=len(e);row[f'active{w}']=int(e[f'ad{w}'].sum())
    for k in [1,2,3,5,8]:row[f'd{w}_{k}']=int((e[f'dep{w}']>=k).sum())
   e=g[g.age>=30]
   for key in ['ggr_usd','bonus_cost_usd','ngr_usd']:row[key]=float(e[key].sum())
   for w in [3,7,14,30]:row[f'b{w}']=int(g[f'b{w}'].sum());row[f'roll{w}']=int(g[f'roll{w}'].sum())
   for i,(lo,hi,_) in enumerate(BUCKETS):row[f'lag{i}']=int(g.lag.between(lo,hi).sum())
   target.append(row)
 # Daily FTD alert cube supports matched FTD-day ranges and fixed windows.
 alerts=[]
 for (fd,geo),g in u[(u.ftd==1)&(u.ftd_date>=start)].groupby(['ftd_date','geo']):
  e=g[g.age>=7]
  alerts.append({'date':str(fd.date()),'month':str(fd.date())[:7],'geo':geo,'base7':len(e),'dep2':int((e.dep7>=2).sum()),'dep3':int((e.dep7>=3).sum()),'r3':int(g.r3.sum()),'b3':int(g.b3.sum())})
 # Monthly unique active players cannot be reconstructed from daily user counts.
 active['month']=active.activity_date.dt.strftime('%Y-%m')
 monthly=active.groupby(['month','geo']).agg(mau=('player_id','nunique'),active_days=('player_id','size')).reset_index()
 # Bonus creation cohorts are separate from transaction-date cost in metrics.
 bonus=[];bonusmeta={}
 for chunk in pd.read_csv(bonuses,chunksize=100000):
  chunk['created']=pd.to_datetime(chunk.created_dttm);chunk=chunk[chunk.created<=end+pd.Timedelta(days=1)-pd.Timedelta(microseconds=1)]
  chunk=chunk.merge(u[['player_id','geo']],on='player_id',how='left');chunk.geo=chunk.geo.fillna('UNKNOWN')
  chunk['month']=chunk.created.dt.strftime('%Y-%m');chunk['issued']=1
  chunk['transferred']=chunk.transferred_to_main_account_flag.astype(str).str.lower().eq('true').astype(int)
  # Do not treat changed_dttm as transfer date. Amount is current state of issued bonus cohort.
  chunk['transferred_value']=chunk.transferred_to_main_account_usd_amount.fillna(0)*chunk.transferred
  chunk['fs']=chunk.freespin_amount.fillna(0)
  bonus+=records(chunk.groupby(['month','geo','bonus_type_name','given_bonus_state_name']).agg(issued=('issued','sum'),transferred=('transferred','sum'),transferred_value=('transferred_value','sum'),freespins=('fs','sum')).reset_index())
 bonus=records(pd.DataFrame(bonus).groupby(['month','geo','bonus_type_name','given_bonus_state_name'],as_index=False)[['issued','transferred','transferred_value','freespins']].sum())
 meta={'as_of':str(end.date()),'activity_start':str(start.date()),'source_snapshot':as_of,'full_registry_from':full_from,'registry_note':registry_note,'users':len(u),'metrics_rows':len(m),'active_users':active.player_id.nunique(),'financial_missing_rows':int(m[['ggr_usd','ngr_usd','turnover_usd','bonus_cost_usd']].isna().any(axis=1).sum()),'lag_seed_users':seed_count,'unknown_profile_users':unknown_profiles,'buckets':[x[2] for x in BUCKETS],'primary':PRIMARY,'geos':geos,'months':sorted(daily.date.str[:7].unique()),'warnings':['Активность = день со ставкой или депозитом. Бонусные операции без них не активность.','Неактивность и возвраты — в наблюдаемой базе. LAG добавляет '+str(seed_count)+' предыдущих активностей до начала истории; игроки без событий во всём окне всё ещё могут отсутствовать в базе чарна.','Линия от ставки использует ставки из metrics, календарные дни и регистрации внутри истории. Соответствие Any money bet в Amplitude требует подтверждения состава SQL.',registry_note+' Регистрационная история с '+str(full_from)+'. Неизвестные GEO бонусных операций: '+str(unknown_profiles)+' игроков.','Верификация — email или SMS, не KYC. Статусы контактов на момент выгрузки.','Выводов средств нет в новых CSV. Их показатели не подменяются нулями.','Bonus cost и NGR по датам — из metrics. Бонусная детализация — по месяцу выдачи, статус на дату выгрузки.']}
 data={'meta':meta,'daily':records(daily),'reactivation':records(r),'cohorts':cohort,'curves':curve,'funnel':funnel,'late':late,'monthly':records(monthly),'bonuses':bonus,'alerts':alerts}
 (out/'dashboard_data.json').write_text(json.dumps(data,ensure_ascii=False,separators=(',',':'),allow_nan=False))
 print(json.dumps(meta,ensure_ascii=False,indent=2))
 return data
if __name__=='__main__':
 p=argparse.ArgumentParser();p.add_argument('--users',required=True);p.add_argument('--metrics',required=True);p.add_argument('--bonuses',required=True);p.add_argument('--registry');p.add_argument('--output',default=str(Path(__file__).parent));p.add_argument('--as-of',required=True);p.add_argument('--users-complete',action='store_true');a=p.parse_args();build(a.users,a.metrics,a.bonuses,a.registry,a.output,a.as_of,a.users_complete)
