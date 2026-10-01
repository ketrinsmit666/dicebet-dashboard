"""Department portal. Run: python -m streamlit run app.py"""
from pathlib import Path
from html import escape
from urllib.parse import urlencode
import csv,json,re,os
import pandas as pd
import plotly.graph_objects as go
import streamlit as st
import streamlit.components.v1 as components
from analytics import PRIMARY,compare,DEFAULTS
ROOT=Path(__file__).resolve().parent
# Accept both a structured project and browser uploads flattened into the root.
DEFAULT_DATA=ROOT/'data' if (ROOT/'data/targets.csv').is_file() else ROOT
DEFAULT_SITE=ROOT/'reporting/site' if (ROOT/'reporting/site/retention.html').is_file() else ROOT
DATA=Path(os.environ.get('REPORT_DATA_DIR',DEFAULT_DATA))
SITE=Path(os.environ.get('REPORT_SITE_DIR',DEFAULT_SITE))
PAGES={'home':'Главная · план–факт','late_ftd':'Долёты','retention':'Ретеншен и воронка','crm':'CRM-рассылки','reactivation':'Реактивация','pulsation':'Операционная пульсация','projects':'Задачи команды'}
FLOWS={'welcome':'Вся welcome-цепочка','dep1_2':'Письма: 1 → 2 депозит','dep2_3':'Письма: 2 → 3 депозит','dep3_5':'Письма: 3 → 5 депозитов','dep5_8':'Письма: 5 → 8 депозитов','late_ftd':'Письма для долётчиков'}
st.set_page_config(page_title='Отчёты отдела',layout='wide')

def load(name,default=None):
 p=DATA/name
 return json.loads(p.read_text()) if p.exists() else default

def csvrows(name):
 p=DATA/name
 if not p.exists():return []
 with p.open(encoding='utf-8-sig',newline='') as f:return list(csv.DictReader(f))
def url(page,**kw):return '?'+urlencode({'page':page,**{k:v for k,v in kw.items() if v is not None}})
def link(label,page,**kw):return f'<a target="_self" href="{escape(url(page,**kw),quote=True)}">{escape(label)}</a>'
def fmt(n):return '—' if n is None else f'{float(n):,.2f}'.rstrip('0').rstrip('.').replace(',',' ')
def go_page(p):
 st.query_params.clear();st.query_params['page']=p;st.rerun()
page=st.query_params.get('page','home')
if page not in PAGES:page='home'
with st.sidebar:
 st.title('Отчёты отдела')
 for key,label in PAGES.items():
  if st.button(label,key='nav_'+key,use_container_width=True,type='primary' if key==page else 'secondary'):go_page(key)
 st.caption('Основные GEO: TR · AR · CO · IN')
 st.caption('Снимки данных имеют собственную дату. Октябрьские факты появятся после новой выгрузки.')
if page!='home':
 if st.button('← На главную'):go_page('home')
plans=csvrows('targets.csv');actuals=load('actuals.json',[]);cube=load('alerts_cube.json',{'rows':[]});rules=load('alert_rules.json',DEFAULTS)
manual=csvrows('manual_facts.csv')
for row in manual:
 actuals=[r for r in actuals if tuple(r.get(k) for k in ['month','section','geo','metric'])!=tuple(row[k] for k in ['month','section','geo','metric'])]
 actuals.append({**row,'actual':float(row['actual']) if row['actual'] else None})

def plan_table(items):
 rows=[]
 for p in items:
  fact=next((r for r in actuals if all(r.get(k)==p[k] for k in ['month','section','geo','metric'])),{})
  prev_month=__import__('analytics').previous(p['month'])
  prior=next((r.get('actual') for r in actuals if all(r.get(k)==p[k] for k in ['section','geo','metric']) and r.get('month')==prev_month),None)
  if prior is None and p.get('previous_month'):prior=float(p['previous_month'])
  target=float(p['target']) if p['target'] else None;value=fact.get('actual');ratio=100*value/target if value is not None and target else None
  color=f'hsl({min(120,max(0,ratio*1.2))},75%,85%)' if ratio is not None else '#eef1f7'
  suffix='%' if p['unit']=='percent' else ''
  rows.append('<tr>'+f'<td>{escape(p["geo"])}</td><td>{link(p["label"],p["section"],month=p["month"],geo=p["geo"])}</td><td>{fmt(prior)}</td><td>{fmt(target)}{suffix if target is not None else ""}</td><td>{fmt(value)}{suffix if value is not None else ""}</td><td style="background:{color};font-weight:700">{fmt(ratio)}{"%" if ratio is not None else ""}</td><td>{escape(p.get("responsible") or "—")}</td><td>{escape(fact.get("as_of","—"))}</td></tr>')
 st.markdown('<style>table.pf{width:100%;border-collapse:collapse}table.pf td,table.pf th{padding:10px;text-align:left;border-bottom:1px solid #dce3ed}</style><div style="overflow:auto"><table class="pf"><tr><th>GEO</th><th>Цель</th><th>Пред. месяц</th><th>План</th><th>Факт</th><th>Выполнение</th><th>Ответственный</th><th>Срез факта</th></tr>'+''.join(rows)+'</table></div>',unsafe_allow_html=True)

