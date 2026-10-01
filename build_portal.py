"""Build a static departmental reporting portal from independent CSV exports."""
import argparse,csv,json,re,subprocess,sys,tempfile
from pathlib import Path
from datetime import datetime
from zoneinfo import ZoneInfo
from html import escape
ROOT=Path(__file__).resolve().parent
parser=argparse.ArgumentParser()
parser.add_argument('--as-of',default=None)
parser.add_argument('--input-dir',type=Path,default=ROOT/'inputs')
parser.add_argument('--output',type=Path,default=ROOT/'site')
a=parser.parse_args();a.output.mkdir(parents=True,exist_ok=True)
def read(path):
    if not path.exists():return []
    with path.open(encoding='utf-8-sig',newline='') as f:return list(csv.DictReader(f))
def page(title,body,back=True):
    return '''<!doctype html><html lang="ru"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>'''+escape(title)+'''</title><style>body{font:15px Segoe UI,Arial,sans-serif;background:#f3f6fb;color:#18243a;margin:0}.wrap{max-width:1300px;margin:auto;padding:28px}header{background:#192d50;color:white;border-radius:18px;padding:26px}h1{margin:0 0 10px}.muted{color:#667893;line-height:1.6}.panel,.card{background:white;border:1px solid #e0e7f1;border-radius:14px;padding:20px;margin-top:18px}.cards{display:grid;grid-template-columns:repeat(auto-fit,minmax(220px,1fr));gap:15px}a{color:#425bd0}a.card{display:block;text-decoration:none;color:#18243a}.card:hover{border-color:#4d65d5}table{border-collapse:collapse;width:100%;white-space:nowrap;font-size:14px}td,th{padding:12px;text-align:right;border-bottom:1px solid #e5eaf2}td:first-child,th:first-child{text-align:left}select{padding:9px;border:1px solid #ccd7e5;border-radius:8px}.scroll{overflow:auto}.pill{display:inline-block;border-radius:20px;background:#edf2fa;padding:4px 8px;font-size:12px}</style><div class="wrap">'''+('<a href="index.html">← Главная</a><br><br>' if back else '')+'<header><h1>'+escape(title)+'</h1></header>'+body+'</div></html>'
sections={'late_ftd':'Долёты','retention':'Retention','reactivation':'Реактивация','crm':'CRM','pulsation':'Операционная пульсация'}
actuals={};status={};today=a.as_of or datetime.now(ZoneInfo('Europe/Moscow')).date().isoformat()
def add(section,month,geo,metric,label,value,unit,as_of):
    key=(section,month,geo,metric)
    if key in actuals:raise ValueError('Duplicate monthly metric: '+str(key))
    actuals[key]={'section':section,'month':month,'geo':geo,'metric':metric,'label':label,'actual':value,'unit':unit,'as_of':as_of}
for section in ['late_ftd','pulsation']:
    src=a.input_dir/(section+'.csv')
    if not src.exists():status[section]='Ожидает выгрузку';continue
    rows=read(src)
    if not rows:raise ValueError(f'Empty export: {src}')
    dst=a.output/(section+'.html')
    command=[sys.executable,str(ROOT/'builders'/section/'build_report.py'),'--input',str(src),'--output',str(dst)]
    with tempfile.TemporaryDirectory() as temporary:
        if section=='late_ftd':
            targets=Path(temporary)/'targets.csv'
            with targets.open('w',newline='') as f:
                writer=csv.writer(f);writer.writerow(['month','geo','target','previous_month_sheet'])
                for target in read(a.input_dir/'targets.csv'):
                    if target['section']=='late_ftd' and target['metric']=='late_ftd_count' and target['target']:
                        writer.writerow([target['month'],target['geo'],target['target'],''])
            command.extend(['--targets',str(targets),'--as-of',today])
        subprocess.run(command,check=True)
    html=dst.read_text();html=re.sub('DiceBet[ ·]*','',html,flags=re.I)
    if 'href="index.html"' not in html:html=html.replace('<body>','<body><div style="padding:15px 28px"><a href="index.html">← Главная страница отчётов</a></div>')
    dst.write_text(html)
    field='ftd_date' if section=='late_ftd' else 'dt'
    status[section]='Данные по '+max(r[field][:10] for r in rows)
    if section=='late_ftd':
        valid=[r for r in rows if r['ftd_date']<today]
        for month in sorted({r['ftd_month'][:7] for r in valid}):
            for geo in sorted({r['geo_short'] for r in valid if r['ftd_month'].startswith(month)}):
                group=[r for r in valid if r['ftd_month'].startswith(month) and r['geo_short']==geo]
                as_of=max(r['ftd_date'] for r in valid if r['ftd_month'].startswith(month))
                add(section,month,geo,'late_ftd_count','Поздние FTD',len(group),'players',as_of)
                add(section,month,geo,'ngr','NGR месяца FTD',sum(float(r['ngr_ftd_month_usd']) for r in group),'USD',as_of)
