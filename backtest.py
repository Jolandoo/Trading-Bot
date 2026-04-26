# =============================================================================
# backtest.py — Backtesting de la stratégie sur données historiques
# =============================================================================
# Télécharge 1 an de bougies BTC/USDT depuis Binance et simule chaque trade.
#
# Métriques calculées :
#   - PnL total et par trade
#   - Win rate, ratio gain/perte
#   - Drawdown maximum
#   - Sharpe ratio, Sortino ratio, Calmar ratio
#   - Profit Factor, Espérance par trade
#   - Pertes consécutives maximales
#   - Comparaison vs Buy & Hold
#
# Analyses disponibles :
#   - Backtest standard (période complète)
#   - Walk-Forward Analysis (découpe en N fenêtres indépendantes)
# =============================================================================

import ccxt
import pandas as pd
import pandas_ta as ta
from datetime import datetime, timedelta
from config import (
    SYMBOL, TIMEFRAME,
    RSI_PERIOD, SMA_FAST, SMA_SLOW, RSI_OVERBOUGHT,
    STOP_LOSS_PCT, TAKE_PROFIT_PCT, RISK_PER_TRADE,
)
import metrics as mt

# =============================================================================
# PARAMÈTRES DU BACKTEST
# =============================================================================
INITIAL_CAPITAL = 10_000   # USDT de départ
MONTHS_BACK     = 12       # Mois d'historique
FEES            = 0.001    # 0.1 % de frais Binance par trade
WF_SPLITS       = 3        # Nombre de fenêtres pour le walk-forward


# =============================================================================
# 1. RÉCUPÉRATION DES DONNÉES HISTORIQUES
# =============================================================================

def fetch_historical_data() -> pd.DataFrame:
    """
    Télécharge les bougies historiques depuis Binance public (sans clé API).
    """
    print(f"Téléchargement des données {SYMBOL} ({TIMEFRAME}) — {MONTHS_BACK} mois...")

    exchange = ccxt.binance({"enableRateLimit": True})
    since = exchange.parse8601(
        (datetime.utcnow() - timedelta(days=30 * MONTHS_BACK)).strftime("%Y-%m-%dT00:00:00Z")
    )

    all_candles = []
    while True:
        candles = exchange.fetch_ohlcv(SYMBOL, timeframe=TIMEFRAME, since=since, limit=1000)
        if not candles:
            break
        all_candles.extend(candles)
        since = candles[-1][0] + 1
        if candles[-1][0] >= exchange.milliseconds() - 2 * 3600 * 1000:
            break

    df = pd.DataFrame(all_candles, columns=["timestamp", "open", "high", "low", "close", "volume"])
    df["timestamp"] = pd.to_datetime(df["timestamp"], unit="ms")
    df.set_index("timestamp", inplace=True)
    df.drop_duplicates(inplace=True)

    print(f"  -> {len(df)} bougies récupérées ({df.index[0].date()} -> {df.index[-1].date()})")
    return df


# =============================================================================
# 2. CALCUL DES INDICATEURS
# =============================================================================

