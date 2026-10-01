import streamlit as st
import pandas as pd
import plotly.express as px
from pathlib import Path

st.set_page_config(page_title='Analytics Portal', layout='wide')
BASE=Path(__file__).parent/'data'

@st.cache_data
def load_users(): return pd.read_csv(BASE/'users.csv', parse_dates=['registration_date','ftd_date','last_activity_date'])
@st.cache_data
def load_metrics(): return pd.read_csv(BASE/'metrics.csv', parse_dates=['activity_date','previous_active_date'])

users=load_users()
metrics=load_metrics()

main_geo=['TR','AR','CO','IN']

page=st.sidebar.radio('Раздел',['Главная','Долеты','Retention','Reactivation','CRM (mockup)'])

if page=='Главная':
    st.title('Analytics Portal')
    st.subheader('План-факт и алерты')
    st.info('Макет: подключение планов и автоматических алертов')
    st.metric('Сильные изменения','—')
    st.write('Алерты будут вести на проблемные разделы: депозитная воронка, retention, CRM.')

elif page=='Долеты':
    st.title('FTD Upsale / Долеты')
    df=users.dropna(subset=['ftd_date']).copy()
    geo=st.multiselect('GEO',sorted(df.geo.unique()),default=[x for x in main_geo if x in df.geo.unique()])
    if geo: df=df[df.geo.isin(geo)]
    st.metric('FTD игроков',len(df))
    st.dataframe(df.groupby('geo').size().reset_index(name='FTD'))

elif page=='Retention':
    st.title('Retention')
    df=users.dropna(subset=['ftd_date']).copy()
    geo=st.multiselect('GEO',sorted(df.geo.unique()),default=[x for x in main_geo if x in df.geo.unique()])
    if geo: df=df[df.geo.isin(geo)]
    ret=df.groupby('geo')[['active_d1_3_flag','active_d4_7_flag','active_d8_14_flag','active_d15_30_flag']].mean()*100
    st.dataframe(ret)
    long=ret.reset_index().melt('geo')
    st.plotly_chart(px.line(long,x='variable',y='value',color='geo',markers=True),use_container_width=True)
    st.caption('Добавление Amplitude-style D0-D30 возможно через metrics activity_date')

elif page=='Reactivation':
    st.title('Reactivation / Churn')
    df=metrics.copy()
    df['churn_category']=pd.cut(df['days_since_previous_active_day'],[-1,7,14,30,60,90,180,99999],labels=['1-7','8-14','15-30','31-60','61-90','91-180','181+'])
    st.dataframe(df.groupby('churn_category').size().reset_index(name='events'))
    st.caption('Доля реактивации будет рассчитана после агрегации player-day')

else:
    st.title('CRM dashboard (mockup)')
    st.write('Welcome, 1→2 deposit, 2→3 deposit, retention CRM journeys — data pending')
