from fastapi import FastAPI
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

from app.routers import billing, usage, webhooks

app = FastAPI(
    title="Usage Metering & Billing Engine",
    description="Idempotent metering, quota enforcement, correct money math, Stripe test-mode billing.",
    version="1.0.0",
)

app.include_router(usage.router)
app.include_router(billing.router)
app.include_router(webhooks.router)


@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request, exc):
    # Requirement: bad input -> clean 4xx, never a 500.
    return JSONResponse(status_code=422, content={"detail": exc.errors()})


@app.get("/health")
async def health():
    return {"status": "ok"}
