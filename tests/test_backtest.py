# =============================================================================
# test_backtest.py — Tests unitaires du moteur de backtesting
# =============================================================================
# On crée des DataFrames synthétiques avec des signaux connus pour vérifier
# que le moteur génère le bon nombre de trades et les bonnes métriques.
# =============================================================================

import pytest
import pandas as pd
import numpy as np
from backtest import run_backtest, compute_metrics, add_indicators, INITIAL_CAPITAL, FEES


# ── Helpers ───────────────────────────────────────────────────────────────────

def _make_df(n: int = 300, base_price: float = 80_000.0) -> pd.DataFrame:
    """Crée un DataFrame OHLCV neutre (prix flat) avec indicateurs précalculés."""
    idx = pd.date_range("2025-01-01", periods=n, freq="4h")
    df = pd.DataFrame({
        "open"     : base_price,
        "high"     : base_price * 1.005,
        "low"      : base_price * 0.995,
        "close"    : base_price,
        "volume"   : 100.0,
        "rsi"      : 50.0,
        "sma_fast" : base_price,
        "sma_slow" : base_price,
        "sma200"   : base_price,
    }, index=idx)
    return df


def _make_golden_cross_df(cross_at: int = 50, n: int = 200) -> pd.DataFrame:
    """
    Crée un DataFrame avec un Golden Cross à la bougie `cross_at` :
    - avant le croisement : sma_fast < sma_slow
    - à partir de cross_at : sma_fast > sma_slow
    RSI = 50 (sous le seuil d'overbought), donc le signal BUY doit se déclencher.
    """
    idx = pd.date_range("2025-01-01", periods=n, freq="4h")
    price = 80_000.0
    sma_fast = np.where(np.arange(n) < cross_at, price - 100, price + 100)
    sma_slow = np.full(n, price)

    df = pd.DataFrame({
        "open"     : price,
        "high"     : price * 1.10,   # High loin pour que le TP puisse se déclencher
        "low"      : price * 0.98,   # Low au-dessus du SL (–3 %)
        "close"    : price,
        "volume"   : 100.0,
        "rsi"      : 50.0,
        "sma_fast" : sma_fast.astype(float),
        "sma_slow" : sma_slow.astype(float),
        "sma200"   : (sma_slow * 0.9).astype(float),  # sous le prix → filtre SMA200 passe
    }, index=idx)
    return df


# ── run_backtest — structure de sortie ────────────────────────────────────────

def test_run_backtest_returns_required_keys():
    df = _make_df()
    result = run_backtest(df)
    assert "trades"        in result
    assert "equity_curve"  in result
    assert "final_capital" in result


def test_equity_curve_starts_at_initial_capital():
    df = _make_df()
    result = run_backtest(df, initial_capital=10_000.0)
    assert result["equity_curve"][0] == pytest.approx(10_000.0)


def test_equity_curve_length_equals_candle_count():
    n = 200
    df = _make_df(n=n)
    result = run_backtest(df)
    # 1 valeur initiale + 1 par bougie (i de 1 à n-1)
    assert len(result["equity_curve"]) == n


def test_no_trades_on_flat_market():
    """Marché totalement plat (sma_fast == sma_slow partout) → aucun trade."""
    df = _make_df()
    result = run_backtest(df)
    assert result["trades"] == []


def test_golden_cross_generates_at_least_one_trade():
    """Un Golden Cross avec RSI neutre doit générer au moins un trade."""
    df = _make_golden_cross_df()
    result = run_backtest(df)
    assert len(result["trades"]) >= 1


def test_trade_has_required_fields():
    df = _make_golden_cross_df()
    result = run_backtest(df)
    if result["trades"]:
        trade = result["trades"][0]
        for field in ["entry_date", "entry", "exit", "pnl_pct", "pnl_usdt", "reason"]:
            assert field in trade, f"Champ '{field}' manquant dans le trade"


def test_capital_is_positive_after_backtest():
    df = _make_golden_cross_df()
    result = run_backtest(df)
    assert result["final_capital"] > 0


# ── compute_metrics ───────────────────────────────────────────────────────────

def test_compute_metrics_returns_empty_for_no_trades():
    df = _make_df()
    result = run_backtest(df)
    metrics = compute_metrics(result, df)
    assert metrics == {}


def test_compute_metrics_all_keys_present():
    df = _make_golden_cross_df()
    result = run_backtest(df)
    if not result["trades"]:
        pytest.skip("Pas de trades générés sur ce jeu de données synthétique")

    metrics = compute_metrics(result, df)
    expected_keys = [
        "total_trades", "win_rate", "total_pnl_usdt", "total_pnl_pct",
        "avg_win_usdt", "avg_loss_usdt", "max_drawdown_pct", "buy_hold_pct",
        "final_capital", "sharpe_ratio", "sortino_ratio", "calmar_ratio",
        "profit_factor", "max_consecutive_losses", "expectancy_usdt",
    ]
    for key in expected_keys:
        assert key in metrics, f"Clé '{key}' absente des métriques"


def test_win_rate_between_0_and_100():
    df = _make_golden_cross_df()
    result = run_backtest(df)
    if not result["trades"]:
        pytest.skip("Pas de trades")
    metrics = compute_metrics(result, df)
    assert 0 <= metrics["win_rate"] <= 100


def test_max_drawdown_non_negative():
    df = _make_golden_cross_df()
    result = run_backtest(df)
    if not result["trades"]:
        pytest.skip("Pas de trades")
    metrics = compute_metrics(result, df)
    assert metrics["max_drawdown_pct"] >= 0


def test_take_profit_trade_has_positive_pnl():
    """Un trade qui sort sur TAKE_PROFIT doit avoir un PnL positif."""
    df = _make_golden_cross_df()
    result = run_backtest(df)
    tp_trades = [t for t in result["trades"] if t["reason"] == "TAKE_PROFIT"]
    for t in tp_trades:
        assert t["pnl_usdt"] > 0, "Un TAKE_PROFIT doit générer un gain"


def test_stop_loss_trade_has_negative_pnl():
    """Un trade qui sort sur STOP_LOSS doit avoir un PnL négatif."""
    # On construit un DF où le low touche toujours le SL
    idx = pd.date_range("2025-01-01", periods=200, freq="4h")
    price = 80_000.0
    n = 200
    cross_at = 50
    sma_fast = np.where(np.arange(n) < cross_at, price - 100, price + 100).astype(float)
    sma_slow = np.full(n, price, dtype=float)

    df = pd.DataFrame({
        "open"     : price,
        "high"     : price * 1.01,   # High bas → TP impossible
        "low"      : price * 0.96,   # Low bas → SL à –3 % déclenché
        "close"    : price,
        "volume"   : 100.0,
        "rsi"      : 50.0,
        "sma_fast" : sma_fast,
        "sma_slow" : sma_slow,
        "sma200"   : sma_slow * 0.9,  # sous le prix → filtre SMA200 passe
    }, index=idx)

    result = run_backtest(df)
    sl_trades = [t for t in result["trades"] if t["reason"] == "STOP_LOSS"]
    for t in sl_trades:
        assert t["pnl_usdt"] < 0, "Un STOP_LOSS doit générer une perte"
