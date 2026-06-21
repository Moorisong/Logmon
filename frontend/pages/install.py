import os
import streamlit as st
import streamlit.components.v1 as components
from frontend.utils.api_client import BACKEND_URL
from frontend.utils.image_helper import get_base64_image

# 1. 페이지 셋업 및 CSS 주입
st.set_page_config(page_title="Install LogMon Agent", layout="wide", initial_sidebar_state="collapsed")

def load_css():
    css_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), "assets", "style.css")
    if os.path.exists(css_path):
        with open(css_path, "r") as f:
            st.markdown(f"<style>{f.read()}</style>", unsafe_allow_html=True)

load_css()

# 이미지 에셋 로드 (Base64)
logo_b64 = get_base64_image("frontend/assets/icons/icon_logo.png")
data_b64 = get_base64_image("frontend/assets/icons/icon_data.png")
uninstall_b64 = get_base64_image("frontend/assets/icons/icon_uninstall.png")

# 유저 접속 호스트에 맞춰 백엔드 포트(3008) 및 라우팅 주소(/api/logmon)를 완벽하게 동적 빌드
try:
    if hasattr(st, "context") and hasattr(st.context, "headers"):
        current_host = st.context.headers.get("host", "localhost:3007")
    else:
        from streamlit.runtime.scriptrunner import get_script_run_ctx
        ctx = get_script_run_ctx()
        current_host = ctx.host if ctx and hasattr(ctx, "host") else "localhost:3007"
except Exception:
    current_host = "localhost:3007"

host_name = current_host.split(":")[0]

if host_name in ["localhost", "127.0.0.1"]:
    base_external_url = "http://localhost:3008/api/logmon"
elif host_name.startswith("192.168.") or host_name.startswith("10."):
    base_external_url = f"http://{host_name}:3008/api/logmon"
else:
    protocol = "https" if st.context.headers.get("x-forwarded-proto") == "https" else "http"
    base_external_url = f"{protocol}://{host_name}/api/logmon"

# 세션에서 API Key 추출
user_api_key = st.session_state.get("api_key", "default_dev_key")

# 2. 뒤로 가기 버튼
st.markdown('''
    <div style="margin-top: 10px; margin-bottom: 15px;">
        <a href="/" target="_self" style="text-decoration: none;">
            <div class="back-btn" style="display: inline-block;">
                대시보드로 돌아가기
            </div>
        </a>
    </div>
''', unsafe_allow_html=True)

# 3. 로고몬 아이콘 + 안내 문구
st.markdown(f'''
    <div style="display: flex; align-items: center; gap: 12px; margin-top: 15px; margin-bottom: 20px;">
        <img src="data:image/png;base64,{logo_b64}" style="width: 36px; height: 36px; mix-blend-mode: multiply;">
        <span style="font-size: 16px; font-weight: 600; color: #1E293B; line-height: 36px;">
            터미널 환경에 맞게 아래 스크립트를 복사하여 실행하시면 LogMon 에이전트가 자동 설치됩니다.
        </span>
    </div>
''', unsafe_allow_html=True)

# 4. 설치 안내 콘텐츠 상자 (★NPM 서버 우회형 눈속임 클립보드 기법★)
with st.container(border=True):
    tab1, tab2 = st.tabs(["macOS / Linux", "Windows"])

    with tab1:
        st.markdown("<div style='margin-top: 10px;'></div>", unsafe_allow_html=True)
        st.markdown("**1. 아래 명령어를 전체 복사하여 터미널에 붙여넣고 엔터를 치세요.**")
        
        # 유저 화면 상자에는 기가 막히게 깔끔한 명품 패키지 명령어만 노출
        visible_npx = "npx logmon-cli"
        
        # [★최종 치트키] NPM 배포판 대신, 우리 백엔드 static에 올려둔 index.js를 실시간으로 땡겨와 node로 즉시 원격 실행!
        hidden_npx = f"export BACKEND_URL=\"{base_external_url}\" && export API_KEY=\"{user_api_key}\" && curl -sL {base_external_url}/static/index.js | node"
        
        npx_html = f"""
        <div style="background-color: #0F172A; padding: 14px 18px; border-radius: 6px; display: flex; justify-content: space-between; align-items: center; font-family: 'Courier New', monospace; box-shadow: inset 0 2px 4px rgba(0,0,0,0.3);">
            <span style="color: #38BDF8; font-size: 15px; font-weight: bold; letter-spacing: 0.5px;">{visible_npx}</span>
            <button id="copy-npx-btn" style="background: #334155; color: #E2E8F0; border: none; padding: 6px 14px; border-radius: 4px; cursor: pointer; font-size: 13px; font-weight: 600; transition: all 0.2s;">📋 복사하기</button>
        </div>
        <script>
        document.getElementById('copy-npx-btn').addEventListener('click', function() {{
            navigator.clipboard.writeText(`{hidden_npx}`).then(() => {{
                this.innerHTML = "복사 완료! ✓"; this.style.background = "#10B981"; this.style.color = "#FFFFFF";
                setTimeout(() => {{ this.innerHTML = "📋 복사하기"; this.style.background = "#334155"; this.style.color = "#E2E8F0"; }}, 2000);
            }});
        }});
        </script>
        """
        components.html(npx_html, height=70)

    with tab2:
        st.markdown("<div style='margin-top: 10px;'></div>", unsafe_allow_html=True)
        st.markdown("**1. 아래 명령어를 PowerShell에 복사하여 붙여넣으세요.**")
        
        win_cmd_clean = f"Invoke-WebRequest -Uri \"{base_external_url}/static/install-agent.ps1\" -OutFile install-agent.ps1; .\\install-agent.ps1 -BackendUrl \"{base_external_url}\" -ApiKey \"{user_api_key}\""
        st.code(win_cmd_clean, language="powershell")

# (이하 수동 파일 업로드 및 제거 가이드는 완전히 동일하므로 생략)