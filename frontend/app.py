import os
from dotenv import load_dotenv

load_dotenv()

import streamlit as st
from frontend.utils.api_client import fetch_stats, send_chat, BACKEND_URL, LOGMON_API_KEY
from frontend.utils.chart_renderer import render_trend_chart

import base64

# 로컬 개발 환경 여부 판단 (localhost 또는 127.0.0.1이 백엔드 URL에 포함되거나 LOGMON_ENV가 local인 경우)
is_local = "localhost" in BACKEND_URL or "127.0.0.1" in BACKEND_URL or os.getenv("LOGMON_ENV", "local") == "local"


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


# Welcome to LogMon 헤더를 컬럼 외부 최상단에 배치하여 CSS 블러 간섭을 원천 차단
logo_b64 = get_base64_image("frontend/assets/icons/icon_logo.png")
st.markdown(f'''
    <div class="welcome-header-container" style="display: flex; align-items: center; gap: 15px; margin-bottom: 0px;">
        <h1 class="welcome-header-title" style="margin: 0;">Welcome to LogMon</h1>
        <img src="data:image/png;base64,{logo_b64}" class="header-icon" style="width: 50px; height: 50px;">
    </div>
''', unsafe_allow_html=True)

# 3. 메인 대시보드 스코어 카드 영역 (웰컴 타이틀 바로 아래에서 에러가 렌더링되도록 시점 배치)
stats = fetch_stats()

# 에러 상태 여부 판단 (기본 stats 조회에 실패했거나 total_lines가 0이면서 세션에 mock_stats가 없는 경우)
is_error_state = "mock_stats" not in st.session_state

if not is_error_state:
    st.markdown("<div style='margin-top: 5px;'></div>", unsafe_allow_html=True)
    st.markdown("로컬 개발 PC의 생산성과 오류 발생 트렌드를 시각화하고 과거 이력에 대해 질문하세요.")

st.markdown("<div style='margin-bottom: 0px;'></div>", unsafe_allow_html=True)

