import os
import streamlit as st
import streamlit.components.v1 as components
from frontend.utils.api_client import BACKEND_URL, LOGMON_API_KEY
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
base_external_url = os.getenv("BACKEND_EXTERNAL_URL")
if not base_external_url:
    if BACKEND_URL and not any(lh in BACKEND_URL for lh in ["localhost", "127.0.0.1", "backend"]):
        base_external_url = f"{BACKEND_URL}/api/logmon"

if not base_external_url:
    try:
        if hasattr(st, "context") and hasattr(st.context, "headers"):
            headers = st.context.headers
            current_host = headers.get("x-forwarded-host") or headers.get("host", "localhost:3007")
            protocol = headers.get("x-forwarded-proto") or "http"
        else:
            from streamlit.runtime.scriptrunner import get_script_run_ctx
            ctx = get_script_run_ctx()
            current_host = ctx.host if ctx and hasattr(ctx, "host") else "localhost:3007"
            protocol = "http"
    except Exception:
        current_host = "localhost:3007"
        protocol = "http"

    host_name = current_host.split(":")[0]
    port = current_host.split(":")[1] if ":" in current_host else ""

    if host_name in ["localhost", "127.0.0.1"]:
        if BACKEND_URL and ("localhost" in BACKEND_URL or "127.0.0.1" in BACKEND_URL):
            base_external_url = f"{BACKEND_URL}/api/logmon"
        else:
            base_external_url = "http://localhost:3008/api/logmon"
    elif host_name.startswith("192.168.") or host_name.startswith("10."):
        base_external_url = f"http://{host_name}:3008/api/logmon"
    else:
        if port == "3007":
            base_external_url = f"{protocol}://{host_name}:3008/api/logmon"
        else:
            base_external_url = f"{protocol}://{current_host}/api/logmon"

# 세션에서 API Key 추출 (없으면 환경변수 및 기본값으로 설정된 LOGMON_API_KEY 로 fallback)
user_api_key = st.session_state.get("api_key") or LOGMON_API_KEY

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

