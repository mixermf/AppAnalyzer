import streamlit as st
import google_play_scraper as gps
import pandas as pd
from openai import OpenAI  # ← Perplexity совместим с OpenAI SDK
import psycopg
import os
from datetime import datetime
import json
import re

# УПРОЩЁННАЯ АВТОРИЗАЦИЯ
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
        **client** / **play123**
        """)

if not st.session_state.logged_in:
    login_page()
    st.stop()

if st.sidebar.button("🚪 Выйти"):
    st.session_state.logged_in = False
    st.rerun()

st.sidebar.success("✅ Авторизован")

# ГЛАВНОЕ ПРИЛОЖЕНИЕ
st.title("🚀 Play Analyzer Pro")
st.caption("Perplexity AI + Google Play скрейпинг")

@st.cache_resource
def init_db():
    conn = psycopg.connect(os.getenv("DATABASE_URL"))
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
    return conn

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
        st.error(f"❌ Скрейпинг: {e}")
        return None

def perplexity_analyze(app_data, scenario, context):
    """Perplexity API"""
    try:
        client = OpenAI(
            api_key=os.getenv("PERPLEXITY_API_KEY"),
            base_url="https://api.perplexity.ai"  # ← Perplexity endpoint
        )
        
        prompt = f"""
        Анализируй Android app для Google Play:
        Название: {app_data['title']}
        Установки: {app_data['installs']}
        Рейтинг: {app_data['score']}*
        Отзывов: {app_data['reviews']}
        Сценарий: {scenario}
        Контекст: {context}
        
        Верни ТОЛЬКО JSON:
        {{
            "market_fit": 8,
            "recommendations": [
                "Конкретная рекомендация 1",
                "Конкретная рекомендация 2", 
                "Конкретная рекомендация 3"
            ]
        }}
        """
        
        response = client.chat.completions.create(
            model="llama-3.1-sonar-small-128k-online",  # Perplexity Sonar
            messages=[{"role": "user", "content": prompt}],
            temperature=0.1
        )
        
        # Извлекаем JSON из ответа
        content = response.choices[0].message.content
        json_match = re.search(r'\{.*\}', content, re.DOTALL)
        if json_match:
            return json.loads(json_match.group())
        else:
            st.warning("JSON не найден, используем мок")
            return {"market_fit": 7, "recommendations": ["Perplexity OK", "Анализ работает", "Данные собраны"]}
            
    except Exception as e:
        st.error(f"❌ Perplexity: {e}")
        return {"market_fit": 5, "recommendations": ["API недоступен", "Скрейпинг работает", "Кэш активен"]}

# Sidebar
with st.sidebar:
    st.header("⚙️ Анализ")
    scenario = st.selectbox("Сценарий", ["competitor", "niche", "validate"])
    app_id = st.text_input("App ID", value="com.whatsapp")
    context = st.text_area("Идея/контекст", "Моя идея для игры...")
    
    if st.button("🔍 Анализировать", type="primary"):
        with st.spinner("⏳ Скрейпинг → Perplexity → Анализ..."):
            conn = init_db()
            
            # КЭШ CHECK (24ч)
            with conn.cursor() as cur:
                cur.execute("SELECT * FROM app_meta WHERE app_id = %s", (app_id,))
                cached = cur.fetchone()
                
                if cached and (datetime.now() - cached[4]).seconds < 86400:
                    app_data = {
                        'title': cached[3],
                        'installs': cached[1],
                        'score': float(cached[2]),
                        'reviews': 0
                    }
                    st.sidebar.success("✅ Кэш (24ч)")
                else:
                    # СКРЕЙПИНГ
                    app_data_raw = scrape_app(app_id)
                    if app_data_raw:
                        cur.execute("""
                            INSERT INTO app_meta (app_id, installs, score, title, last_updated)
                            VALUES (%s, %s, %s, %s, %s) ON CONFLICT (app_id) 
                            DO UPDATE SET installs=%s, score=%s, title=%s, last_updated=%s
                        """, (app_id, app_data_raw['installs'], app_data_raw['score'], 
                              app_data_raw['title'], datetime.now(),
                              app_data_raw['installs'], app_data_raw['score'], 
                              app_data_raw['title'], datetime.now()))
                        conn.commit()
                        app_data = app_data_raw
                        st.sidebar.success("✅ Свежие данные")
                    else:
                        st.error("❌ Скрейпинг failed")
                        st.stop()
            
            # PERPLEXITY АНАЛИЗ
            analysis = perplexity_analyze(app_data, scenario, context)
            st.session_state.analysis = {
                'app_data': app_data,
                'analysis': analysis,
                'app_id': app_id
            }
            st.balloons()  # 🎉

# РЕЗУЛЬТАТЫ
if 'analysis' in st.session_state:
    result = st.session_state.analysis
    
    col1, col2, col3 = st.columns(3)
    col1.metric("📊 Market Fit", f"{result['analysis']['market_fit']}/10")
    col2.metric("📱 Installs", result['app_data']['installs'])
    col3.metric("⭐ Rating", f"{result['app_data']['score']:.1f}")
    
    st.success(f"✅ Анализ {result['app_id']} завершён")
    
    st.subheader("🎯 Рекомендации Perplexity AI")
    for i, rec in enumerate(result['analysis']['recommendations'], 1):
        st.info(f"{i}. {rec}")
    
    # ИСТОРИЯ
    st.subheader("📈 База данных")
    try:
        conn = init_db()
        df = pd.read_sql("SELECT * FROM app_meta ORDER BY last_updated DESC LIMIT 10", conn)
        st.dataframe(df)
    except Exception as e:
        st.info(f"База: {e}")

st.caption("🔥 Perplexity AI + Google Play | Railway v1.0")