# Player-level retention is aggregated before rendering or publishing.
retention_source=a.input_dir/'user_lifecycle.csv'
retention_cube=a.input_dir/'retention_cube.json'
retention_connected=retention_source.exists() or retention_cube.exists()
if retention_connected:
    import importlib.util
    spec=importlib.util.spec_from_file_location('retention_builder',ROOT/'builders'/'retention'/'build_report.py')
    module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
    if retention_source.exists():
        cube=module.aggregate(retention_source,today)
    else:
        cube=json.loads(retention_cube.read_text())
    module.write_report(cube,a.output/'retention.html')
    status['retention']='Выгрузка '+cube['meta']['snapshot_date']
    grouped={}
    for row in cube['rows']:
        if not row['ftd_month']:continue
        key=(row['ftd_month'],row['geo'])
        value=grouped.setdefault(key,[0,0]);value[0]+=row['v']['r3'];value[1]+=row['v']['m3']
    for (month,geo),(num,den) in grouped.items():
        add('retention',month,geo,'retention_d3_plus','D3+ Retention (месяц FTD)',100*num/den if den else None,'percent',cube['meta']['snapshot_date'])
        actuals[('retention',month,geo,'retention_d3_plus')]['numerator']=num
        actuals[('retention',month,geo,'retention_d3_plus')]['denominator']=den

for section in ['retention','reactivation','crm']:
    if section=='retention' and retention_connected:continue
    rows=read(a.input_dir/(section+'.csv'));status[section]='Ожидает выгрузку' if not rows else 'Данные по '+max(r['as_of'] for r in rows)
    table=''
    if rows:
        for r in rows:add(section,r['month'],r['geo'],r['metric'],r['label'],float(r['actual']),r['unit'],r['as_of'])
        table='<div class="scroll"><table><tr><th>Месяц</th><th>GEO</th><th>Метрика</th><th>Факт</th><th>Дата среза</th></tr>'+''.join('<tr>'+''.join('<td>'+escape(str(r[k]))+'</td>' for k in ['month','geo','label','actual','as_of'])+'</tr>' for r in rows)+'</table></div>'
    else:table='<p>Выгрузка для этого раздела ещё не подключена.</p><p class="muted">После добавления данных здесь появятся показатели, а на главной — их план–факт. Детальную структуру отчёта можно расширить под нужные разрезы.</p>'
    (a.output/(section+'.html')).write_text(page(sections[section],'<div class="panel">'+table+'</div>'))
plans={}
for r in read(a.input_dir/'targets.csv'):
    key=(r['section'],r['month'],r['geo'],r['metric'])
    if key in plans:raise ValueError('Duplicate target: '+str(key))
    plans[key]=r
for key,row in actuals.items():
    p=plans.get(key);row['target']=float(p['target']) if p and p['target'] else None
for key,p in plans.items():
    if key not in actuals:actuals[key]={'section':key[0],'month':key[1],'geo':key[2],'metric':key[3],'label':p['label'],'actual':None,'target':float(p['target']) if p['target'] else None,'unit':p['unit'],'as_of':'—'}
home_curve=''
if retention_connected:
    def curve_chart(geo_list):
        colors=['#2563eb','#ef8c25','#8b5cf6','#16a89a','#69849f']
        svg='<svg viewBox="0 0 1050 360" role="img" aria-label="Rolling retention от FTD" style="width:100%;min-width:650px">'
        for percent in range(0,101,25):
            y=290-2.5*percent
            svg+=f'<line x1="55" y1="{y}" x2="1015" y2="{y}" stroke="#dae3ef"/><text x="8" y="{y+5}" fill="#60728a">{percent}%</text>'
        for day in range(0,31,3):svg+=f'<text x="{55+32*day}" y="318" text-anchor="middle" fill="#60728a">D{day}</text>'
        legends=[]
        for i,geo in enumerate(geo_list):
            group=[r['v'] for r in cube['rows'] if r['geo']==geo]
            den=sum(r.get('curve90_den',0) for r in group)
            if not den:continue
            color=colors[i%len(colors)];values=[sum(r.get(f'curve90_{d}',0) for r in group) for d in range(31)]
            points=' '.join(f'{55+32*d},{290-250*n/den}' for d,n in enumerate(values))
            svg+=f'<polyline fill="none" stroke="{color}" stroke-width="3" points="{points}"/>'
            for d,n in enumerate(values):svg+=f'<circle cx="{55+32*d}" cy="{290-250*n/den}" r="3" fill="{color}"><title>{escape(geo)} · D{d}+: {100*n/den:.2f}% · {int(n)} / {int(den)}</title></circle>'
            legends.append(f'<span style="color:{color};margin-right:20px">● {escape(geo)} · {int(den):,} зрелых FTD</span>')
        return '<div class="scroll">'+svg+'</svg></div><p>'+' '.join(legends)+'</p>'
    primary=['TR','AR','CO','IN'];secondary=sorted({r['geo'] for r in cube['rows']}-set(primary))
    home_curve='<section class="panel"><h2>Rolling retention D0–D30 · FTD за последние 90 дней</h2>'+curve_chart(primary)+'<p class="muted">Отдельный обзор последних 90 дней до '+cube['meta']['snapshot_date']+'; фильтр месяца план–факта к нему не применяется. Единая база: только зрелые D30 FTD. Dn+ — активность на день n или позднее, включая дни после D30. D0 = 100%. Наведите на точку для числа игроков и процента. Отсчёт от первого депозита.</p><details><summary>Другие GEO — показать отдельно</summary>'+curve_chart(secondary)+'</details></section>'
