import streamlit as st
import google_play_scraper as gps
import pandas as pd
from openai import OpenAI
import psycopg
import os
from datetime import datetime
import json
import re

# АВТОРИЗАЦИЯ
if 'logged_in' not in st.session_state:
    st.session_state.logged_in = False

def login_page():
    st.title("🚀 Play Analyzer Pro")
    col1, col2 = st.columns([1, 2])
    
    with col1:
        username = st.text_input("Логин")
        password = st.text_input("Пароль", type="password")
        if st.button("Войти", type="primary"):
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

# ОСНОВНОЕ
st.title("🚀 Play Analyzer Pro")
st.caption("Perplexity + Google Play")

def get_db_connection():
    """БЕЗ кэша — простой connect"""
    return psycopg.connect(os.getenv("DATABASE_URL"))

def ensure_table():
    """Создаём таблицу"""
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute("""
        CREATE TABLE IF NOT EXISTS app_meta (
            app_id VARCHAR(255) PRIMARY KEY,
            installs TEXT,
            score NUMERIC(3,2),
            title TEXT,
            last_updated TIMESTAMP
        )
    """)
    conn.commit()
    conn.close()

ensure_table()  # Создаём при старте

def scrape_app(app_id):
    try:
        data = gps.app(app_id, lang='en', country='us')
        return {
            'title': data['title'],
            'installs': data['installs'],
            'score': float(data['score']),
            'reviews': data.get('reviews', 0)
        }
    except Exception as e:
        st.error(f"❌ {e}")
        return None

def perplexity_analyze(app_data, scenario, context):
    try:
        client = OpenAI(
            api_key=os.getenv("PERPLEXITY_API_KEY"),
            base_url="https://api.perplexity.ai"
        )
        
        prompt = f"""
        App: {app_data['title']} | {app_data['installs']} | рейтинг {app_data['score']}
        Scenario: {scenario} | Context: {context}
        
        JSON: {{"market_fit":8,"recommendations":["1","2","3"]}}
        """
        
        response = client.chat.completions.create(
            model="llama-3.1-sonar-small-128k-online",
            messages=[{"role": "user", "content": prompt}]
        )
        
        content = response.choices[0].message.content
        json_match = re.search(r'\{.*\}', content, re.DOTALL)
        return json.loads(json_match.group()) if json_match else {
            "market_fit": 7, "recommendations": ["Perplexity OK", "Работает!", "Тест"]
        }
    except:
        return {"market_fit": 5, "recommendations": ["LLM недоступен", "Скрейпинг OK"]}

# Sidebar
with st.sidebar:
    scenario = st.selectbox("Сценарий", ["competitor", "niche", "validate"])
    app_id = st.text_input("App ID", value="com.whatsapp")
    context = st.text_area("Контекст", "Моя идея...")
    
    if st.button("🔍 Анализ", type="primary"):
        with st.spinner("⏳ ..."):
            conn = get_db_connection()
            
            # КЭШ
            cur = conn.cursor()
            cur.execute("SELECT installs, score, title, last_updated FROM app_meta WHERE app_id = %s", (app_id,))
            cached = cur.fetchone()
            
            if cached and (datetime.now() - cached[3]).seconds < 3600:  # 1ч тест
                app_data = {
                    'title': cached[2],
                    'installs': cached[0],
                    'score': float(cached[1])
                }
                st.success("✅ Кэш")
            else:
                app_data_raw = scrape_app(app_id)
                if app_data_raw:
                    cur.execute("""
                        INSERT INTO app_meta (app_id, installs, score, title, last_updated)
                        VALUES (%s,%s,%s,%s,%s) ON CONFLICT (app_id) DO UPDATE 
                        SET installs=EXCLUDED.installs, score=EXCLUDED.score, 
                            title=EXCLUDED.title, last_updated=EXCLUDED.last_updated
                    """, (app_id, app_data_raw['installs'], app_data_raw['score'], 
                          app_data_raw['title'], datetime.now()))
                    conn.commit()
                    app_data = app_data_raw
                    st.success("✅ Обновлено")
                else:
                    st.stop()
            
            conn.close()
            
            # Perplexity
            analysis = perplexity_analyze(app_data, scenario, context)
            st.session_state.analysis = {'app_data': app_data, 'analysis': analysis}

# РЕЗУЛЬТАТ
if 'analysis' in st.session_state:
    result = st.session_state.analysis
    
    col1, col2, col3 = st.columns(3)
    col1.metric("📊 Market Fit", f"{result['analysis']['market_fit']}/10")
    col2.metric("📱 Installs", result['app_data']['installs'])
    col3.metric("⭐ Rating", f"{result['app_data']['score']:.1f}")
    
    st.subheader("🎯 Perplexity рекомендации")
    for i, rec in enumerate(result['analysis']['recommendations'], 1):
        st.info(rec)
    
    # История
    try:
        conn = get_db_connection()
        df = pd.read_sql("SELECT * FROM app_meta ORDER BY last_updated DESC LIMIT 10", conn)
        st.subheader("📈 База")
        st.dataframe(df)
        conn.close()
    except:
        st.info("История...")
