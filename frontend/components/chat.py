import datetime
import streamlit as st
from frontend.utils.image_helper import get_base64_image
from frontend.utils.api_client import send_chat

def render_chat_interface(is_error_state: bool, is_local: bool):
    """
    RAG 챗 인터페이스를 렌더링합니다.
    """
    st.markdown(f"""
        <div style="display: flex; align-items: center; margin-top: 20px; margin-bottom: 10px;">
            <h3 style="margin: 0;">Logmon AI 어시스턴트</h3>
        </div>
    """, unsafe_allow_html=True)

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

    # 어시스턴트가 응답 대기 중인지 상태 체크
    is_waiting = st.session_state.get("waiting_for_reply", False)
    disabled_state = is_error_state or is_waiting

    # 채팅 입력창 (컨테이너 하단에 위치하도록 설정)
    with st.form("chat_form", clear_on_submit=True):
        col1, col2 = st.columns([0.85, 0.15])
        with col1:
            placeholder_text = "어시스턴트의 답변이 끝난 후 입력할 수 있습니다." if is_waiting else "질문 내용을 입력하세요."
            user_query = st.text_input("질문", placeholder=placeholder_text, label_visibility="collapsed", disabled=disabled_state)
        with col2:
            submit_btn = st.form_submit_button("전송", use_container_width=True, disabled=disabled_state)

    if submit_btn and user_query:
        # 유저 메시지 화면 추가 (컨테이너 내부에 렌더링)
        st.session_state.messages.append({"role": "user", "content": user_query})
        st.session_state["waiting_for_reply"] = True
        st.rerun()

    if st.session_state.get("waiting_for_reply", False):
        with chat_container:
            # AI 봇 응답 (스피너) (컨테이너 내부에 렌더링)
            with st.chat_message("assistant", avatar=assistant_avatar):
                with st.spinner("과거 로그 검색 및 AI 분석 중..."):
                    # 마지막으로 추가한 유저 쿼리를 백엔드로 전송
                    last_user_query = ""
                    for msg in reversed(st.session_state.messages):
                        if msg["role"] == "user":
                            last_user_query = msg["content"]
                            break
                    ai_answer = send_chat(last_user_query)
                    st.markdown(ai_answer)
                    st.session_state.messages.append({"role": "assistant", "content": ai_answer})
        st.session_state["waiting_for_reply"] = False
        st.rerun()

