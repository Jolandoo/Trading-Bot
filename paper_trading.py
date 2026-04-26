# =============================================================================
# paper_trading.py — Paper trading sur le VRAI marché Binance
# =============================================================================
# Connecté aux prix réels de Binance (sans clé API, sans ordres réels).
# Simule exactement la même stratégie que le bot live, mais :
#   - Prix : Binance public (marché réel, pas le Testnet)
#   - Ordres : simulés en mémoire (aucun ordre envoyé)
#   - Persistance : chaque trade fermé est écrit dans un CSV horodaté
#   - Affichage : dashboard terminal mis à jour à chaque itération
#
# Usage :  python paper_trading.py
# Arrêt  : Ctrl+C → rapport de session complet + chemin du CSV
#
# Durée recommandée avant de passer en live : 4 à 8 semaines minimum.
# =============================================================================

import os
import csv
import time
import logging
from logging.handlers import RotatingFileHandler
from datetime import datetime

# ── Logging : fichier uniquement (le dashboard occupe le terminal) ────────────
os.makedirs("logs", exist_ok=True)
_root = logging.getLogger()
_root.handlers.clear()
_fh = RotatingFileHandler(
    "logs/paper.log", maxBytes=5 * 1024 * 1024, backupCount=3, encoding="utf-8"
)
_fh.setFormatter(logging.Formatter(
    "%(asctime)s | %(levelname)-8s | %(name)-12s | %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
))
_root.addHandler(_fh)
_root.setLevel(logging.INFO)

logger = logging.getLogger("paper")

# ── Imports métier (après le logging pour éviter tout affichage console) ──────
from config import (
    SYMBOL, TIMEFRAME, LOOP_INTERVAL,
    RSI_OVERBOUGHT, SMA_FAST, SMA_SLOW,
    STOP_LOSS_PCT, TAKE_PROFIT_PCT, RISK_PER_TRADE,
)
from data       import fetch_ohlcv, get_current_price, create_public_exchange
from indicators import add_indicators, get_latest
from strategy   import check_signal, Signal
from risk       import calculate_position, check_exit_conditions

# =============================================================================
# CONSTANTES
# =============================================================================
INITIAL_CAPITAL = 10_000.0
FEES            = 0.001    # 0,1 % par ordre (simulé)


# =============================================================================
# ÉTAT DU PAPER TRADING
# =============================================================================

class PaperState:
    """
    Gère l'état de la session paper trading :
    position ouverte, capital, historique des trades, persistance CSV.
    """

    def __init__(self):
        self.in_position  = False
        self.entry_price  = 0.0
        self.btc_held     = 0.0
        self.stop_loss    = 0.0
        self.take_profit  = 0.0
        self.capital      = INITIAL_CAPITAL
        self.trades: list[dict] = []
        self.start_time   = datetime.now()

        ts = self.start_time.strftime("%Y%m%d_%H%M%S")
        self.csv_path = f"logs/paper_{ts}.csv"
        self._init_csv()

    def _init_csv(self):
        with open(self.csv_path, "w", newline="", encoding="utf-8") as f:
            csv.writer(f).writerow([
                "timestamp", "entry_date", "entry_price", "exit_price",
                "pnl_pct", "pnl_usdt", "reason", "capital_after",
            ])

    def open_position(self, price: float, risk_info: dict) -> bool:
        cost = risk_info["position_usdt"] * (1 + FEES)
        if cost > self.capital:
            logger.warning("Capital insuffisant pour ouvrir une position")
            return False
        self.capital    -= cost
        self.btc_held    = risk_info["position_usdt"] / price
        self.entry_price = price
        self.stop_loss   = risk_info["stop_loss"]
        self.take_profit = risk_info["take_profit"]
        self.in_position = True
        logger.info(
            f"BUY @ {price:,.2f} | SL : {self.stop_loss:,.2f} | TP : {self.take_profit:,.2f}"
        )
        return True

    def close_position(self, exit_price: float, reason: str):
        proceeds = self.btc_held * exit_price * (1 - FEES)
        pnl_usdt = proceeds - (self.btc_held * self.entry_price)
        pnl_pct  = (exit_price - self.entry_price) / self.entry_price * 100
        self.capital += proceeds

        trade = {
            "timestamp"    : datetime.now().isoformat(timespec="seconds"),
            "entry_date"   : datetime.now().strftime("%Y-%m-%d"),
            "entry_price"  : round(self.entry_price, 2),
            "exit_price"   : round(exit_price, 2),
            "pnl_pct"      : round(pnl_pct, 2),
            "pnl_usdt"     : round(pnl_usdt, 2),
            "reason"       : reason,
            "capital_after": round(self.capital, 2),
        }
        self.trades.append(trade)

        with open(self.csv_path, "a", newline="", encoding="utf-8") as f:
            csv.writer(f).writerow(list(trade.values()))

        logger.info(
            f"SELL @ {exit_price:,.2f} [{reason}] | "
            f"PnL : {pnl_pct:+.2f}% ({pnl_usdt:+.2f} USDT)"
        )
        self.in_position = False
        self.entry_price = 0.0
        self.btc_held    = 0.0
        self.stop_loss   = 0.0
        self.take_profit = 0.0

    def latent_pnl(self, current_price: float) -> tuple[float, float]:
        """PnL non réalisé de la position ouverte (pct, usdt)."""
        if not self.in_position:
            return 0.0, 0.0
        pct  = (current_price - self.entry_price) / self.entry_price * 100
        usdt = self.btc_held * (current_price - self.entry_price)
        return pct, usdt

    def session_stats(self) -> dict:
        total   = len(self.trades)
        wins    = sum(1 for t in self.trades if t["pnl_usdt"] > 0)
        pnl     = sum(t["pnl_usdt"] for t in self.trades)
        elapsed = datetime.now() - self.start_time
        h, rem  = divmod(int(elapsed.total_seconds()), 3600)
        return {
            "total"  : total,
            "wins"   : wins,
            "pnl"    : round(pnl, 2),
            "elapsed": f"{h}h{rem // 60:02d}m",
        }


