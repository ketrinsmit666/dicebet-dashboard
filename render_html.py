"""Render standalone HTML reports from aggregates. No CDN or web server needed."""
from pathlib import Path
import json,csv
ROOT=Path(__file__).resolve().parent
SETS={'index':['late','funnel','alerts','daily'],'pulsation':['daily','monthly','bonuses'],'retention':['cohorts','curves','funnel'],'late_ftd':['late'],'reactivation':['reactivation']}
def render(root=ROOT):
 root=Path(root);data=json.loads((root/'dashboard_data.json').read_text())
 for f,key in [('targets.csv','plans'),('manual_facts.csv','manual')]:
  with (root/f).open(encoding='utf-8-sig') as h:data[key]=list(csv.DictReader(h))
 css=(root/'dashboard.css').read_text();js=(root/'dashboard.js').read_text()
 for page,keys in SETS.items():
  obj={k:data[k] for k in ['meta','plans','manual']+keys};raw=json.dumps(obj,ensure_ascii=False,separators=(',',':')).replace('</','<\\/')
  html='<!doctype html><html lang="ru"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>Отчёты отдела</title><style>'+css+'</style></head><body data-page="'+page+'"><div class="wrap"><header><a href="index.html">← Главная страница</a><h1 id="title"></h1><div id="stamp"></div></header><nav id="nav"></nav><div class="filters"><label>Месяц<select id="month"></select></label><label>GEO<select id="geo"></select></label><button id="download">Скачать таблицы CSV</button></div><div id="tabs" class="tabs"></div><main id="content"></main><footer>Источник: DWH · показатели агрегированы, персональные идентификаторы в HTML не передаются. Наведите курсор на точку графика для значения.</footer></div><script>const DATA='+raw+';</script><script>'+js+'</script></body></html>'
  (root/(page+'.html')).write_text(html)
 print('Rendered',', '.join(SETS))
if __name__=='__main__':render()
