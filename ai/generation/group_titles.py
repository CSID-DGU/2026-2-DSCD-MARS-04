"""Generate group titles: python -m ai.generation.group_titles INPUT.json."""

import argparse
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
from pydantic import BaseModel, ConfigDict, model_validator

from data_pipeline.schemas.group import GroupAnalysis, GroupPresentation

ROOT = Path(__file__).resolve().parents[2]
PROMPT_PATH = Path(__file__).with_name("prompts") / "group_titles.md"


class GroupTitlesInput(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)

    document_id: str
    groups: list[GroupAnalysis]

    @model_validator(mode="after")
    def validate_groups(self):
        if not self.document_id.strip() or not self.groups:
            raise ValueError("document_id와 하나 이상의 그룹이 필요합니다.")
        ids = [group.group_id for group in self.groups]
        if len(ids) != len(set(ids)):
            raise ValueError("입력 group_id가 중복됩니다.")
        for group in self.groups:
            if not group.group_id.strip() or not group.summary.strip():
                raise ValueError("group_id와 summary는 비어 있을 수 없습니다.")
            if not group.sentence_ids or any(
                not sid.strip() for sid in group.sentence_ids
            ):
                raise ValueError("비어 있지 않은 sentence_ids가 필요합니다.")
        return self


class GroupTitlesOutput(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)

    document_id: str
    group_presentations: list[GroupPresentation]


def validate_output(source: GroupTitlesInput, result: GroupTitlesOutput) -> None:
    if result.document_id != source.document_id:
        raise ValueError("출력 document_id가 입력과 다릅니다.")
    expected = [group.group_id for group in source.groups]
    actual = [group.group_id for group in result.group_presentations]
    if actual != expected:
        raise ValueError(
            f"출력 그룹 ID·순서·개수가 입력과 다릅니다: {actual} != {expected}"
        )
    for group in result.group_presentations:
        if not group.topic.strip() or not group.headline.strip():
            raise ValueError(f"빈 topic 또는 headline: {group.group_id}")


def _generate_group_titles(
    data: dict | GroupTitlesInput,
    *,
    model: str | None = None,
    client: OpenAI | None = None,
    prompt_path: Path = PROMPT_PATH,
    record: dict,
) -> GroupTitlesOutput:
    """Validate before calling the API; preserve input group order exactly."""
    record["stage"] = "input_validation"
    source = GroupTitlesInput.model_validate(data, strict=True)
    record.update(document_id=source.document_id, group_count=len(source.groups))
    record["stage"] = "prompt_load"
    prompt = prompt_path.read_text(encoding="utf-8").strip()
    record["prompt_sha256"] = hashlib.sha256(prompt.encode("utf-8")).hexdigest()
    if not prompt:
        raise ValueError("제목 생성 프롬프트가 비어 있습니다.")
    load_dotenv(ROOT / ".env")
    selected_model = (
        model if model is not None else os.getenv("GENERATION_MODEL", "gpt-4.1-mini")
    )
    record["model"] = selected_model
    if not selected_model.strip():
        raise ValueError("GENERATION_MODEL은 비어 있을 수 없습니다.")
    api = client if client is not None else OpenAI()
    record["stage"] = "api_call"
    response = api.responses.parse(
        model=selected_model,
        input=[
            {"role": "system", "content": prompt},
            {"role": "user", "content": source.model_dump_json()},
        ],
        text_format=GroupTitlesOutput,
    )
    record["response_id"] = getattr(response, "id", None)
    record["response_model"] = getattr(response, "model", None)
    record["response_status"] = response.status
    usage = getattr(response, "usage", None)
    record["usage"] = usage.model_dump(mode="json") if usage is not None else None
    record["stage"] = "output_validation"
    if response.status != "completed":
        raise RuntimeError(f"제목 생성 응답이 완료되지 않았습니다: {response.status}")
    for item in response.output:
        for content in getattr(item, "content", []):
            if content.type == "refusal":
                raise RuntimeError(
                    f"모델이 제목 생성을 거부했습니다: {content.refusal}"
                )
    if response.output_parsed is None:
        raise RuntimeError("스키마에 맞는 제목 생성 결과가 없습니다.")
    result = GroupTitlesOutput.model_validate(response.output_parsed, strict=True)
    validate_output(source, result)
    return result


def generate_group_titles(
    data: dict | GroupTitlesInput,
    *,
    model: str | None = None,
    client: OpenAI | None = None,
    prompt_path: Path = PROMPT_PATH,
    log_path: Path | None = None,
) -> GroupTitlesOutput:
    """Append one JSONL event per call; never log source text or exception bodies.

    GENERATION_LOG_PATH overrides the default logs/group_titles.jsonl path.
    Log write failures warn on stderr without replacing generation errors/results.
    """
    started = time.perf_counter()
    record = {
        "run_id": str(uuid4()),
        "started_at": datetime.now(UTC).isoformat(),
        "document_id": None,
        "group_count": None,
        "model": model,
        "prompt_sha256": None,
        "usage": None,
        "status": "failed",
    }
    try:
        result = _generate_group_titles(
            data,
            model=model,
            client=client,
            prompt_path=prompt_path,
            record=record,
        )
        record.update(status="success", result=result.model_dump(mode="json"))
        return result
    except Exception as exc:
        # Validation/API error messages may contain input text or credentials.
        record["error"] = {"type": type(exc).__name__, "stage": record.get("stage")}
        raise
    finally:
        record["finished_at"] = datetime.now(UTC).isoformat()
        record["elapsed_seconds"] = round(time.perf_counter() - started, 3)
        try:
            destination = (
                Path(log_path)
                if log_path is not None
                else Path(
                    os.getenv(
                        "GENERATION_LOG_PATH", str(ROOT / "logs/group_titles.jsonl")
                    )
                )
            )
            destination.parent.mkdir(parents=True, exist_ok=True)
            with destination.open("a", encoding="utf-8") as stream:
                stream.write(json.dumps(record, ensure_ascii=False) + "\n")
        except OSError:
            print("경고: 제목 생성 로그 파일을 기록하지 못했습니다.", file=sys.stderr)


def main() -> None:
    parser = argparse.ArgumentParser(description="그룹별 topic/headline 생성")
    parser.add_argument("input", type=Path)
    parser.add_argument("--model", help="GENERATION_MODEL보다 우선하는 비교용 모델")
    parser.add_argument("--log-path", type=Path, help="JSONL 로그 저장 경로")
    args = parser.parse_args()
    data = json.loads(args.input.read_text(encoding="utf-8"))
    result = generate_group_titles(data, model=args.model, log_path=args.log_path)
    print(result.model_dump_json(indent=2))


if __name__ == "__main__":
    main()
