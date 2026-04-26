# =============================================================================
# backtest.py — Backtesting de la stratégie sur données historiques
# =============================================================================
# Télécharge des bougies BTC/USDT depuis Binance et simule chaque trade.
#
# Métriques calculées :
#   - PnL total et par trade, Win rate, ratio gain/perte, espérance
#   - Drawdown maximum, pertes consécutives maximales
#   - Sharpe ratio, Sortino ratio, Calmar ratio, Profit Factor
#   - Comparaison vs Buy & Hold
#
# Analyses disponibles (python backtest.py [mode]) :
#   standard    — backtest sur 12 mois (défaut si lancé sans argument)
#   walkforward — découpe en N fenêtres indépendantes (robustesse temporelle)
#   periods     — compare 1 an, 3 ans, 5 ans de données
#   regimes     — compare bull 2020-2021, bear 2022, chop 2023, bull 2024
#   timeframes  — compare 1h, 4h, 1d sur la même période
#   all         — lance toutes les analyses ci-dessus
# =============================================================================

import sys
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
MONTHS_BACK     = 12       # Mois d'historique pour le backtest standard
FEES            = 0.001    # 0.1 % de frais Binance par trade
WF_SPLITS       = 3        # Fenêtres pour le walk-forward

# Périodes testées lors de l'analyse multi-périodes
PERIODS_CONFIG: dict[str, int] = {
    "1 an":  12,
    "3 ans": 36,
    "5 ans": 60,
}

# Régimes de marché identifiés sur BTC/USDT
REGIME_CONFIG: dict[str, tuple[str, str]] = {
    "Bull 2020-21": ("2020-01-01", "2022-01-01"),
    "Bear 2022":    ("2022-01-01", "2023-01-01"),
    "Chop 2023":    ("2023-01-01", "2024-01-01"),
    "Bull 2024":    ("2024-01-01", "2025-01-01"),
}

# Timeframes testés lors de l'analyse multi-timeframes
TIMEFRAMES_CONFIG: list[str] = ["1h", "4h", "1d"]


# =============================================================================
# 1. RÉCUPÉRATION DES DONNÉES HISTORIQUES
# =============================================================================

def fetch_historical_data() -> pd.DataFrame:
    """Télécharge MONTHS_BACK mois depuis aujourd'hui (usage standard)."""
    start = (datetime.utcnow() - timedelta(days=30 * MONTHS_BACK)).strftime("%Y-%m-%d")
    print(f"Téléchargement {SYMBOL} ({TIMEFRAME}) — {MONTHS_BACK} mois ({start} → aujourd'hui)...")
    return fetch_data_between(TIMEFRAME, start_date=start)


def fetch_data_between(
    timeframe: str,
    start_date: str,
    end_date: str | None = None,
) -> pd.DataFrame:
    """
    Télécharge toutes les bougies entre start_date et end_date (format YYYY-MM-DD).
    Sans end_date, récupère jusqu'à maintenant.
    Gère la pagination automatiquement (Binance limite à 1000 bougies/appel).
    """
    exchange = ccxt.binance({"enableRateLimit": True})
    since = exchange.parse8601(f"{start_date}T00:00:00Z")
    until = (
        exchange.parse8601(f"{end_date}T00:00:00Z")
        if end_date
        else exchange.milliseconds()
    )

    all_candles: list = []
    while True:
        batch = exchange.fetch_ohlcv(SYMBOL, timeframe=timeframe, since=since, limit=1000)
        if not batch:
            break
        for candle in batch:
            if candle[0] < until:
                all_candles.append(candle)
        if batch[-1][0] >= until:
            break
        since = batch[-1][0] + 1

    if not all_candles:
        return pd.DataFrame(columns=["open", "high", "low", "close", "volume"])

    df = pd.DataFrame(all_candles, columns=["timestamp", "open", "high", "low", "close", "volume"])
    df["timestamp"] = pd.to_datetime(df["timestamp"], unit="ms")
    df.set_index("timestamp", inplace=True)
    df.drop_duplicates(inplace=True)

    print(f"  -> {len(df)} bougies  ({df.index[0].date()} → {df.index[-1].date()})")
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
    SL/TP vérifiés sur le high/low de chaque bougie (simulation réaliste).
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

        price     = float(row["close"])
        rsi       = float(row["rsi"])
        sma_fast  = float(row["sma_fast"])
        sma_slow  = float(row["sma_slow"])
        prev_fast = float(prev["sma_fast"])
        prev_slow = float(prev["sma_slow"])

        # ── Vérification SL/TP sur le high/low de la bougie ──────────────────
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

        # ── Détection Golden Cross (hors position uniquement) ─────────────────
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

        equity_curve.append(capital + (btc_held * price if in_position else 0))

    # Fermeture forcée si encore en position à la fin des données
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
        "trades"          : trades,
        "equity_curve"    : equity_curve,
        "final_capital"   : round(capital, 2),
        "initial_capital" : initial_capital,
    }