def related(flow=None):
 st.markdown('**Связанные CRM-отчёты · макет**')
 keys=[flow] if flow else list(FLOWS)
 st.markdown(' · '.join(link(FLOWS[k],'crm',flow=k,geo=st.query_params.get('geo','all'),month=st.query_params.get('month','all')) for k in keys),unsafe_allow_html=True)
 st.caption('Рассылки ещё не подключены. Ссылки открывают заготовки нужных цепочек; показатели не подставлены.')

def alert_block(month):
 st.subheader('Сильные изменения к предыдущему месяцу')
 with st.expander('Порог алертов и методика'):
  cfg=dict(rules)
  cfg['rate_pp']=st.number_input('Изменение конверсии, п.п.',min_value=0.1,value=float(rules['rate_pp']))
  cfg['relative_pct']=st.number_input('Изменение количества / среднего, %',min_value=1.0,value=float(rules['relative_pct']))
  cfg['min_base']=st.number_input('Минимальная база в каждом месяце',min_value=1,value=int(rules['min_base']))
  st.caption('Сравниваются одинаковые дни месяца FTD и завершённые окна: воронка D7, возврат по фиксированным интервалам. Это пороговые сигналы, не статистическая значимость. Rolling retention и lifetime-воронка исключены из алертов из-за разной длины наблюдения. NGR сравнивается на зрелом D0–D30. Пульсация — суммы за одинаковые дни; суммы дневных пользователей не равны уникальным игрокам месяца. Начальные правила можно изменить в data/alert_rules.json.')
 alerts,skipped=compare(cube,month,cfg)
 st.caption('Последний полностью используемый день: '+str(cube.get('cutoffs',{}))+'. Нет факта — нет вывода о падении.')
 def show(items):
  if not items:st.info('Сильных изменений на достаточной базе не обнаружено либо нет сопоставимых данных.');return
  for a in items:
   unit=' п.п.' if a['kind']=='rate' else ''
   text=f"{a['geo']} · {a['label']}: {fmt(a['previous'])} → {fmt(a['current'])}; Δ {fmt(a['delta'])}{unit}"
   (st.info if a['metric'].startswith('pulse_') else st.warning if a['delta']<0 else st.success)(text)
   st.caption(f"{a['previous_month']} → {month}, дни FTD 1–{a['days']}. База: {fmt(a['previous_base'])} → {fmt(a['base'])}." if a['base'] is not None else f"{a['previous_month']} → {month}, дни 1–{a['days']}.")
   st.markdown(link('Открыть показатель и сравнение',a['page'],month=month,geo=a['geo'],tab=a['tab'],alert=a['metric'])+(' · '+link('Связанные письма', 'crm',flow=a['flow'],geo=a['geo'],month=month) if a['flow'] else ''),unsafe_allow_html=True)
 show([a for a in alerts if a['geo'] in PRIMARY+['ALL']])
 with st.expander('Другие GEO · изменения'):show([a for a in alerts if a['geo'] not in PRIMARY+['ALL']])
 with st.expander('Почему часть показателей не проверена'):st.json(skipped)


