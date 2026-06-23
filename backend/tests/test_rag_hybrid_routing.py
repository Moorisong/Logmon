# backend/tests/test_rag_hybrid_routing.py
"""
Hybrid RAG Router / IDE Classifier / Chroma 메타데이터 스키마 테스트
"""
from __future__ import annotations

import os
import pytest
from unittest.mock import patch, AsyncMock

# 테스트 환경 강제 분리
os.environ["LOGMON_ENV"] = "test"
os.environ["LOGMON_DB_DIR"] = "/tmp/logmon_test_rag_hybrid_db"
os.environ["LOGMON_CHROMA_DIR"] = "/tmp/logmon_test_rag_hybrid_chroma"

from backend.llm.ide_classifier import classify_source_ide, classify_source_ide_from_fields
from backend.llm.router import (
    detect_fast_track,
    parse_llm_filter_response,
    build_llm_fallback_prompt,
    ROUTE_FAST_TRACK,
    ROUTE_LLM_FALLBACK,
)
from backend.db.chroma_handler import (
    classify_action_type,
    timestamp_to_epoch,
    normalize_log_level,
)


# ──────────────────────────────────────────────
# 1. IDE Signature Matcher 테스트
# ──────────────────────────────────────────────

class TestIDEClassifier:
    def test_antigravity_ide(self):
        assert classify_source_ide("Antigravity IDE session started") == "Antigravity IDE"

    def test_cursor_server(self):
        assert classify_source_ide("cursor-server extension activated") == "cursor"

    def test_cursor(self):
        assert classify_source_ide("cursor opened file main.py") == "cursor"

    def test_vscode_code_helper(self):
        assert classify_source_ide("Code Helper process started") == "vscode"
        assert classify_source_ide("vscode language server") == "vscode"

    def test_jetbrains_idea_log(self):
        assert classify_source_ide("idea.log: build succeeded") == "JetBrains"
        assert classify_source_ide("JetBrains Gateway connected") == "JetBrains"
        assert classify_source_ide("IntelliJ IDEA 2024.1") == "JetBrains"

    def test_windsurf(self):
        assert classify_source_ide("windsurf session init") == "windsurf"

    def test_zed(self):
        assert classify_source_ide("zed opened workspace") == "zed"

    def test_unknown_default(self):
        assert classify_source_ide("some unknown tool") == "Unknown"
        assert classify_source_ide("") == "Unknown"
        assert classify_source_ide(None) == "Unknown"

    def test_classify_from_fields_source_tool_priority(self):
        """source_tool에서 먼저 매칭, Unknown이면 raw_message로 재시도"""
        result = classify_source_ide_from_fields("cursor", "some message")
        assert result == "cursor"

    def test_classify_from_fields_fallback_to_raw(self):
        """source_tool Unknown이면 raw_message로 분류"""
        result = classify_source_ide_from_fields("unknown_tool", "windsurf opened project")
        assert result == "windsurf"

    def test_classify_from_fields_both_unknown(self):
        result = classify_source_ide_from_fields("random", "random message")
        assert result == "Unknown"


# ──────────────────────────────────────────────
# 2. Hybrid Router Fast-track 테스트
# ──────────────────────────────────────────────

class TestHybridRouterFastTrack:
    def test_error_fast_track(self):
        result = detect_fast_track("오늘 에러 몇 개야?")
        assert result is not None
        assert result.route == ROUTE_FAST_TRACK
        assert result.fast_track_key == "error"

    def test_warning_fast_track(self):
        result = detect_fast_track("경고 건수 알려줘")
        assert result is not None
        assert result.route == ROUTE_FAST_TRACK
        assert result.fast_track_key == "warning"

    def test_token_fast_track(self):
        result = detect_fast_track("token 사용량 보여줘")
        assert result is not None
        assert result.route == ROUTE_FAST_TRACK
        assert result.fast_track_key == "token"

    def test_git_fast_track(self):
        result = detect_fast_track("git commit 내역 알려줘")
        assert result is not None
        assert result.route == ROUTE_FAST_TRACK
        assert result.fast_track_key == "git"

    def test_network_db_fast_track(self):
        """현실적인 network error 복합 질문 → network_db fast-track"""
        result = detect_fast_track("network error 몇 건이야?")
        assert result is not None
        assert result.route == ROUTE_FAST_TRACK
        assert result.fast_track_key == "network_db"

    def test_ide_uptime_fast_track(self):
        """현실적인 IDE 활동 질문 → ide_uptime fast-track"""
        result = detect_fast_track("IDE 종류별 활동 보여줘")
        assert result is not None
        assert result.route == ROUTE_FAST_TRACK
        assert result.fast_track_key == "ide_uptime"

    def test_complex_query_no_fast_track(self):
        """복잡한 분석/추론 질문은 Fast-track 차단 → None 반환 (LLM Fallback 강제)"""
        result = detect_fast_track("어제 JetBrains에서 발생한 빌드 실패 상세 분석해줘")
        assert result is None, (
            f"복잡 분석 질문이 Fast-track에 잘못 라우팅됨: key={result.fast_track_key if result else None}"
        )


# ──────────────────────────────────────────────
# 3. LLM 필터 응답 파싱 테스트
# ──────────────────────────────────────────────