# =============================================================================
# 4. CALCUL DES MÉTRIQUES
# =============================================================================

def compute_metrics(
    results: dict,
    df: pd.DataFrame,
    timeframe: str = TIMEFRAME,   # paramètre pour l'annualisation correcte
) -> dict:
    trades        = results["trades"]
    equity_curve  = results["equity_curve"]
    final_capital = results["final_capital"]
    init_capital  = results.get("initial_capital", INITIAL_CAPITAL)

    if not trades:
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
    peak, max_dd = init_capital, 0.0
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

    # ── Durée (pour Calmar) ───────────────────────────────────────────────────
    years = max((df.index[-1] - df.index[0]).days / 365.25, 1 / 365)

    return {
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
        "sharpe_ratio"          : mt.sharpe_ratio(equity_curve, timeframe),
        "sortino_ratio"         : mt.sortino_ratio(equity_curve, timeframe),
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
    min_candles = max(SMA_SLOW * 10, 100)
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
# 6. HELPER : lancer un backtest complet sur un DataFrame quelconque
# =============================================================================

def _backtest_df(label: str, df_raw: pd.DataFrame, timeframe: str = TIMEFRAME) -> dict | None:
    """
    Ajoute les indicateurs, lance le backtest et retourne les métriques.
    Retourne None si les données sont insuffisantes.
    """
    MIN_CANDLES = max(SMA_SLOW * 2 + RSI_PERIOD, 50)
    if len(df_raw) < MIN_CANDLES:
        print(f"  {label}: données insuffisantes ({len(df_raw)} bougies, minimum {MIN_CANDLES})")
        return None

    df_ind = add_indicators(df_raw)
    if len(df_ind) < 10:
        return None

    result  = run_backtest(df_ind)
    metrics = compute_metrics(result, df_ind, timeframe=timeframe)
    if metrics:
        metrics["label"]     = label
        metrics["timeframe"] = timeframe
    return metrics or None


# =============================================================================
# 7. ANALYSE MULTI-PÉRIODES — 1 an, 3 ans, 5 ans
# =============================================================================

def run_period_analysis() -> list[dict]:
    """
    Teste la stratégie sur 1 an, 3 ans et 5 ans d'historique.
    Indique si les performances se maintiennent sur longue durée ou sont
    le produit d'une période favorable récente.
    """
    results = []
    for label, months in PERIODS_CONFIG.items():
        start = (datetime.utcnow() - timedelta(days=30 * months)).strftime("%Y-%m-%d")
        print(f"  [{label}] {start} → aujourd'hui ({TIMEFRAME})")
        df_raw = fetch_data_between(TIMEFRAME, start_date=start)
        m = _backtest_df(label, df_raw)
        if m:
            results.append(m)
    return results


# =============================================================================
# 8. ANALYSE PAR RÉGIME DE MARCHÉ — bull, bear, chop
# =============================================================================

def run_regime_analysis() -> list[dict]:
    """
    Teste la stratégie sur des régimes de marché distincts.
    Crucial pour identifier dans quel contexte la stratégie est rentable
    et où elle perd de l'argent (typiquement en marché baissier/lateral).
    """
    results = []
    for label, (start, end) in REGIME_CONFIG.items():
        print(f"  [{label}] {start} → {end} ({TIMEFRAME})")
        df_raw = fetch_data_between(TIMEFRAME, start_date=start, end_date=end)
        m = _backtest_df(label, df_raw)
        if m:
            results.append(m)
    return results


# =============================================================================
# 9. ANALYSE MULTI-TIMEFRAMES — 1h, 4h, 1d
# =============================================================================

def run_timeframe_analysis(months: int = MONTHS_BACK) -> list[dict]:
    """
    Teste la stratégie sur 1h, 4h et 1d sur la même période.
    Révèle le timeframe optimal : 1h génère plus de signaux mais plus de bruit,
    1d est plus robuste mais réagit lentement.
    Les métriques Sharpe/Sortino sont correctement annualisées par timeframe.
    """
    start = (datetime.utcnow() - timedelta(days=30 * months)).strftime("%Y-%m-%d")
    results = []
    for tf in TIMEFRAMES_CONFIG:
        print(f"  [Timeframe {tf}] {start} → aujourd'hui")
        df_raw = fetch_data_between(tf, start_date=start)
        m = _backtest_df(tf, df_raw, timeframe=tf)
        if m:
            results.append(m)
    return results


# =============================================================================
# 10. AFFICHAGE — rapport standard
# =============================================================================

def _fmt_inf(val: float, fmt: str = ".2f") -> str:
    if val == float("inf"):
        return "  ∞"
    return f"{val:{fmt}}"


def print_report(metrics: dict):
    if not metrics:
        return

    trades  = metrics["trades"]
    pnl     = metrics["total_pnl_usdt"]
    pnl_pct = metrics["total_pnl_pct"]
    bh      = metrics["buy_hold_pct"]
    sign    = "+" if pnl >= 0 else ""
    bh_sign = "+" if bh >= 0 else ""

    print("\n" + "=" * 62)
    print("  RAPPORT DE BACKTESTING — BTC/USDT")
    print("=" * 62)

    print(f"\n  Capital initial    : {metrics['initial_capital']:>10,.2f} USDT")
    print(f"  Capital final      : {metrics['final_capital']:>10,.2f} USDT")
    print(f"  PnL total          : {sign}{pnl:>9,.2f} USDT  ({sign}{pnl_pct}%)")
    print(f"  Buy & Hold         : {bh_sign}{bh:>9.2f}%  (référence passive)")

    print(f"\n  Nombre de trades   : {metrics['total_trades']:>10}")
    print(f"  Win rate           : {metrics['win_rate']:>9.1f}%")
    print(f"  Gain moyen/trade   : +{metrics['avg_win_usdt']:>8,.2f} USDT")
    print(f"  Perte moyenne/trade:  {metrics['avg_loss_usdt']:>8,.2f} USDT")
    print(f"  Ratio Gain/Perte   : {metrics['ratio_gain_loss']:>10.2f}")
    print(f"  Espérance/trade    : {metrics['expectancy_usdt']:>+10.2f} USDT")

    print(f"\n  Drawdown maximum   : -{metrics['max_drawdown_pct']:>8.2f}%")
    print(f"  Pertes consécutives: {metrics['max_consecutive_losses']:>10}")

    print(f"\n  Sharpe ratio       : {_fmt_inf(metrics['sharpe_ratio'], '.3f'):>10}")
    print(f"  Sortino ratio      : {_fmt_inf(metrics['sortino_ratio'], '.3f'):>10}")
    print(f"  Calmar ratio       : {_fmt_inf(metrics['calmar_ratio'], '.3f'):>10}")
    print(f"  Profit Factor      : {_fmt_inf(metrics['profit_factor'], '.2f'):>10}")

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
    if pnl > 0 and pnl_pct > bh:
        print("  Stratégie GAGNANTE et meilleure que Buy & Hold.")
    elif pnl > 0:
        print("  Stratégie GAGNANTE mais Buy & Hold aurait fait mieux.")
    else:
        print("  Stratégie PERDANTE — revoir la stratégie avant de passer en live.")
    print()


# =============================================================================
# 11. AFFICHAGE — walk-forward
# =============================================================================

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

    profitable = 0
    for f in folds:
        period   = f"{f['period_start']} → {f['period_end']}"
        pnl_sign = "+" if f["total_pnl_pct"] >= 0 else ""
        if f["total_pnl_pct"] >= 0:
            profitable += 1
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
    consistency = profitable / len(folds) * 100
    print(f"\n  Fenêtres rentables : {profitable}/{len(folds)} ({consistency:.0f}%)")
    if consistency == 100:
        print("  Excellente robustesse : profitable sur chaque fenêtre.")
    elif consistency >= 67:
        print("  Bonne robustesse : majoritairement profitable.")
    else:
        print("  Robustesse faible : résultats trop dépendants d'une période.")
    print()


# =============================================================================
# 12. AFFICHAGE — tableau de comparaison multi-analyses
# =============================================================================

def print_comparison_table(title: str, results: list[dict]):
    """
    Affiche un tableau synthétique comparant plusieurs backtests côte à côte.
    Utilisé par les analyses multi-périodes, régimes et timeframes.
    """
    if not results:
        print(f"{title} : aucun résultat.\n")
        return

    W = 95
    print(f"\n{'=' * W}")
    print(f"  {title}")
    print(f"{'=' * W}")
    print(
        f"  {'Label':<16} {'TF':>4} {'Trades':>6} {'Win%':>6} {'PnL%':>8} "
        f"{'Sharpe':>8} {'Sortino':>9} {'MaxDD%':>8} {'PF':>6} {'Espér.':>8} {'B&H%':>8}"
    )
    print(f"{'-' * W}")

    for r in results:
        pnl_sign = "+" if r["total_pnl_pct"] >= 0 else ""
        bh_sign  = "+" if r["buy_hold_pct"]  >= 0 else ""
        tf       = r.get("timeframe", TIMEFRAME)
        print(
            f"  {r['label']:<16} {tf:>4} {r['total_trades']:>6} "
            f"{r['win_rate']:>5.1f}% "
            f"{pnl_sign}{r['total_pnl_pct']:>7.2f}% "
            f"{_fmt_inf(r['sharpe_ratio'], '.2f'):>8} "
            f"{_fmt_inf(r['sortino_ratio'], '.2f'):>9} "
            f"-{r['max_drawdown_pct']:>6.2f}% "
            f"{_fmt_inf(r['profit_factor'], '.2f'):>6} "
            f"{r['expectancy_usdt']:>+8.2f} "
            f"{bh_sign}{r['buy_hold_pct']:>7.2f}%"
        )

    print(f"{'=' * W}\n")

    # Verdict automatique
    profitable = sum(1 for r in results if r["total_pnl_pct"] > 0)
    print(f"  Configurations rentables : {profitable}/{len(results)}")
    best = max(results, key=lambda r: r["sharpe_ratio"] if r["sharpe_ratio"] != float("inf") else 0)
    print(f"  Meilleur Sharpe          : {best['label']} ({_fmt_inf(best['sharpe_ratio'], '.2f')})")
    print()


# =============================================================================
# POINT D'ENTRÉE
# =============================================================================

def _section(title: str):
    print(f"\n{'─' * 62}")
    print(f"  {title}")
    print(f"{'─' * 62}")


if __name__ == "__main__":
    mode = sys.argv[1] if len(sys.argv) > 1 else "standard"
    valid_modes = {"standard", "walkforward", "periods", "regimes", "timeframes", "all"}

    if mode not in valid_modes:
        print(f"Usage : python backtest.py [{' | '.join(sorted(valid_modes))}]")
        print("  standard    — backtest 12 mois (défaut)")
        print("  walkforward — walk-forward analysis")
        print("  periods     — compare 1an / 3ans / 5ans")
        print("  regimes     — compare bull / bear / chop / bull2024")
        print("  timeframes  — compare 1h / 4h / 1d")
        print("  all         — tout lancer")
        sys.exit(1)

    df_standard = None   # mis en cache pour éviter un double téléchargement

    if mode in ("standard", "all"):
        _section("BACKTEST STANDARD — 12 mois")
        df_standard = fetch_historical_data()
        df_standard = add_indicators(df_standard)
        results     = run_backtest(df_standard)
        metrics_std = compute_metrics(results, df_standard)
        print_report(metrics_std)

    if mode in ("walkforward", "all"):
        _section("WALK-FORWARD ANALYSIS")
        if df_standard is None:
            df_standard = add_indicators(fetch_historical_data())
        folds = walk_forward_analysis(df_standard)
        print_walk_forward_report(folds)

    if mode in ("periods", "all"):
        _section("ANALYSE MULTI-PÉRIODES — 1an / 3ans / 5ans")
        period_results = run_period_analysis()
        print_comparison_table("MULTI-PÉRIODES : 1an / 3ans / 5ans", period_results)

    if mode in ("regimes", "all"):
        _section("ANALYSE PAR RÉGIME DE MARCHÉ")
        regime_results = run_regime_analysis()
        print_comparison_table("RÉGIMES : bull 2020-21 / bear 2022 / chop 2023 / bull 2024", regime_results)

    if mode in ("timeframes", "all"):
        _section("ANALYSE MULTI-TIMEFRAMES — 1h / 4h / 1d")
        tf_results = run_timeframe_analysis()
        print_comparison_table("MULTI-TIMEFRAMES (12 mois)", tf_results)
