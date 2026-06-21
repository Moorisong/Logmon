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

# 4. 설치 안내 콘텐츠 상자 (★NPM 공식 등록 패키지 연동★)
with st.container(border=True):
    tab1, tab2 = st.tabs(["macOS / Linux", "Windows"])

    with tab1:
        st.markdown("<div style='margin-top: 10px;'></div>", unsafe_allow_html=True)
        st.markdown("**1. 아래 명령어를 전체 복사하여 터미널에 붙여넣고 엔터를 치세요.**")
        
        # 유저 화면 상자에는 명품 오픈소스 감성의 세상 깔끔한 표준 명령어 노출
        visible_npx = "npx logmon-cli"
        
        # [★정식 NPM 연동 완료] 유저가 복사 버튼을 누르면 내부적으로 API Key와 백엔드 주소를 주입하고,
        # NPM 마켓에 방금 등록 성공한 진짜 형님의 공식 패키지(@thiagomiki/logmon-cli)를 원격 호출하여 다이렉트로 가동합니다!
        hidden_npx = f"BACKEND_URL=\"{base_external_url}\" API_KEY=\"{user_api_key}\" npx @thiagomiki/logmon-cli"
        
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
        st.markdown("**1. 터미널 실행창에 보이는 마스킹된 주소 대신, 복사 버튼을 클릭하여 실행하십시오.**")
        st.code("curl -sL ****** | bash", language="bash")
        
        real_mac_cmd = f"curl -sL {base_external_url}/static/uninstall-agent.sh | bash"
        
        mac_html_template = """
            <button id="copy-mac-btn" style="
                background: linear-gradient(135deg, #3B82F6, #2563EB); 
                color: white; border: none; padding: 10px 18px; 
                border-radius: 6px; cursor: pointer; font-size: 14px; font-weight: 600;
                font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
                box-shadow: 0 4px 6px -1px rgba(0,0,0,0.1); transition: all 0.2s;
            ">
                📋 제거 명령어 복사하기
            </button>
            <script>
            const btn = document.getElementById('copy-mac-btn');
            btn.addEventListener('click', () => {
                navigator.clipboard.writeText("REAL_MAC_CMD").then(() => {
                    const origText = btn.innerHTML;
                    btn.innerHTML = "제거 명령어 복사 완료! ✓";
                    btn.style.background = "linear-gradient(135deg, #10B981, #059669)";
                    setTimeout(() => {
                        btn.innerHTML = origText;
                        btn.style.background = "linear-gradient(135deg, #3B82F6, #2563EB)";
                    }, 2000);
                });
            });
            </script>
        """
        components.html(mac_html_template.replace("REAL_MAC_CMD", real_mac_cmd), height=60)
        
    with tab_un_win:
        st.markdown("<div style='margin-top: 10px;'></div>", unsafe_allow_html=True)
        st.markdown("**1. 관리자 권한의 PowerShell 창에서 복사 버튼을 클릭하여 실행하십시오.**")
        st.code("Invoke-WebRequest -Uri ****** -OutFile uninstall-agent.ps1; .\\uninstall-agent.ps1", language="powershell")
        
        real_win_cmd = f"Invoke-WebRequest -Uri {base_external_url}/static/uninstall-agent.ps1 -OutFile uninstall-agent.ps1; .\\uninstall-agent.ps1"
        
        win_html_template = """
            <button id="copy-win-btn" style="
                background: linear-gradient(135deg, #3B82F6, #2563EB); 
                color: white; border: none; padding: 10px 18px; 
                border-radius: 6px; cursor: pointer; font-size: 14px; font-weight: 600;
                font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
                box-shadow: 0 4px 6px -1px rgba(0,0,0,0.1); transition: all 0.2s;
            ">
                📋 제거 명령어 복사하기
            </button>
            <script>
            const btn = document.getElementById('copy-win-btn');
            btn.addEventListener('click', () => {
                navigator.clipboard.writeText("REAL_WIN_CMD").then(() => {
                    const origText = btn.innerHTML;
                    btn.innerHTML = "제거 명령어 복사 완료! ✓";
                    btn.style.background = "linear-gradient(135deg, #10B981, #059669)";
                    setTimeout(() => {
                        btn.innerHTML = origText;
                        btn.style.background = "linear-gradient(135deg, #3B82F6, #2563EB)";
                    }, 2000);
                });
            });
            </script>
        """
        components.html(win_html_template.replace("REAL_WIN_CMD", real_win_cmd), height=60)