# 4. 설치 안내 콘텐츠 상자 (★지저분한 변수 없는 원클릭 동적 세션 라우팅 기법★)
with st.container(border=True):
    tab1, tab2 = st.tabs(["macOS / Linux", "Windows"])

    with tab1:
        st.markdown("<div style='margin-top: 10px;'></div>", unsafe_allow_html=True)
        st.markdown("**1. 아래 명령어를 전체 복사하여 터미널에 붙여넣고 엔터를 치세요.**")
        
        # 유저 화면 상자에는 명품 감성의 주소 노출
        visible_npx = "npx @thiagomiki/logmon-cli@latest"
        
        # 백엔드 URL이 기본 로컬 주소인 경우 URL 매개변수 전송을 과감히 생략하여 간결함 극대화
        if "localhost" in base_external_url or "127.0.0.1" in base_external_url:
            hidden_npx = f"npx @thiagomiki/logmon-cli@latest {user_api_key}"
        else:
            hidden_npx = f"npx @thiagomiki/logmon-cli@latest {user_api_key} {base_external_url}"
        
        copy_svg = '<svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round"><rect x="9" y="9" width="13" height="13" rx="2" ry="2"></rect><path d="M5 15H5a2 2 0 0 1-2-2V4a2 2 0 0 1 2-2h9a2 2 0 0 1 2 2v1"></path></svg>'
        check_svg = '<svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="3" stroke-linecap="round" stroke-linejoin="round"><polyline points="20 6 9 17 4 12"></polyline></svg>'
        
        npx_html = f"""
        <style>
        #copy-npx-btn:hover {{
            background-color: #CBD5E1 !important;
            color: #1E293B !important;
        }}
        </style>
        <div style="background-color: #F1F5F9; border: 1px solid #E2E8F0; padding: 12px 16px; border-radius: 8px; display: flex; justify-content: space-between; align-items: center; font-family: 'Courier New', monospace;">
            <span style="color: #0F172A; font-size: 15px; font-weight: bold; letter-spacing: 0.5px;">{visible_npx}</span>
            <button id="copy-npx-btn" style="background: #E2E8F0; color: #475569; border: none; width: 32px; height: 32px; display: flex; justify-content: center; align-items: center; border-radius: 6px; cursor: pointer; transition: all 0.2s;" title="클립보드에 복사">{copy_svg}</button>
        </div>
        <script>
        const copySvg = `{copy_svg}`;
        const checkSvg = `{check_svg}`;
        document.getElementById('copy-npx-btn').addEventListener('click', function() {{
            navigator.clipboard.writeText(`{hidden_npx}`).then(() => {{
                this.innerHTML = checkSvg; this.style.background = "#10B981"; this.style.color = "#FFFFFF";
                setTimeout(() => {{ this.innerHTML = copySvg; this.style.background = "#E2E8F0"; this.style.color = "#475569"; }}, 2000);
            }});
        }});
        </script>
        """
        components.html(npx_html, height=70)

    with tab2:
        st.markdown("<div style='margin-top: 10px;'></div>", unsafe_allow_html=True)
        st.markdown("**1. 아래 명령어를 PowerShell에 복사하여 붙여넣으세요.**")
        
        win_cmd_clean = f"Invoke-WebRequest -Uri \"{base_external_url}/static/install-agent.ps1\" -OutFile install-agent.ps1; .\\install-agent.ps1 -BackendUrl \"{base_external_url}\" -ApiKey \"{user_api_key}\""
        visible_win = "powershell -Command \"iwr -Uri [LogMon_Server] -OutFile install-agent.ps1...\""
        
        win_html = f"""
        <style>
        #copy-win-install-btn:hover {{
            background-color: #CBD5E1 !important;
            color: #1E293B !important;
        }}
        </style>
        <div style="background-color: #F1F5F9; border: 1px solid #E2E8F0; padding: 12px 16px; border-radius: 8px; display: flex; justify-content: space-between; align-items: center; font-family: 'Courier New', monospace;">
            <span style="color: #0F172A; font-size: 14px; font-weight: bold; letter-spacing: 0.5px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; max-width: 85%;">{visible_win}</span>
            <button id="copy-win-install-btn" style="background: #E2E8F0; color: #475569; border: none; width: 32px; height: 32px; display: flex; justify-content: center; align-items: center; border-radius: 6px; cursor: pointer; transition: all 0.2s;" title="PowerShell 명령어 복사">{copy_svg}</button>
        </div>
        <script>
        const copyWinSvg = `{copy_svg}`;
        const checkWinSvg = `{check_svg}`;
        document.getElementById('copy-win-install-btn').addEventListener('click', function() {{
            navigator.clipboard.writeText(`{win_cmd_clean}`).then(() => {{
                this.innerHTML = checkWinSvg; this.style.background = "#10B981"; this.style.color = "#FFFFFF";
                setTimeout(() => {{ this.innerHTML = copyWinSvg; this.style.background = "#E2E8F0"; this.style.color = "#475569"; }}, 2000);
            }});
        }});
        </script>
        """
        components.html(win_html, height=70)

# 5. 수동 파일 업로드 섹션
st.markdown("<div style='margin-top: 40px;'></div>", unsafe_allow_html=True)

with st.container(border=True):
    st.markdown(f'''
        <div style="display: flex; align-items: center; gap: 10px; margin-bottom: 12px; margin-top: 10px;">
            <img src="data:image/png;base64,{data_b64}" class="icon-img" style="width: 28px; height: 28px;">
            <h3 style="margin: 0; font-size: 20px; font-weight: 700;">수동 파일 업로드</h3>
        </div>
    ''', unsafe_allow_html=True)

    st.markdown("에이전트를 설치할 수 없는 환경이라면 직접 로그 파일을 업로드하실 수 있습니다.")

    uploaded_file = st.file_uploader("로그 파일 선택", type=["txt", "log", "json", "md"], help="텍스트 기반 로그 파일을 업로드해주세요.", label_visibility="collapsed")

    if uploaded_file is not None:
        st.markdown("<div style='margin-top: 10px;'></div>", unsafe_allow_html=True)
        if st.button("업로드 전송", use_container_width=True):
            from frontend.utils.api_client import upload_log
            file_bytes = uploaded_file.read()
            with st.spinner("파일을 분석하고 백엔드로 전송 중입니다..."):
                success = upload_log(file_bytes, uploaded_file.name)
            if success:
                st.success("파일이 성공적으로 업로드 및 처리되었습니다!")

# 6. 에이전트 제거 가이드 섹션
st.markdown("<div style='margin-top: 40px;'></div>", unsafe_allow_html=True)

