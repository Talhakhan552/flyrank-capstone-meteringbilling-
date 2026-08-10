"""
Cost calculation. Modeled on FlyRank's chat-pricing.config.ts: pinned
constants, integer-safe math (Decimal, never float), and the three rules
that make AI token pricing tricky:

  1. Cached input tokens are billed cheaper than fresh input tokens.
  2. Reasoning tokens are billed at the OUTPUT rate — they are not a
     separate, free category.
  3. Token categories cannot just be summed and priced once; each has
     its own rate and must be priced independently, then added.

All money is expressed in integer cents at the boundary. Internal math
uses Decimal to avoid float rounding errors — see README for why floats
are banned from this codebase.
"""
from decimal import ROUND_HALF_UP, Decimal

# Pinned pricing constants — cents per 1,000,000 tokens.
TOKEN_PRICE_CENTS_PER_MILLION: dict[str, Decimal] = {
    "input": Decimal("300"),        # $3.00 / 1M fresh input tokens
    "cached_input": Decimal("75"),  # $0.75 / 1M cached input tokens (75% cheaper)
    "output": Decimal("1500"),      # $15.00 / 1M output tokens (reasoning billed here too)
}

# Pinned constant — price per metered API call.
API_CALL_PRICE_CENTS_PER_CALL = Decimal("0.1")  # $0.001 per call


def calculate_token_cost_cents(
    input_tokens: int = 0,
    cached_input_tokens: int = 0,
    output_tokens: int = 0,
    reasoning_tokens: int = 0,
) -> int:
    """
    Price each token category at its own rate, then sum. Reasoning tokens
    are folded into the output bucket before pricing — they are not a
    separate free category, and they are not priced at the input rate.
    """
    billable_output_tokens = Decimal(output_tokens) + Decimal(reasoning_tokens)

    total_cents = (
        Decimal(input_tokens) * TOKEN_PRICE_CENTS_PER_MILLION["input"]
        + Decimal(cached_input_tokens) * TOKEN_PRICE_CENTS_PER_MILLION["cached_input"]
        + billable_output_tokens * TOKEN_PRICE_CENTS_PER_MILLION["output"]
    ) / Decimal(1_000_000)

    return int(total_cents.to_integral_value(rounding=ROUND_HALF_UP))


def calculate_api_call_cost_cents(call_count: int) -> int:
    """Convert a count of metered API calls into an integer-cent cost."""
    total_cents = Decimal(call_count) * API_CALL_PRICE_CENTS_PER_CALL
    return int(total_cents.to_integral_value(rounding=ROUND_HALF_UP))
