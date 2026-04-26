# =============================================================================
# test_risk.py — Tests unitaires du module risk
# =============================================================================

import pytest
from risk import calculate_position, check_exit_conditions


# ── calculate_position ────────────────────────────────────────────────────────

def test_position_size_math():
    """
    Avec 10 000 USDT, risque 1 %, SL 3 % :
    risk_usdt = 100 → position = 100 / 0.03 = 3 333.33 USDT
    """
    result = calculate_position(capital_usdt=10_000.0, entry_price=50_000.0)
    assert result["risk_usdt"]     == pytest.approx(100.0,    abs=0.01)
    assert result["position_usdt"] == pytest.approx(3_333.33, abs=1.0)


def test_position_never_exceeds_95_percent_of_capital():
    """Avec un capital très élevé le cap à 95 % doit s'appliquer."""
    result = calculate_position(capital_usdt=1_000_000.0, entry_price=50_000.0)
    assert result["position_usdt"] <= 1_000_000.0 * 0.95


def test_stop_loss_and_take_profit_levels():
    """SL à –3 % et TP à +6 % depuis le prix d'entrée."""
    result = calculate_position(capital_usdt=10_000.0, entry_price=100_000.0)
    assert result["stop_loss"]   == pytest.approx(100_000.0 * 0.97, abs=1.0)
    assert result["take_profit"] == pytest.approx(100_000.0 * 1.06, abs=1.0)


def test_btc_amount_consistent():
    """position_btc doit correspondre à position_usdt / entry_price."""
    entry = 80_000.0
    result = calculate_position(capital_usdt=10_000.0, entry_price=entry)
    expected_btc = result["position_usdt"] / entry
    assert result["position_btc"] == pytest.approx(expected_btc, rel=1e-4)


def test_rr_ratio():
    """R:R ratio doit être TAKE_PROFIT_PCT / STOP_LOSS_PCT = 2.0."""
    result = calculate_position(capital_usdt=10_000.0, entry_price=50_000.0)
    assert result["rr_ratio"] == pytest.approx(2.0, abs=0.05)


# ── check_exit_conditions ─────────────────────────────────────────────────────

def test_stop_loss_triggered():
    """Prix sous le stop-loss → 'STOP_LOSS'."""
    reason = check_exit_conditions(
        entry_price   = 100_000.0,
        current_price = 96_000.0,
        stop_loss     = 97_000.0,
        take_profit   = 106_000.0,
    )
    assert reason == "STOP_LOSS"


def test_take_profit_triggered():
    """Prix au-dessus du take-profit → 'TAKE_PROFIT'."""
    reason = check_exit_conditions(
        entry_price   = 100_000.0,
        current_price = 107_000.0,
        stop_loss     = 97_000.0,
        take_profit   = 106_000.0,
    )
    assert reason == "TAKE_PROFIT"


def test_hold_when_between_sl_and_tp():
    """Prix dans la plage SL/TP → None (on reste en position)."""
    reason = check_exit_conditions(
        entry_price   = 100_000.0,
        current_price = 102_000.0,
        stop_loss     = 97_000.0,
        take_profit   = 106_000.0,
    )
    assert reason is None


def test_stop_loss_at_exact_level():
    """Le stop se déclenche exactement au niveau SL (bord ≤)."""
    reason = check_exit_conditions(
        entry_price   = 100_000.0,
        current_price = 97_000.0,
        stop_loss     = 97_000.0,
        take_profit   = 106_000.0,
    )
    assert reason == "STOP_LOSS"


def test_take_profit_at_exact_level():
    """Le TP se déclenche exactement au niveau TP (bord ≥)."""
    reason = check_exit_conditions(
        entry_price   = 100_000.0,
        current_price = 106_000.0,
        stop_loss     = 97_000.0,
        take_profit   = 106_000.0,
    )
    assert reason == "TAKE_PROFIT"