cards=''.join(f'<a class="card" href="{k}.html"><h2>{v}</h2><span class="pill">{escape(status.get(k,"Ожидает выгрузку"))}</span><p>Открыть раздел →</p></a>' for k,v in sections.items())
payload=json.dumps(list(actuals.values()),ensure_ascii=False).replace('</','<\\/')
script='''<script>const rows=__ROWS__,names=__NAMES__,m=document.getElementById('month');const months=[...new Set(rows.map(r=>r.month))].sort();m.innerHTML=months.map(x=>`<option>${x}</option>`).join('');m.value=months.at(-1)||'';const esc=x=>String(x).replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));const fmt=x=>x===null?'—':Number(x).toLocaleString('ru-RU',{maximumFractionDigits:2});const primary=['TR','AR','CO','IN'];const order=(a,b)=>(primary.includes(a.geo)?primary.indexOf(a.geo):99)-(primary.includes(b.geo)?primary.indexOf(b.geo):99)||a.geo.localeCompare(b.geo);function attainment(r){if(r.actual===null||!r.target)return '—';const value=100*r.actual/r.target,hue=Math.max(0,Math.min(120,value*1.2));return `<span style="display:inline-block;padding:7px 12px;border-radius:8px;font-weight:700;background:hsl(${hue},75%,85%);color:hsl(${hue},75%,22%)">${fmt(value)}%</span>`}function rowHTML(r){const link=r.section==='retention'?`retention.html?ftd_month=${encodeURIComponent(r.month)}&geo=${encodeURIComponent(r.geo)}`:`${esc(r.section)}.html`;return `<tr><td><a href="${link}">${esc(names[r.section]||r.section)} · ${esc(r.label)}</a></td><td>${esc(r.geo)}</td><td>${fmt(r.target)}${r.unit==='percent'&&r.target!==null?'%':''}</td><td>${fmt(r.actual)}${r.unit==='percent'&&r.actual!==null?'%':''}</td><td>${attainment(r)}</td><td>${r.denominator!==undefined?fmt(r.numerator)+' / '+fmt(r.denominator):'—'}</td><td>${r.unit==='percent'?'%':r.unit==='players'?'игроки':esc(r.unit)}</td><td>${esc(r.as_of)}</td></tr>`}function render(){const filtered=rows.filter(r=>r.month===m.value).sort(order);document.getElementById('facts').innerHTML=filtered.filter(r=>r.target!==null&&primary.includes(r.geo)).map(rowHTML).join('');document.getElementById('otherPlans').innerHTML=filtered.filter(r=>r.target!==null&&!primary.includes(r.geo)).map(rowHTML).join('');document.getElementById('otherFacts').innerHTML=filtered.filter(r=>r.target===null).map(rowHTML).join('')}m.onchange=render;render();</script>'''.replace('__ROWS__',payload).replace('__NAMES__',json.dumps(sections,ensure_ascii=False))
body='<p class="muted">Отчёты отдела · последняя сборка '+datetime.now(ZoneInfo('Europe/Moscow')).strftime('%d.%m.%Y %H:%M МСК')+'</p><section class="panel"><h2>План–факт отдела</h2><label>Месяц <select id="month"></select></label><p class="muted">Подключённые планы и факты. Шкала выполнения: 0% — красный, 50% — жёлтый, 100% и выше — зелёный. «—» означает, что значение не предоставлено. Процент показывает отношение факта к плану; для метрик, которые нужно снижать, оценивайте направление отдельно. У каждого раздела своя дата среза.</p><div class="scroll"><table><thead><tr><th>Раздел · метрика</th><th>GEO</th><th>План</th><th>Факт</th><th>Выполнение</th><th>Возвраты / зрелые FTD</th><th>Ед.</th><th>Дата среза</th></tr></thead><tbody id="facts"></tbody></table></div><p class="muted">D3+ — активность на третий день после FTD или позднее. План относится к когорте FTD выбранного месяца; знаменатель — только matured_d3 = 1. Это rolling retention, а не возврат строго на D3. Данные ограничены регистрациями за период выгрузки.</p></section><details class="panel"><summary>Другие GEO · план–факт</summary><div class="scroll"><table><tbody id="otherPlans"></tbody></table></div></details><details class="panel"><summary>Факты без заданного плана</summary><div class="scroll"><table><tbody id="otherFacts"></tbody></table></div></details><div class="cards">'+cards+'</div>'+script
body=body.replace('</section><details class="panel">','</section>'+home_curve+'<details class="panel">',1)
(a.output/'index.html').write_text(page('Отчёты отдела',body,False))
print('Portal ready:',a.output)
