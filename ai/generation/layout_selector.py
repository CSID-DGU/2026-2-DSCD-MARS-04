import hashlib
import json
import os
import sys
import time
from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

from dotenv import load_dotenv
from openai import OpenAI

from ai.generation.layout_loader import load_layout_options
from data_pipeline.schemas.group import Group
from data_pipeline.schemas.layout import (
    LayoutSelectionInput,
    LayoutSelectionOutput,
)

ROOT_DIR = Path(__file__).resolve().parents[2]
LAYOUTS_PATH = ROOT_DIR / "data" / "layouts.json"
PROMPT_PATH = Path(__file__).parent / "prompts" / "layout_selection.md"
DEFAULT_LOG_PATH = ROOT_DIR / "logs" / "layout_selection.jsonl"

MODEL = "gpt-4.1-mini"


def validate_layout_selections(
    result: LayoutSelectionOutput,
    request: LayoutSelectionInput,
) -> None:
    """입력 그룹과 레이아웃 선택 결과가 일치하는지 검증"""

    if result.document_id != request.document_id:
        raise ValueError("문서 ID가 일치하지 않습니다.")

    expected_ids = [group.group_id for group in request.groups]
    actual_ids = [item.group_id for item in result.layout_selections]

    if actual_ids != expected_ids:
        raise ValueError(
            "레이아웃 선택 결과의 그룹 ID 또는 순서가 일치하지 않습니다."
        )

    valid_layout_ids = {
        layout.layout_id for layout in request.available_layouts
    }

    for item in result.layout_selections:
        if item.layout_id not in valid_layout_ids:
            raise ValueError(
                f"허용되지 않은 레이아웃입니다: {item.layout_id}"
            )


def select_layouts(
    document_id: str,
    groups: list[Group],
    client: OpenAI | None = None,
    model: str | None = None,
    log_path: Path | None = None,
) -> LayoutSelectionOutput:
    """LLM으로 그룹별 레이아웃을 선택하고 실행 로그를 저장"""

    started = time.perf_counter()

    record = {
        "run_id": str(uuid4()),
        "started_at": datetime.now(UTC).isoformat(),
        "document_id": document_id,
        "group_count": len(groups),
        "model": None,
        "prompt_sha256": None,
        "response_id": None,
        "response_status": None,
        "usage": None,
        "status": "failed",
        "stage": "input_validation",
    }

    try:
        # 1. 입력 검증
        if not document_id.strip():
            raise ValueError("문서 ID가 비어 있습니다.")

        if not groups:
            raise ValueError("레이아웃을 선택할 그룹이 없습니다.")

        group_ids = [group.group_id for group in groups]

        if len(group_ids) != len(set(group_ids)):
            raise ValueError("중복된 그룹 ID가 존재합니다.")

        if any(
            not group.group_id.strip() or not group.summary.strip()
            for group in groups
        ):
            raise ValueError("그룹 ID와 summary는 비어 있을 수 없습니다.")

        # 2. 레이아웃 정의 불러오기
        record["stage"] = "layout_load"
        available_layouts = load_layout_options(LAYOUTS_PATH)

        request = LayoutSelectionInput(
            document_id=document_id,
            groups=groups,
            available_layouts=available_layouts,
        )

        # 3. 프롬프트 불러오기
        record["stage"] = "prompt_load"
        prompt = PROMPT_PATH.read_text(encoding="utf-8").strip()

        if not prompt:
            raise ValueError("레이아웃 선택 프롬프트가 비어 있습니다.")

        record["prompt_sha256"] = hashlib.sha256(
            prompt.encode("utf-8")
        ).hexdigest()

        # 4. API 설정
        load_dotenv(ROOT_DIR / ".env")

        selected_model = (
            model
            if model is not None
            else os.getenv("LAYOUT_SELECTION_MODEL", MODEL)
        )

        if not selected_model.strip():
            raise ValueError("레이아웃 선택 모델이 비어 있습니다.")

        record["model"] = selected_model

        api_client = client if client is not None else OpenAI()

        # 5. LLM 호출
        record["stage"] = "api_call"

        response = api_client.responses.parse(
            model=selected_model,
            input=[
                {
                    "role": "system",
                    "content": prompt,
                },
                {
                    "role": "user",
                    "content": json.dumps(
                        request.model_dump(),
                        ensure_ascii=False,
                    ),
                },
            ],
            text_format=LayoutSelectionOutput,
        )

        # 6. API 실행 정보 기록
        record["response_id"] = getattr(response, "id", None)
        record["response_status"] = response.status
        record["response_model"] = getattr(response, "model", None)

        usage = getattr(response, "usage", None)

        if usage is not None:
            record["usage"] = usage.model_dump(mode="json")

        # 7. 출력 검증
        record["stage"] = "output_validation"

        if response.status != "completed":
            raise RuntimeError(
                f"레이아웃 선택 응답이 완료되지 않았습니다: {response.status}"
            )

        for item in response.output:
            for content in getattr(item, "content", []):
                if content.type == "refusal":
                    raise RuntimeError("모델이 레이아웃 선택을 거부했습니다.")

        result = response.output_parsed

        if result is None:
            raise ValueError("레이아웃 선택 결과를 생성하지 못했습니다.")

        validate_layout_selections(result, request)

        record["status"] = "success"
        record["stage"] = "completed"

        return result

    except Exception as exc:
        record["error"] = {
            "type": type(exc).__name__,
            "stage": record["stage"],
        }
        raise

    finally:
        # 8. 성공/실패 여부와 관계없이 실행 로그 저장
        record["finished_at"] = datetime.now(UTC).isoformat()
        record["elapsed_seconds"] = round(
            time.perf_counter() - started, 3
        )

        try:
            destination = (
                Path(log_path)
                if log_path is not None
                else DEFAULT_LOG_PATH
            )

            destination.parent.mkdir(
                parents=True,
                exist_ok=True,
            )

            with destination.open("a", encoding="utf-8") as file:
                file.write(
                    json.dumps(record, ensure_ascii=False) + "\n"
                )

        except OSError:
            print(
                "경고: 레이아웃 선택 실행 로그를 저장하지 못했습니다.",
                file=sys.stderr,
            )
