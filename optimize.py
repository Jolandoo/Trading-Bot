# =============================================================================
# optimize.py — Optimisation des paramètres de la stratégie par grid search
# =============================================================================
# Teste toutes les combinaisons de paramètres sur des données historiques et
# classe les résultats par Sharpe ratio pour identifier la configuration optimale.
#
# Usage :
#   python optimize.py            # 12 mois de données, 4h
#   python optimize.py 24         # 24 mois de données, 4h
#   python optimize.py 12 1h      # 12 mois, timeframe 1h
#
# Résultats : top 10 configurations + tableau complet dans optimize_results.csv
# =============================================================================

import sys
import csv
import math
import itertools
import pandas as pd
import pandas_ta as ta
from datetime import datetime, timedelta

from backtest import (
    fetch_data_between,
    run_backtest,
    compute_metrics,
    INITIAL_CAPITAL, FEES,
)
from config import (
    SYMBOL, TIMEFRAME,
    RSI_PERIOD, STOP_LOSS_PCT, TAKE_PROFIT_PCT, RISK_PER_TRADE,
)

# =============================================================================
# GRILLE DE PARAMÈTRES À EXPLORER
# =============================================================================
GRID = {
    "sma_fast"         : [5, 7, 9, 12],
    "sma_slow"         : [15, 21, 30, 50],
    "rsi_overbought"   : [55, 60, 65, 70],
    "use_sma200_filter": [True, False],
}

MIN_TRADES = 3   # Ignore les configs qui génèrent trop peu de trades


# =============================================================================
# INDICATEURS PARAMÉTRABLES (pour la grille)
# =============================================================================

def _add_indicators_grid(
    df: pd.DataFrame,
    sma_fast: int,
    sma_slow: int,
) -> pd.DataFrame:
    """Calcule RSI + SMA fast/slow + SMA200 avec les paramètres de la grille."""
    df = df.copy()
    df["rsi"]      = ta.rsi(df["close"], length=RSI_PERIOD)
    df["sma_fast"] = ta.sma(df["close"], length=sma_fast)
    df["sma_slow"] = ta.sma(df["close"], length=sma_slow)
    df["sma200"]   = ta.sma(df["close"], length=200)
    df.dropna(subset=["rsi", "sma_fast", "sma_slow"], inplace=True)
    return df


# =============================================================================
# GRID SEARCH
# =============================================================================

def grid_search(df_raw: pd.DataFrame, timeframe: str = TIMEFRAME) -> list[dict]:
    """
    Teste toutes les combinaisons de la grille sur df_raw.
    Retourne la liste des résultats triée par Sharpe ratio décroissant.
    """
    keys   = list(GRID.keys())
    values = list(GRID.values())
    combos = list(itertools.product(*values))
    total  = len(combos)

    print(f"\n  {total} combinaisons à tester sur {len(df_raw)} bougies ({timeframe})…")

    results = []

    for idx, combo in enumerate(combos, 1):
        params = dict(zip(keys, combo))

        # Combinaisons invalides : sma_fast doit être strictement < sma_slow
        if params["sma_fast"] >= params["sma_slow"]:
            continue

        # Affiche la progression toutes les 10 combos
        if idx % 10 == 0 or idx == total:
            print(f"  [{idx:>3}/{total}]  SMA{params['sma_fast']}/{params['sma_slow']}  "
                  f"RSI<{params['rsi_overbought']}  SMA200={'oui' if params['use_sma200_filter'] else 'non'}", end="\r")

        df_ind = _add_indicators_grid(df_raw, params["sma_fast"], params["sma_slow"])
        if len(df_ind) < 10:
            continue

        result  = run_backtest(
            df_ind,
            initial_capital=INITIAL_CAPITAL,
            rsi_overbought=params["rsi_overbought"],
            use_sma200_filter=params["use_sma200_filter"],
        )
        metrics = compute_metrics(result, df_ind, timeframe=timeframe)

        if not metrics or metrics["total_trades"] < MIN_TRADES:
            continue

        sharpe = metrics["sharpe_ratio"]
        if math.isinf(sharpe):
            sharpe = 999.0

        results.append({
            "sma_fast"         : params["sma_fast"],
            "sma_slow"         : params["sma_slow"],
            "rsi_overbought"   : params["rsi_overbought"],
            "use_sma200_filter": params["use_sma200_filter"],
            "trades"           : metrics["total_trades"],
            "win_rate"         : metrics["win_rate"],
            "total_pnl_pct"    : metrics["total_pnl_pct"],
            "sharpe_ratio"     : round(sharpe, 3),
            "sortino_ratio"    : round(metrics["sortino_ratio"] if not math.isinf(metrics["sortino_ratio"]) else 999.0, 3),
            "max_drawdown_pct" : metrics["max_drawdown_pct"],
            "profit_factor"    : round(metrics["profit_factor"] if not math.isinf(metrics["profit_factor"]) else 999.0, 3),
            "expectancy_usdt"  : metrics["expectancy_usdt"],
        })

    print()  # Saute la ligne après la progression
    results.sort(key=lambda r: r["sharpe_ratio"], reverse=True)
    return results


