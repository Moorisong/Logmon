import plotly.graph_objects as go
import streamlit as st
from typing import List, Dict, Any

def render_trend_chart(trend_data: List[Dict[str, Any]]):
    """
    백엔드에서 넘겨받은 최근 7일 트렌드 배열을 파스텔 톤 차트로 렌더링합니다.
    """
    if not trend_data:
        st.info("시각화할 데이터가 충분하지 않습니다.")
        return

    dates = [item["date"][-5:] for item in trend_data]  # MM-DD 형식 축약
    counts = [item["count"] for item in trend_data]

    fig = go.Figure()
    
    # 바 차트 (세이지 그린 뉴모피즘 스타일)
    fig.add_trace(go.Bar(
        x=dates,
        y=counts,
        marker_color="#A3C1AD",
        marker_line_color="#8A9A90",
        marker_line_width=1.5,
        opacity=0.8,
        name="Logs"
    ))
    
    # 둥근 모서리 및 투명 배경
    fig.update_layout(
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(0,0,0,0)",
        margin=dict(l=20, r=20, t=30, b=20),
        xaxis=dict(
            showgrid=False,
            zeroline=False,
            color="#8A9A90"
        ),
        yaxis=dict(
            showgrid=True,
            gridcolor="#E2ECE5",
            zeroline=False,
            color="#8A9A90"
        ),
        height=250,
        showlegend=False
    )
    
    st.plotly_chart(fig, use_container_width=True, config={'displayModeBar': False})
