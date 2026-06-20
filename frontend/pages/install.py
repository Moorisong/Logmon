import os
import streamlit as st
from frontend.utils.api_client import BACKEND_URL

# 1. 페이지 셋업 및 CSS 주입
st.set_page_config(page_title="Install LogMon Agent", page_icon="🚀", layout="wide", initial_sidebar_state="collapsed")

def load_css():
    css_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), "assets", "style.css")
    if os.path.exists(css_path):
        with open(css_path, "r") as f:
            st.markdown(f"<style>{f.read()}</style>", unsafe_allow_html=True)

load_css()

# 2. 뒤로 가기 버튼
st.markdown("<div style='margin-bottom: 20px;'></div>", unsafe_allow_html=True)
st.page_link("app.py", label="메인 대시보드로 돌아가기", icon="⬅️")

# 3. 설치 안내 콘텐츠
st.title("🚀 에이전트 설치 안내")
st.markdown("터미널 환경에 맞게 아래 스크립트를 복사하여 실행하시면 LogMon 에이전트가 자동 설치됩니다.")

st.markdown("<div class='neumorphic-card' style='text-align: left; margin-top: 30px; padding: 30px;'>", unsafe_allow_html=True)

mac_cmd = f"curl -sL {BACKEND_URL}/api/logmon/static/install-agent.sh | bash"
win_cmd = f"Invoke-WebRequest -Uri {BACKEND_URL}/api/logmon/static/install-agent.ps1 -OutFile install-agent.ps1; .\\install-agent.ps1"

tab1, tab2 = st.tabs(["🍏 macOS / Linux", "🪟 Windows"])

with tab1:
    st.markdown("<br/>**1. 아래 명령어를 터미널에 복사하여 붙여넣으세요.**", unsafe_allow_html=True)
    st.write(f"`BACKEND_URL: ********`")
    st.code(mac_cmd, language="bash")

with tab2:
    st.markdown("<br/>**1. 아래 명령어를 PowerShell에 복사하여 붙여넣으세요.**", unsafe_allow_html=True)
    st.write(f"`BACKEND_URL: ********`")
    st.code(win_cmd, language="powershell")

st.markdown("</div>", unsafe_allow_html=True)

st.divider()

st.subheader("🛠️ 수동 파일 업로드")
st.markdown("에이전트를 설치할 수 없는 환경이라면 직접 로그 파일을 업로드하실 수 있습니다.")

uploaded_file = st.file_uploader("로그 파일 선택", type=["txt", "log", "json", "md"], help="에이전트가 자동 수집하는 형식의 텍스트 기반 로그 파일을 올려주세요.")
if uploaded_file is not None:
    if st.button("업로드 전송", use_container_width=True):
        from frontend.utils.api_client import upload_log
        file_bytes = uploaded_file.read()
        with st.spinner("파일을 분석하고 백엔드로 전송 중입니다..."):
            success = upload_log(file_bytes, uploaded_file.name)
        if success:
            st.success("✅ 파일이 성공적으로 업로드 및 처리되었습니다!")
