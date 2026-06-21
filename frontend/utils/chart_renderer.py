import plotly.graph_objects as go
import streamlit as st
from typing import List, Dict, Any

def render_trend_chart(trend_data: List[Dict[str, Any]]):
    """
    백엔드에서 넘겨받은 최근 7일 트렌드 배열을 파스텔 톤 차트로 렌더링합니다.
    """
    if not trend_data:
        st.markdown("<p style='color: #64748B; font-style: italic; font-size: 14px;'>시각화할 데이터가 충분하지 않습니다.</p>", unsafe_allow_html=True)
        return

    dates = [item["date"][-5:] for item in trend_data]  # MM-DD 형식 축약
    counts = [item["count"] for item in trend_data]

    fig = go.Figure()
    
    # 라인점 차트 (인디고 블루 뉴모피즘/글래스모피즘 조화)
    fig.add_trace(go.Scatter(
        x=dates,
        y=counts,
        mode="lines+markers+text",
        text=[f"{c:,}건" for c in counts],
        textposition="top center",
        cliponaxis=False,
        textfont=dict(
            color="#4F46E5",
            size=9  # 작고 귀여운 사이즈
        ),
        name="로그 수 (건)",
        line=dict(
            color="#6366F1",  # 인디고 블루
            width=3,
            shape="spline",   # 부드러운 곡선 효과
            smoothing=1.3
        ),
        marker=dict(
            size=8,
            color="#4F46E5",  # 어두운 인디고 포인트
            symbol="circle",
            line=dict(
                color="#FFFFFF",
                width=1.5
            )
        ),
        fill="tozeroy",
        fillcolor="rgba(99, 102, 241, 0.08)"  # 투명도 높은 하단 영역 채우기
    ))
    
    max_val = max(counts) if counts else 0
    yaxis_config = dict(
        rangemode="nonnegative",
        tickformat="d",  # 소수점 표시 원천 방지 (정수 포맷)
        showgrid=True,
        gridcolor="#F1F5F9",
        zeroline=False,
        color="#64748B"
    )
    if max_val < 5:
        yaxis_config["dtick"] = 1  # 최대값이 작을 때는 1단위로 눈금 강제 지정
        yaxis_config["range"] = [0, 5]  # 마진 여유를 두어 텍스트 레이블 잘림 방지
    else:
        # 최대값의 45% 마진을 위쪽에 더 주어 데이터 레이블이 잘리는 것을 방지
        yaxis_config["range"] = [0, int(max_val * 1.45) + 1]
        
    # 둥근 모서리 및 투명 배경
    fig.update_layout(
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(0,0,0,0)",
        margin=dict(l=40, r=40, t=50, b=20),
        xaxis=dict(
            showgrid=False,
            zeroline=False,
            color="#64748B",
            range=[-0.5, len(dates) - 0.5]
        ),
        yaxis=yaxis_config,
        height=250,
        showlegend=True,
        legend=dict(
            orientation="h",
            yanchor="bottom",
            y=1.02,
            xanchor="right",
            x=1,
            font=dict(
                size=9,
                color="#64748B"
            )
        )
    )
    
    st.plotly_chart(fig, use_container_width=True, config={'staticPlot': True})