def focus_alert():
 metric=st.query_params.get('alert')
 if not metric:return
 month=st.query_params.get('month','');geo=st.query_params.get('geo','')
 items,_=compare(cube,month,{**rules,'rate_pp':0,'relative_pct':0,'min_base':1,'min_count':0})
 a=next((x for x in items if x['metric']==metric and x['geo']==geo),None)
 if a:
  st.subheader('Сравнение из алерта: '+a['label'])
  c1,c2=st.columns(2);c1.metric(a['previous_month'],fmt(a['previous']));c2.metric(a['month'],fmt(a['current']),fmt(a['delta'])+(' п.п.' if a['kind']=='rate' else ''))
  st.caption(f"GEO {geo}; дни месяца FTD 1–{a['days']}; окно D{a['window']}. Числитель / база: {fmt(a['previous_n'])} / {fmt(a['previous_base'])} → {fmt(a['n'])} / {fmt(a['base'])}. Ниже полный отчёт: его общий период наблюдения может отличаться от фиксированного окна алерта.")
  if a['flow']:related(a['flow'])

def embedded(name):
 html=(SITE/(name+'.html')).read_text()
 params={k:st.query_params.get(k,'') for k in ['month','geo','tab']}
 if name=='retention' and params['month'] not in ['', 'all'] and not any(r['ftd_month']==params['month'] for r in load('retention_cube.json',{'rows':[]})['rows']):
  st.info('За этот месяц FTD данные ещё не поступили. Выберите раздел заново в меню для просмотра доступных периодов.');return
 q=urlencode({'ftd_month':params['month'],'geo':params['geo']})
 html=html.replace('new URLSearchParams(location.search)','new URLSearchParams('+json.dumps('?'+q)+')')
 html=html.replace('href="index.html"','target="_top" href="?page=home"')
 js=''
 if name=='retention':
  js+="if("+json.dumps(params['tab'])+"!==''&&Number("+json.dumps(params['tab'])+")>=0&&Number("+json.dumps(params['tab'])+")<=4)active=Number("+json.dumps(params['tab'])+");"
  js+="""const relatedHtml=(keys)=>'<section class="panel wide"><h2>Связанные CRM-рассылки · макет</h2>'+keys.map(k=>'<p><a target="_top" href="?page=crm&flow='+k+'&geo='+encodeURIComponent($('geo').value)+'&month='+encodeURIComponent($('ftd_month').value)+'">'+({welcome:'Вся welcome-цепочка',dep1_2:'Письма 1 → 2 депозит',dep2_3:'Письма 2 → 3 депозит',dep3_5:'Письма 3 → 5 депозитов',dep5_8:'Письма 5 → 8 депозитов'}[k])+'</a></p>').join('')+'<p>Ожидает подключения данных рассылок.</p></section>';const originalFunnel=funnel;funnel=(a,v)=>relatedHtml(['dep1_2','dep2_3','dep3_5','dep5_8'])+originalFunnel(a,v);const originalRetention=retention;retention=(a,v)=>relatedHtml(['welcome'])+originalRetention(a,v);"""
 if name=='late_ftd':
  js+="const incoming="+json.dumps(params)+";for(const [key,value] of [['geo',incoming.geo],['ftd',incoming.month]])if([...$(key).options].some(x=>x.value===value))$(key).value=value;if(incoming.month&&planRows.some(p=>p.month===incoming.month))planMonth=incoming.month;if(incoming.tab!==''&&Number(incoming.tab)>=0&&Number(incoming.tab)<=7)active=Number(incoming.tab);"
  if st.query_params.get('alert'):js+="activityWindow='d7';"
  js+="""const originalActivity=activityPage;activityPage=(a)=>'<section class="panel"><h2>Связанные CRM-рассылки · макет</h2>'+['dep1_2','dep2_3','dep3_5','dep5_8'].map((k,i)=>'<p><a target="_top" href="?page=crm&flow='+k+'&geo='+encodeURIComponent($('geo').value)+'&month='+encodeURIComponent($('ftd').value)+'">Письма '+['1 → 2','2 → 3','3 → 5','5 → 8'][i]+' депозит</a></p>').join('')+'</section>'+originalActivity(a);"""
 if js:
  pos=html.rfind('render();');html=html[:pos]+js+html[pos:]
 components.html(html,height=1300,scrolling=True)

