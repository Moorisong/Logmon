import os
import streamlit as st
from frontend.utils.api_client import BACKEND_URL
from frontend.utils.image_helper import get_base64_image
import streamlit.components.v1 as components

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

# 2. 뒤로 가기 버튼 (좌측 상단에 배치, 버튼 스타일 적용)
st.markdown('''
    <div style="margin-top: 10px; margin-bottom: 15px;">
        <a href="/" target="_self" style="text-decoration: none;">
            <div class="back-btn" style="display: inline-block;">
                대시보드로 돌아가기
            </div>
        </a>
    </div>
''', unsafe_allow_html=True)

# 3. 로고몬 아이콘 + 안내 문구 결합 배치
st.markdown(f'''
    <div style="display: flex; align-items: center; gap: 12px; margin-top: 15px; margin-bottom: 20px;">
        <img src="data:image/png;base64,{logo_b64}" style="width: 36px; height: 36px; mix-blend-mode: multiply;">
        <span style="font-size: 16px; font-weight: 600; color: #1E293B; line-height: 36px;">
            터미널 환경에 맞게 아래 스크립트를 복사하여 실행하시면 LogMon 에이전트가 자동 설치됩니다.
        </span>
    </div>
''', unsafe_allow_html=True)

# 4. 설치 안내 콘텐츠 (자바스크립트 동적 주소 추출 마법 컴포넌트)
with st.container(border=True):
    tab1, tab2 = st.tabs(["macOS / Linux", "Windows"])

    # 자바스크립트가 브라우저 주소창의 IP를 그대로 훔쳐와서 버튼을 만들어주는 템플릿
    universal_html_template = """
        <div style="font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; margin-bottom: 15px;">
            <code id="cmd-text" style="display:block; padding: 12px; background: #0F172A; color: #38BDF8; border-radius: 6px; font-size: 14px; word-break: break-all;">
                주소를 계산 중입니다...
            </code>
            <button id="copy-btn" style="
                background: linear-gradient(135deg, #3B82F6, #2563EB); 
                color: white; border: none; padding: 10px 18px; margin-top: 10px;
                border-radius: 6px; cursor: pointer; font-size: 14px; font-weight: 600;
                box-shadow: 0 4px 6px -1px rgba(0,0,0,0.1); transition: all 0.2s;
            ">
                📋 명령어 복사하기
            </button>
        </div>
        <script>
            // 브라우저 주소창에서 현재 도메인/IP 추출 (예: 125.190.25.48:3007 또는 localhost:3007)
            const currentHost = window.location.host;
            let baseExternalUrl = "";
            
            if (currentHost.includes(":")) {
                // 포트가 있으면 (3007) -> 백엔드 외부 포트인 3008로 변경
                baseExternalUrl = "http://" + currentHost.split(":")[0] + ":3008";
            } else {
                // 도메인이면 (/api 구조로 변경)
                baseExternalUrl = "http://" + currentHost + "/api";
            }

            // OS 타입에 따라 명령어 생성
            const isWin = "IS_WINDOWS" === "true";
            const finalCmd = isWin 
                ? `Invoke-WebRequest -Uri ${baseExternalUrl}/api/logmon/static/install-agent.ps1 -OutFile install-agent.ps1; .\\\\install-agent.ps1`
                : `curl -sL ${baseExternalUrl}/api/logmon/static/install-agent.sh | bash`;

            const textEl = document.getElementById('cmd-text');
            const btn = document.getElementById('copy-btn');
            
            textEl.innerText = finalCmd;

            btn.addEventListener('click', () => {
                navigator.clipboard.writeText(finalCmd).then(() => {
                    const origText = btn.innerHTML;
                    btn.innerHTML = "복사 완료! ✓";
                    btn.style.background = "linear-gradient(135deg, #10B981, #059669)";
                    setTimeout(() => {
                        btn.innerHTML = origText;
                        btn.style.background = "linear-gradient(135deg, #3B82F6, #2563EB)";
                    }, 2000);
                });
            });
        </script>
    """

    with tab1:
        st.markdown("<div style='margin-top: 10px;'></div>", unsafe_allow_html=True)
        st.markdown("**1. 아래 명령어를 터미널에 복사하여 붙여넣으세요.**")
        components.html(universal_html_template.replace("IS_WINDOWS", "false"), height=130)

    with tab2:
        st.markdown("<div style='margin-top: 10px;'></div>", unsafe_allow_html=True)
        st.markdown("**1. 아래 명령어를 PowerShell에 복사하여 붙여넣으세요.**")
        components.html(universal_html_template.replace("IS_WINDOWS", "true"), height=130)

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

uninstall_b64 = get_base64_image("frontend/assets/icons/icon_uninstall.png")

with st.container(border=True):
    st.markdown(f'''
        <div style="display: flex; align-items: center; gap: 10px; margin-bottom: 12px; margin-top: 10px;">
            <img src="data:image/png;base64,{uninstall_b64}" class="icon-img" style="width: 28px; height: 28px; mix-blend-mode: multiply;">
            <h3 style="margin: 0; font-size: 20px; font-weight: 700;">에이전트 제거 가이드</h3>
        </div>
    ''', unsafe_allow_html=True)

    st.markdown("설치된 에이전트를 시스템에서 완전히 삭제하려면 아래 가이드를 따르십시오.")
    
    tab_un_mac, tab_un_win = st.tabs(["macOS / Linux 제거", "Windows 제거"])
    
    # 제거 주소를 브라우저 자바스크립트로 처리하는 템플릿
    uninstall_html_template = """
        <button id="copy-un-btn" style="
            background: linear-gradient(135deg, #3B82F6, #2563EB); 
            color: white; border: none; padding: 10px 18px; 
            border-radius: 6px; cursor: pointer; font-size: 14px; font-weight: 600;
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
            box-shadow: 0 4px 6px -1px rgba(0,0,0,0.1); transition: all 0.2s;
        ">
            📋 제거 명령어 복사하기
        </button>
        <script>
            const currentHost = window.location.host;
            let baseExternalUrl = currentHost.includes(":") 
                ? "http://" + currentHost.split(":")[0] + ":3008" 
                : "http://" + currentHost + "/api";
            
            const isWin = "IS_WINDOWS" === "true";
            const unCmd = isWin
                ? `Invoke-WebRequest -Uri ${baseExternalUrl}/api/logmon/static/uninstall-agent.ps1 -OutFile uninstall-agent.ps1; .\\\\uninstall-agent.ps1`
                : `curl -sL ${baseExternalUrl}/api/logmon/static/uninstall-agent.sh | bash`;

            const btn = document.getElementById('copy-un-btn');
            btn.addEventListener('click', () => {
                navigator.clipboard.writeText(unCmd).then(() => {
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

    with tab_un_mac:
        st.markdown("<div style='margin-top: 10px;'></div>", unsafe_allow_html=True)
        st.markdown("**1. 터미널 실행창에 보이는 마스킹된 주소 대신, 복사 버튼을 클릭하여 실행하십시오.**")
        st.code("curl -sL ****** | bash", language="bash")
        components.html(uninstall_html_template.replace("IS_WINDOWS", "false"), height=60)
        
    with tab_un_win:
        st.markdown("<div style='margin-top: 10px;'></div>", unsafe_allow_html=True)
        st.markdown("**1. 관리자 권한의 PowerShell 창에서 복사 버튼을 클릭하여 실행하십시오.**")
        st.code("Invoke-WebRequest -Uri ****** -OutFile uninstall-agent.ps1; .\\uninstall-agent.ps1", language="powershell")
        components.html(uninstall_html_template.replace("IS_WINDOWS", "true"), height=60)