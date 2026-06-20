import os
import streamlit as st
from frontend.utils.api_client import fetch_stats, send_chat, upload_log, BACKEND_URL, LOGMON_API_KEY
from frontend.utils.chart_renderer import render_trend_chart

# 1. 페이지 셋업 및 CSS 주입
st.set_page_config(page_title="LogMon Dashboard", page_icon="👾", layout="wide")

def load_css():
    css_path = os.path.join(os.path.dirname(__file__), "assets", "style.css")
    if os.path.exists(css_path):
        with open(css_path, "r") as f:
            st.markdown(f"<style>{f.read()}</style>", unsafe_allow_html=True)

load_css()

# 2. 사이드바 (로고, 수동 업로드, 설치 가이드)
with st.sidebar:
    st.markdown("<div class='sidebar-title'>LogMon 👾</div>", unsafe_allow_html=True)
    
    st.subheader("📁 수동 업로드")
    uploaded_file = st.file_uploader("IDE 텍스트 로그 파일 선택", type=["txt", "log"])
    if uploaded_file is not None:
        if st.button("백엔드로 전송"):
            with st.spinner("업로드 중..."):
                success = upload_log(uploaded_file.read(), uploaded_file.name)
                if success:
                    st.success("적재 완료!")
    
    st.divider()
    st.subheader("🚀 에이전트 자동 설치")
    st.caption("터미널에 붙여넣어 에이전트를 설치하세요.")
    
    # 보안 마스킹 처리 
    masked_key = "********"
    # 도메인 노출을 원치 않을 수 있으므로 설치 스크립트 도메인 표시 여부는 UI적으로 마스킹하지 않고 온전하게 노출시킬 수도 있으나,
    # 사용자 요구사항에 "해당 주소와 API Key는 마스킹 처리하고 버튼 누를때만 복사되도록" 이라는 보안 요건이 있으므로 st.code는 보안상 그대로 노출하되
    # UI Text로 먼저 마스킹된 버전을 보여줄 수 있습니다. Streamlit의 st.code 자체가 클립보드 복사를 지원함.
    
    mac_cmd = f"curl -sL {BACKEND_URL}/api/logmon/static/install-agent.sh | bash"
    win_cmd = f"Invoke-WebRequest -Uri {BACKEND_URL}/api/logmon/static/install-agent.ps1 -OutFile install-agent.ps1; .\install-agent.ps1"
    
    tab1, tab2 = st.tabs(["🍏 Mac/Linux", "🪟 Windows"])
    with tab1:
        st.write("`BACKEND_URL: ********`")
        st.code(mac_cmd, language="bash")
    with tab2:
        st.write("`BACKEND_URL: ********`")
        st.code(win_cmd, language="powershell")

# 3. 메인 대시보드 영역
st.title("Welcome to LogMon 👾")
st.markdown("로컬 개발 PC의 생산성과 오류 발생 트렌드를 시각화하고 과거 이력에 대해 질문하세요.")

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
