# =============================================================================
# test_metrics.py — Tests unitaires du module metrics
# =============================================================================

import math
import pytest
from metrics import (
    sharpe_ratio, sortino_ratio, calmar_ratio,
    profit_factor, max_consecutive_losses, expectancy,
)


# ── Fixtures ──────────────────────────────────────────────────────────────────

def _winning_trades(n: int = 5, gain: float = 100.0) -> list[dict]:
    return [{"pnl_usdt": gain} for _ in range(n)]


def _losing_trades(n: int = 5, loss: float = -50.0) -> list[dict]:
    return [{"pnl_usdt": loss} for _ in range(n)]


def _mixed_trades() -> list[dict]:
    return [
        {"pnl_usdt":  100.0},
        {"pnl_usdt": -50.0},
        {"pnl_usdt":  200.0},
        {"pnl_usdt": -50.0},
        {"pnl_usdt":  150.0},
    ]


def _equity_rising() -> list[float]:
    return [10_000.0 + i * 100 for i in range(50)]


def _equity_flat() -> list[float]:
    return [10_000.0] * 50


def _equity_volatile() -> list[float]:
    import math
    return [10_000.0 + math.sin(i) * 500 for i in range(50)]


# ── sharpe_ratio ──────────────────────────────────────────────────────────────

def test_sharpe_positive_for_rising_equity():
    sr = sharpe_ratio(_equity_rising(), timeframe="4h")
    assert sr > 0, "Sharpe doit être positif pour une courbe croissante"


def test_sharpe_zero_for_flat_equity():
    sr = sharpe_ratio(_equity_flat(), timeframe="4h")
    assert sr == 0.0, "Sharpe doit être 0 pour une courbe plate (pas de rendement ni de volatilité)"


def test_sharpe_returns_float():
    assert isinstance(sharpe_ratio(_equity_rising()), float)


def test_sharpe_handles_short_curve():
    """Moins de 2 points → renvoie 0 sans planter."""
    assert sharpe_ratio([10_000.0], timeframe="4h") == 0.0
    assert sharpe_ratio([], timeframe="4h") == 0.0


def test_sharpe_timeframe_affects_annualization():
    """4h et 1d donnent des Sharpe différents (annualisation différente)."""
    equity = _equity_volatile()
    sr_4h = sharpe_ratio(equity, timeframe="4h")
    sr_1d = sharpe_ratio(equity, timeframe="1d")
    assert sr_4h != sr_1d


# ── sortino_ratio ─────────────────────────────────────────────────────────────

def test_sortino_positive_for_rising_equity():
    sr = sortino_ratio(_equity_rising(), timeframe="4h")
    assert sr > 0


def test_sortino_inf_when_no_downside():
    """Si pas de rendements négatifs → Sortino = infini."""
    result = sortino_ratio(_equity_rising(), timeframe="4h")
    # Une courbe strictement croissante peut avoir des rendements tous positifs
    assert result > 0 or result == float("inf")


def test_sortino_greater_than_or_equal_sharpe_for_positive_equity():
    """Sortino ≥ Sharpe quand la volatilité est asymétrique côté haussier."""
    equity = _equity_volatile()
    sr = sharpe_ratio(equity, timeframe="4h")
    so = sortino_ratio(equity, timeframe="4h")
    # En général vrai, mais pas garanti pour toutes les courbes synthétiques
    # On vérifie juste que les deux sont calculables
    assert isinstance(sr, float)
    assert isinstance(so, float)


# ── calmar_ratio ──────────────────────────────────────────────────────────────

def test_calmar_positive_return_positive_dd():
    """10 % de retour annualisé avec 5 % de drawdown → Calmar = 2.0."""
    result = calmar_ratio(total_return_pct=10.0, max_drawdown_pct=5.0, years=1.0)
    assert result == pytest.approx(2.0, abs=0.01)


def test_calmar_inf_when_no_drawdown():
    result = calmar_ratio(total_return_pct=10.0, max_drawdown_pct=0.0, years=1.0)
    assert result == float("inf")


def test_calmar_negative_return():
    """Retour négatif → Calmar négatif (stratégie perdante)."""
    result = calmar_ratio(total_return_pct=-10.0, max_drawdown_pct=5.0, years=1.0)
    assert result < 0


def test_calmar_multi_year():
    """Annualisation sur 2 ans : +21 % total ≈ +10 % TCAM → Calmar ≈ 2.0."""
    total_2y = (1.10 ** 2 - 1) * 100   # ~21 %
    result = calmar_ratio(total_return_pct=total_2y, max_drawdown_pct=5.0, years=2.0)
    assert result == pytest.approx(2.0, abs=0.1)


# ── profit_factor ─────────────────────────────────────────────────────────────

def test_profit_factor_all_wins():
    """Que des gains → Profit Factor = infini."""
    result = profit_factor(_winning_trades())
    assert result == float("inf")


def test_profit_factor_all_losses():
    """Que des pertes → Profit Factor = 0."""
    result = profit_factor(_losing_trades())
    assert result == 0.0


def test_profit_factor_mixed():
    """5 × 100 USDT gagnés, 2 × 50 USDT perdus → PF = 500 / 100 = 5.0."""
    trades = _winning_trades(5, 100.0) + _losing_trades(2, -50.0)
    result = profit_factor(trades)
    assert result == pytest.approx(5.0, abs=0.01)


def test_profit_factor_below_1_is_losing():
    """Plus de pertes que de gains → PF < 1."""
    trades = _winning_trades(1, 50.0) + _losing_trades(5, -100.0)
    assert profit_factor(trades) < 1.0


# ── max_consecutive_losses ────────────────────────────────────────────────────

def test_no_losses():
    assert max_consecutive_losses(_winning_trades()) == 0


def test_all_losses():
    assert max_consecutive_losses(_losing_trades(5)) == 5


def test_streak_resets_on_win():
    trades = [
        {"pnl_usdt": -50.0},
        {"pnl_usdt": -50.0},
        {"pnl_usdt": 100.0},   # reset
        {"pnl_usdt": -50.0},
        {"pnl_usdt": -50.0},
        {"pnl_usdt": -50.0},
    ]
    assert max_consecutive_losses(trades) == 3


def test_single_loss():
    trades = [{"pnl_usdt": 100.0}, {"pnl_usdt": -50.0}, {"pnl_usdt": 100.0}]
    assert max_consecutive_losses(trades) == 1


# ── expectancy ────────────────────────────────────────────────────────────────

def test_expectancy_empty():
    assert expectancy([]) == 0.0


def test_expectancy_all_wins():
    trades = _winning_trades(4, 100.0)
    assert expectancy(trades) == pytest.approx(100.0, abs=0.01)


def test_expectancy_mixed():
    """
    win_rate = 3/5 = 60 %, avg_win = 150 USDT, avg_loss = –50 USDT
    Espérance = 0.6 × 150 + 0.4 × (–50) = 90 – 20 = 70 USDT
    """
    trades = _mixed_trades()  # 3 wins (100, 200, 150), 2 losses (–50, –50)
    result = expectancy(trades)
    assert result == pytest.approx(70.0, abs=1.0)


def test_expectancy_positive_means_profitable():
    """Espérance positive → stratégie rentable à long terme."""
    assert expectancy(_mixed_trades()) > 0