with st.container(border=True):
    st.markdown(f'''
        <div style="display: flex; align-items: center; gap: 10px; margin-bottom: 12px; margin-top: 10px;">
            <img src="data:image/png;base64,{uninstall_b64}" class="icon-img" style="width: 28px; height: 28px; mix-blend-mode: multiply;">
            <h3 style="margin: 0; font-size: 20px; font-weight: 700;">에이전트 제거 가이드</h3>
        </div>
    ''', unsafe_allow_html=True)

    st.markdown("설치된 에이전트를 시스템에서 완전히 삭제하려면 아래 가이드를 따르십시오.")
    
    tab_un_mac, tab_un_win = st.tabs(["macOS / Linux 제거", "Windows 제거"])
    
    with tab_un_mac:
        st.markdown("<div style='margin-top: 10px;'></div>", unsafe_allow_html=True)
        st.markdown("**1. 아래 제거 명령어를 복사하여 터미널에 실행하십시오.**")
        
        real_mac_cmd = f"npx @thiagomiki/logmon-cli@latest uninstall {base_external_url}"
        visible_un_mac = "npx @thiagomiki/logmon-cli@latest uninstall"
        
        un_mac_html = f"""
        <style>
        #copy-un-mac-btn:hover {{
            background-color: #CBD5E1 !important;
            color: #1E293B !important;
        }}
        </style>
        <div style="background-color: #F1F5F9; border: 1px solid #E2E8F0; padding: 12px 16px; border-radius: 8px; display: flex; justify-content: space-between; align-items: center; font-family: 'Courier New', monospace;">
            <span style="color: #0F172A; font-size: 14px; font-weight: bold; letter-spacing: 0.5px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; max-width: 85%;">{visible_un_mac}</span>
            <button id="copy-un-mac-btn" style="background: #E2E8F0; color: #475569; border: none; width: 32px; height: 32px; display: flex; justify-content: center; align-items: center; border-radius: 6px; cursor: pointer; transition: all 0.2s;" title="제거 명령어 복사">{copy_svg}</button>
        </div>
        <script>
        const copyUnMacSvg = `{copy_svg}`;
        const checkUnMacSvg = `{check_svg}`;
        document.getElementById('copy-un-mac-btn').addEventListener('click', function() {{
            navigator.clipboard.writeText(`{real_mac_cmd}`).then(() => {{
                this.innerHTML = checkUnMacSvg; this.style.background = "#10B981"; this.style.color = "#FFFFFF";
                setTimeout(() => {{ this.innerHTML = copyUnMacSvg; this.style.background = "#E2E8F0"; this.style.color = "#475569"; }}, 2000);
            }});
        }});
        </script>
        """
        components.html(un_mac_html, height=70)
        
    with tab_un_win:
        st.markdown("<div style='margin-top: 10px;'></div>", unsafe_allow_html=True)
        st.markdown("**1. 관리자 권한의 PowerShell 창에서 아래 명령어를 실행하십시오.**")
        
        real_win_cmd = f"Invoke-WebRequest -Uri {base_external_url}/static/uninstall-agent.ps1 -OutFile uninstall-agent.ps1; .\\uninstall-agent.ps1"
        visible_un_win = "powershell -Command \"iwr -Uri [LogMon_Server]/static/uninstall-agent.ps1 -OutFile uninstall-agent.ps1...\""
        
        un_win_html = f"""
        <style>
        #copy-un-win-btn:hover {{
            background-color: #CBD5E1 !important;
            color: #1E293B !important;
        }}
        </style>
        <div style="background-color: #F1F5F9; border: 1px solid #E2E8F0; padding: 12px 16px; border-radius: 8px; display: flex; justify-content: space-between; align-items: center; font-family: 'Courier New', monospace;">
            <span style="color: #0F172A; font-size: 14px; font-weight: bold; letter-spacing: 0.5px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; max-width: 85%;">{visible_un_win}</span>
            <button id="copy-un-win-btn" style="background: #E2E8F0; color: #475569; border: none; width: 32px; height: 32px; display: flex; justify-content: center; align-items: center; border-radius: 6px; cursor: pointer; transition: all 0.2s;" title="제거 명령어 복사">{copy_svg}</button>
        </div>
        <script>
        const copyUnWinSvg = `{copy_svg}`;
        const checkUnWinSvg = `{check_svg}`;
        document.getElementById('copy-un-win-btn').addEventListener('click', function() {{
            navigator.clipboard.writeText(`{real_win_cmd}`).then(() => {{
                this.innerHTML = checkUnWinSvg; this.style.background = "#10B981"; this.style.color = "#FFFFFF";
                setTimeout(() => {{ this.innerHTML = copyUnWinSvg; this.style.background = "#E2E8F0"; this.style.color = "#475569"; }}, 2000);
            }});
        }});
        </script>
        """
        components.html(un_win_html, height=70)