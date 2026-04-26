# =============================================================================
# test_strategy.py — Tests unitaires du module strategy
# =============================================================================

import pytest
from strategy import Signal, check_signal


# ── Helpers ───────────────────────────────────────────────────────────────────

def _values(
    rsi: float = 50.0,
    sma_fast: float = 100.0,
    sma_slow: float = 95.0,
    prev_fast: float = 90.0,
    prev_slow: float = 95.0,
    close: float = 50_000.0,
) -> dict:
    return {
        "close"         : close,
        "rsi"           : rsi,
        "sma_fast"      : sma_fast,
        "sma_slow"      : sma_slow,
        "prev_sma_fast" : prev_fast,
        "prev_sma_slow" : prev_slow,
    }


# ── Golden Cross → BUY ────────────────────────────────────────────────────────

def test_golden_cross_generates_buy():
    """SMA rapide croise SMA lente par le haut + RSI sous le seuil → BUY."""
    v = _values(rsi=50.0, sma_fast=101.0, sma_slow=100.0, prev_fast=99.0, prev_slow=100.0)
    assert check_signal(v, in_position=False) == Signal.BUY


def test_golden_cross_blocked_by_overbought_rsi():
    """Golden Cross mais RSI suracheté (≥70) → HOLD, pas de BUY."""
    v = _values(rsi=75.0, sma_fast=101.0, sma_slow=100.0, prev_fast=99.0, prev_slow=100.0)
    assert check_signal(v, in_position=False) == Signal.HOLD


def test_no_buy_when_in_position():
    """Même un Golden Cross parfait → HOLD si déjà en position."""
    v = _values(rsi=50.0, sma_fast=101.0, sma_slow=100.0, prev_fast=99.0, prev_slow=100.0)
    assert check_signal(v, in_position=True) == Signal.HOLD


def test_no_buy_when_sma_already_crossed():
    """SMA rapide au-dessus depuis plusieurs bougies (pas de croisement) → HOLD."""
    v = _values(rsi=50.0, sma_fast=105.0, sma_slow=100.0, prev_fast=104.0, prev_slow=100.0)
    assert check_signal(v, in_position=False) == Signal.HOLD


# ── Death Cross → SELL ────────────────────────────────────────────────────────

def test_death_cross_generates_sell():
    """SMA rapide croise SMA lente par le bas en position → SELL."""
    v = _values(rsi=50.0, sma_fast=99.0, sma_slow=100.0, prev_fast=101.0, prev_slow=100.0)
    assert check_signal(v, in_position=True) == Signal.SELL


def test_rsi_overbought_generates_sell():
    """RSI > 70 en position → SELL (suracheté)."""
    v = _values(rsi=75.0, sma_fast=105.0, sma_slow=100.0, prev_fast=104.0, prev_slow=100.0)
    assert check_signal(v, in_position=True) == Signal.SELL


def test_no_sell_when_not_in_position():
    """Death Cross sans être en position → HOLD (pas de position à fermer)."""
    v = _values(rsi=50.0, sma_fast=99.0, sma_slow=100.0, prev_fast=101.0, prev_slow=100.0)
    assert check_signal(v, in_position=False) == Signal.HOLD


# ── HOLD ──────────────────────────────────────────────────────────────────────

def test_hold_when_no_signal():
    """SMA rapide en dessous, pas de croisement, RSI neutre → HOLD."""
    v = _values(rsi=50.0, sma_fast=95.0, sma_slow=100.0, prev_fast=94.0, prev_slow=100.0)
    assert check_signal(v, in_position=False) == Signal.HOLD


def test_hold_in_position_no_exit_condition():
    """En position, RSI neutre, pas de death cross → HOLD."""
    v = _values(rsi=55.0, sma_fast=105.0, sma_slow=100.0, prev_fast=104.0, prev_slow=100.0)
    assert check_signal(v, in_position=True) == Signal.HOLD


# ── Signal enum ───────────────────────────────────────────────────────────────

def test_signal_values_are_strings():
    assert Signal.BUY.value  == "BUY"
    assert Signal.SELL.value == "SELL"
    assert Signal.HOLD.value == "HOLD"
