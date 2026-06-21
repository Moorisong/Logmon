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
    is_agent_installed = stats.get("is_agent_installed", False)

    # 에이전트 설치 상태 변경 감지하여 전체 화면(챗봇 등) 새로고침
    prev_installed = st.session_state.get("is_agent_installed", None)
    if prev_installed is not None and prev_installed != is_agent_installed:
        st.session_state["is_agent_installed"] = is_agent_installed
        st.rerun()
    st.session_state["is_agent_installed"] = is_agent_installed

    # 3. 헤더 및 에이전트 설치 버튼 통합 렌더링 (동기화 영역과의 겹침 및 간섭 해결)
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
        st.markdown("<div style='margin-top: 10px;'></div>", unsafe_allow_html=True) # 로고 타이틀과 수직 정렬을 맞추기 위한 상단 패딩
        
        if is_agent_installed:
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

    # 에러 상태 여부 판단 (백엔드가 오프라인이고, 세션에 mock_stats가 없는 경우)
    is_error_state = not stats.get("is_online", True) and "mock_stats" not in st.session_state
    st.session_state["is_error_state"] = is_error_state

    if not is_error_state:
        st.markdown("<div style='margin-top: 15px;'></div>", unsafe_allow_html=True)
        st.markdown("<div style='margin-bottom: 30px;'>로컬 개발 PC 환경 트렌드를 파악하고 과거 이력에 대해 질문하세요.</div>", 
        unsafe_allow_html=True
        )

    if "mock_stats" in st.session_state:
        for k, v in st.session_state["mock_stats"].items():
            stats[k] = v

    if is_error_state:
        # 에러 상태일 때 오직 에러 알림창(stAlert)만 또렷하게 남기고 페이지 전체의 모든 요소를 블러/비활성화 처리
        st.markdown("""
            <style>
            /* 1. 기본 스타일 트랜지션 제공 */
            .stApp, .glass-card, [data-testid="stForm"], .install-btn, 
            button, h1, h2, h3, hr, .stMarkdown, .stPlotlyChart {
                transition: all 0.3s ease;
            }
            
            /* 2. 에러 알림창을 제외한 모든 핵심 블록과 텍스트를 흐리게 처리 */
            [data-testid="stHeader"], 
            h1:not([class*="welcome"]), 
            .install-btn, 
            .glass-card, 
            .stPlotlyChart, 
            [data-testid="stForm"], 
            [data-testid="stChatMessage"], 
            .custom-progress-container, 
            h3, 
            h2, 
            hr, 
            .stDivider, 
            [data-testid="stText"],
            .stMarkdown:not(:has(.welcome-header-container)):not(:has(.stAlert)):not(:has([data-testid="stAlert"])),
            button {
                opacity: 0.3 !important;
                filter: grayscale(90%) blur(2px) !important;
                pointer-events: none !important;
                user-select: none !important;
            }
            
            /* 3. 에러 알림창(stAlert) 및 Welcome 헤더 타이틀만 원본 선명도로 강조 */
            div[data-testid="element-container"]:has(.stAlert),
            div[data-testid="element-container"]:has([data-testid="stAlert"]),
            .stAlert,
            [data-testid="stAlert"],
            [data-testid="stAlert"] *,
            div[data-testid="column"]:first-child,
            div[data-testid="column"]:first-child * {
                opacity: 1 !important;
                filter: none !important;
                pointer-events: auto !important;
                user-select: auto !important;
            }

            /* Welcome 헤더 영역은 강제로 모든 필터를 해제하고 선명하게 고정 */
            .welcome-header-container,
            .welcome-header-container *,
            .welcome-header-title,
            .welcome-header-title *,
            div[data-testid="element-container"]:has(.welcome-header-container),
            div[data-testid="element-container"]:has(.welcome-header-container) *,
            div[data-testid="column"]:has(.welcome-header-container),
            div[data-testid="column"]:has(.welcome-header-container) *,
            div[data-testid="column"]:has(.welcome-header-title),
            div[data-testid="column"]:has(.welcome-header-title) * {
                opacity: 1 !important;
                filter: none !important;
                pointer-events: auto !important;
                user-select: auto !important;
            }
            </style>
        """, unsafe_allow_html=True)

    # 메인 대시보드 렌더링 (카드, 게이지바, 트렌드 차트)
    if is_agent_installed:
        render_dashboard(stats)
    else:
        render_empty_state()

# 라이브 대시보드 프래그먼트 호출
live_dashboard_fragment()

# 에이전트가 설치된 경우에만 RAG 챗 인터페이스 렌더링
if st.session_state.get("is_agent_installed", False):
    st.divider()
    is_err = st.session_state.get("is_error_state", False)
    render_chat_interface(is_err, is_local)
