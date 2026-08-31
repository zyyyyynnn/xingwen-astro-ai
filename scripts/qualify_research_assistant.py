"""Run one real, sanitized Research Assistant qualification call."""

from __future__ import annotations

from datetime import UTC, datetime
import json
import sys

from app.config import settings
from app.schemas.manifest import load_manifest_bundle
from app.schemas.core import ResearchProject, ResearchThreadSummary
from app.services.model_execution import ModelExecutionError, QwenModelExecutionAdapter
from app.services.research_planner import ResearchContractPlanner


def main() -> int:
    message = (
        sys.argv[1]
        if len(sys.argv) > 1
        else "比较太阳型恒星与红矮星宜居带行星研究的观测偏差，并先确认研究范围。"
    )
    if not settings.research_assistant_ready or settings.DASHSCOPE_API_KEY is None:
        print(json.dumps({"status": "blocked", "code": "MODEL_RUNTIME_UNAVAILABLE"}))
        return 2

    adapter = QwenModelExecutionAdapter(
        api_key=settings.DASHSCOPE_API_KEY.get_secret_value(),
        base_url=settings.DASHSCOPE_BASE_URL,
        timeout_seconds=settings.DASHSCOPE_TIMEOUT_SECONDS,
    )
    planner = ResearchContractPlanner(
        model_port=adapter,
        provider="dashscope",
        requested_model=settings.DASHSCOPE_MODEL,
        explicit_revision=settings.DASHSCOPE_EXPLICIT_MODEL_REVISION,
        manifests=load_manifest_bundle(
            "services/data_pipeline/manifests/exoplanet_host_star/case-manifest.json",
            "services/data_pipeline/manifests/exoplanet_host_star/field-manifest.json",
        ),
    )
    now = datetime.now(UTC)
    project = ResearchProject(
        id="qualification-project",
        session_id="qualification-session",
        name="研究助手真实调用资格验证",
        description="只验证真实 Planner 调用与结构化输出，不保存原始响应。",
        case_key="exoplanet_host_star",
        thread_summary=ResearchThreadSummary(
            has_thread_entries=False,
            latest_thread_actor=None,
            has_unanswered_clarification=False,
        ),
        created_at=now,
        updated_at=now,
        revision=1,
    )
    request = planner.prepare_request(
        project=project,
        entries=(),
        message=message,
        answer_to_question_id=None,
    )
    try:
        result = planner.execute(request)
    except ModelExecutionError as exc:
        print(json.dumps({"status": "failed", "code": exc.code}, ensure_ascii=False))
        return 1

    evidence = {
        "status": "passed",
        "provider": request.provider,
        "official_route": settings.DASHSCOPE_BASE_URL,
        "requested_model": request.requested_model,
        "provider_returned_model": result.response.provider_returned_model,
        "explicit_revision": request.explicit_revision,
        "prompt": request.prompt_name,
        "prompt_version": request.prompt_version,
        "prompt_hash": request.prompt_hash,
        "input_hash": request.input_hash,
        "parameters_hash": request.parameters_hash,
        "output_hash": result.response.output_hash,
        "latency_ms": result.response.latency_ms,
        "token_usage": result.response.token_usage,
        "provider_request_id": result.response.provider_request_id,
        "outcome": result.output.outcome,
    }
    print(json.dumps(evidence, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
