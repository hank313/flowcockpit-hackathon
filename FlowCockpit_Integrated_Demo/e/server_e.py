"""FlowCockpit E：可選的雲端比較服務。沒有 API Key 或斷網時安全回傳 local_only。"""

from typing import Any

from fastapi import FastAPI
from pydantic import BaseModel, Field

from cloud_enhance import MODEL_NAME, get_comparison


class CompareRequest(BaseModel):
    task_id: str
    base_version: int = Field(ge=0)
    candidates: list[dict[str, Any]]
    conditions: dict[str, Any]
    raw_text: str | None = None


app = FastAPI(title="FlowCockpit Cloud Enhancement Module E")


@app.get("/health")
def health():
    import os

    return {
        "status": "ready" if os.getenv("ANTHROPIC_API_KEY") else "offline_only",
        "model": MODEL_NAME,
    }


@app.post("/api/compare")
def compare(request: CompareRequest):
    text = get_comparison(request.candidates, request.conditions, request.raw_text)
    return {
        "task_id": request.task_id,
        "base_version": request.base_version,
        "comparison_text": text,
        "status": "enhanced" if text else "local_only",
    }
