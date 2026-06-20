import os
from dotenv import load_dotenv

load_dotenv()

import streamlit as st
from frontend.utils.api_client import fetch_stats, send_chat, BACKEND_URL, LOGMON_API_KEY
from frontend.utils.chart_renderer import render_trend_chart

# 1. 페이지 셋업 및 CSS 주입
st.set_page_config(page_title="LogMon Dashboard", page_icon="👾", layout="wide", initial_sidebar_state="collapsed")

def load_css():
    css_path = os.path.join(os.path.dirname(__file__), "assets", "style.css")
    if os.path.exists(css_path):
        with open(css_path, "r") as f:
            st.markdown(f"<style>{f.read()}</style>", unsafe_allow_html=True)

load_css()

# 2. 메인 타이틀 및 상단 컨트롤 영역
col_logo, col_title, col_btn = st.columns([0.1, 0.7, 0.2])
with col_logo:
    st.image("frontend/assets/logo.png", width=80)
with col_title:
    st.title("Welcome to LogMon")
    st.markdown("로컬 개발 PC의 생산성과 오류 발생 트렌드를 시각화하고 과거 이력에 대해 질문하세요.")
with col_btn:
    st.markdown("<div style='margin-top: 25px;'></div>", unsafe_allow_html=True)
    st.page_link("pages/install.py", label="에이전트 설치하기", icon="🚀", use_container_width=True)

# 3. 메인 대시보드 스코어 카드 영역
stats = fetch_stats()

import datetime

def format_sync_time(last_sync_time_str: str) -> str:
    if not last_sync_time_str:
        return "데이터 없음"
    try:
        last_dt = datetime.datetime.strptime(last_sync_time_str, "%Y-%m-%d %H:%M:%S")
        now = datetime.datetime.now()
        diff = int((now - last_dt).total_seconds())
        if diff < 60:
            return f"{diff}초 전 (정상)"
        elif diff < 3600:
            return f"{diff // 60}분 전 (정상)"
        elif diff < 86400:
            return f"{diff // 3600}시간 전"
        else:
            return f"{diff // 86400}일 전"
    except Exception:
        return "알 수 없음"

col1, col2, col3 = st.columns(3)
with col1:
    uptime_days = stats.get('uptime_days', 0)
    st.markdown(f"""
    <div class='neumorphic-card'>
        <div class='neumorphic-title'>설치 후 경과일 (가동 시간)</div>
        <div class='neumorphic-value' style='font-size: 1.1rem;'>📅 에이전트 가동: {uptime_days}일째</div>
    </div>
    """, unsafe_allow_html=True)
with col2:
    lines = stats.get('total_lines', 0)
    mb = stats.get('total_bytes', 0) / (1024 * 1024)
    st.markdown(f"""
    <div class='neumorphic-card'>
        <div class='neumorphic-title'>누적 수집 데이터량</div>
        <div class='neumorphic-value' style='font-size: 1.1rem;'>📦 자동 수집: 총 {lines:,}라인 ({mb:.2f} MB)</div>
    </div>
    """, unsafe_allow_html=True)
with col3:
    sync_str = format_sync_time(stats.get('last_sync_time'))
    st.markdown(f"""
    <div class='neumorphic-card'>
        <div class='neumorphic-title'>가장 최신 동기화 시간 ⭐</div>
        <div class='neumorphic-value' style='font-size: 1.1rem;'>🔄 최근 동기화: {sync_str}</div>
    </div>
    """, unsafe_allow_html=True)

current_db_mb = stats.get('current_db_mb', 0.0)
max_db_mb = stats.get('max_db_mb', 500.0)
usage_ratio = current_db_mb / max_db_mb if max_db_mb > 0 else 0

st.markdown("<br/>", unsafe_allow_html=True)
st.progress(min(usage_ratio, 1.0), text=f"현재 저장 공간 사용량: {current_db_mb:.1f}MB / {max_db_mb}MB ({usage_ratio*100:.1f}%)")

if usage_ratio >= 0.9:
    st.warning("🚨 용량 한도 초과(또는 임박)로 인해 오래된 로그부터 자동 정리 중입니다.")

st.subheader("최근 7일 수집 트렌드")
render_trend_chart(stats.get("trend_7d", []))
st.divider()

# 4. RAG 챗 인터페이스
st.subheader("💬 Logmon AI 어시스턴트")

if "messages" not in st.session_state:
    st.session_state.messages = [{"role": "assistant", "content": "과거 로그 컨텍스트에 대해 무엇이든 물어보세요!"}]

# 기존 대화 렌더링
for msg in st.session_state.messages:
    with st.chat_message(msg["role"]):
        st.markdown(msg["content"])

# 채팅 입력창
if user_query := st.chat_input("에러 해결법이나 과거 작성했던 코드 내역을 질문하세요..."):
    # 유저 메시지 화면 추가
    st.session_state.messages.append({"role": "user", "content": user_query})
    with st.chat_message("user"):
        st.markdown(user_query)
        
    # AI 봇 응답 (스피너)
    with st.chat_message("assistant"):
        with st.spinner("과거 로그 검색 및 AI 분석 중..."):
            ai_answer = send_chat(user_query)
            st.markdown(ai_answer)
            st.session_state.messages.append({"role": "assistant", "content": ai_answer})
