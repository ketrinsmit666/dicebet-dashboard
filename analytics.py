"""Matched cohort comparisons. No significance claim; thresholds are configurable."""
import calendar
from datetime import date,timedelta
from collections import defaultdict
PRIMARY=['TR','AR','CO','IN']
DEFAULTS={'rate_pp':5.0,'relative_pct':20.0,'min_base':100,'min_count':30}
METRICS={
 'dep2':('Конверсия FTD → 2+ депозитов · D7','retention',2,'dep1_2',7,'d2','m7','rate'),
 'dep3':('Конверсия FTD → 3+ депозитов · D7','retention',2,'dep2_3',7,'d3','m7','rate'),
 'dep5':('Конверсия FTD → 5+ депозитов · D7','retention',2,'dep3_5',7,'d5','m7','rate'),
 'dep8':('Конверсия FTD → 8+ депозитов · D7','retention',2,'dep5_8',7,'d8','m7','rate'),
 'step23':('Переток 2 → 3 депозита · D7','retention',2,'dep2_3',7,'d3','d2','rate'),
 'step35':('Переток 3 → 5 депозитов · D7','retention',2,'dep3_5',7,'d5','d3','rate'),
 'step58':('Переток 5 → 8 депозитов · D7','retention',2,'dep5_8',7,'d8','d5','rate'),
 'return3':('Возврат в D1–3 после FTD','retention',1,'welcome',3,'a3','m3','rate'),
 'return7':('Возврат в D4–7 после FTD','retention',1,'welcome',7,'a7','m7','rate'),
 'return14':('Возврат в D8–14 после FTD','retention',1,'welcome',14,'a14','m14','rate'),
 'return30':('Возврат в D15–30 после FTD','retention',1,'welcome',30,'a30','m30','rate'),
 'late':('Число долётов','late_ftd',0,'late_ftd',0,'late',None,'count'),
 'late_active':('Среднее активных дней долётчиков · D7','late_ftd',7,'welcome',7,'days7','late7','mean'),
 'late_dep2':('Долётчики: FTD → 2+ депозита · D7','late_ftd',7,'dep1_2',7,'late_d2','late7','rate'),
 'late_dep3':('Долётчики: 2 → 3 депозита · D7','late_ftd',7,'dep2_3',7,'late_d3','late_d2','rate'),
}
METRICS['ngr30']=('NGR / зрелый FTD · D0–D30','retention',3,'welcome',30,'ngr30','m30','mean')
PULSE_LABELS={'deposits_cnt':'Число депозитов','depositors':'Депозиторы · сумма дневных чисел','deposit_sum_usd':'Сумма депозитов, USD','withdrawals_cnt':'Число выводов','withdrawers':'Выводящие · сумма дневных чисел','withdrawal_sum_usd':'Сумма выводов, USD','net_deposit_usd':'Net deposit, USD','casino_players':'Casino players · сумма дневных чисел','casino_bets_cnt':'Ставки казино','casino_turnover_usd':'Casino turnover, USD','casino_ggr_usd':'Casino GGR, USD','real_turnover_usd':'Real turnover, USD','bonus_turnover_usd':'Bonus turnover, USD','real_ggr_usd':'Real GGR, USD','bonus_ggr_usd':'Bonus GGR, USD','bonuses_issued':'Выдано бонусов','bonus_users':'Bonus users · сумма дневных чисел','bonus_issued_usd':'Выдано бонусов, USD','freespins_issued':'Выдано фриспинов','bonuses_transferred':'Переведено бонусов','bonus_cost_usd':'Bonus cost, USD'}
for key,label in PULSE_LABELS.items():METRICS['pulse_'+key]=(label,'pulsation',0,None,0,'pulse_'+key,None,'count')
def previous(month):
 return (date.fromisoformat(month+'-01')-timedelta(days=1)).strftime('%Y-%m')
def compare(cube,month,config=None):
 cfg={**DEFAULTS,**(config or {})};prev=previous(month);results=[];skipped=defaultdict(int)
 for metric,spec in METRICS.items():
  label,page,tab,flow,window,num,den,kind=spec
  source='pulsation' if metric.startswith('pulse_') else 'late' if metric.startswith('late') else 'lifecycle'
  if not cube.get('cutoffs',{}).get(source):skipped['Нет источника']+=1;continue
  cutoff=date.fromisoformat(cube['cutoffs'][source])-timedelta(days=window)
  cap=min(calendar.monthrange(*map(int,month.split('-')))[1],calendar.monthrange(*map(int,prev.split('-')))[1],(cutoff-date.fromisoformat(month+'-01')).days+1)
  if not any(r['month']==prev and num in r['v'] for r in cube['rows']):skipped['Нет предыдущего периода']+=1;continue
  if cap<=0:skipped['Нет зрелых данных за выбранный месяц']+=1;continue
  for geo in sorted({r['geo'] for r in cube['rows']}):
   vals=[]
   for m in [month,prev]:
    group=[r['v'] for r in cube['rows'] if r['geo']==geo and r['month']==m and r['day']<=cap]
    n=sum(r.get(num,0) for r in group);d=sum(r.get(den,0) for r in group) if den else None
    vals.append((n,d))
   (n,d),(pn,pd)=vals
   if den and min(d,pd)<cfg['min_base']:skipped['Малая база']+=1;continue
   if not den and max(abs(n),abs(pn))<cfg['min_count']:skipped['Малая база']+=1;continue
   cur=n/d*(100 if kind=='rate' else 1) if den else n
   old=pn/pd*(100 if kind=='rate' else 1) if den else pn
   delta=cur-old;rel=100*delta/abs(old) if old else None
   strong=abs(delta)>=cfg['rate_pp'] if kind=='rate' else (rel is not None and abs(rel)>=cfg['relative_pct']) or (old==0 and abs(cur)>=cfg['min_count'])
   if strong:results.append(dict(metric=metric,label=label,page=page,tab=tab,flow=flow,geo=geo,month=month,previous_month=prev,current=cur,previous=old,delta=delta,relative=rel,kind=kind,n=n,base=d,previous_n=pn,previous_base=pd,days=cap,window=window))
 return sorted(results,key=lambda r:(r['delta']>=0,-abs(r['delta']))),dict(skipped)
