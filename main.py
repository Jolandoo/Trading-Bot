# =============================================================================
# main.py — Boucle principale du bot de trading
# =============================================================================
# C'est le chef d'orchestre : il appelle tous les autres modules dans l'ordre
# et gère l'état de la position (est-ce qu'on a du BTC ou pas ?).
#
# Cycle à chaque itération :
#   1. Récupérer les bougies récentes
#   2. Calculer les indicateurs
#   3. Vérifier stop-loss / take-profit si en position
#   4. Évaluer la stratégie → signal BUY / SELL / HOLD
#   5. Exécuter l'ordre si nécessaire
#   6. Attendre avant la prochaine itération
# =============================================================================

import os
import time
import logging
from datetime import datetime
from logging.handlers import RotatingFileHandler
from config import LOOP_INTERVAL, DRY_RUN, LOG_LEVEL

# --- Configuration du logger ---
_LOG_FORMAT = "%(asctime)s | %(levelname)-8s | %(name)-12s | %(message)s"
_DATE_FMT   = "%H:%M:%S"
_DATE_FMT_FILE = "%Y-%m-%d %H:%M:%S"

logging.basicConfig(
    level   = getattr(logging, LOG_LEVEL),
    format  = _LOG_FORMAT,
    datefmt = _DATE_FMT,
)

# Rotation automatique : 5 Mo par fichier, 5 fichiers conservés
os.makedirs("logs", exist_ok=True)
_file_handler = RotatingFileHandler(
    "logs/bot.log", maxBytes=5 * 1024 * 1024, backupCount=5, encoding="utf-8"
)
_file_handler.setFormatter(logging.Formatter(_LOG_FORMAT, datefmt=_DATE_FMT_FILE))
logging.getLogger().addHandler(_file_handler)

logger = logging.getLogger("main")

# --- Import des modules du bot ---
from data       import create_exchange, fetch_ohlcv, get_current_price, get_balance
from indicators import add_indicators, get_latest
from strategy   import check_signal, Signal
from risk       import calculate_position, check_exit_conditions
from executor   import buy_market, sell_market


class BotState:
    """
    Conserve l'état du bot entre les itérations.
    Un bot sans mémoire ne saurait pas s'il est déjà en position !
    """
    def __init__(self):
        self.in_position  : bool  = False    # On possède du BTC ?
        self.entry_price  : float = 0.0      # Prix auquel on a acheté
        self.btc_held     : float = 0.0      # Quantité de BTC en portefeuille
        self.stop_loss    : float = 0.0      # Niveau de stop-loss actif
        self.take_profit  : float = 0.0      # Niveau de take-profit actif
        self.trades       : list  = []       # Historique de tous les trades
        self.start_usdt   : float = 0.0      # Capital de départ (pour calculer le PnL)

    def open_position(self, entry_price, btc_amount, stop_loss, take_profit):
        self.in_position = True
        self.entry_price = entry_price
        self.btc_held    = btc_amount
        self.stop_loss   = stop_loss
        self.take_profit = take_profit
        logger.info(f"Position OUVERTE — Entrée : {entry_price:.2f} | BTC : {btc_amount:.6f}")

    def close_position(self, exit_price, reason):
        pnl_pct = ((exit_price - self.entry_price) / self.entry_price) * 100
        pnl_usdt = self.btc_held * (exit_price - self.entry_price)
        self.trades.append({
            "entry"   : self.entry_price,
            "exit"    : exit_price,
            "pnl_pct" : round(pnl_pct, 2),
            "pnl_usdt": round(pnl_usdt, 2),
            "reason"  : reason,
            "time"    : datetime.now().isoformat(),
        })
        emoji = "✓" if pnl_usdt >= 0 else "✗"
        logger.info(
            f"Position FERMÉE [{reason}] {emoji} — "
            f"Entrée : {self.entry_price:.2f} | Sortie : {exit_price:.2f} | "
            f"PnL : {pnl_pct:+.2f}% ({pnl_usdt:+.2f} USDT)"
        )
        self.in_position = False
        self.entry_price = 0.0
        self.btc_held    = 0.0
        self.stop_loss   = 0.0
        self.take_profit = 0.0

    def print_summary(self):
        if not self.trades:
            logger.info("Aucun trade effectué pour l'instant.")
            return
        total_pnl = sum(t["pnl_usdt"] for t in self.trades)
        wins  = sum(1 for t in self.trades if t["pnl_usdt"] > 0)
        total = len(self.trades)
        logger.info(
            f"--- Résumé ({total} trades) --- "
            f"Win rate : {wins/total*100:.0f}% | PnL total : {total_pnl:+.2f} USDT"
        )


def run():
    """Point d'entrée principal du bot."""
    logger.info("=" * 60)
    logger.info(f"  BOT DE TRADING DÉMARRÉ {'[DRY RUN]' if DRY_RUN else '[LIVE]'}")
    logger.info("=" * 60)

    # Initialisation
    exchange = create_exchange()
    state    = BotState()

    # Récupération du capital de départ
    balances         = get_balance(exchange)
    state.start_usdt = balances["USDT"]
    logger.info(f"Capital de départ : {state.start_usdt:.2f} USDT")

    iteration = 0

    try:
        while True:
            iteration += 1
            logger.info(f"--- Itération #{iteration} ---")

            try:
                # ── 1. Données ─────────────────────────────────────────────
                df = fetch_ohlcv(exchange)

                # ── 2. Indicateurs ─────────────────────────────────────────
                df     = add_indicators(df)
                values = get_latest(df)
                price  = values["close"]

                # ── 3. Vérification stop-loss / take-profit ────────────────
                if state.in_position:
                    current_price = get_current_price(exchange)
                    exit_reason   = check_exit_conditions(
                        state.entry_price, current_price,
                        state.stop_loss, state.take_profit,
                    )
                    if exit_reason:
                        order = sell_market(exchange, state.btc_held)
                        if order:
                            state.close_position(current_price, exit_reason)
                        continue  # Passe à la prochaine itération sans réévaluer

                # ── 4. Évaluation de la stratégie ──────────────────────────
                signal = check_signal(values, state.in_position)

                # ── 5. Exécution ───────────────────────────────────────────
                if signal == Signal.BUY:
                    balances  = get_balance(exchange)
                    risk_info = calculate_position(balances["USDT"], price)

                    order = buy_market(exchange, risk_info["position_usdt"])
                    if order:
                        btc_received = risk_info["position_usdt"] / price
                        state.open_position(
                            entry_price = price,
                            btc_amount  = btc_received,
                            stop_loss   = risk_info["stop_loss"],
                            take_profit = risk_info["take_profit"],
                        )

                elif signal == Signal.SELL and state.in_position:
                    order = sell_market(exchange, state.btc_held)
                    if order:
                        state.close_position(price, "STRATEGY_SIGNAL")

            except RuntimeError as e:
                logger.error(f"Erreur récupérable : {e} — nouvelle tentative dans {LOOP_INTERVAL}s")

            except Exception as e:
                logger.exception(f"Erreur inattendue : {e}")
                break

            # ── 6. Attente ─────────────────────────────────────────────────
            logger.debug(f"Prochaine itération dans {LOOP_INTERVAL}s…")
            time.sleep(LOOP_INTERVAL)

    except KeyboardInterrupt:
        pass  # Ctrl+C intercepté ici (pendant le code ou le sleep)
    finally:
        logger.info("Arrêt du bot (Ctrl+C)")
        state.print_summary()


if __name__ == "__main__":
    run()