if page=='home':
 st.title('План–факт отдела')
 months=sorted({r['month'] for r in plans}|{r['month'] for r in actuals},reverse=True)
 desired=st.query_params.get('month',months[0]);month=st.selectbox('Месяц',months,index=months.index(desired) if desired in months else 0)
 selected=[r for r in plans if r['month']==month]
 st.caption('Красный → жёлтый → зелёный: 0% → 50% → 100% выполнения. «—» означает отсутствие факта или плана.')
 plan_table(sorted([r for r in selected if r['geo'] in PRIMARY],key=lambda r:PRIMARY.index(r['geo'])))
 if month=='2026-10':st.info('На скрине цели RR 3D пустые. Нужно заполнить план и подтвердить, что RR 3D означает наш D3+ rolling retention. Октябрьские данные пока не поступили.')
 with st.expander('Общие цели команды',expanded=True):plan_table([r for r in selected if r['geo']=='ALL'])
 with st.expander('Другие GEO · план–факт'):plan_table([r for r in selected if r['geo'] not in PRIMARY+['ALL']])
 alert_block(month)
 st.subheader('Разделы отчётов')
 st.markdown(' · '.join(link(v,k) for k,v in PAGES.items() if k!='home'),unsafe_allow_html=True)
 st.subheader('Rolling retention D0–D30 · FTD за последние 90 дней')
 lifecycle=load('retention_cube.json',{'rows':[],'meta':{}})
 def plot(geos):
  fig=go.Figure()
  for geo in geos:
   vals=[r['v'] for r in lifecycle['rows'] if r['geo']==geo];den=sum(v.get('curve90_den',0) for v in vals)
   if den:fig.add_scatter(x=list(range(31)),y=[100*sum(v.get('curve90_'+str(d),0) for v in vals)/den for d in range(31)],name=f'{geo} · {int(den)} FTD',mode='lines+markers')
  fig.update_layout(yaxis=dict(range=[0,100],title='Retention, %'),xaxis_title='День после FTD',height=430)
  st.plotly_chart(fig,use_container_width=True)
 plot(PRIMARY)
 with st.expander('Другие GEO · график'):plot(sorted({r['geo'] for r in lifecycle['rows']}-set(PRIMARY)))
 st.caption('Единый знаменатель: зрелые D30 FTD. Активность на Dn или позднее, включая дни после D30. Срез '+lifecycle['meta'].get('snapshot_date','—')+'. Фильтр месяца план–факта к этому обзору не применяется.')
elif page in ['late_ftd','retention','pulsation']:
 focus_alert()
 if page=='retention':related('welcome')
 embedded(page)
elif page=='crm':
 st.title('CRM-рассылки · макет')
 flow=st.query_params.get('flow','welcome');flow=st.selectbox('Цепочка',list(FLOWS),index=list(FLOWS).index(flow) if flow in FLOWS else 0,format_func=FLOWS.get)
 st.info('Данные рассылок ещё не подключены. Ниже структура будущего отчёта.')
 st.caption('Контекст: GEO '+st.query_params.get('geo','all')+' · месяц '+st.query_params.get('month','all'))
 c=st.columns(4)
 for col,label in zip(c,['Отправлено','Доставлено','Open Rate','Целевая конверсия']):col.metric(label,'—')
 st.dataframe(pd.DataFrame(columns=['Письмо / campaign_id','GEO','Отправлено','Доставлено','Открыто','Клики','Целевое действие','Конверсия','Контрольная группа','NGR']),use_container_width=True)
 st.markdown('Будут добавлены: список писем цепочки, доставляемость, открытия и клики, переход в следующий депозит, сравнение с контролем и NGR. Welcome — отдельный обзор всей цепочки.')
 st.caption('Статусы коммуникаций — из CRM; депозиты, активность и экономика — из DWH. Open Rate: уникальные открытые сообщения / уникальные доставленные сообщения, при согласованной гранулярности message_id. Правило целевой конверсии и окно атрибуции задаются перед подключением.')
 st.markdown(link('Вернуться к депозитной воронке','retention',tab=2,geo=st.query_params.get('geo','all'),month=st.query_params.get('month','all'))+' · '+link('Ретеншен','retention',tab=0),unsafe_allow_html=True)
elif page=='projects':
 st.title('Задачи команды')
 plan_table([p for p in plans if p['section']=='projects'])
 st.caption('Фактический прогресс заполняется в data/manual_facts.csv. Завершение задач не проставляется автоматически.')
elif page=='reactivation':
 st.title('Реактивация');st.info('Ожидает выгрузку. Здесь будут возврат неактивных игроков, депозиты, активность и NGR по кампаниям и контрольным группам.')
 related('late_ftd')
