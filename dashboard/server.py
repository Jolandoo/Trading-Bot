# =============================================================================
# dashboard/server.py — Backend FastAPI du dashboard de trading
# =============================================================================
# Lit les fichiers produits par main.py :
#   - logs/trades.jsonl  → historique des trades clôturés
#   - logs/state.json    → snapshot de l'état courant (position, capital sim, indicateurs)
#   - logs/bot.log       → tail des logs récents
#
# Aucun couplage direct au bot : si main.py n'est pas lancé, le dashboard
# affiche les dernières données disponibles en lecture seule.
#
# Lancement :
#   python -m uvicorn dashboard.server:app --host 0.0.0.0 --port 8000 --reload
# =============================================================================

import json
import os
import time
from collections import deque
from pathlib import Path

from fastapi import FastAPI
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from config import TIMEFRAME
from data import create_public_exchange, fetch_ohlcv
from indicators import add_indicators
from metrics import (
    sharpe_ratio,
    sortino_ratio,
    profit_factor,
    expectancy,
    max_consecutive_losses,
)

# Le capital de départ est lu depuis le snapshot (state.json) ; fallback 10 000.
ROOT          = Path(__file__).resolve().parent.parent
TRADES_FILE   = ROOT / "logs" / "trades.jsonl"
STATE_FILE    = ROOT / "logs" / "state.json"
LOG_FILE      = ROOT / "logs" / "bot.log"
STATIC_DIR    = Path(__file__).resolve().parent / "static"

app = FastAPI(title="Trading Bot Dashboard")
app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")

# Connexion Binance publique (sans clé) réutilisée entre requêtes
_PUBLIC_EXCHANGE = None
# Cache OHLCV : on évite de spammer Binance (refresh dashboard toutes les 5s)
_OHLCV_CACHE: dict = {"ts": 0.0, "data": None}
_OHLCV_TTL = 30.0  # secondes


