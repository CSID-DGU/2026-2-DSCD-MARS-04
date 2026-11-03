"""FastAPI 앱. 실행: uvicorn backend.main:app --reload (레포 루트에서)"""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Annotated

from fastapi import BackgroundTasks, Body, Depends, FastAPI, Query, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from backend.core.responses import ApiError, api_error_handler, ok, validation_error_handler
from backend.core.store import Store
from backend.services import workflow as wf
from backend.services.pipeline import Pipeline, RepoPipeline

ROOT = Path(__file__).resolve().parents[1]
LAYOUTS_PATH = ROOT / "data" / "layouts.json"
BASE = "/api/v1"


def create_app(store: Store | None = None, pipeline: Pipeline | None = None) -> FastAPI:
    app = FastAPI(title="CardSync API", version="0.1.0", docs_url="/docs")
    app.state.store = store or Store(
        os.getenv("CARDSYNC_DB_PATH", str(ROOT / "data" / "outputs" / "cardsync.db"))
    )
    app.state.pipeline = pipeline or RepoPipeline()
    app.state.layouts = json.loads(LAYOUTS_PATH.read_text(encoding="utf-8"))
    app.add_exception_handler(ApiError, api_error_handler)
    app.add_exception_handler(RequestValidationError, validation_error_handler)
    origins = os.getenv("CARDSYNC_CORS_ORIGINS", "http://localhost:5173").split(",")
    app.add_middleware(
        CORSMiddleware, allow_origins=origins, allow_methods=["*"], allow_headers=["*"]
    )
    register(app)
    return app


def store_of(request: Request) -> Store:
    return request.app.state.store


def pipeline_of(request: Request) -> Pipeline:
    return request.app.state.pipeline


StoreDep = Annotated[Store, Depends(store_of)]
PipelineDep = Annotated[Pipeline, Depends(pipeline_of)]


class DocumentIn(BaseModel):
    text: str
    title: str | None = None
    source_url: str | None = None
    source_name: str | None = None
    license: str | None = None


class SelectionIn(BaseModel):
    required_group_ids: list[str]


class CheckIn(BaseModel):
    card_ids: list[str] | None = None