# =============================================================================
# DASHBOARD TERMINAL
# =============================================================================

def _clear():
    os.system("cls" if os.name == "nt" else "clear")


def print_dashboard(
    state: PaperState,
    values: dict,
    current_price: float,
    iteration: int,
):
    stats  = state.session_stats()
    now    = datetime.now().strftime("%H:%M:%S")
    trend  = "↑ Bullish" if values["sma_fast"] > values["sma_slow"] else "↓ Bearish"
    W      = 54

    _clear()
    print("═" * W)
    print(f"  PAPER TRADING  ·  {SYMBOL} ({TIMEFRAME})  ·  Binance Live")
    print(f"  #{iteration:<5}  ·  {now}  ·  Session : {stats['elapsed']}")
    print("═" * W)

    # ── Marché ────────────────────────────────────────────────────────────────
    print("  MARCHÉ")
    print(f"    Prix actuel   :  {current_price:>12,.2f} USDT")
    print(f"    RSI ({TIMEFRAME})       :  {values['rsi']:>12.1f}")
    print(f"    SMA({SMA_FAST}/{SMA_SLOW})      :  {values['sma_fast']:>10,.0f}  /  {values['sma_slow']:,.0f}   {trend}")
    print("─" * W)

    # ── Position ──────────────────────────────────────────────────────────────
    if state.in_position:
        pnl_pct, pnl_usdt = state.latent_pnl(current_price)
        sign = "+" if pnl_pct >= 0 else ""
        print("  POSITION : ● OUVERTE")
        print(f"    Entrée        :  {state.entry_price:>12,.2f} USDT")
        print(f"    PnL latent    :  {sign}{pnl_pct:>10.2f} %  ({sign}{pnl_usdt:,.2f} USDT)")
        print(f"    Stop-Loss     :  {state.stop_loss:>12,.2f}   TP : {state.take_profit:,.2f}")
    else:
        print("  POSITION : ○ AUCUNE")
        print(f"    En attente d'un Golden Cross + RSI < {RSI_OVERBOUGHT}")
        print(f"    (SMA{SMA_FAST} doit croiser SMA{SMA_SLOW} à la hausse)")
        print()
    print("─" * W)

    # ── Session ───────────────────────────────────────────────────────────────
    print("  SESSION")
    if stats["total"] > 0:
        wr   = stats["wins"] / stats["total"] * 100
        sign = "+" if stats["pnl"] >= 0 else ""
        print(f"    Trades        :  {stats['total']}  (✓ {stats['wins']} / ✗ {stats['total'] - stats['wins']})")
        print(f"    Win rate      :  {wr:.0f}%")
        print(f"    PnL réalisé   :  {sign}{stats['pnl']:,.2f} USDT")
    else:
        print("    Aucun trade fermé pour l'instant")
    print(f"    Capital       :  {state.capital:>12,.2f} USDT")
    print(f"    CSV           :  {state.csv_path}")
    print("═" * W)
    print(f"  Prochaine vérif dans {LOOP_INTERVAL}s  ·  Ctrl+C pour quitter")


