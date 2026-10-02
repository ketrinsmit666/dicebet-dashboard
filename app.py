"""Streamlit entrypoint. All files can be uploaded to repository root."""
from pathlib import Path
import json,re,csv
from urllib.parse import urlencode
import streamlit as st
import streamlit.components.v1 as components
ROOT=Path(__file__).resolve().parent
st.set_page_config(page_title='Отчёты отдела',layout='wide')
PAGES={'index':'Главная · план–факт','late_ftd':'Долёты','retention':'Ретеншен и воронка','pulsation':'Пульсация','reactivation':'Чарн и реактивация','crm':'CRM · макет','crm_controls':'CRM · контрольные группы','crm_experiment':'CRM · эксперимент','projects':'Задачи команды'}
page=st.query_params.get('page','index')
if page=='home':page='index'
if page not in PAGES:page='index'
with st.sidebar:
 st.title('Отчёты отдела')
 for key,label in PAGES.items():
  if st.button(label,key=key,use_container_width=True,type='primary' if page==key else 'secondary'):
   st.query_params.clear();st.query_params['page']=key;st.rerun()
 st.caption('TR · AR · CO · IN — основные GEO')
 st.caption('Факт по 30.09.2026. CRM пока без данных.')
path=ROOT/(page+'.html')
if not path.exists():st.error('Файл раздела отсутствует: '+path.name);st.stop()
html=path.read_text()
# CSV plans are authoritative even when an older standalone HTML remains in Git.
for filename,key in [('targets.csv','plans'),('manual_facts.csv','manual')]:
 plan_path=ROOT/filename
 if plan_path.exists():
  with plan_path.open(encoding='utf-8-sig') as f: rows=list(csv.DictReader(f))
  payload=json.dumps(rows,ensure_ascii=False).replace('</','<\\/')
  marker='</script><script>'
  html=html.replace(marker,'</script><script>DATA.'+key+'='+payload+';</script><script>',1)

# Inline local CRM assets for components.html, which has no relative file access.
html=html.replace('<link rel="stylesheet" href="crm.css">','<style>'+(ROOT/'crm.css').read_text()+'</style>')
html=html.replace('<script src="crm.js"></script>','<script>'+(ROOT/'crm.js').read_text()+'</script>')
query='?'+urlencode({k:v for k,v in st.query_params.items() if k!='page'})
html=html.replace('new URLSearchParams(location.search)','new URLSearchParams('+json.dumps(query)+')')
# Covers static and dynamically rendered navigation inside iframe; keeps all filter parameters.
bridge="""<script>document.addEventListener('click',function(e){const a=e.target.closest('a');if(!a)return;const raw=a.getAttribute('href')||'';const m=raw.match(/^([a-z_]+)\\.html(?:\\?(.*))?$/);if(!m)return;e.preventDefault();const q=new URLSearchParams(m[2]||'');q.set('page',m[1]);const dest=document.createElement('a');dest.href='?'+q.toString();dest.target='_top';document.body.appendChild(dest);dest.click();dest.remove();});</script>"""
html=html.replace('</body>',bridge+'</body>')
components.html(html,height=1450,scrolling=True)
