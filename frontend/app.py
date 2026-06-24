import os
from dotenv import load_dotenv

load_dotenv()

import streamlit as st
from frontend.utils.api_client import fetch_stats, BACKEND_URL
from frontend.utils.image_helper import get_base64_image
from frontend.components.dashboard import render_dashboard, render_empty_state
from frontend.components.chat import render_chat_interface

is_local = ("localhost" in BACKEND_URL or "127.0.0.1" in BACKEND_URL) and "logmon-backend" not in BACKEND_URL and "haroo.site" not in BACKEND_URL

# 1. 페이지 셋업 및 CSS 주입
icon_path = os.path.join(os.path.dirname(__file__), "assets", "icons", "icon_logo.png")
st.set_page_config(page_title="LogMon Dashboard", page_icon=icon_path, layout="wide", initial_sidebar_state="collapsed")

def load_css():
    css_path = os.path.join(os.path.dirname(__file__), "assets", "style.css")
    if os.path.exists(css_path):
        with open(css_path, "r") as f:
            st.markdown(f"<style>{f.read()}</style>", unsafe_allow_html=True)

load_css()

# 2. 메인 대시보드 스코어 카드 데이터 패칭 및 헤더 렌더링 (Live Sync)
if hasattr(st, "fragment"):
    fragment_decorator = st.fragment(run_every="2s")
elif hasattr(st, "experimental_fragment"):
    fragment_decorator = st.experimental_fragment(run_every="2s")
else:
    fragment_decorator = lambda f: f

@fragment_decorator
def live_dashboard_fragment():
    stats = fetch_stats()
    
    # 서버 자체가 아예 응답을 안 할 때만 에러 상태로 처리
    is_server_down = (stats is None)
    st.session_state["is_server_down"] = is_server_down
    
    # 에이전트 설치 및 5분 이내 통신 여부
    is_agent_installed = stats.get("is_agent_installed", False) if stats else False
    is_agent_online = stats.get("is_online", False) if stats else False

    # 3. 헤더 및 에이전트 설치 버튼 통합 렌더링
    col_logo_title, col_install_btn = st.columns([0.8, 0.2])

    with col_logo_title:
        logo_b64 = get_base64_image("frontend/assets/icons/icon_logo.png")
        st.markdown(f'''
            <div class="welcome-header-container" style="display: flex; align-items: center; gap: 15px; margin-bottom: 0px;">
                <h1 class="welcome-header-title" style="margin: 0;">Welcome to LogMon</h1>
                <img src="data:image/png;base64,{logo_b64}" class="header-icon" style="width: 50px; height: 50px;">
            </div>
        ''', unsafe_allow_html=True)

    with col_install_btn:
        st.markdown("<div style='margin-top: 10px;'></div>", unsafe_allow_html=True)
        # 에이전트가 설치되어 있고 살아있을 때만 '제거하기' 버튼 표시
        if is_agent_installed and is_agent_online:
            btn_text = "에이전트 제거하기"
            btn_link = "/install?mode=uninstall"
            st.markdown(
                f'''<a href="{btn_link}" target="_self" style="text-decoration: none;">
                     <div class="install-btn">
                        {btn_text}
                    </div>
                </a>''', 
                unsafe_allow_html=True
            )

    # 서버가 죽었을 때 (API 통신 불가)
    if is_server_down:
        st.markdown(
            '<div class="stAlert" data-testid="stAlert" style="background-color: rgba(255, 75, 75, 0.1); border: 1px solid rgba(255, 75, 75, 0.2); border-radius: 8px; padding: 12px 16px; margin-top: 15px; margin-bottom: 20px;">'
            '<div style="color: #FF4B4B; line-height: 1.45; font-size: 14px; font-weight: 500;">'
            '💡 서버가 일시적으로 오프라인 상태예요.<br/>'
            '<div style="margin-left: 20px; margin-top: 4px; font-size: 13px; font-weight: normal; opacity: 0.9;">잠시 점검 중이거나 쉬고 있는 것 같으니, 조금만 기다렸다가 다시 찾아와 주세요!</div>'
            '</div>'
            '</div>',
            unsafe_allow_html=True
        )
        st.markdown("""
            <style>
            .stApp, .glass-card, [data-testid="stForm"], .install-btn, button, h1, h2, h3, hr, .stMarkdown, .stPlotlyChart { transition: all 0.3s ease; }
            [data-testid="stHeader"], h1:not([class*="welcome"]), .install-btn, .glass-card, .stPlotlyChart, [data-testid="stForm"], [data-testid="stChatMessage"], h3, h2, hr, .stDivider, [data-testid="stText"], button {
                opacity: 0.3 !important; filter: grayscale(90%) blur(2px) !important; pointer-events: none !important; user-select: none !important;
            }
            .welcome-header-container, .welcome-header-title { opacity: 1 !important; filter: none !important; }
            </style>
        """, unsafe_allow_html=True)
        return

    # 정상 상태 UI 렌더링
    st.markdown("<div style='margin-top: 15px;'></div>", unsafe_allow_html=True)
    st.markdown("<div style='margin-bottom: 30px;'>로컬 개발 PC 환경 트렌드를 파악하고 과거 이력에 대해 질문하세요.</div>", 
    unsafe_allow_html=True
    )

    # 핵심 로직 변경: 에이전트가 설치되어 있더라도 오프라인이면 구현해두신 "empty_state" 렌더링
    if is_agent_installed and is_agent_online:
        render_dashboard(stats)
        st.session_state["show_chat"] = True
    else:
        render_empty_state()
        st.session_state["show_chat"] = False

# 라이브 대시보드 프래그먼트 호출
live_dashboard_fragment()

# 에이전트가 정상적으로 켜져 있을 때만 챗 인터페이스 렌더링
if st.session_state.get("show_chat", False) and not st.session_state.get("is_server_down", False):
    st.divider()
    render_chat_interface(False, is_local)