# =============================================================================
# RAPPORT DE FIN DE SESSION
# =============================================================================

def print_session_report(state: PaperState):
    trades = state.trades
    stats  = state.session_stats()
    pnl    = state.capital - INITIAL_CAPITAL

    print("\n" + "=" * 58)
    print("  RAPPORT DE SESSION — PAPER TRADING")
    print("=" * 58)
    print(f"  Durée          :  {stats['elapsed']}")
    print(f"  Capital initial:  {INITIAL_CAPITAL:>10,.2f} USDT")
    print(f"  Capital final  :  {state.capital:>10,.2f} USDT")
    print(f"  PnL total      :  {pnl:>+10,.2f} USDT  ({pnl / INITIAL_CAPITAL * 100:+.2f} %)")

    if trades:
        wr = stats["wins"] / stats["total"] * 100
        print(f"\n  Trades fermés  :  {stats['total']}")
        print(f"  Win rate       :  {wr:.0f}%  ({stats['wins']} gagnants / {stats['total'] - stats['wins']} perdants)")
        print(f"\n  {'Date':<12} {'Entrée':>10} {'Sortie':>10} {'PnL %':>7} {'PnL USDT':>10}  Raison")
        print("  " + "-" * 56)
        for t in trades:
            s = "+" if t["pnl_usdt"] >= 0 else ""
            print(
                f"  {t['entry_date']:<12} "
                f"{t['entry_price']:>10,.0f} "
                f"{t['exit_price']:>10,.0f} "
                f"{s}{t['pnl_pct']:>6.2f}% "
                f"{s}{t['pnl_usdt']:>9.2f}  "
                f"{t['reason']}"
            )
    else:
        print("\n  Aucun trade fermé pendant cette session.")
        print("  → La stratégie Golden Cross sur 4h est peu fréquente.")
        print("    Laisse tourner plusieurs heures ou jours pour avoir des signaux.")

    print(f"\n  CSV            :  {state.csv_path}")
    print("=" * 58 + "\n")


# =============================================================================
# BOUCLE PRINCIPALE
# =============================================================================

def run():
    exchange = create_public_exchange()
    state    = PaperState()

    print(f"Démarrage paper trading — {SYMBOL} ({TIMEFRAME}) sur Binance Live")
    print(f"Capital de départ : {INITIAL_CAPITAL:,.0f} USDT  |  SL {STOP_LOSS_PCT*100:.0f}%  TP {TAKE_PROFIT_PCT*100:.0f}%  Risque {RISK_PER_TRADE*100:.0f}%/trade")
    print(f"Logs → {state.csv_path}")
    print("Chargement des données initiales...")

    iteration = 0

    try:
        while True:
            iteration += 1

            try:
                # ── 1. Données et indicateurs ─────────────────────────────────
                df            = fetch_ohlcv(exchange)
                df            = add_indicators(df)
                values        = get_latest(df)
                current_price = get_current_price(exchange)

                # ── 2. Vérification SL/TP sur le prix live ────────────────────
                if state.in_position:
                    reason = check_exit_conditions(
                        state.entry_price, current_price,
                        state.stop_loss, state.take_profit,
                    )
                    if reason:
                        state.close_position(current_price, reason)

                # ── 3. Signal de stratégie ────────────────────────────────────
                signal = check_signal(values, state.in_position)

                if signal == Signal.BUY and not state.in_position:
                    risk_info = calculate_position(state.capital, current_price)
                    state.open_position(current_price, risk_info)

                elif signal == Signal.SELL and state.in_position:
                    state.close_position(current_price, "STRATEGY_SIGNAL")

                # ── 4. Dashboard ──────────────────────────────────────────────
                print_dashboard(state, values, current_price, iteration)

            except Exception as e:
                logger.error(f"Erreur itération #{iteration} : {e}")

            time.sleep(LOOP_INTERVAL)

    except KeyboardInterrupt:
        pass
    finally:
        _clear()
        print_session_report(state)


if __name__ == "__main__":
    run()
