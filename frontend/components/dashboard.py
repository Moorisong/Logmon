import datetime
import streamlit as st
from frontend.utils.image_helper import get_base64_image
from frontend.utils.chart_renderer import render_trend_chart

def format_sync_time(last_sync_time_str: str) -> str:
    if not last_sync_time_str:
        return "데이터 없음"
    try:
        last_dt = datetime.datetime.strptime(last_sync_time_str, "%Y-%m-%d %H:%M:%S")
        now = datetime.datetime.now()
        diff = int((now - last_dt).total_seconds())
        if diff < 60:
            return "방금 전 (동기화 중 🟢)"
        elif diff < 3600:
            return f"{diff // 60}분 전 (정상)"
        elif diff < 86400:
            return f"{diff // 3600}시간 전"
        else:
            return f"{diff // 86400}일 전"
    except Exception:
        return "알 수 없음"

def render_dashboard(stats: dict):
    """
    메인 대시보드의 스코어 카드 및 트렌드 차트를 렌더링합니다.
    """
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

    # 데이터 저장 공간 사용량
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

    st.markdown("<div style='margin-top: 40px;'></div>", unsafe_allow_html=True)
    st.subheader("최근 7일 수집 트렌드")
    render_trend_chart(stats.get("trend_7d", []))

def render_empty_state():
    """
    에이전트가 설치되지 않았을 때 표시되는 빈 화면 디자인입니다.
    """
    box_b64 = get_base64_image("frontend/assets/icons/icon_logo.png")
    st.markdown(f"""
    <div style="display: flex; flex-direction: column; align-items: center; justify-content: center; padding: 100px 20px; background: rgba(255, 255, 255, 0.6); border: 1px dashed rgba(148, 163, 184, 0.4); border-radius: 24px; margin-top: 30px; margin-bottom: 30px; backdrop-filter: blur(12px); box-shadow: 0 10px 40px rgba(0, 0, 0, 0.03);">
        <img src="data:image/png;base64,{box_b64}" style="width: 90px; height: 90px; margin-bottom: 25px; filter: grayscale(40%) opacity(80%);">
        <h2 style="color: #1E293B; font-size: 32px; margin-bottom: 15px; font-weight: 700; letter-spacing: -0.5px;">에이전트가 연결되지 않았어요</h2>
        <p style="color: #64748B; font-size: 17px; margin-bottom: 40px; text-align: center; max-width: 550px; line-height: 1.6;">
            LogMon은 로컬 IDE(Cursor/Antigravity 등)의 로그를<br>
            실시간으로 수집하고 분석해주는 모니터링 대시보드입니다.<br><br>
            지금 에이전트를 설치하여 개발 환경의 로그와 연동 상태를<br>
            실시간으로 확인해보세요!
        </p>
        <a href="/install?mode=install" target="_self" style="text-decoration: none;">
            <div style="background: linear-gradient(135deg, #3B82F6 0%, #1D4ED8 100%); color: white; padding: 16px 36px; border-radius: 16px; font-size: 18px; font-weight: 700; box-shadow: 0 8px 25px rgba(59, 130, 246, 0.4); transition: all 0.3s cubic-bezier(0.4, 0, 0.2, 1); display: inline-block;">
                ✨ 에이전트 설치하고 시작하기
            </div>
        </a>
    </div>
    <style>
    /* 엠프티 스테이트 버튼 호버 이펙트 */
    a > div:hover {{
        transform: translateY(-3px) scale(1.03);
        box-shadow: 0 12px 30px rgba(59, 130, 246, 0.5);
    }}
    </style>
    """, unsafe_allow_html=True)