class TestLLMFilterResponseParser:
    def test_parse_full_response(self):
        raw = (
            "keywords: build, error, exception\n"
            "log_level: ERROR\n"
            "source_ide: JetBrains\n"
            "action_type: build"
        )
        result = parse_llm_filter_response(raw)
        assert result["keywords"] == ["build", "error", "exception"]
        assert result["log_level"] == "ERROR"
        assert result["source_ide"] == "JetBrains"
        assert result["action_type"] == "build"

    def test_parse_partial_response(self):
        raw = "keywords: git, push\nlog_level: ERROR"
        result = parse_llm_filter_response(raw)
        assert "git" in result["keywords"]
        assert result["log_level"] == "ERROR"
        assert result["source_ide"] == ""
        assert result["action_type"] == ""

    def test_parse_empty_response(self):
        result = parse_llm_filter_response("")
        assert result["keywords"] == []
        assert result["log_level"] == ""
        assert result["source_ide"] == ""
        assert result["action_type"] == ""

    def test_parse_none_response(self):
        result = parse_llm_filter_response(None)
        assert result["keywords"] == []

    def test_log_level_uppercase_normalization(self):
        raw = "keywords: warn\nlog_level: warn\nsource_ide:\naction_type:"
        result = parse_llm_filter_response(raw)
        assert result["log_level"] == "WARN"

    def test_few_shot_prompt_contains_examples(self):
        prompt = build_llm_fallback_prompt("어제 JetBrains 빌드 에러")
        assert "JetBrains" in prompt
        assert "keywords:" in prompt
        assert "log_level:" in prompt
        assert "source_ide:" in prompt
        assert "action_type:" in prompt
        assert "어제 JetBrains 빌드 에러" in prompt


# ──────────────────────────────────────────────
# 4. ChromaDB 메타데이터 유틸 테스트
# ──────────────────────────────────────────────

class TestChromaMetadataUtils:
    def test_timestamp_to_epoch_valid(self):
        epoch = timestamp_to_epoch("2026-06-23 10:00:00")
        assert isinstance(epoch, int)
        assert epoch > 0

    def test_timestamp_to_epoch_empty(self):
        assert timestamp_to_epoch("") == 0
        assert timestamp_to_epoch(None) == 0

    def test_timestamp_to_epoch_invalid(self):
        assert timestamp_to_epoch("not-a-date") == 0

    def test_classify_action_type_network(self):
        assert classify_action_type("connection timeout occurred") == "network"

    def test_classify_action_type_build(self):
        assert classify_action_type("gradle build failed") == "build"

    def test_classify_action_type_git(self):
        assert classify_action_type("git push rejected") == "git"

    def test_classify_action_type_system(self):
        assert classify_action_type("high CPU usage detected") == "system"

    def test_classify_action_type_unknown(self):
        assert classify_action_type("random log message") == ""
        assert classify_action_type("") == ""

    def test_normalize_log_level_error(self):
        assert normalize_log_level("ERROR", "some text") == "ERROR"
        assert normalize_log_level("CRITICAL", "some text") == "ERROR"

    def test_normalize_log_level_warn(self):
        assert normalize_log_level("WARNING", "some text") == "WARN"
        assert normalize_log_level("WARN", "some text") == "WARN"

    def test_normalize_log_level_debug(self):
        assert normalize_log_level("DEBUG", "debug: verbose output") == "DEBUG"

    def test_normalize_log_level_fallback_from_text(self):
        """event_type 불명확 시 chunk 텍스트에서 추론"""
        assert normalize_log_level("", "[error]: connection refused") == "ERROR"
        assert normalize_log_level("", "[warning]: disk space low") == "WARN"
        assert normalize_log_level("", "normal info message") == "INFO"


# ──────────────────────────────────────────────
# 5. RAG 엔진 LLM Fallback 필터 통합 테스트
# ──────────────────────────────────────────────

@pytest.mark.asyncio
async def test_rag_engine_applies_llm_filters():
    """LLM Fallback 필터가 query_vectors 호출 시 올바르게 전달되는지 검증"""
    from unittest.mock import AsyncMock, MagicMock, patch as local_patch
    from backend.llm.rag_engine import ask_rag_agent

    extract_mock = AsyncMock(return_value={
        "keywords": ["build", "exception"],
        "log_level": "ERROR",
        "source_ide": "JetBrains",
        "action_type": "build",
    })
    query_mock = MagicMock(return_value=[["[2026-06-23 09:00:00] [ERROR] Gradle build failed"]])
    generate_mock = AsyncMock(return_value="빌드 에러 분석 완료")

    with local_patch("backend.llm.rag_engine.extract_llm_filters", extract_mock), \
         local_patch("backend.llm.rag_engine.query_vectors", query_mock), \
         local_patch("backend.llm.rag_engine.generate_completion", generate_mock):
        # fast-track 비대상 질문 (에러/경고 키워드 없음)
        answer = await ask_rag_agent("어제 JetBrains 빌드 상세 화면 분석해줘", "test_user")

    assert answer == "빌드 에러 분석 완료"
    call_kwargs = query_mock.call_args.kwargs
    assert call_kwargs.get("log_level") == "ERROR"
    assert call_kwargs.get("source_ide") == "JetBrains"
    assert call_kwargs.get("action_type") == "build"
    assert "build" in call_kwargs.get("keywords", [])


@pytest.mark.asyncio
@patch("backend.llm.rag_engine.extract_llm_filters")
@patch("backend.llm.rag_engine.query_vectors")
@patch("backend.llm.rag_engine.generate_completion")
async def test_rag_engine_empty_llm_filters_no_crash(
    mock_generate, mock_query, mock_extract
):
    """LLM 필터 추출 실패(빈 dict) 시 크래시 없이 정상 동작하는지 검증"""
    from backend.llm.rag_engine import ask_rag_agent

    mock_extract.return_value = {}
    mock_query.return_value = [["[2026-06-23 09:00:00] [INFO] System running normally"]]
    mock_generate.return_value = "정상 운영 중"

    answer = await ask_rag_agent("오늘 시스템 상태는?", "test_user")
    assert answer == "정상 운영 중"
