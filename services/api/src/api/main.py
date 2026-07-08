from __future__ import annotations

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from api.models import AnalyzeRequest, AnalyzeResponse, CollectRequest, CollectResponse
from api.services import analyze_service, collect_service

app = FastAPI(title="SAG API")


@app.exception_handler(RuntimeError)
async def runtime_error_handler(_: Request, exc: RuntimeError) -> JSONResponse:
    return JSONResponse(status_code=500, content={"detail": str(exc)})


@app.post("/collect", response_model=CollectResponse)
def collect(request: CollectRequest) -> dict:
    return collect_service(request)


@app.post("/analyze", response_model=AnalyzeResponse)
def analyze(request: AnalyzeRequest) -> dict:
    return analyze_service(request)