def register(app: FastAPI) -> None:
    @app.get(f"{BASE}/health", tags=["System"], summary="서버 상태 확인")
    def health():
        return ok(
            "서버가 정상입니다.",
            {"status": "ok", "openai_key_configured": bool(os.getenv("OPENAI_API_KEY"))},
        )

    @app.get(f"{BASE}/layouts", tags=["Layout"], summary="레이아웃 정의 조회")
    def layouts(request: Request):
        return ok("레이아웃 정의를 조회했습니다.", request.app.state.layouts)

    @app.post(
        f"{BASE}/documents", tags=["Document"], summary="원문 등록 및 분석 시작", status_code=202
    )
    def create_document(
        body: DocumentIn,
        tasks: BackgroundTasks,
        store: StoreDep,
        pipeline: PipelineDep,
    ):
        doc, job = wf.create_document(store, body.model_dump())
        tasks.add_task(
            wf.run_job, store, job, wf.analysis_work(store, pipeline, doc["document_id"])
        )
        data = {"document_id": doc["document_id"], "job_id": job["job_id"], "status": "analyzing"}
        return ok("원문 분석을 시작했습니다.", data, 202)

    @app.get(f"{BASE}/jobs/{{job_id}}", tags=["Job"], summary="작업 상태 조회")
    def get_job(job_id: str, store: StoreDep):
        job = store.get_job(job_id)
        if job is None:
            raise ApiError(404, "존재하지 않는 작업입니다.")
        keys = ("job_id", "kind", "status", "stage", "document_id", "error", "elapsed_seconds")
        return ok("작업 상태를 조회했습니다.", {k: job[k] for k in keys})

    @app.get(f"{BASE}/documents/{{document_id}}", tags=["Document"], summary="원문·정보 묶음 조회")
    def get_document(document_id: str, store: StoreDep):
        doc = wf.require_document(store, document_id, analyzed=True)
        return ok("문서를 조회했습니다.", wf.doc_view(doc))

    @app.put(
        f"{BASE}/documents/{{document_id}}/selection",
        tags=["Selection"],
        summary="카드에 담을 정보 묶음 저장",
    )
    def put_selection(document_id: str, body: SelectionIn, store: StoreDep):
        data = wf.save_selection(store, document_id, body.required_group_ids)
        return ok("선택한 정보 묶음을 저장했습니다.", data)

    @app.post(
        f"{BASE}/documents/{{document_id}}/cards",
        tags=["Card"],
        summary="카드뉴스 생성 시작",
        status_code=202,
    )
    def create_cards(
        document_id: str,
        tasks: BackgroundTasks,
        store: StoreDep,
        pipeline: PipelineDep,
        overwrite: Annotated[bool, Query()] = False,
    ):
        job = wf.start_generation(store, document_id, overwrite)
        tasks.add_task(wf.run_job, store, job, wf.generation_work(store, pipeline, document_id))
        data = {"document_id": document_id, "job_id": job["job_id"], "status": "generating"}
        return ok("카드 생성을 시작했습니다.", data, 202)

    @app.get(f"{BASE}/documents/{{document_id}}/cards", tags=["Card"], summary="카드 목록 조회")
    def list_cards(document_id: str, store: StoreDep):
        wf.require_document(store, document_id)
        cards = [wf.card_view(store, c) for c in store.list_cards(document_id)]
        return ok("카드 목록을 조회했습니다.", {"cards": cards})

    @app.patch(
        f"{BASE}/documents/{{document_id}}/cards/{{card_id}}",
        tags=["Card"],
        summary="카드 문구 수정",
    )
    def patch_card(
        document_id: str,
        card_id: str,
        request: Request,
        body: Annotated[dict, Body()],
        store: StoreDep,
    ):
        card = wf.update_card(store, document_id, card_id, body, request.app.state.layouts)
        return ok("카드를 수정했습니다.", {"card": card})

    @app.post(
        f"{BASE}/documents/{{document_id}}/checks",
        tags=["Check"],
        summary="카드 사실성 검사 시작",
        status_code=202,
    )
    def create_checks(
        document_id: str,
        tasks: BackgroundTasks,
        store: StoreDep,
        pipeline: PipelineDep,
        body: Annotated[CheckIn | None, Body()] = None,
    ):
        job, card_ids = wf.start_check(store, document_id, body.card_ids if body else None)
        tasks.add_task(
            wf.run_job, store, job, wf.check_work(store, pipeline, document_id, card_ids)
        )
        return ok("카드 검사를 시작했습니다.", {"job_id": job["job_id"], "card_ids": card_ids}, 202)

    @app.post(
        f"{BASE}/documents/{{document_id}}/cards/{{card_id}}/repair",
        tags=["Check"],
        summary="AI 수정안 생성 (준비 중)",
    )
    def repair(document_id: str, card_id: str, store: StoreDep):
        wf.find_card(store, document_id, card_id)
        raise ApiError(501, "수정안 기능은 아직 준비되지 않았습니다.")

    @app.get(
        f"{BASE}/documents/{{document_id}}/record", tags=["Export"], summary="검수 기록 내보내기"
    )
    def record(document_id: str, store: StoreDep):
        response = ok("검수 기록을 만들었습니다.", wf.build_record(store, document_id))
        name = f"CardSync-{document_id}-record.json"
        response.headers["Content-Disposition"] = f'attachment; filename="{name}"'
        return response

    @app.get(
        f"{BASE}/documents/{{document_id}}/cards/{{card_id}}/png",
        tags=["Export"],
        summary="카드 PNG 내보내기 (준비 중)",
    )
    def png(document_id: str, card_id: str, store: StoreDep):
        wf.find_card(store, document_id, card_id)
        raise ApiError(501, "서버 렌더링은 아직 준비되지 않았습니다.")


class _LazyApp:
    """import만으로 DB 파일이 생기지 않게 첫 요청 때 앱을 만든다."""

    _app: FastAPI | None = None

    async def __call__(self, scope, receive, send):
        if self._app is None:
            self._app = create_app()
        await self._app(scope, receive, send)


app = _LazyApp()

__all__ = ["create_app", "app"]
