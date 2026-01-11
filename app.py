import streamlit as st
import streamlit_authenticator as stauth
import yaml
import google_play_scraper as gps
import pandas as pd
import plotly.express as px
from openai import OpenAI
import psycopg  # ← ИСПРАВЛЕНО: psycopg вместо psycopg2
import os
from datetime import datetime, timedelta
import json

# Конфиг пользователей
config = {
    "credentials": {
        "usernames": {
            "client": {
                "email": "client@example.com",
                "name": "Клиент",
                "password": "play123"
            }
        }
    },
    "cookie": {"name": "play_auth", "key": "random_key_123", "expiry_days": 30}
}

@st.cache_resource
def init_db():
    """Подключение к Railway Postgres через psycopg"""
    conn = psycopg.connect(os.getenv("DATABASE_URL"))
    cur = conn.cursor()
    
    # Создаём таблицы
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
    """Скрейпинг приложения"""
    try:
        data = gps.app(app_id, lang='en', country='us')
        return {
            'title': data['title'],
            'installs': data['installs'],
            'score': float(data['score']),  # ← ИСПРАВЛЕНО: float
            'reviews': data['reviews']
        }
    except Exception as e:
        st.error(f"Ошибка скрейпинга: {e}")
        return None

def llm_analyze(app_data, scenario, context):
    """Анализ через OpenAI"""
    try:
        client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))
        
        prompt = f"""
        App: {app_data['title']} ({app_data['installs']}, рейтинг {app_data['score']}*)
        Scenario: {scenario}
        Context: {context}
        
        Верни JSON: {{"market_fit": 8, "recommendations": ["rec1", "rec2", "rec3"]}}
        """
        
        response = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[{"role": "user", "content": prompt}]
        )
        
        content = response.choices[0].message.content
        return json.loads(content)
    except Exception as e:
        st.error(f"Ошибка LLM: {e}")
        return {"market_fit": 0, "recommendations": ["Ошибка анализа"]}

# Streamlit app
def main():
    st.set_page_config(layout="wide", page_title="Play Analyzer")
    st.title("🚀 Play Analyzer Pro")
    
    authenticator = stauth.Authenticate(
        config['credentials'], 
        config['cookie']['name'],
        config['cookie']['key'], 
        config['cookie']['expiry_days']
    )
    
    name, authentication_status, username = authenticator.login('Логин', 'Пароль')
    
    if authentication_status == False:
        st.error('❌ Неправильный логин/пароль')
        st.stop()
    elif authentication_status == None:
        st.warning('👆 Введите логин и пароль')
        st.stop()
    
    # Sidebar logout
    if st.sidebar.button("🚪 Logout"):
        authenticator.logout()
        st.rerun()
    
    st.sidebar.success(f"Привет, {name}!")
    
    # Sidebar inputs
    with st.sidebar:
        st.header("⚙️ Анализ")
        scenario = st.selectbox("Сценарий", ["competitor", "niche", "validate"])
        app_id = st.text_input("App ID", value="com.whatsapp")
        context = st.text_area("Контекст/идея", "Моя идея...")
        
        if st.button("🔍 Анализировать", type="primary"):
            with st.spinner("⏳ Скрейпим + анализируем..."):
                try:
                    conn = init_db()
                    
                    # 1. Проверяем кэш (24ч)
                    with conn.cursor() as cur:
                        cur.execute("SELECT * FROM app_meta WHERE app_id = %s", (app_id,))
                        cached = cur.fetchone()
                        
                        if cached and (datetime.now() - cached[3]).seconds < 86400:
                            app_data = {
                                'title': f"Cached: {app_id}",
                                'installs': cached[1],
                                'score': float(cached[2])
                            }
                            st.success("✅ Используем кэш")
                        else:
                            # 2. Скрейпинг
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
                                st.success("✅ Свежие данные + сохранены")
                            else:
                                st.error("❌ Не удалось скрейпить")
                                st.stop()
                    
                    # 3. LLM анализ
                    analysis = llm_analyze(app_data, scenario, context)
                    
                    st.session_state.analysis = {
                        'app_data': app_data,
                        'analysis': analysis,
                        'app_id': app_id
                    }
                    
                except Exception as e:
                    st.error(f"Ошибка пайплайна: {e}")
    
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
        st.subheader("📈 История данных")
        try:
            conn = init_db()
            df = pd.read_sql("SELECT * FROM app_meta ORDER BY last_updated DESC LIMIT 10", conn)
            st.dataframe(df)
        except:
            st.info("История появится после первых анализов")
    
    st.caption("👨‍💻 Play Analyzer v1.0 | Railway")

if __name__ == "__main__":
    main()
