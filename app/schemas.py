from pydantic import BaseModel, Field


class TokenBreakdown(BaseModel):
    input: int = 0
    cached_input: int = 0
    output: int = 0
    reasoning: int = 0


class GenerateRequest(BaseModel):
    """The one dummy billable endpoint. usage_type decides how quantity is interpreted."""
    usage_type: str = Field(pattern="^(api_call|ai_tokens)$")
    quantity: int = Field(gt=0, description="For api_call: number of calls. For ai_tokens: total tokens (informational).")
    token_breakdown: TokenBreakdown | None = None


class GenerateResponse(BaseModel):
    usage_event_id: str
    tenant_id: str
    usage_type: str
    quantity: int
    idempotent_replay: bool
    cost_cents_for_this_event: int


class UsageResponse(BaseModel):
    tenant_id: str
    plan: str
    period: str
    api_calls_used: int
    api_calls_limit: int
    ai_tokens_used: int
    ai_tokens_limit: int
    cost_cents: int


class CheckoutRequest(BaseModel):
    price_id: str | None = None  # defaults to configured Pro price


class CheckoutResponse(BaseModel):
    checkout_url: str
    session_id: str


class ErrorResponse(BaseModel):
    detail: str
