import pytest
from unittest.mock import patch, MagicMock
import sys
import os

# add frontend to sys path so we can import utils
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '../../../frontend')))
from utils.chart_renderer import render_trend_chart

@patch("utils.chart_renderer.st.plotly_chart")
@patch("utils.chart_renderer.st.markdown")
def test_render_trend_chart_empty(mock_st_markdown, mock_st_plotly_chart):
    # 데이터가 없을 때의 대체 마크다운 메시지 노출 검증
    render_trend_chart([])
    assert mock_st_markdown.called
    assert not mock_st_plotly_chart.called
    call_args = mock_st_markdown.call_args[0][0]
    assert "시각화할 데이터가 충분하지 않습니다." in call_args

@patch("utils.chart_renderer.st.plotly_chart")
@patch("utils.chart_renderer.st.markdown")
def test_render_trend_chart_with_data(mock_st_markdown, mock_st_plotly_chart):
    # 데이터가 있을 때 Scatter 플롯 및 staticPlot 설정이 정상 적용되는지 검증
    trend_data = [
        {"date": "2026-06-20", "count": 5},
        {"date": "2026-06-21", "count": 10}
    ]
    render_trend_chart(trend_data)
    
    assert not mock_st_markdown.called
    assert mock_st_plotly_chart.called
    
    # st.plotly_chart 호출 인자 획득
    call_args, call_kwargs = mock_st_plotly_chart.call_args
    fig = call_args[0]
    
    # 데이터 트레이스 형식 검증 (Scatter/Line+Markers+Text/Indigo/Fill)
    assert len(fig.data) == 1
    trace = fig.data[0]
    assert trace.type == "scatter"
    assert trace.mode == "lines+markers+text"
    assert trace.line.color == "#6366F1"
    assert trace.marker.color == "#4F46E5"
    assert trace.cliponaxis is False
    assert trace.fill == "tozeroy"
    assert list(trace.text) == ["5건", "10건"]
    assert fig.layout.yaxis.title.text is None
    assert fig.layout.yaxis.rangemode == "nonnegative"
    assert fig.layout.yaxis.tickformat == "d"
    assert fig.layout.yaxis.dtick is None  # 최댓값이 10이므로 dtick 설정은 제공하지 않음
    assert list(fig.layout.yaxis.range) == [0, 15]  # 최댓값 10에 45% 마진 적용 (int(10*1.45)+1 = 15)
    
    # read-only 설정을 위한 staticPlot 옵션 검증
    assert call_kwargs.get("use_container_width") is True
    assert call_kwargs.get("config") == {'staticPlot': True}

@patch("utils.chart_renderer.st.plotly_chart")
@patch("utils.chart_renderer.st.markdown")
def test_render_trend_chart_small_data(mock_st_markdown, mock_st_plotly_chart):
    # 최댓값이 5 미만일 때 dtick=1 및 range=[0, 5] 설정이 포함되는지 검증
    trend_data = [
        {"date": "2026-06-20", "count": 1},
        {"date": "2026-06-21", "count": 2}
    ]
    render_trend_chart(trend_data)
    
    assert mock_st_plotly_chart.called
    fig = mock_st_plotly_chart.call_args[0][0]
    
    assert fig.layout.yaxis.dtick == 1
    assert list(fig.layout.yaxis.range) == [0, 5]

@patch("utils.chart_renderer.st.plotly_chart")
@patch("utils.chart_renderer.st.markdown")
def test_render_trend_chart_strict_design_lock(mock_st_markdown, mock_st_plotly_chart):
    # 차트 디자인/테마 설정이 임의로 변경되지 않도록 세부 시각 속성을 아주 빡세게 검증합니다.
    trend_data = [
        {"date": "2026-06-20", "count": 2},
        {"date": "2026-06-21", "count": 4}
    ]
    render_trend_chart(trend_data)
    
    assert mock_st_plotly_chart.called
    fig = mock_st_plotly_chart.call_args[0][0]
    trace = fig.data[0]
    
    # 1. 트레이스 스타일 검증
    assert trace.line.width == 3
    assert trace.line.shape == "linear"
    assert trace.marker.size == 8
    assert trace.marker.symbol == "circle"
    assert trace.marker.line.color == "#FFFFFF"
    assert trace.marker.line.width == 1.5
    assert trace.fillcolor == "rgba(99, 102, 241, 0.08)"
    
    # 2. 레이아웃 배경 및 여백 검증
    assert fig.layout.paper_bgcolor == "rgba(0,0,0,0)"
    assert fig.layout.plot_bgcolor == "rgba(0,0,0,0)"
    assert fig.layout.margin.l == 40
    assert fig.layout.margin.r == 40
    assert fig.layout.margin.t == 50
    assert fig.layout.margin.b == 20
    assert fig.layout.height == 320
    
    # 3. 범례(Legend) 스타일 검증
    assert fig.layout.showlegend is True
    assert fig.layout.legend.orientation == "h"
    assert fig.layout.legend.yanchor == "bottom"
    assert fig.layout.legend.y == 1.02
    assert fig.layout.legend.xanchor == "right"
    assert fig.layout.legend.x == 1
    assert fig.layout.legend.font.size == 9
    assert fig.layout.legend.font.color == "#64748B"
    
    # 4. 축(Axis) 스타일 검증
    assert fig.layout.xaxis.type == "category"
    assert fig.layout.xaxis.showgrid is False
    assert fig.layout.xaxis.zeroline is False
    assert fig.layout.xaxis.color == "#64748B"
    assert list(fig.layout.xaxis.range) == [-0.5, 1.5]  # len(dates) = 2일 때 [-0.5, 1.5]
    
    assert fig.layout.yaxis.showgrid is True
    assert fig.layout.yaxis.gridcolor == "#F1F5F9"
    assert fig.layout.yaxis.zeroline is False
    assert fig.layout.yaxis.color == "#64748B"

@patch("utils.chart_renderer.st.plotly_chart")
@patch("utils.chart_renderer.st.markdown")
def test_render_trend_chart_spike_handling_and_clipping_prevention(mock_st_markdown, mock_st_plotly_chart):
    # 0건에서 갑자기 15건으로 튀어 올라 spline 보간 시 언더슈트가 우려되는 실제 데이터를 주입
    trend_data = [
        {"date": "2026-06-17", "count": 0},
        {"date": "2026-06-18", "count": 0},
        {"date": "2026-06-19", "count": 0},
        {"date": "2026-06-20", "count": 0},
        {"date": "2026-06-21", "count": 15}
    ]
    render_trend_chart(trend_data)
    
    assert mock_st_plotly_chart.called
    fig = mock_st_plotly_chart.call_args[0][0]
    trace = fig.data[0]
    
    # 1. 급격한 기울기 변화 시 언더슈트(처짐)를 원천 차단하기 위해 linear 꺾은선으로 렌더링 검증
    assert trace.line.shape == "linear"
    
    # 2. X축 날짜 해석 오작동을 차단하기 위한 카테고리 타입 지정 검증
    assert fig.layout.xaxis.type == "category"
    assert list(fig.layout.xaxis.range) == [-0.5, 4.5] # 5일치 데이터이므로 [-0.5, 4.5] 여야 함
    
    # 3. Y축 마진에 따른 데이터 레이블 잘림 방지 범위 검증
    # 최댓값 15에 대해 45% 마진을 주어 int(15 * 1.45) + 1 = 22이 Y축 상한선이어야 함
    assert list(fig.layout.yaxis.range) == [0, 22]
    
    # 4. 차트 가독성 확장을 위해 키운 height=320 검증
    assert fig.layout.height == 320