def add_indicators(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()
    df["rsi"]      = ta.rsi(df["close"], length=RSI_PERIOD)
    df["sma_fast"] = ta.sma(df["close"], length=SMA_FAST)
    df["sma_slow"] = ta.sma(df["close"], length=SMA_SLOW)
    df["sma200"]   = ta.sma(df["close"], length=200)
    df.dropna(inplace=True)
    return df


# =============================================================================
# 3. MOTEUR DE SIMULATION
# =============================================================================

def run_backtest(df: pd.DataFrame, initial_capital: float = INITIAL_CAPITAL) -> dict:
    """
    Simule le bot trade par trade sur toutes les bougies historiques.
    Retourne les trades réalisés et la courbe d'équité.
    """
    capital      = float(initial_capital)
    in_position  = False
    entry_price  = 0.0
    btc_held     = 0.0
    stop_loss    = 0.0
    take_profit  = 0.0
    trades       = []
    equity_curve = [capital]

    for i in range(1, len(df)):
        row  = df.iloc[i]
        prev = df.iloc[i - 1]

        price      = float(row["close"])
        rsi        = float(row["rsi"])
        sma_fast   = float(row["sma_fast"])
        sma_slow   = float(row["sma_slow"])
        prev_fast  = float(prev["sma_fast"])
        prev_slow  = float(prev["sma_slow"])

        # ── Vérification SL/TP sur le high/low de la bougie (plus réaliste) ─
        if in_position:
            exit_reason = None

            if float(row["low"]) <= stop_loss:
                exit_reason = "STOP_LOSS"
                exit_price  = stop_loss
            elif float(row["high"]) >= take_profit:
                exit_reason = "TAKE_PROFIT"
                exit_price  = take_profit

            if exit_reason:
                pnl_pct  = (exit_price - entry_price) / entry_price
                proceeds = btc_held * exit_price * (1 - FEES)
                capital += proceeds
                trades.append({
                    "entry_date": df.index[i].strftime("%Y-%m-%d"),
                    "entry"     : round(entry_price, 2),
                    "exit"      : round(exit_price, 2),
                    "pnl_pct"   : round(pnl_pct * 100, 2),
                    "pnl_usdt"  : round(proceeds - (btc_held * entry_price), 2),
                    "reason"    : exit_reason,
                })
                in_position = False
                btc_held    = 0.0

        # ── Détection des signaux (seulement hors position) ──────────────────
        if not in_position:
            golden_cross = (prev_fast <= prev_slow) and (sma_fast > sma_slow)

            if golden_cross and rsi < RSI_OVERBOUGHT:
                risk_usdt    = capital * RISK_PER_TRADE
                position_usd = min(risk_usdt / STOP_LOSS_PCT, capital * 0.95)
                cost         = position_usd * (1 + FEES)

                if cost > capital:
                    equity_curve.append(capital)
                    continue

                btc_held    = position_usd / price
                capital    -= cost
                entry_price = price
                stop_loss   = price * (1 - STOP_LOSS_PCT)
                take_profit = price * (1 + TAKE_PROFIT_PCT)
                in_position = True

        portfolio_value = capital + (btc_held * price if in_position else 0)
        equity_curve.append(portfolio_value)

    # Fermeture forcée si encore en position à la fin
    if in_position:
        final_price = float(df.iloc[-1]["close"])
        proceeds    = btc_held * final_price * (1 - FEES)
        capital    += proceeds
        trades.append({
            "entry_date": "—",
            "entry"     : round(entry_price, 2),
            "exit"      : round(final_price, 2),
            "pnl_pct"   : round((final_price - entry_price) / entry_price * 100, 2),
            "pnl_usdt"  : round(proceeds - (btc_held * entry_price), 2),
            "reason"    : "END_OF_DATA",
        })

    return {
        "trades"       : trades,
        "equity_curve" : equity_curve,
        "final_capital": round(capital, 2),
        "initial_capital": initial_capital,
    }


# =============================================================================
# 4. CALCUL DES MÉTRIQUES
# =============================================================================

def compute_metrics(results: dict, df: pd.DataFrame) -> dict:
    trades        = results["trades"]
    equity_curve  = results["equity_curve"]
    final_capital = results["final_capital"]
    init_capital  = results.get("initial_capital", INITIAL_CAPITAL)

    if not trades:
        print("Aucun trade généré — essaie d'élargir la période ou d'assouplir les conditions.")
        return {}

    # ── Métriques de base ────────────────────────────────────────────────────
    total_trades  = len(trades)
    wins          = [t for t in trades if t["pnl_usdt"] > 0]
    losses        = [t for t in trades if t["pnl_usdt"] <= 0]
    win_rate      = len(wins) / total_trades * 100
    total_pnl     = final_capital - init_capital
    total_pnl_pct = total_pnl / init_capital * 100
    avg_win       = sum(t["pnl_usdt"] for t in wins)   / len(wins)   if wins   else 0.0
    avg_loss      = sum(t["pnl_usdt"] for t in losses) / len(losses) if losses else 0.0
    ratio_gl      = round(avg_win / abs(avg_loss), 2) if losses and avg_loss != 0 else float("inf")

    # ── Drawdown maximum ─────────────────────────────────────────────────────
    peak   = init_capital
    max_dd = 0.0
    for val in equity_curve:
        if val > peak:
            peak = val
        dd = (peak - val) / peak * 100
        if dd > max_dd:
            max_dd = dd

    # ── Buy & Hold ───────────────────────────────────────────────────────────
    buy_hold_return = (
        (float(df["close"].iloc[-1]) - float(df["close"].iloc[0])) / float(df["close"].iloc[0]) * 100
    )

    # ── Durée de la période (pour Calmar et annualisations) ──────────────────
    years = max((df.index[-1] - df.index[0]).days / 365.25, 1 / 365)

    return {
        # Base
        "total_trades"          : total_trades,
        "win_rate"              : round(win_rate, 1),
        "total_pnl_usdt"        : round(total_pnl, 2),
        "total_pnl_pct"         : round(total_pnl_pct, 2),
        "avg_win_usdt"          : round(avg_win, 2),
        "avg_loss_usdt"         : round(avg_loss, 2),
        "ratio_gain_loss"       : ratio_gl,
        "max_drawdown_pct"      : round(max_dd, 2),
        "buy_hold_pct"          : round(buy_hold_return, 2),
        "final_capital"         : final_capital,
        "initial_capital"       : init_capital,
        "trades"                : trades,
        # Métriques avancées (Phase 1)
        "sharpe_ratio"          : mt.sharpe_ratio(equity_curve, TIMEFRAME),
        "sortino_ratio"         : mt.sortino_ratio(equity_curve, TIMEFRAME),
        "calmar_ratio"          : mt.calmar_ratio(total_pnl_pct, max_dd, years),
        "profit_factor"         : mt.profit_factor(trades),
        "max_consecutive_losses": mt.max_consecutive_losses(trades),
        "expectancy_usdt"       : mt.expectancy(trades),
        "period_years"          : round(years, 2),
    }


# =============================================================================
# 5. WALK-FORWARD ANALYSIS
# =============================================================================

def walk_forward_analysis(df: pd.DataFrame, n_splits: int = WF_SPLITS) -> list[dict]:
    """
    Découpe les données en n_splits fenêtres temporelles indépendantes et
    évalue la stratégie sur chacune. Révèle si les performances sont stables
    dans le temps ou si elles dépendent d'une seule période favorable.
    """
    min_candles = max(SMA_SLOW * 10, 100)  # Assez de données pour les indicateurs
    window_size = len(df) // n_splits
    folds       = []

    for i in range(n_splits):
        start = i * window_size
        end   = (i + 1) * window_size if i < n_splits - 1 else len(df)
        fold  = df.iloc[start:end].copy()

        if len(fold) < min_candles:
            print(f"  Fenêtre {i+1} ignorée : seulement {len(fold)} bougies (minimum {min_candles})")
            continue

        fold_results = run_backtest(fold, initial_capital=INITIAL_CAPITAL)
        fold_metrics = compute_metrics(fold_results, fold)

        if fold_metrics:
            fold_metrics["window"]       = i + 1
            fold_metrics["period_start"] = fold.index[0].strftime("%Y-%m-%d")
            fold_metrics["period_end"]   = fold.index[-1].strftime("%Y-%m-%d")
            folds.append(fold_metrics)

    return folds


# =============================================================================
# 6. AFFICHAGE DES RÉSULTATS
# =============================================================================

def _fmt_inf(val: float, fmt: str = ".2f") -> str:
    """Formate un float en gérant les valeurs infinies."""
    if val == float("inf"):
        return "  ∞"
    return f"{val:{fmt}}"


def print_report(metrics: dict):
    if not metrics:
        return

    trades   = metrics["trades"]
    pnl      = metrics["total_pnl_usdt"]
    pnl_pct  = metrics["total_pnl_pct"]
    bh       = metrics["buy_hold_pct"]
    sign     = "+" if pnl >= 0 else ""
    bh_sign  = "+" if bh >= 0 else ""

    print("\n" + "=" * 62)
    print("  RAPPORT DE BACKTESTING — BTC/USDT")
    print("=" * 62)

    # ── Capital ──────────────────────────────────────────────────────────────
    print(f"\n  Capital initial    : {metrics['initial_capital']:>10,.2f} USDT")
    print(f"  Capital final      : {metrics['final_capital']:>10,.2f} USDT")
    print(f"  PnL total          : {sign}{pnl:>9,.2f} USDT  ({sign}{pnl_pct}%)")
    print(f"  Buy & Hold         : {bh_sign}{bh:>9.2f}%  (référence passive)")

    # ── Trades ───────────────────────────────────────────────────────────────
    print(f"\n  Nombre de trades   : {metrics['total_trades']:>10}")
    print(f"  Win rate           : {metrics['win_rate']:>9.1f}%")
    print(f"  Gain moyen/trade   : +{metrics['avg_win_usdt']:>8,.2f} USDT")
    print(f"  Perte moyenne/trade:  {metrics['avg_loss_usdt']:>8,.2f} USDT")
    print(f"  Ratio Gain/Perte   : {metrics['ratio_gain_loss']:>10.2f}")
    print(f"  Espérance/trade    : {metrics['expectancy_usdt']:>+10.2f} USDT")

    # ── Risque ───────────────────────────────────────────────────────────────
    print(f"\n  Drawdown maximum   : -{metrics['max_drawdown_pct']:>8.2f}%")
    print(f"  Pertes consécutives: {metrics['max_consecutive_losses']:>10}")

    # ── Métriques avancées ───────────────────────────────────────────────────
    print(f"\n  Sharpe ratio       : {_fmt_inf(metrics['sharpe_ratio'], '.3f'):>10}")
    print(f"  Sortino ratio      : {_fmt_inf(metrics['sortino_ratio'], '.3f'):>10}")
    print(f"  Calmar ratio       : {_fmt_inf(metrics['calmar_ratio'], '.3f'):>10}")
    print(f"  Profit Factor      : {_fmt_inf(metrics['profit_factor'], '.2f'):>10}")

    # ── Détail des trades ────────────────────────────────────────────────────
    print("\n" + "-" * 62)
    print(f"  {'Date':<12} {'Entrée':>10} {'Sortie':>10} {'PnL %':>8} {'PnL USDT':>10}  Raison")
    print("-" * 62)
    for t in trades[-20:]:
        s = "+" if t["pnl_usdt"] >= 0 else ""
        print(
            f"  {t['entry_date']:<12} "
            f"{t['entry']:>10,.0f} "
            f"{t['exit']:>10,.0f} "
            f"{s}{t['pnl_pct']:>7.2f}% "
            f"{s}{t['pnl_usdt']:>9.2f}  "
            f"{t['reason']}"
        )
    if len(trades) > 20:
        print(f"  ... et {len(trades) - 20} trades supplémentaires")

    print("=" * 62)
    print()

    # ── Verdict ──────────────────────────────────────────────────────────────
    if pnl > 0 and pnl_pct > bh:
        print("  Stratégie GAGNANTE et meilleure que Buy & Hold.")
    elif pnl > 0:
        print("  Stratégie GAGNANTE mais Buy & Hold aurait fait mieux.")
        print("  → Piste d'amélioration : optimiser les paramètres.")
    else:
        print("  Stratégie PERDANTE sur cette période.")
        print("  → Ne pas passer en live — revoir la stratégie d'abord.")
    print()


def print_walk_forward_report(folds: list[dict]):
    if not folds:
        print("Walk-Forward : aucune fenêtre à analyser.")
        return

    print("\n" + "=" * 80)
    print("  WALK-FORWARD ANALYSIS — Stabilité de la stratégie dans le temps")
    print("=" * 80)
    print(
        f"  {'Fenêtre':<8} {'Période':<24} {'Trades':>6} {'Win%':>6} "
        f"{'PnL%':>7} {'Sharpe':>8} {'Sortino':>9} {'MaxDD%':>8} {'PF':>6}"
    )
    print("-" * 80)

    profitable_windows = 0
    for f in folds:
        period = f"{f['period_start']} → {f['period_end']}"
        pnl_sign = "+" if f["total_pnl_pct"] >= 0 else ""
        if f["total_pnl_pct"] >= 0:
            profitable_windows += 1

        print(
            f"  {f['window']:<8} {period:<24} {f['total_trades']:>6} "
            f"{f['win_rate']:>5.1f}% "
            f"{pnl_sign}{f['total_pnl_pct']:>6.2f}% "
            f"{_fmt_inf(f['sharpe_ratio'], '.2f'):>8} "
            f"{_fmt_inf(f['sortino_ratio'], '.2f'):>9} "
            f"-{f['max_drawdown_pct']:>6.2f}% "
            f"{_fmt_inf(f['profit_factor'], '.2f'):>6}"
        )

    print("=" * 80)
    consistency = profitable_windows / len(folds) * 100
    print(f"\n  Fenêtres rentables : {profitable_windows}/{len(folds)} ({consistency:.0f}%)")

    if consistency == 100:
        print("  Excellente robustesse : la stratégie est profitable sur chaque période.")
    elif consistency >= 67:
        print("  Bonne robustesse : majoritairement profitable — quelques périodes difficiles.")
    else:
        print("  Robustesse faible : la stratégie dépend trop d'une période spécifique.")
    print()


# =============================================================================
# POINT D'ENTRÉE
# =============================================================================

if __name__ == "__main__":
    print("\n[1/3] Téléchargement des données historiques...")
    df = fetch_historical_data()
    df = add_indicators(df)

    print("\n[2/3] Backtest complet sur la période entière...")
    results = run_backtest(df)
    metrics_full = compute_metrics(results, df)
    print_report(metrics_full)

    print("\n[3/3] Walk-Forward Analysis...")
    folds = walk_forward_analysis(df, n_splits=WF_SPLITS)
    print_walk_forward_report(folds)
