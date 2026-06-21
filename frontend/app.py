import os
from dotenv import load_dotenv

load_dotenv()

import streamlit as st
from frontend.utils.api_client import fetch_stats, send_chat, BACKEND_URL, LOGMON_API_KEY
from frontend.utils.chart_renderer import render_trend_chart

import base64

def get_base64_image(image_path):
    with open(image_path, "rb") as f:
        data = f.read()
    return base64.b64encode(data).decode()

# 1. 페이지 셋업 및 CSS 주입
st.set_page_config(page_title="LogMon Dashboard", layout="wide", initial_sidebar_state="collapsed")

def load_css():
    css_path = os.path.join(os.path.dirname(__file__), "assets", "style.css")
    if os.path.exists(css_path):
        with open(css_path, "r") as f:
            st.markdown(f"<style>{f.read()}</style>", unsafe_allow_html=True)

load_css()


col_title, col_btn = st.columns([0.8, 0.2])
with col_title:
    logo_b64 = get_base64_image("frontend/assets/icons/icon_logo.png")
    st.markdown(f'''
        <div style="display: flex; align-items: center; gap: 15px; margin-bottom: 10px;">
            <h1 style="margin: 0;">Welcome to LogMon</h1>
            <img src="data:image/png;base64,{logo_b64}" class="header-icon" style="width: 50px; height: 50px;">
        </div>
    ''', unsafe_allow_html=True)
    st.markdown("로컬 개발 PC의 생산성과 오류 발생 트렌드를 시각화하고 과거 이력에 대해 질문하세요.")
with col_btn:
    st.markdown("<div style='margin-top: 25px;'></div>", unsafe_allow_html=True)
    st.markdown(
        f'''<a href="/install" target="_self" style="text-decoration: none;">
            <div class="install-btn">
                에이전트 설치하기
            </div>
        </a>''', 
        unsafe_allow_html=True
    )

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
uptime_b64 = get_base64_image("frontend/assets/icons/icon_uptime.png")
data_b64 = get_base64_image("frontend/assets/icons/icon_data.png")
sync_b64 = get_base64_image("frontend/assets/icons/icon_sync.png")

with col1:
    uptime_days = stats.get('uptime_days', 0)
    st.markdown(f"""
    <div class='glass-card'>
        <div class='glass-title'><img src="data:image/png;base64,{uptime_b64}" class="icon-img"> 설치 후 경과일 (가동 시간)</div>
        <div class='glass-value'>에이전트 가동: {uptime_days}일째</div>
    </div>
    """, unsafe_allow_html=True)
with col2:
    lines = stats.get('total_lines', 0)
    mb = stats.get('total_bytes', 0) / (1024 * 1024)
    st.markdown(f"""
    <div class='glass-card'>
        <div class='glass-title'><img src="data:image/png;base64,{data_b64}" class="icon-img"> 누적 수집 데이터량</div>
        <div class='glass-value'>총 {lines:,}라인 ({mb:.2f} MB)</div>
    </div>
    """, unsafe_allow_html=True)
with col3:
    sync_str = format_sync_time(stats.get('last_sync_time'))
    st.markdown(f"""
    <div class='glass-card'>
        <div class='glass-title'><img src="data:image/png;base64,{sync_b64}" class="icon-img"> 가장 최신 동기화 시간</div>
        <div class='glass-value'>최근 동기화: {sync_str}</div>
    </div>
    """, unsafe_allow_html=True)

current_db_mb = stats.get('current_db_mb', 0.0)
max_db_mb = stats.get('max_db_mb', 500.0)
usage_ratio = current_db_mb / max_db_mb if max_db_mb > 0 else 0

st.markdown("<br/>", unsafe_allow_html=True)
st.progress(min(usage_ratio, 1.0), text=f"현재 저장 공간 사용량: {current_db_mb:.1f}MB / {max_db_mb}MB ({usage_ratio*100:.1f}%)")

if usage_ratio >= 0.9:
    alert_b64 = get_base64_image("frontend/assets/icons/icon_alert.png")
    st.markdown(f"""
        <div style="background-color: #FEF2F2; border: 1px solid #FCA5A5; padding: 12px; border-radius: 8px; color: #DC2626; display: flex; align-items: center; font-weight: bold;">
            <img src="data:image/png;base64,{alert_b64}" class="icon-img" style="margin-right: 12px;"> 용량 한도 초과(또는 임박)로 인해 오래된 로그부터 자동 정리 중입니다.
        </div>
    """, unsafe_allow_html=True)

st.subheader("최근 7일 수집 트렌드")
render_trend_chart(stats.get("trend_7d", []))
st.divider()

# 4. RAG 챗 인터페이스
st.markdown(f"""
    <div style="display: flex; align-items: center; margin-top: 20px; margin-bottom: 10px;">
        <h3 style="margin: 0;">Logmon AI 어시스턴트</h3>
    </div>
""", unsafe_allow_html=True)

if "messages" not in st.session_state:
    st.session_state.messages = [{"role": "assistant", "content": "과거 로그 컨텍스트에 대해 무엇이든 물어보세요!"}]

# 기존 대화 렌더링
for msg in st.session_state.messages:
    with st.chat_message(msg["role"]):
        st.markdown(msg["content"])

# 채팅 입력창
with st.form("chat_form", clear_on_submit=True):
    col1, col2 = st.columns([0.85, 0.15])
    with col1:
        user_query = st.text_input("질문", placeholder="에러 해결법이나 과거 작성했던 코드 내역을 질문하세요...", label_visibility="collapsed")
    with col2:
        submit_btn = st.form_submit_button("전송", use_container_width=True)

if submit_btn and user_query:
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

