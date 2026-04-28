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
import json
import time
import logging
from datetime import datetime
from logging.handlers import RotatingFileHandler
from config import LOOP_INTERVAL, DRY_RUN, LOG_LEVEL

# Fichier de persistance des trades (ré-utilisé par le dashboard)
TRADES_FILE = os.path.join("logs", "trades.jsonl")
STATE_FILE  = os.path.join("logs", "state.json")

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
from data       import create_exchange, create_public_exchange, fetch_ohlcv, get_current_price, get_balance
from indicators import add_indicators, get_latest
from strategy   import check_signal, Signal
from risk       import calculate_position, check_exit_conditions
from executor   import buy_market, sell_market


class BotState:
    """
    Conserve l'état du bot entre les itérations.
    Un bot sans mémoire ne saurait pas s'il est déjà en position !

    En DRY_RUN, on tient un capital simulé (`sim_usdt` / `sim_btc`) indépendant
    du solde réel testnet, qui se met à jour à chaque trade fermé. Cela permet
    de tracer une equity curve fidèle dans le dashboard.
    """
    def __init__(self):
        self.in_position  : bool  = False    # On possède du BTC ?
        self.entry_price  : float = 0.0      # Prix auquel on a acheté
        self.btc_held     : float = 0.0      # Quantité de BTC en portefeuille
        self.stop_loss    : float = 0.0      # Niveau de stop-loss actif
        self.take_profit  : float = 0.0      # Niveau de take-profit actif
        self.trades       : list  = []       # Historique de tous les trades
        self.start_usdt   : float = 0.0      # Capital de départ (pour calculer le PnL)

        # Capital simulé (DRY_RUN uniquement)
        self.sim_usdt     : float = 0.0      # USDT disponibles dans la simulation
        self.sim_btc      : float = 0.0      # BTC détenus dans la simulation

        # Recharge l'historique persistant
        self._load_trades()

    def _load_trades(self):
        """Recharge les trades persistés depuis logs/trades.jsonl (si présent)."""
        if not os.path.exists(TRADES_FILE):
            return
        try:
            with open(TRADES_FILE, "r", encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if line:
                        self.trades.append(json.loads(line))
            if self.trades:
                logger.info(f"Historique chargé : {len(self.trades)} trades depuis {TRADES_FILE}")
        except (OSError, json.JSONDecodeError) as e:
            logger.warning(f"Impossible de recharger {TRADES_FILE} : {e}")

    def _persist_trade(self, trade: dict):
        """Ajoute un trade en append au fichier JSONL."""
        try:
            os.makedirs(os.path.dirname(TRADES_FILE), exist_ok=True)
            with open(TRADES_FILE, "a", encoding="utf-8") as f:
                f.write(json.dumps(trade) + "\n")
        except OSError as e:
            logger.warning(f"Échec de persistance du trade : {e}")

    def snapshot(self, current_price: float | None = None, indicators: dict | None = None):
        """
        Écrit un snapshot de l'état courant dans logs/state.json.
        Lu par le dashboard pour afficher la position en cours et les métriques live.
        Écriture atomique via fichier temporaire + rename.
        """
        equity = None
        if DRY_RUN and current_price is not None:
            equity = self.sim_usdt + self.sim_btc * current_price

        snapshot = {
            "updated_at"   : datetime.now().isoformat(),
            "dry_run"      : DRY_RUN,
            "in_position"  : self.in_position,
            "entry_price"  : self.entry_price if self.in_position else None,
            "btc_held"     : self.btc_held    if self.in_position else None,
            "stop_loss"    : self.stop_loss   if self.in_position else None,
            "take_profit"  : self.take_profit if self.in_position else None,
            "current_price": current_price,
            "sim_usdt"     : self.sim_usdt,
            "sim_btc"      : self.sim_btc,
            "equity"       : round(equity, 2) if equity is not None else None,
            "start_usdt"   : self.start_usdt,
            "trades_count" : len(self.trades),
            "indicators"   : indicators,
        }
        try:
            os.makedirs(os.path.dirname(STATE_FILE), exist_ok=True)
            tmp = STATE_FILE + ".tmp"
            with open(tmp, "w", encoding="utf-8") as f:
                json.dump(snapshot, f, indent=2)
            os.replace(tmp, STATE_FILE)
        except OSError as e:
            logger.warning(f"Échec de snapshot : {e}")

    def open_position(self, entry_price, btc_amount, stop_loss, take_profit, cost_usdt=None):
        self.in_position = True
        self.entry_price = entry_price
        self.btc_held    = btc_amount
        self.stop_loss   = stop_loss
        self.take_profit = take_profit

        # Mise à jour du capital simulé : on dépense des USDT, on reçoit des BTC
        if DRY_RUN:
            spent = cost_usdt if cost_usdt is not None else btc_amount * entry_price
            self.sim_usdt -= spent
            self.sim_btc  += btc_amount

        logger.info(
            f"Position OUVERTE — Entrée : {entry_price:.2f} | BTC : {btc_amount:.6f}"
            + (f" | Capital sim : {self.sim_usdt:.2f} USDT + {self.sim_btc:.6f} BTC" if DRY_RUN else "")
        )

    def close_position(self, exit_price, reason):
        pnl_pct = ((exit_price - self.entry_price) / self.entry_price) * 100
        pnl_usdt = self.btc_held * (exit_price - self.entry_price)

        # Mise à jour du capital simulé : on récupère des USDT, on rend les BTC
        if DRY_RUN:
            self.sim_usdt += self.btc_held * exit_price
            self.sim_btc  -= self.btc_held

        equity_after = self.sim_usdt + self.sim_btc * exit_price if DRY_RUN else None

        trade = {
            "entry"     : round(self.entry_price, 2),
            "exit"      : round(exit_price, 2),
            "btc"       : round(self.btc_held, 6),
            "pnl_pct"   : round(pnl_pct, 2),
            "pnl_usdt"  : round(pnl_usdt, 2),
            "reason"    : reason,
            "time"      : datetime.now().isoformat(),
            "equity"    : round(equity_after, 2) if equity_after is not None else None,
            "dry_run"   : DRY_RUN,
        }
        self.trades.append(trade)
        self._persist_trade(trade)

        emoji = "✓" if pnl_usdt >= 0 else "✗"
        logger.info(
            f"Position FERMÉE [{reason}] {emoji} — "
            f"Entrée : {self.entry_price:.2f} | Sortie : {exit_price:.2f} | "
            f"PnL : {pnl_pct:+.2f}% ({pnl_usdt:+.2f} USDT)"
            + (f" | Equity : {equity_after:.2f} USDT" if equity_after is not None else "")
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
        if DRY_RUN:
            logger.info(
                f"Capital simulé final : {self.sim_usdt:.2f} USDT + {self.sim_btc:.6f} BTC"
            )


def run():
    """Point d'entrée principal du bot."""
    logger.info("=" * 60)
    logger.info(f"  BOT DE TRADING DÉMARRÉ {'[DRY RUN]' if DRY_RUN else '[LIVE]'}")
    logger.info("=" * 60)

    # Initialisation
    # - exchange (testnet)        : pour les soldes et les ordres (auth)
    # - data_exchange (public)    : pour OHLCV et prix courant (Binance Testnet
    #   ne sert que ~166 bougies historiques, insuffisant pour calculer SMA200)
    exchange      = create_exchange()
    data_exchange = create_public_exchange()
    state         = BotState()

    # Récupération du capital de départ (réel testnet)
    balances         = get_balance(exchange)
    state.start_usdt = balances["USDT"]
    logger.info(f"Capital de départ : {state.start_usdt:.2f} USDT")

    # En DRY_RUN : on initialise le capital simulé à partir du solde réel
    # Si un historique existe, on reprend depuis l'equity du dernier trade clôturé
    if DRY_RUN:
        if state.trades and state.trades[-1].get("equity") is not None:
            state.sim_usdt = state.trades[-1]["equity"]
            logger.info(
                f"Capital simulé restauré depuis l'historique : {state.sim_usdt:.2f} USDT "
                f"({len(state.trades)} trades précédents)"
            )
        else:
            state.sim_usdt = state.start_usdt
            logger.info(f"Capital simulé initialisé à : {state.sim_usdt:.2f} USDT")
        state.sim_btc = 0.0

    iteration = 0

    try:
        while True:
            iteration += 1
            logger.info(f"--- Itération #{iteration} ---")

            try:
                # ── 1. Données ─────────────────────────────────────────────
                df = fetch_ohlcv(data_exchange)

                # ── 2. Indicateurs ─────────────────────────────────────────
                df     = add_indicators(df)
                values = get_latest(df)
                price  = values["close"]

                # ── 3. Vérification stop-loss / take-profit ────────────────
                if state.in_position:
                    current_price = get_current_price(data_exchange)
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
                    # En DRY_RUN, on dimensionne sur le capital simulé pour
                    # une equity curve cohérente. En LIVE, sur le solde réel.
                    if DRY_RUN:
                        capital_for_sizing = state.sim_usdt
                    else:
                        balances           = get_balance(exchange)
                        capital_for_sizing = balances["USDT"]

                    risk_info = calculate_position(capital_for_sizing, price)

                    order = buy_market(exchange, risk_info["position_usdt"])
                    if order:
                        btc_received = risk_info["position_usdt"] / price
                        state.open_position(
                            entry_price = price,
                            btc_amount  = btc_received,
                            stop_loss   = risk_info["stop_loss"],
                            take_profit = risk_info["take_profit"],
                            cost_usdt   = risk_info["position_usdt"],
                        )

                elif signal == Signal.SELL and state.in_position:
                    order = sell_market(exchange, state.btc_held)
                    if order:
                        state.close_position(price, "STRATEGY_SIGNAL")

                # ── 6. Snapshot pour le dashboard ──────────────────────────
                state.snapshot(current_price=price, indicators={
                    "rsi"      : round(values["rsi"], 2),
                    "sma_fast" : round(values["sma_fast"], 2),
                    "sma_slow" : round(values["sma_slow"], 2),
                    "sma200"   : round(values["sma200"], 2) if values["sma200"] == values["sma200"] else None,
                })

            except RuntimeError as e:
                logger.error(f"Erreur récupérable : {e} — nouvelle tentative dans {LOOP_INTERVAL}s")

            except Exception as e:
                logger.exception(f"Erreur inattendue : {e}")
                break

            # ── 7. Attente ─────────────────────────────────────────────────
            logger.debug(f"Prochaine itération dans {LOOP_INTERVAL}s…")
            time.sleep(LOOP_INTERVAL)

    except KeyboardInterrupt:
        pass  # Ctrl+C intercepté ici (pendant le code ou le sleep)
    finally:
        logger.info("Arrêt du bot (Ctrl+C)")
        state.print_summary()


if __name__ == "__main__":
    run()
