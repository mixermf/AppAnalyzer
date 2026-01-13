import os

import pandas as pd
import streamlit as st

from db import Database
from pipeline import run_user_pipeline


def _auth_gate() -> None:
    required = os.getenv("APP_PASSWORD")
    if not required:
        return

    if "authed" not in st.session_state:
        st.session_state.authed = False

    if st.session_state.authed:
        return

    st.title("Play Analyzer")
    pwd = st.text_input("Password", type="password")
    if st.button("Login"):
        if pwd == required:
            st.session_state.authed = True
            st.rerun()
        else:
            st.error("Invalid password")
    st.stop()


_auth_gate()

st.title("Play Analyzer")
st.caption("Google Play scraper + Postgres + Perplexity")

with st.sidebar:
    app_id = st.text_input("App ID", "com.whatsapp")
    scenario = st.text_input("Scenario", "default")
    user_context = st.text_area("User context (optional)", "")
    client_id = st.text_input("Client id (optional)", "")
    lang = st.text_input("Lang", os.getenv("SCRAPE_LANG", "en"))
    country = st.text_input("Country", os.getenv("SCRAPE_COUNTRY", "us"))
    run = st.button("🔍 Analyze")

if run:
    with st.spinner("Working..."):
        st.session_state.result = run_user_pipeline(
            app_id=app_id.strip(),
            scenario=scenario.strip() or "default",
            user_context=user_context.strip() or None,
            client_id=client_id.strip() or None,
            lang=lang.strip() or "en",
            country=country.strip() or "us",
        )

if "result" in st.session_state:
    r = st.session_state.result
    analysis = r.get("analysis") or {}
    meta = r.get("meta") or {}

    st.success(f"Source: {r.get('source')}")

    col1, col2, col3 = st.columns(3)
    col1.metric("Market fit", f"{analysis.get('market_fit', '-')}/10")
    col2.metric("Installs", str(meta.get("installs") or "-"))
    score = meta.get("score")
    col3.metric("Rating", f"{float(score):.1f}" if score is not None else "-")

    st.subheader("Recommendations")
    for rec in analysis.get("recommendations") or []:
        st.write(f"- {rec}")

    with st.expander("Meta info"):
        st.json(meta)

    with st.expander("Raw LLM response"):
        st.json(analysis.get("raw"))

    st.subheader("Recent analyses")
    try:
        db = Database()
        with db.connect() as conn:
            df = pd.read_sql(
                """
                SELECT app_id, scenario, client_id, market_fit, analyzed_at
                FROM app_analysis
                ORDER BY analyzed_at DESC
                LIMIT 20
                """,
                conn,
            )
        st.dataframe(df, use_container_width=True)
    except Exception:
        pass

st.caption("Railway modular v2")
