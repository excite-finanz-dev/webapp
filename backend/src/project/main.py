from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from budgets import router as budget_router


class HealthResponse(BaseModel):
    status: str


app = FastAPI(title="Budget Controlling API")
app.include_router(budget_router)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
    allow_methods=["GET", "POST", "PUT", "PATCH"],
)


@app.get("/api/health", tags=["Health"])
def health() -> HealthResponse:
    return HealthResponse(status="ok")