col_title, col_btn = st.columns([0.8, 0.2])
with col_btn:
    st.markdown(
        f'''<a href="/install" target="_self" style="text-decoration: none;">
            <div class="install-btn">
                에이전트 설치하기
            </div>
        </a>''', 
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
fill_width = min(usage_ratio * 100, 100.0)
fill_color = "linear-gradient(90deg, #FBBF24, #F59E0B)" if usage_ratio >= 0.9 else "linear-gradient(90deg, #A3C1AD, #8A9A90)"

st.markdown(f"""
<div class="custom-progress-container" style="margin-bottom: 4px; width: 100%;">
    <div style="display: flex; justify-content: space-between; font-size: 14px; color: #8A9A90; margin-bottom: 6px; font-weight: 500;">
        <span>현재 저장 공간 사용량</span>
        <span>{current_db_mb:.1f}MB / {max_db_mb:.1f}MB ({usage_ratio*100:.1f}%)</span>
    </div>
    <div style="background: rgba(255, 255, 255, 0.3); border: 1px solid rgba(255, 255, 255, 0.5); height: 12px; border-radius: 6px; overflow: hidden; backdrop-filter: blur(12px); width: 100%;">
        <div style="width: {fill_width}%; height: 100%; background: {fill_color}; border-radius: 6px; transition: width 0.5s ease-in-out;"></div>
    </div>
</div>
""", unsafe_allow_html=True)


if usage_ratio >= 0.9:
    alert_b64 = get_base64_image("frontend/assets/icons/icon_alert.png")
    st.markdown(f"""
        <div style="color: #DC2626; display: flex; align-items: center; font-weight: normal; margin-top: 2px; margin-bottom: 15px; font-size: 12px;">
            <img src="data:image/png;base64,{alert_b64}" class="icon-img" style="margin-right: 6px; width: 14px; height: 14px; vertical-align: middle;"> 용량 한도 초과(또는 임박)로 인해 오래된 로그부터 자동 정리 중입니다.
        </div>
    """, unsafe_allow_html=True)



st.subheader("최근 7일 수집 트렌드")
render_trend_chart(stats.get("trend_7d", []))
st.divider()

# 대시보드 비활성화 영역 래핑 끝
st.markdown('</div>', unsafe_allow_html=True)

# 4. RAG 챗 인터페이스
col_chat_title, col_chat_mock = st.columns([0.75, 0.25])
with col_chat_title:
    st.markdown(f"""
        <div style="display: flex; align-items: center; margin-top: 20px; margin-bottom: 10px;">
            <h3 style="margin: 0;">Logmon AI 어시스턴트</h3>
        </div>
    """, unsafe_allow_html=True)
with col_chat_mock:
    if is_local:
        st.markdown("<div style='margin-top: 15px;'></div>", unsafe_allow_html=True)
        if st.button("🔌 목 데이터 주입", key="inject_mock_btn", use_container_width=True):
            # 대시보드 전체(스코어카드 + 차트) 목 데이터 정의
            st.session_state["mock_stats"] = {
                "uptime_days": 5,
                "total_lines": 15420,
                "total_bytes": 1024 * 1024 * 1.25,  # 1.25 MB
                "last_sync_time": (datetime.datetime.now() - datetime.timedelta(seconds=45)).strftime("%Y-%m-%d %H:%M:%S"),
                "current_db_mb": 462.5,
                "max_db_mb": 500.0,

                "trend_7d": [
                    {"date": "2026-06-15", "count": 12},
                    {"date": "2026-06-16", "count": 25},
                    {"date": "2026-06-17", "count": 18},
                    {"date": "2026-06-18", "count": 42},
                    {"date": "2026-06-19", "count": 30},
                    {"date": "2026-06-20", "count": 55},
                    {"date": "2026-06-21", "count": 22}
                ]
            }
            st.session_state["messages"] = [
                {"role": "assistant", "content": "안녕하세요! Logmon AI 어시스턴트예요. 최근 발생한 로그에 대해 편하게 질문해 보세요!"},
                {"role": "user", "content": "최근 24시간 동안 발생한 가장 심각한 에러는 무엇인가요?"},
                {"role": "assistant", "content": "오전 10시 45분쯤 `auth_service.py`에서 발생한 `DatabaseConnectionError`가 가장 치명적이에요. 총 5번이나 반복해서 일어났네요."},
                {"role": "user", "content": "그 에러의 상세 원인과 해결 방법을 제안해줄 수 있어?"},
                {"role": "assistant", "content": """데이터베이스 연결 풀(Connection Pool)이 꽉 차서 새로운 연결 요청이 대기하다가 시간 초과(타임아웃)된 것으로 보여요.

이 문제를 해결하려면 아래 조치들을 해보시는 걸 권해 드려요:

1. **설정값 늘려주기**:
   `database.py`나 환경 설정 파일에서 풀 크기와 관련된 설정들을 조금 늘려주는 것이 좋아요.
   ```python
   # 예시 설정 변경
   engine = create_engine(
       DATABASE_URL,
       pool_size=20,       # 기본 풀 크기를 5에서 20으로 늘려요
       max_overflow=10,    # 순간적으로 요청이 몰릴 때를 대비해 초과분 10을 허용해요
       pool_timeout=30     # 대기 시간 한도를 30초로 설정해요
   )
   ```

2. **사용한 연결 잘 닫기**:
   데이터베이스 작업을 마치고 나서 연결이 제대로 닫히는지(close) 확인해야 해요. `with` 구문이나 `try...finally`를 쓰면 안전해요.
   ```python
   # SQLAlchemy 세션을 안전하게 닫는 코드 예시에요
   from contextlib import contextmanager

   @contextmanager
   def session_scope():
       session = Session()
       try:
           yield session
           session.commit()
       except Exception:
           session.rollback()
           raise
       finally:
           session.close() # 작업이 끝나면 꼭 리소스를 돌려줘요
   ```

3. **연결 주기 리사이클(Recycle) 설정**:
   오래된 연결이 끊어지는 걸 막기 위해 SQLAlchemy의 `pool_recycle` 시간을 데이터베이스 자체의 연결 한도 시간보다 짧게 잡아주는 것이 안전해요."""}
            ]

            st.rerun()



if "messages" not in st.session_state:
    st.session_state.messages = [{"role": "assistant", "content": "오늘 하신 작업에 대해 궁금한 점이 있다면 무엇이든 물어보세요!"}]

# 대화 아이콘 로드 (Base64)
user_avatar_b64 = get_base64_image("frontend/assets/icons/icon_user.png")
bot_avatar_b64 = get_base64_image("frontend/assets/icons/icon_logo.png")
user_avatar = f"data:image/png;base64,{user_avatar_b64}"
assistant_avatar = f"data:image/png;base64,{bot_avatar_b64}"

# 기존 대화 렌더링
for msg in st.session_state.messages:
    avatar = user_avatar if msg["role"] == "user" else assistant_avatar
    with st.chat_message(msg["role"], avatar=avatar):
        st.markdown(msg["content"])

# 채팅 입력창
with st.form("chat_form", clear_on_submit=True):
    col1, col2 = st.columns([0.85, 0.15])
    with col1:
        user_query = st.text_input("질문", placeholder="질문 내용을 입력하세요.", label_visibility="collapsed", disabled=is_error_state)
    with col2:
        submit_btn = st.form_submit_button("전송", use_container_width=True, disabled=is_error_state)

if submit_btn and user_query:
    # 유저 메시지 화면 추가
    st.session_state.messages.append({"role": "user", "content": user_query})
    with st.chat_message("user", avatar=user_avatar):
        st.markdown(user_query)
        
    # AI 봇 응답 (스피너)
    with st.chat_message("assistant", avatar=assistant_avatar):
        with st.spinner("과거 로그 검색 및 AI 분석 중..."):
            ai_answer = send_chat(user_query)
            st.markdown(ai_answer)
            st.session_state.messages.append({"role": "assistant", "content": ai_answer})

