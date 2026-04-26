# =============================================================================
# metrics.py — Métriques avancées de performance pour le backtesting
# =============================================================================
# Sharpe    : rendement ajusté à la volatilité totale (annualisé)
# Sortino   : comme Sharpe mais ne pénalise que la volatilité négative
# Calmar    : TCAM / drawdown maximum (robustesse long terme)
# Profit Factor : somme des gains / somme des pertes (>1 = rentable)
# =============================================================================

import numpy as np

# Nombre de bougies par an selon le timeframe (pour l'annualisation)
PERIODS_PER_YEAR: dict[str, int] = {
    "1m": 525_600, "3m": 175_200, "5m": 105_120, "15m": 35_040,
    "30m": 17_520, "1h": 8_760, "2h": 4_380, "4h": 2_190,
    "6h": 1_460, "8h": 1_095, "12h": 730, "1d": 365, "1w": 52,
}


def _returns(equity_curve: list[float]) -> np.ndarray:
    eq = np.asarray(equity_curve, dtype=float)
    return np.diff(eq) / eq[:-1]


def sharpe_ratio(
    equity_curve: list[float],
    timeframe: str = "4h",
    risk_free: float = 0.0,
) -> float:
    """Ratio de Sharpe annualisé. Négatif = stratégie sous le taux sans risque."""
    r = _returns(equity_curve)
    if len(r) < 2 or r.std() == 0:
        return 0.0
    ann = PERIODS_PER_YEAR.get(timeframe, 2190)
    per_period_rf = risk_free / ann
    return round(float((r.mean() - per_period_rf) / r.std() * np.sqrt(ann)), 3)


def sortino_ratio(
    equity_curve: list[float],
    timeframe: str = "4h",
    risk_free: float = 0.0,
) -> float:
    """Ratio de Sortino annualisé. Ignore la volatilité haussière."""
    r = _returns(equity_curve)
    downside = r[r < 0]
    ann = PERIODS_PER_YEAR.get(timeframe, 2190)
    if len(downside) == 0 or downside.std() == 0:
        return float("inf")
    per_period_rf = risk_free / ann
    return round(float((r.mean() - per_period_rf) / downside.std() * np.sqrt(ann)), 3)


def calmar_ratio(
    total_return_pct: float,
    max_drawdown_pct: float,
    years: float,
) -> float:
    """
    Calmar = TCAM (%) / Drawdown max (%).
    Un Calmar > 1 signifie que le gain annuel dépasse le risque de drawdown.
    """
    if max_drawdown_pct == 0 or years <= 0:
        return float("inf")
    cagr_pct = ((1 + total_return_pct / 100) ** (1 / years) - 1) * 100
    return round(cagr_pct / max_drawdown_pct, 3)


def profit_factor(trades: list[dict]) -> float:
    """
    Profit Factor = somme des gains / valeur absolue des pertes.
    < 1 = perdant, 1-1.5 = marginal, > 2 = excellent.
    """
    gross_profit = sum(t["pnl_usdt"] for t in trades if t["pnl_usdt"] > 0)
    gross_loss = abs(sum(t["pnl_usdt"] for t in trades if t["pnl_usdt"] < 0))
    if gross_loss == 0:
        return float("inf")
    return round(gross_profit / gross_loss, 2)


def max_consecutive_losses(trades: list[dict]) -> int:
    """Nombre maximal de pertes consécutives (risque psychologique et de drawdown)."""
    best, current = 0, 0
    for t in trades:
        if t["pnl_usdt"] <= 0:
            current += 1
            best = max(best, current)
        else:
            current = 0
    return best


def expectancy(trades: list[dict]) -> float:
    """
    Espérance mathématique par trade (USDT).
    Espérance = (win_rate × avg_win) + (loss_rate × avg_loss)
    > 0 est indispensable pour une stratégie rentable à long terme.
    """
    if not trades:
        return 0.0
    wins   = [t["pnl_usdt"] for t in trades if t["pnl_usdt"] > 0]
    losses = [t["pnl_usdt"] for t in trades if t["pnl_usdt"] <= 0]
    wr  = len(wins) / len(trades)
    lr  = 1 - wr
    avg_w = sum(wins)   / len(wins)   if wins   else 0.0
    avg_l = sum(losses) / len(losses) if losses else 0.0
    return round(wr * avg_w + lr * avg_l, 2)
