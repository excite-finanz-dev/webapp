from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel


class HealthResponse(BaseModel):
    status: str


app = FastAPI(title="Budget Controlling API")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
    allow_methods=["GET"],
)


@app.get("/api/health", tags=["Health"])
def health() -> HealthResponse:
    return HealthResponse(status="ok")
