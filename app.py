import streamlit as st
import google_play_scraper as gps
import pandas as pd
from openai import OpenAI
import psycopg
import os
from datetime import datetime
import json

# УПРОЩЁННАЯ АВТОРИЗАЦИЯ (работает всегда)
if 'logged_in' not in st.session_state:
    st.session_state.logged_in = False

def login_page():
    st.title("🚀 Play Analyzer Pro")
    col1, col2 = st.columns([1, 2])
    
    with col1:
        st.markdown("## 🔐 Вход")
        username = st.text_input("Логин")
        password = st.text_input("Пароль", type="password")
        if st.button("Войти", type="primary"):
            if username == "client" and password == "play123":
                st.session_state.logged_in = True
                st.rerun()
            else:
                st.error("❌ Неверный логин/пароль")
    
    with col2:
        st.markdown("""
        ### 👋 Добро пожаловать!
        - Логин: **client**
        - Пароль: **play123**
        """)

if not st.session_state.logged_in:
    login_page()
    st.stop()

# Logout
if st.sidebar.button("🚪 Выйти"):
    st.session_state.logged_in = False
    st.rerun()

st.sidebar.success("✅ Авторизован")

# ГЛАВНОЕ ПРИЛОЖЕНИЕ
st.title("🚀 Play Analyzer Pro")
st.caption("AI‑анализ конкурентов Google Play")

@st.cache_resource
def init_db():
    conn = psycopg.connect(os.getenv("DATABASE_URL"))
    cur = conn.cursor()
    cur.execute("""
        CREATE TABLE IF NOT EXISTS app_meta (
            app_id VARCHAR(255) PRIMARY KEY,
            installs TEXT,
            score NUMERIC(3,2),
            last_updated TIMESTAMP
        )
    """)
    conn.commit()
    return conn

def scrape_app(app_id):
    try:
        data = gps.app(app_id, lang='en', country='us')
        return {
            'title': data['title'],
            'installs': data['installs'],
            'score': float(data['score']),
            'reviews': data['reviews']
        }
    except Exception as e:
        st.error(f"❌ Скрейпинг: {e}")
        return None

def llm_analyze(app_data, scenario, context):
    try:
        client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))
        prompt = f"""
        App: {app_data['title']} ({app_data['installs']}, {app_data['score']}*)
        Scenario: {scenario}
        Context: {context}
        JSON: {{"market_fit":8,"recommendations":["1","2","3"]}}
        """
        response = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[{"role": "user", "content": prompt}]
        )
        return json.loads(response.choices[0].message.content)
    except Exception as e:
        return {"market_fit": 5, "recommendations": ["Тест OK", "LLM недоступен", "Данные собраны"]}

# Sidebar
with st.sidebar:
    st.header("⚙️ Настройки")
    scenario = st.selectbox("Сценарий", ["competitor", "niche", "validate"])
    app_id = st.text_input("App ID", value="com.whatsapp")
    context = st.text_area("Идея/контекст", "Моя идея...")
    
    if st.button("🔍 Анализировать", type="primary"):
        with st.spinner("⏳ Работаем..."):
            conn = init_db()
            
            # КЭШ (24ч)
            with conn.cursor() as cur:
                cur.execute("SELECT * FROM app_meta WHERE app_id = %s", (app_id,))
                cached = cur.fetchone()
                
                if cached and (datetime.now() - cached[3]).seconds < 86400:
                    app_data = {
                        'title': f"Cached: {app_id}",
                        'installs': cached[1],
                        'score': float(cached[2])
                    }
                    st.sidebar.success("✅ Кэш свежий")
                else:
                    app_data_raw = scrape_app(app_id)
                    if app_data_raw:
                        cur.execute("""
                            INSERT INTO app_meta (app_id, installs, score, last_updated)
                            VALUES (%s, %s, %s, %s) ON CONFLICT (app_id) 
                            DO UPDATE SET installs=%s, score=%s, last_updated=%s
                        """, (app_id, app_data_raw['installs'], app_data_raw['score'], 
                              datetime.now(), app_data_raw['installs'], app_data_raw['score'], datetime.now()))
                        conn.commit()
                        app_data = app_data_raw
                        st.sidebar.success("✅ Данные обновлены")
                    else:
                        st.error("Не удалось собрать данные")
                        st.stop()
            
            # LLM
            analysis = llm_analyze(app_data, scenario, context)
            st.session_state.analysis = {
                'app_data': app_data,
                'analysis': analysis,
                'app_id': app_id
            }

# Результаты
if 'analysis' in st.session_state:
    result = st.session_state.analysis
    
    col1, col2, col3 = st.columns(3)
    col1.metric("📊 Market Fit", f"{result['analysis']['market_fit']}/10")
    col2.metric("📱 Installs", result['app_data']['installs'])
    col3.metric("⭐ Rating", f"{result['app_data']['score']:.1f}")
    
    st.subheader("🎯 Рекомендации")
    for i, rec in enumerate(result['analysis']['recommendations'], 1):
        st.info(f"{i}. {rec}")
    
    # История
    st.subheader("📈 История")
    try:
        conn = init_db()
        df = pd.read_sql("SELECT * FROM app_meta ORDER BY last_updated DESC LIMIT 10", conn)
        st.dataframe(df)
    except:
        st.info("Первые записи появятся после анализа")

st.caption("✅ v1.0 | Railway | Кэш + LLM")
