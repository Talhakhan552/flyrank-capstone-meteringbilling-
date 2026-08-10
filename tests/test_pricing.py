"""
Pinned cost-calculation tests. These numbers are the contract — if a
pricing constant changes, these tests change with it, deliberately and
visibly, never silently.
"""
from app.services.pricing import calculate_api_call_cost_cents, calculate_token_cost_cents


def test_fresh_input_tokens_priced_at_input_rate():
    # 1,000,000 input tokens @ $3.00/1M = 300 cents
    assert calculate_token_cost_cents(input_tokens=1_000_000) == 300


def test_cached_input_tokens_are_cheaper_than_fresh_input():
    fresh = calculate_token_cost_cents(input_tokens=1_000_000)
    cached = calculate_token_cost_cents(cached_input_tokens=1_000_000)
    assert cached < fresh
    assert cached == 75  # $0.75/1M


def test_reasoning_tokens_billed_at_output_rate_not_input_rate():
    output_only = calculate_token_cost_cents(output_tokens=500_000)
    reasoning_only = calculate_token_cost_cents(reasoning_tokens=500_000)
    # Reasoning tokens must cost exactly what the same quantity of output
    # tokens would cost — they are the same bucket, not a separate rate.
    assert output_only == reasoning_only == 750  # 500k * $15/1M


def test_reasoning_and_output_tokens_combine_in_the_same_bucket():
    combined = calculate_token_cost_cents(output_tokens=250_000, reasoning_tokens=250_000)
    single_bucket = calculate_token_cost_cents(output_tokens=500_000)
    assert combined == single_bucket == 750


def test_categories_are_priced_independently_then_summed_not_flat_rate():
    # 200k input + 800k cached_input + 100k output + 50k reasoning
    # = (200000*300 + 800000*75 + 150000*1500) / 1_000_000
    # = (60,000,000 + 60,000,000 + 225,000,000) / 1,000,000 = 345 cents
    cost = calculate_token_cost_cents(
        input_tokens=200_000,
        cached_input_tokens=800_000,
        output_tokens=100_000,
        reasoning_tokens=50_000,
    )
    assert cost == 345


def test_zero_usage_costs_nothing():
    assert calculate_token_cost_cents() == 0


def test_small_token_counts_round_half_up_not_truncated():
    # 3 input tokens * 300 cents / 1_000_000 = 0.0009 cents -> rounds to 0
    assert calculate_token_cost_cents(input_tokens=3) == 0
    # 1700 input tokens * 300 / 1_000_000 = 0.51 cents -> rounds to 1
    assert calculate_token_cost_cents(input_tokens=1700) == 1


def test_api_call_cost_is_linear_and_pinned():
    # $0.001/call -> 1000 calls = 100 cents = $1.00
    assert calculate_api_call_cost_cents(1000) == 100
    assert calculate_api_call_cost_cents(0) == 0
    assert calculate_api_call_cost_cents(1) == 0  # 0.1 cents rounds down to 0 for a single call
    assert calculate_api_call_cost_cents(5) == 1   # 0.5 cents rounds up to 1
