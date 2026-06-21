import datetime
import streamlit as st
from frontend.utils.image_helper import get_base64_image
from frontend.utils.api_client import send_chat

def render_chat_interface(is_error_state: bool, is_local: bool):
    """
    RAG 챗 인터페이스와 목 데이터 주입 패널을 렌더링합니다.
    """
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
                # 캐시 강제 비우기를 수행하여 mock_stats 주입이 즉시 반영되도록 함
                st.cache_data.clear()
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

    # 대화 기록을 렌더링할 컨테이너 생성
    chat_container = st.container()

    # 기존 대화 렌더링
    with chat_container:
        for msg in st.session_state.messages:
            avatar = user_avatar if msg["role"] == "user" else assistant_avatar
            with st.chat_message(msg["role"], avatar=avatar):
                st.markdown(msg["content"])

    # 채팅 입력창 (컨테이너 하단에 위치하도록 설정)
    with st.form("chat_form", clear_on_submit=True):
        col1, col2 = st.columns([0.85, 0.15])
        with col1:
            user_query = st.text_input("질문", placeholder="질문 내용을 입력하세요.", label_visibility="collapsed", disabled=is_error_state)
        with col2:
            submit_btn = st.form_submit_button("전송", use_container_width=True, disabled=is_error_state)

    if submit_btn and user_query:
        # 유저 메시지 화면 추가 (컨테이너 내부에 렌더링)
        st.session_state.messages.append({"role": "user", "content": user_query})
        with chat_container:
            with st.chat_message("user", avatar=user_avatar):
                st.markdown(user_query)
            
            # AI 봇 응답 (스피너) (컨테이너 내부에 렌더링)
            with st.chat_message("assistant", avatar=assistant_avatar):
                with st.spinner("과거 로그 검색 및 AI 분석 중..."):
                    ai_answer = send_chat(user_query)
                    st.markdown(ai_answer)
                    st.session_state.messages.append({"role": "assistant", "content": ai_answer})

