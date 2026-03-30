# =============================================================================
# executor.py — Passage des ordres sur Binance (Testnet ou réel)
# =============================================================================
# Ce module est le seul à toucher à de l'argent réel.
# DRY_RUN = True → les ordres sont simulés, rien n'est envoyé à Binance.
# DRY_RUN = False → les ordres sont réellement exécutés sur le Testnet.
# =============================================================================

import ccxt
import logging
from config import SYMBOL, DRY_RUN

logger = logging.getLogger(__name__)


def buy_market(exchange: ccxt.binance, usdt_amount: float) -> dict | None:
    """
    Passe un ordre d'achat au prix du marché.

    Args:
        exchange     : instance CCXT connectée au Testnet
        usdt_amount  : montant en USDT à dépenser

    Returns:
        Le détail de l'ordre exécuté, ou un dict simulé en DRY_RUN.
    """
    if DRY_RUN:
        logger.info(f"[DRY RUN] Achat simulé — {usdt_amount:.2f} USDT sur {SYMBOL}")
        # On retourne un dict qui ressemble à une vraie réponse CCXT
        return {
            "id"     : "DRY_RUN_BUY",
            "status" : "closed",
            "side"   : "buy",
            "amount" : usdt_amount,
            "cost"   : usdt_amount,
            "dry_run": True,
        }

    try:
        # "quoteOrderQty" = on dépense exactement N USDT (plutôt que d'acheter N BTC)
        order = exchange.create_order(
            symbol = SYMBOL,
            type   = "market",
            side   = "buy",
            amount = usdt_amount,
            params = {"quoteOrderQty": usdt_amount},
        )
        logger.info(f"Ordre BUY exécuté — ID : {order['id']} | Montant : {usdt_amount:.2f} USDT")
        return order

    except ccxt.InsufficientFunds:
        logger.error("Fonds insuffisants pour passer l'ordre d'achat")
        return None
    except ccxt.ExchangeError as e:
        logger.error(f"Erreur lors de l'achat : {e}")
        return None


def sell_market(exchange: ccxt.binance, btc_amount: float) -> dict | None:
    """
    Passe un ordre de vente au prix du marché.

    Args:
        exchange    : instance CCXT connectée au Testnet
        btc_amount  : quantité de BTC à vendre

    Returns:
        Le détail de l'ordre exécuté, ou un dict simulé en DRY_RUN.
    """
    if DRY_RUN:
        logger.info(f"[DRY RUN] Vente simulée — {btc_amount:.6f} BTC sur {SYMBOL}")
        return {
            "id"     : "DRY_RUN_SELL",
            "status" : "closed",
            "side"   : "sell",
            "amount" : btc_amount,
            "dry_run": True,
        }

    try:
        order = exchange.create_order(
            symbol = SYMBOL,
            type   = "market",
            side   = "sell",
            amount = btc_amount,
        )
        logger.info(f"Ordre SELL exécuté — ID : {order['id']} | Quantité : {btc_amount:.6f} BTC")
        return order

    except ccxt.InsufficientFunds:
        logger.error("Fonds insuffisants pour passer l'ordre de vente")
        return None
    except ccxt.ExchangeError as e:
        logger.error(f"Erreur lors de la vente : {e}")
        return None
