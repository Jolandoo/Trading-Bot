# =============================================================================
# backtest.py — Backtesting de la stratégie sur données historiques
# =============================================================================
# On télécharge 1 an de bougies BTC/USDT depuis Binance (pas le testnet,
# le vrai Binance — les données historiques sont publiques et gratuites).
# Puis on simule exactement ce que le bot aurait fait, trade par trade.
#
# Métriques calculées :
#   - PnL total et par trade
#   - Win rate (% de trades gagnants)
#   - Drawdown maximum (pire perte depuis un sommet)
#   - Ratio de Sharpe simplifié
#   - Comparaison vs Buy & Hold (juste acheter et garder)
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

# =============================================================================
# PARAMÈTRES DU BACKTEST
# =============================================================================
INITIAL_CAPITAL = 10_000   # USDT de départ (correspond au Testnet)
MONTHS_BACK     = 12       # Nombre de mois d'historique à tester
FEES            = 0.001    # 0.1% de frais Binance par trade (réaliste)


# =============================================================================
# 1. RÉCUPÉRATION DES DONNÉES HISTORIQUES
# =============================================================================

def fetch_historical_data() -> pd.DataFrame:
    """
    Télécharge les bougies historiques depuis le vrai Binance (données publiques).
    Pas besoin de clé API pour lire les données historiques.
    """
    print(f"Téléchargement des données {SYMBOL} ({TIMEFRAME}) — {MONTHS_BACK} mois...")

    # Connexion au vrai Binance (lecture seule, sans clé API)
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
        # Stop quand on a rattrapé le présent
        if candles[-1][0] >= exchange.milliseconds() - 2 * 3600 * 1000:
            break

    df = pd.DataFrame(all_candles, columns=["timestamp", "open", "high", "low", "close", "volume"])
    df["timestamp"] = pd.to_datetime(df["timestamp"], unit="ms")
    df.set_index("timestamp", inplace=True)
    df.drop_duplicates(inplace=True)

    print(f"  → {len(df)} bougies récupérées ({df.index[0].date()} → {df.index[-1].date()})")
    return df


# =============================================================================
# 2. CALCUL DES INDICATEURS
# =============================================================================