def _read_trades() -> list[dict]:
    if not TRADES_FILE.exists():
        return []
    trades: list[dict] = []
    with TRADES_FILE.open("r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                try:
                    trades.append(json.loads(line))
                except json.JSONDecodeError:
                    pass
    return trades


def _read_state() -> dict | None:
    if not STATE_FILE.exists():
        return None
    try:
        return json.loads(STATE_FILE.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None


def _tail_log(n: int = 50) -> list[str]:
    """Retourne les n dernières lignes du fichier de log."""
    if not LOG_FILE.exists():
        return []
    try:
        with LOG_FILE.open("r", encoding="utf-8", errors="replace") as f:
            return [line.rstrip("\n") for line in deque(f, maxlen=n)]
    except OSError:
        return []


def _build_equity_curve(trades: list[dict], start: float) -> list[dict]:
    """
    Reconstruit la courbe d'equity à partir des trades clôturés.
    Si chaque trade a un champ 'equity' (post-trade), on l'utilise directement.
    Sinon, on cumule les pnl_usdt sur le capital de départ.
    """
    points = [{"time": "start", "equity": round(start, 2)}]
    running = start
    for t in trades:
        if t.get("equity") is not None:
            running = t["equity"]
        else:
            running += t.get("pnl_usdt", 0.0)
        points.append({
            "time"  : t.get("time", ""),
            "equity": round(running, 2),
        })
    return points


def _max_drawdown(curve: list[dict]) -> float:
    """Drawdown maximum en %, calculé sur la courbe d'equity."""
    if len(curve) < 2:
        return 0.0
    peak = curve[0]["equity"]
    max_dd = 0.0
    for p in curve:
        eq = p["equity"]
        if eq > peak:
            peak = eq
        if peak > 0:
            dd = (peak - eq) / peak * 100
            if dd > max_dd:
                max_dd = dd
    return round(max_dd, 2)


def _compute_metrics(trades: list[dict], curve: list[dict]) -> dict:
    """Métriques agrégées sur les trades clôturés + courbe d'equity."""
    if not trades:
        return {
            "trades_count"     : 0,
            "win_rate"         : 0.0,
            "total_pnl_usdt"   : 0.0,
            "total_pnl_pct"    : 0.0,
            "sharpe"           : 0.0,
            "sortino"          : 0.0,
            "profit_factor"    : 0.0,
            "expectancy"       : 0.0,
            "max_consec_losses": 0,
            "max_drawdown_pct" : 0.0,
        }

    wins  = [t for t in trades if t.get("pnl_usdt", 0) > 0]
    total = len(trades)
    total_pnl_usdt = sum(t.get("pnl_usdt", 0) for t in trades)
    start_eq = curve[0]["equity"] if curve else 1.0
    end_eq   = curve[-1]["equity"] if curve else start_eq
    total_pnl_pct = (end_eq / start_eq - 1) * 100 if start_eq > 0 else 0.0

    eq_values = [p["equity"] for p in curve]
    pf = profit_factor(trades)
    return {
        "trades_count"     : total,
        "win_rate"         : round(len(wins) / total * 100, 1),
        "total_pnl_usdt"   : round(total_pnl_usdt, 2),
        "total_pnl_pct"    : round(total_pnl_pct, 2),
        "sharpe"           : sharpe_ratio(eq_values, timeframe=TIMEFRAME),
        "sortino"          : sortino_ratio(eq_values, timeframe=TIMEFRAME) if len(eq_values) > 2 else 0.0,
        "profit_factor"    : pf if pf != float("inf") else None,
        "expectancy"       : expectancy(trades),
        "max_consec_losses": max_consecutive_losses(trades),
        "max_drawdown_pct" : _max_drawdown(curve),
    }


def _fetch_ohlcv_cached() -> dict:
    """Renvoie OHLCV + indicateurs, mis en cache 30s pour ne pas spammer Binance."""
    global _PUBLIC_EXCHANGE
    now = time.time()
    if _OHLCV_CACHE["data"] is not None and (now - _OHLCV_CACHE["ts"]) < _OHLCV_TTL:
        return _OHLCV_CACHE["data"]

    if _PUBLIC_EXCHANGE is None:
        _PUBLIC_EXCHANGE = create_public_exchange()

    try:
        df = fetch_ohlcv(_PUBLIC_EXCHANGE)
        df = add_indicators(df)
    except Exception as e:
        # En cas d'échec, on retombe sur le cache si dispo
        if _OHLCV_CACHE["data"] is not None:
            return _OHLCV_CACHE["data"]
        return {"error": str(e), "candles": []}

    candles = [
        {
            "time"    : ts.isoformat(),
            "open"    : round(float(row["open"]),     2),
            "high"    : round(float(row["high"]),     2),
            "low"     : round(float(row["low"]),      2),
            "close"   : round(float(row["close"]),    2),
            "volume"  : round(float(row["volume"]),   4),
            "sma_fast": round(float(row["sma_fast"]), 2),
            "sma_slow": round(float(row["sma_slow"]), 2),
            "sma200"  : (round(float(row["sma200"]), 2) if row["sma200"] == row["sma200"] else None),
            "rsi"     : round(float(row["rsi"]),      2),
        }
        for ts, row in df.iterrows()
    ]
    payload = {
        "timeframe": TIMEFRAME,
        "candles"  : candles,
    }
    _OHLCV_CACHE["data"] = payload
    _OHLCV_CACHE["ts"]   = now
    return payload


@app.get("/")
def root():
    return FileResponse(STATIC_DIR / "index.html")


@app.get("/api/ohlcv")
def api_ohlcv():
    """Bougies + indicateurs (SMA9, SMA21, SMA200, RSI). Cache 30s."""
    return _fetch_ohlcv_cached()


@app.get("/api/state")
def api_state():
    """Endpoint principal : tout ce qu'il faut pour rafraîchir le dashboard."""
    trades  = _read_trades()
    state   = _read_state()
    start_usdt = (state or {}).get("start_usdt") or 10_000.0
    curve   = _build_equity_curve(trades, start=start_usdt)
    metrics = _compute_metrics(trades, curve)
    return {
        "state"        : state,
        "trades"       : trades,
        "equity_curve" : curve,
        "metrics"      : metrics,
        "logs_tail"    : _tail_log(60),
        "config"       : {"timeframe": TIMEFRAME},
    }