# =============================================================================
# AFFICHAGE
# =============================================================================

def print_optimization_report(results: list[dict], top_n: int = 10):
    if not results:
        print("\n  Aucune configuration valide trouvée.\n")
        return

    W = 110
    print(f"\n{'=' * W}")
    print(f"  OPTIMISATION — TOP {min(top_n, len(results))} CONFIGURATIONS (classées par Sharpe)")
    print(f"{'=' * W}")
    print(
        f"  {'#':>3}  {'SMA':>8}  {'RSI<':>5}  {'SMA200':>6}  "
        f"{'Trades':>6}  {'Win%':>6}  {'PnL%':>7}  "
        f"{'Sharpe':>7}  {'Sortino':>8}  {'MaxDD%':>7}  {'PF':>6}  {'Espér.':>8}"
    )
    print(f"{'-' * W}")

    for rank, r in enumerate(results[:top_n], 1):
        sma_label  = f"{r['sma_fast']}/{r['sma_slow']}"
        sma200_lbl = "oui" if r["use_sma200_filter"] else "non"
        pnl_sign   = "+" if r["total_pnl_pct"] >= 0 else ""
        print(
            f"  {rank:>3}  {sma_label:>8}  {r['rsi_overbought']:>5}  {sma200_lbl:>6}  "
            f"{r['trades']:>6}  {r['win_rate']:>5.1f}%  "
            f"{pnl_sign}{r['total_pnl_pct']:>6.2f}%  "
            f"{r['sharpe_ratio']:>7.3f}  {r['sortino_ratio']:>8.3f}  "
            f"-{r['max_drawdown_pct']:>6.2f}%  "
            f"{r['profit_factor']:>6.2f}  "
            f"{r['expectancy_usdt']:>+8.2f}"
        )

    print(f"{'=' * W}")
    best = results[0]
    print(f"\n  Meilleure configuration :")
    print(f"    SMA_FAST         = {best['sma_fast']}")
    print(f"    SMA_SLOW         = {best['sma_slow']}")
    print(f"    RSI_OVERBOUGHT   = {best['rsi_overbought']}")
    print(f"    USE_SMA200_FILTER= {best['use_sma200_filter']}")
    print(f"    → Sharpe {best['sharpe_ratio']:.3f}  |  PnL {'+' if best['total_pnl_pct'] >= 0 else ''}{best['total_pnl_pct']:.2f}%  |  {best['trades']} trades\n")


def save_results_csv(results: list[dict], path: str = "optimize_results.csv"):
    if not results:
        return
    with open(path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=results[0].keys())
        writer.writeheader()
        writer.writerows(results)
    print(f"  Résultats complets → {path}")


# =============================================================================
# POINT D'ENTRÉE
# =============================================================================

if __name__ == "__main__":
    months    = int(sys.argv[1]) if len(sys.argv) > 1 else 12
    timeframe = sys.argv[2] if len(sys.argv) > 2 else TIMEFRAME

    start = (datetime.utcnow() - timedelta(days=30 * months)).strftime("%Y-%m-%d")
    print(f"Téléchargement {SYMBOL} ({timeframe}) — {months} mois ({start} → aujourd'hui)…")

    df_raw = fetch_data_between(timeframe, start_date=start)
    if df_raw.empty:
        print("Aucune donnée récupérée.")
        sys.exit(1)

    print(f"  → {len(df_raw)} bougies chargées")

    results = grid_search(df_raw, timeframe=timeframe)
    print_optimization_report(results)
    save_results_csv(results)
