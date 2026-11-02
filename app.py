"""Streamlit entrypoint. All files can be uploaded to repository root."""
from pathlib import Path
import json,re,csv,tempfile
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
   st.query_params['page']=key;st.query_params.pop('tab',None);st.rerun()
 st.caption('TR · AR · CO · IN — основные GEO')
 st.caption('Дата актуальности указана в шапке каждого отчёта. CRM пока без данных.')
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
# A bidirectional component relays navigation to Python, avoiding iframe top navigation.
bridge="""<script>document.addEventListener('click',function(e){const a=e.target.closest('a');if(!a)return;const raw=a.getAttribute('href')||'';const m=raw.match(/^([a-z_]+)\\.html(?:\\?(.*))?$/);if(!m)return;e.preventDefault();const q=new URLSearchParams(m[2]||'');q.set('page',m[1]);for(const k of ['month','geo']){const el=document.getElementById(k);if(el&&!q.has(k))q.set(k,el.value);}parent.postMessage({dashboardNavigation:Object.fromEntries(q)},'*');},true);</script>"""
html=html.replace('</body>',bridge+'</body>')
if '</body>' not in html:html+=bridge
COMPONENT_HTML="""<!doctype html><html><body style="margin:0"><iframe id="report" style="border:0;width:100%;height:1450px" title="Отчёт"></iframe><script>
const send=(type,extra={})=>parent.postMessage({isStreamlitMessage:true,type,...extra},'*');
window.addEventListener('message',e=>{
 if(e.source===parent&&e.data&&e.data.type==='streamlit:render'){document.getElementById('report').srcdoc=e.data.args.html;send('streamlit:setFrameHeight',{height:1450});}
 if(e.source===document.getElementById('report').contentWindow&&e.data.dashboardNavigation)send('streamlit:setComponentValue',{value:{params:e.data.dashboardNavigation,nonce:Date.now()},dataType:'json'});
});send('streamlit:componentReady',{apiVersion:1});
</script></body></html>"""
@st.cache_resource
def navigation_component():
 folder=Path(tempfile.mkdtemp(prefix='reports_component_'))
 (folder/'index.html').write_text(COMPONENT_HTML,encoding='utf-8')
 return components.declare_component('department_reports',path=str(folder))
event=navigation_component()(html=html,key='report_navigation',default=None)
if event and event.get('nonce')!=st.session_state.get('navigation_nonce'):
 st.session_state['navigation_nonce']=event.get('nonce')
 params=event.get('params',{})
 if params.get('page') in PAGES:
  for k in ['page','month','geo','tab','flow','window','metric','anchor','kind']:
   if k in params:st.query_params[k]=str(params[k])
   elif k not in ['month','geo']:st.query_params.pop(k,None)
  st.rerun()
