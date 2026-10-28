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

from ai.generation.card_checks import validate_input, validate_output
from ai.generation.layout_loader import load_layout_options
from data_pipeline.schemas.card import (
    CardGenerationInput,
    CardGenerationOutput,
)
from data_pipeline.schemas.group import Group
from data_pipeline.schemas.layout import LayoutOption, LayoutSelection

ROOT = Path(__file__).resolve().parents[2]
PROMPT_PATH = Path(__file__).parent / "prompts" / "card_generation.md"
LAYOUTS_PATH = ROOT / "data" / "layouts.json"
DEFAULT_LOG_PATH = ROOT / "logs" / "card_generation.jsonl"

DEFAULT_MODEL = "gpt-4.1-mini"
MAX_RETRIES = 2


def save_log(record: dict, log_path: Path | None) -> None:
    """Save execution metadata without storing article or card text."""

    destination = Path(log_path) if log_path is not None else DEFAULT_LOG_PATH

    destination.parent.mkdir(parents=True, exist_ok=True)

    with destination.open("a", encoding="utf-8") as stream:
        stream.write(json.dumps(record, ensure_ascii=False) + "\n")


def build_group_request(
    request: CardGenerationInput,
    group_id: str,
) -> CardGenerationInput:
    """Create input containing exactly one selected group."""

    groups = [group for group in request.groups if group.group_id == group_id]

    selections = [
        selection for selection in request.layout_selections if selection.group_id == group_id
    ]

    return CardGenerationInput(
        document_id=request.document_id,
        groups=groups,
        layout_selections=selections,
        available_layouts=request.available_layouts,
    )


def extract_group_result(
    result: CardGenerationOutput,
    group_id: str,
) -> CardGenerationOutput:
    """Extract cards belonging to one group."""

    return CardGenerationOutput(
        document_id=result.document_id,
        cards=[card for card in result.cards if card.group_id == group_id],
    )


def build_correction_message(
    request: CardGenerationInput,
    previous_result: CardGenerationOutput,
    error: ValueError,
) -> str:
    """Request precise correction of a single invalid group."""

    layout_id = request.layout_selections[0].layout_id

    layout_rules = next(
        option.fields for option in request.available_layouts if option.layout_id == layout_id
    )

    return (
        "이전 카드 생성 결과가 레이아웃 검증에 실패했습니다.\n\n"
        f"검증 오류: {error}\n\n"
        "이번에는 오류가 발생한 필드를 정확하게 수정해야 합니다.\n"
        "글자 수는 공백과 문장부호를 포함한 Python len() 기준입니다.\n"
        "최대 글자 수에 딱 맞추기보다 2~3자 여유 있게 작성하세요.\n\n"
        "선택된 레이아웃의 상세 필드 규칙:\n"
        f"{json.dumps(layout_rules, ensure_ascii=False)}\n\n"
        "수정 우선순위:\n"
        "1. 검증 오류가 발생한 필드를 우선 수정하세요.\n"
        "2. 제목만 초과했다면 제목을 줄이고 카드 수는 유지하세요.\n"
        "3. 제목은 짧고 자연스러운 핵심 메시지로 작성하세요.\n"
        "4. 본문이 초과했다면 중복 표현과 불필요한 수식어를 줄이세요.\n"
        "5. 한 장으로 핵심 정보를 보존할 수 있다면 1장으로 작성하세요.\n"
        "6. 한 장으로 정보 보존이 어려운 경우에만 최대 2장으로 나누세요.\n"
        "7. 이미 2장으로 구성된 경우에는 2장 안에서 수정하세요.\n"
        "8. 문자열을 기계적으로 자르거나 필수 정보를 삭제하지 마세요.\n"
        "9. 의미 단위로 문구를 구성하고 같은 내용을 반복하지 마세요.\n"
        "10. 판단 주체, 수치, 조건, 시점, 가능성, 부정 표현을 유지하세요.\n"
        "11. 당사자의 주장과 확정된 사실을 명확하게 구분하세요.\n"
        "12. 원문에 없는 사실이나 해석을 추가하지 마세요.\n"
        "13. 제목과 본문이 동일한 내용을 불필요하게 반복하지 않도록 하세요.\n"
        "14. group_id와 선택된 layout_id를 유지하세요.\n"
        "15. sids에는 해당 그룹의 문장 ID만 사용하세요.\n"
        "16. 다른 그룹의 카드를 생성하지 마세요.\n"
        "17. document_id를 원래 입력과 동일하게 유지하세요.\n\n"
        "수정할 그룹의 원래 입력:\n"
        f"{request.model_dump_json()}\n\n"
        "이전 생성 결과:\n"
        f"{previous_result.model_dump_json()}\n\n"
        "최종 출력 전 모든 카드의 제목, 본문, 항목, 비교 필드가 "
        "각각의 글자 수 및 항목 수 제한을 지키는지 확인하세요.\n"
        "CardGenerationOutput 스키마에 맞는 JSON만 반환하세요."
    )