def add_indicators(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()
    df["rsi"]      = ta.rsi(df["close"], length=RSI_PERIOD)
    df["sma_fast"] = ta.sma(df["close"], length=SMA_FAST)
    df["sma_slow"] = ta.sma(df["close"], length=SMA_SLOW)
    df["sma200"]   = ta.sma(df["close"], length=200)   # ← filtre tendance
    df.dropna(inplace=True)
    return df


# =============================================================================
# 3. MOTEUR DE SIMULATION
# =============================================================================

def run_backtest(df: pd.DataFrame) -> dict:
    """
    Simule le bot trade par trade sur toutes les bougies historiques.
    À chaque bougie, on évalue les mêmes conditions que le bot en live.
    """
    capital      = float(INITIAL_CAPITAL)
    in_position  = False
    entry_price  = 0.0
    btc_held     = 0.0
    stop_loss    = 0.0
    take_profit  = 0.0
    trades       = []
    equity_curve = [capital]   # Valeur du portefeuille à chaque bougie

    for i in range(1, len(df)):
        row  = df.iloc[i]
        prev = df.iloc[i - 1]

        price      = float(row["close"])
        rsi        = float(row["rsi"])
        sma_fast   = float(row["sma_fast"])
        sma_slow   = float(row["sma_slow"])
        prev_fast  = float(prev["sma_fast"])
        prev_slow  = float(prev["sma_slow"])

        # ── Vérification stop-loss / take-profit (prioritaire) ────────────
        if in_position:
            exit_reason = None

            # On vérifie aussi le high/low de la bougie (plus réaliste)
            if float(row["low"]) <= stop_loss:
                exit_reason = "STOP_LOSS"
                exit_price  = stop_loss   # On sort exactement au niveau SL
            elif float(row["high"]) >= take_profit:
                exit_reason = "TAKE_PROFIT"
                exit_price  = take_profit

            if exit_reason:
                pnl_pct  = (exit_price - entry_price) / entry_price
                proceeds = btc_held * exit_price * (1 - FEES)
                capital += proceeds
                trades.append({
                    "entry_date" : df.index[i].strftime("%Y-%m-%d"),
                    "entry"      : round(entry_price, 2),
                    "exit"       : round(exit_price, 2),
                    "pnl_pct"    : round(pnl_pct * 100, 2),
                    "pnl_usdt"   : round(proceeds - (btc_held * entry_price), 2),
                    "reason"     : exit_reason,
                })
                in_position = False
                btc_held    = 0.0

        # ── Détection des signaux (seulement si pas en position) ──────────
        if not in_position:
            golden_cross = (prev_fast <= prev_slow) and (sma_fast > sma_slow)

            if golden_cross and rsi < RSI_OVERBOUGHT:
                # Calcul de la taille de position
                risk_usdt    = capital * RISK_PER_TRADE
                position_usd = min(risk_usdt / STOP_LOSS_PCT, capital * 0.95)
                cost         = position_usd * (1 + FEES)   # Frais d'entrée

                if cost > capital:
                    equity_curve.append(capital)
                    continue

                btc_held    = position_usd / price
                capital    -= cost
                entry_price = price
                stop_loss   = price * (1 - STOP_LOSS_PCT)
                take_profit = price * (1 + TAKE_PROFIT_PCT)
                in_position = True

        # ── Mise à jour de la courbe d'équité ─────────────────────────────
        portfolio_value = capital + (btc_held * price if in_position else 0)
        equity_curve.append(portfolio_value)

    # Fermeture forcée si encore en position à la fin
    if in_position:
        final_price = float(df.iloc[-1]["close"])
        proceeds    = btc_held * final_price * (1 - FEES)
        capital    += proceeds
        trades.append({
            "entry_date" : "—",
            "entry"      : round(entry_price, 2),
            "exit"       : round(final_price, 2),
            "pnl_pct"    : round((final_price - entry_price) / entry_price * 100, 2),
            "pnl_usdt"   : round(proceeds - (btc_held * entry_price), 2),
            "reason"     : "END_OF_DATA",
        })

    return {
        "trades"       : trades,
        "equity_curve" : equity_curve,
        "final_capital": round(capital, 2),
    }


# =============================================================================
# 4. CALCUL DES MÉTRIQUES
# =============================================================================

def compute_metrics(results: dict, df: pd.DataFrame) -> dict:
    trades        = results["trades"]
    equity_curve  = results["equity_curve"]
    final_capital = results["final_capital"]

    if not trades:
        print("Aucun trade généré — essaie d'élargir la période ou d'assouplir les conditions.")
        return {}

    # Métriques de base
    total_trades  = len(trades)
    wins          = [t for t in trades if t["pnl_usdt"] > 0]
    losses        = [t for t in trades if t["pnl_usdt"] <= 0]
    win_rate      = len(wins) / total_trades * 100
    total_pnl     = final_capital - INITIAL_CAPITAL
    total_pnl_pct = total_pnl / INITIAL_CAPITAL * 100
    avg_win       = sum(t["pnl_usdt"] for t in wins)   / len(wins)   if wins   else 0
    avg_loss      = sum(t["pnl_usdt"] for t in losses) / len(losses) if losses else 0

    # Drawdown maximum
    peak     = INITIAL_CAPITAL
    max_dd   = 0.0
    for val in equity_curve:
        if val > peak:
            peak = val
        dd = (peak - val) / peak * 100
        if dd > max_dd:
            max_dd = dd

    # Buy & Hold (comparaison) : on aurait juste acheté au début et gardé
    buy_hold_return = (float(df["close"].iloc[-1]) - float(df["close"].iloc[0])) / float(df["close"].iloc[0]) * 100

    return {
        "total_trades"    : total_trades,
        "win_rate"        : round(win_rate, 1),
        "total_pnl_usdt"  : round(total_pnl, 2),
        "total_pnl_pct"   : round(total_pnl_pct, 2),
        "avg_win_usdt"    : round(avg_win, 2),
        "avg_loss_usdt"   : round(avg_loss, 2),
        "max_drawdown_pct": round(max_dd, 2),
        "buy_hold_pct"    : round(buy_hold_return, 2),
        "final_capital"   : final_capital,
        "trades"          : trades,
    }


# =============================================================================
# 5. AFFICHAGE DES RÉSULTATS
# =============================================================================

def print_report(metrics: dict):
    if not metrics:
        return

    trades = metrics["trades"]

    print("\n" + "=" * 58)
    print("  RAPPORT DE BACKTESTING — BTC/USDT")
    print("=" * 58)

    print(f"\n  Capital initial    : {INITIAL_CAPITAL:>10,.2f} USDT")
    print(f"  Capital final      : {metrics['final_capital']:>10,.2f} USDT")

    pnl = metrics['total_pnl_usdt']
    pnl_pct = metrics['total_pnl_pct']
    sign = "+" if pnl >= 0 else ""
    print(f"  PnL total          : {sign}{pnl:>9,.2f} USDT  ({sign}{pnl_pct}%)")

    bh = metrics['buy_hold_pct']
    bh_sign = "+" if bh >= 0 else ""
    print(f"  Buy & Hold         : {bh_sign}{bh:>9.2f}%  (référence passive)")

    print(f"\n  Nombre de trades   : {metrics['total_trades']:>10}")
    print(f"  Win rate           : {metrics['win_rate']:>9.1f}%")
    print(f"  Gain moyen/trade   : +{metrics['avg_win_usdt']:>8,.2f} USDT")
    print(f"  Perte moyenne/trade:  {metrics['avg_loss_usdt']:>8,.2f} USDT")
    print(f"  Drawdown maximum   : -{metrics['max_drawdown_pct']:>8.2f}%")

    print("\n" + "-" * 58)
    print(f"  {'Date':<12} {'Entrée':>10} {'Sortie':>10} {'PnL %':>8} {'PnL USDT':>10}  Raison")
    print("-" * 58)
    for t in trades[-20:]:   # Affiche les 20 derniers trades
        sign = "+" if t["pnl_usdt"] >= 0 else ""
        print(
            f"  {t['entry_date']:<12} "
            f"{t['entry']:>10,.0f} "
            f"{t['exit']:>10,.0f} "
            f"{sign}{t['pnl_pct']:>7.2f}% "
            f"{sign}{t['pnl_usdt']:>9.2f}  "
            f"{t['reason']}"
        )
    if len(trades) > 20:
        print(f"  ... et {len(trades) - 20} trades supplémentaires")

    print("=" * 58)

    # Verdict final
    print()
    if pnl > 0 and pnl_pct > bh:
        print("  Stratégie GAGNANTE et meilleure que Buy & Hold.")
    elif pnl > 0:
        print("  Stratégie GAGNANTE mais Buy & Hold aurait fait mieux.")
        print("  → Piste d'amélioration : optimiser les paramètres.")
    else:
        print("  Stratégie PERDANTE sur cette période.")
        print("  → Ne pas passer en live — revoir la stratégie d'abord.")
    print()


# =============================================================================
# POINT D'ENTRÉE
# =============================================================================

if __name__ == "__main__":
    df      = fetch_historical_data()
    df      = add_indicators(df)
    results = run_backtest(df)
    metrics = compute_metrics(results, df)
    print_report(metrics)