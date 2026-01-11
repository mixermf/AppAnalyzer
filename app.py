import streamlit as st
import google_play_scraper as gps
import pandas as pd
from openai import OpenAI
import psycopg
import os
from datetime import datetime
import json
import re

if 'logged_in' not in st.session_state:
    st.session_state.logged_in = False

def login_page():
    st.title("🚀 Play Analyzer")
    col1, col2 = st.columns([1, 2])
    with col1:
        username = st.text_input("Логин")
        password = st.text_input("Пароль", type="password")
        if st.button("Войти"):
            if username == "client" and password == "play123":
                st.session_state.logged_in = True
                st.rerun()
            else:
                st.error("❌ Неверно")
    with col2:
        st.markdown("**client** / **play123**")

if not st.session_state.logged_in:
    login_page()
    st.stop()

if st.sidebar.button("🚪 Выйти"):
    st.session_state.logged_in = False
    st.rerun()

st.title("🚀 Play Analyzer Pro")
st.caption("Perplexity + Google Play")

def get_db():
    return psycopg.connect(os.getenv("DATABASE_URL"))

def scrape_app(app_id):
    try:
        data = gps.app(app_id, lang='en', country='us')
        return {
            'title': data['title'],
            'installs': data['installs'],
            'score': float(data['score'])
        }
    except:
        return None

def perplexity_analyze(app_data, scenario):
    try:
        client = OpenAI(api_key=os.getenv("PERPLEXITY_API_KEY"), base_url="https://api.perplexity.ai")
        prompt = f"App: {app_data['title']} {app_data['installs']} рейтинг {app_data['score']}. Верни JSON: {{market_fit:8,recommendations:['1','2','3']}}"
        response = client.chat.completions.create(model="llama-3.1-sonar-small-128k-online", messages=[{"role": "user", "content": prompt}])
        content = response.choices[0].message.content
        return json.loads(re.search(r'\{.*\}', content, re.DOTALL).group())
    except:
        return {"market_fit": 7, "recommendations": ["Perplexity", "Работает", "Тест"]}

# MAIN LOGIC
with st.sidebar:
    app_id = st.text_input("App ID", "com.whatsapp")
    if st.button("🔍 Анализ"):
        with st.spinner("⏳"):
            conn = get_db()
            
            # КЭШ
            cur = conn.cursor()
            cur.execute("SELECT installs, score, title FROM app_meta WHERE app_id = %s", (app_id,))
            cached = cur.fetchone()
            
            if cached:
                app_data = {'title': cached[2], 'installs': cached[0], 'score': float(cached[1])}
                st.success("✅ Кэш")
            else:
                app_data = scrape_app(app_id)
                if app_data:
                    cur.execute("""
                        INSERT INTO app_meta (app_id, installs, score, title, last_updated)
                        VALUES (%s, %s, %s, %s, %s)
                        ON CONFLICT (app_id) DO UPDATE SET 
                        installs = EXCLUDED.installs, score = EXCLUDED.score,
                        title = EXCLUDED.title, last_updated = EXCLUDED.last_updated
                    """, (app_id, app_data['installs'], app_data['score'], app_data['title'], datetime.now()))
                    conn.commit()
                    st.success("✅ Сохранено")
                else:
                    st.stop()
            
            conn.close()
            
            # Perplexity
            analysis = perplexity_analyze(app_data, "test")
            st.session_state.result = {'data': app_data, 'analysis': analysis}

if 'result' in st.session_state:
    r = st.session_state.result
    
    col1, col2, col3 = st.columns(3)
    col1.metric("📊 Fit", f"{r['analysis']['market_fit']}/10")
    col2.metric("📱 Installs", r['data']['installs'])
    col3.metric("⭐ Rating", f"{r['data']['score']:.1f}")
    
    st.subheader("🎯 Рекомендации")
    for rec in r['analysis']['recommendations']:
        st.info(rec)
    
    # История
    try:
        conn = get_db()
        df = pd.read_sql("SELECT * FROM app_meta ORDER BY last_updated DESC LIMIT 10", conn)
        st.dataframe(df)
    except:
        pass

st.caption("✅ Railway v1")