def generate_cards(
    document_id: str,
    groups: list[Group],
    layout_selections: list[LayoutSelection],
    available_layouts: list[LayoutOption] | None = None,
    *,
    model: str | None = None,
    client: OpenAI | None = None,
    log_path: Path | None = None,
) -> CardGenerationOutput:
    """Generate cards and correct invalid groups independently."""

    started = time.perf_counter()

    record = {
        "run_id": str(uuid4()),
        "started_at": datetime.now(UTC).isoformat(),
        "document_id": document_id,
        "group_count": len(groups),
        "model": None,
        "prompt_sha256": None,
        "status": "failed",
        "stage": "input_validation",
        "attempt_count": 0,
        "correction_count": 0,
        "corrected_group_ids": [],
        "validation_failure_count": 0,
        "usage": {
            "input_tokens": 0,
            "output_tokens": 0,
            "total_tokens": 0,
        },
    }

    try:
        if available_layouts is None:
            available_layouts = load_layout_options(LAYOUTS_PATH)

        request = CardGenerationInput(
            document_id=document_id,
            groups=groups,
            layout_selections=layout_selections,
            available_layouts=available_layouts,
        )

        validate_input(request)

        record["stage"] = "prompt_load"

        prompt = PROMPT_PATH.read_text(encoding="utf-8").strip()

        if not prompt:
            raise ValueError("카드 생성 프롬프트가 비어 있습니다.")

        record["prompt_sha256"] = hashlib.sha256(prompt.encode("utf-8")).hexdigest()

        load_dotenv(ROOT / ".env")

        selected_model = (
            model if model is not None else os.getenv("CARD_GENERATION_MODEL", DEFAULT_MODEL)
        )

        if not selected_model or not selected_model.strip():
            raise ValueError("카드 생성 모델이 비어 있습니다.")

        record["model"] = selected_model

        api = client if client is not None else OpenAI()

        def call_model(user_message: str) -> CardGenerationOutput:
            """Call the model and accumulate token usage."""

            record["stage"] = "api_call"
            record["attempt_count"] += 1

            response = api.responses.parse(
                model=selected_model,
                input=[
                    {
                        "role": "system",
                        "content": prompt,
                    },
                    {
                        "role": "user",
                        "content": user_message,
                    },
                ],
                text_format=CardGenerationOutput,
            )

            record["response_id"] = getattr(response, "id", None)
            record["response_status"] = response.status

            usage = getattr(response, "usage", None)

            if usage is not None:
                for key in (
                    "input_tokens",
                    "output_tokens",
                    "total_tokens",
                ):
                    record["usage"][key] += getattr(usage, key, 0) or 0

            record["stage"] = "response_validation"

            if response.status != "completed":
                raise RuntimeError(f"카드 생성 응답이 완료되지 않았습니다: {response.status}")

            for item in response.output:
                for content in getattr(item, "content", []):
                    if content.type == "refusal":
                        raise RuntimeError("모델이 카드 생성을 거부했습니다.")

            if response.output_parsed is None:
                raise RuntimeError("카드 생성 결과를 파싱하지 못했습니다.")

            return CardGenerationOutput.model_validate(response.output_parsed)

        # 1. 모든 그룹의 카드를 한 번에 생성
        initial_result = call_model(request.model_dump_json())

        if initial_result.document_id != document_id:
            raise ValueError("최초 생성 결과의 document_id가 일치하지 않습니다.")

        expected_group_ids = {group.group_id for group in request.groups}

        unexpected_group_ids = {
            card.group_id
            for card in initial_result.cards
            if card.group_id not in expected_group_ids
        }

        if unexpected_group_ids:
            raise ValueError(
                "최초 생성 결과에 선택하지 않은 그룹이 있습니다: "
                f"{sorted(str(value) for value in unexpected_group_ids)}"
            )

        # 2. 그룹별 검증
        record["stage"] = "group_validation"

        validated_cards = []

        for group in request.groups:
            group_id = group.group_id

            group_request = build_group_request(
                request=request,
                group_id=group_id,
            )

            group_result = extract_group_result(
                result=initial_result,
                group_id=group_id,
            )

            try:
                validate_output(group_request, group_result)

            except ValueError as initial_error:
                record["validation_failure_count"] += 1
                record["corrected_group_ids"].append(group_id)

                print(
                    f"[{group_id}] 최초 검증 실패: {initial_error}",
                    file=sys.stderr,
                )

                last_error = initial_error

                # 3. 실패한 그룹만 최대 2회 재생성
                for retry in range(1, MAX_RETRIES + 1):
                    record["stage"] = "group_correction"
                    record["correction_count"] += 1

                    print(
                        f"[{group_id}] 수정 시도 {retry}/{MAX_RETRIES}",
                        file=sys.stderr,
                    )

                    correction_message = build_correction_message(
                        request=group_request,
                        previous_result=group_result,
                        error=last_error,
                    )

                    group_result = call_model(correction_message)

                    record["stage"] = "group_validation"

                    try:
                        validate_output(
                            group_request,
                            group_result,
                        )

                    except ValueError as error:
                        last_error = error
                        record["validation_failure_count"] += 1

                        print(
                            f"[{group_id}] 수정 검증 실패: {error}",
                            file=sys.stderr,
                        )

                    else:
                        print(
                            f"[{group_id}] 수정 완료: {len(group_result.cards)}장",
                            file=sys.stderr,
                        )
                        break

                else:
                    raise ValueError(
                        f"{group_id}: 최대 {MAX_RETRIES}회 수정 후에도 "
                        f"검증에 실패했습니다. 마지막 오류: {last_error}"
                    ) from last_error

            # 4. 검증을 통과한 그룹은 그대로 확정
            validated_cards.extend(group_result.cards)

        # 5. 그룹 순서대로 최종 카드 결합
        final_result = CardGenerationOutput(
            document_id=document_id,
            cards=validated_cards,
        )

        # 6. 전체 결과 최종 검증
        record["stage"] = "final_validation"

        validate_output(request, final_result)

        record["status"] = "success"
        record["stage"] = "completed"
        record["card_count"] = len(final_result.cards)

        return final_result

    except Exception as exc:
        record["error"] = {
            "type": type(exc).__name__,
            "stage": record["stage"],
        }
        raise

    finally:
        record["finished_at"] = datetime.now(UTC).isoformat()
        record["elapsed_seconds"] = round(
            time.perf_counter() - started,
            3,
        )

        try:
            save_log(record, log_path)
        except OSError:
            print(
                "경고: 카드 생성 로그를 저장하지 못했습니다.",
                file=sys.stderr,
            )
