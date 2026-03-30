# =============================================================================
# risk.py — Gestion du risque et calcul de la taille de position
# =============================================================================
# Règle fondamentale : on ne risque jamais plus de X% du capital par trade.
#
# Formule :
#   montant_à_risquer = capital_total × risk_pct
#   taille_position   = montant_à_risquer / stop_loss_pct
#
# Exemple concret :
#   Capital = 1 000 USDT, risque = 1%, stop-loss = 3%
#   → On risque 10 USDT par trade
#   → Taille de position = 10 / 0.03 = 333 USDT
#   → Si le prix baisse de 3%, on perd exactement 10 USDT (= 1% du capital)
# =============================================================================

import logging
from config import RISK_PER_TRADE, STOP_LOSS_PCT, TAKE_PROFIT_PCT

logger = logging.getLogger(__name__)


def calculate_position(capital_usdt: float, entry_price: float) -> dict:
    """
    Calcule la taille de position optimale selon la règle de gestion du risque.

    Args:
        capital_usdt : capital disponible en USDT
        entry_price  : prix d'achat prévu (généralement le prix actuel)

    Returns:
        dict avec :
            position_usdt  → montant en USDT à investir
            position_btc   → quantité de BTC à acheter
            stop_loss      → prix de déclenchement du stop-loss
            take_profit    → prix cible de prise de bénéfice
            risk_usdt      → montant réellement risqué
    """
    # Montant risqué = 1% du capital (par défaut)
    risk_usdt = capital_usdt * RISK_PER_TRADE

    # Taille de position : si le stop-loss se déclenche, on perd exactement risk_usdt
    position_usdt = risk_usdt / STOP_LOSS_PCT

    # Sécurité : jamais plus que 95% du capital disponible (garde une marge)
    position_usdt = min(position_usdt, capital_usdt * 0.95)

    # Convertir en quantité de BTC
    position_btc = position_usdt / entry_price

    # Niveaux de stop-loss et take-profit
    stop_loss   = entry_price * (1 - STOP_LOSS_PCT)
    take_profit = entry_price * (1 + TAKE_PROFIT_PCT)

    result = {
        "position_usdt" : round(position_usdt, 2),
        "position_btc"  : round(position_btc, 6),
        "stop_loss"     : round(stop_loss, 2),
        "take_profit"   : round(take_profit, 2),
        "risk_usdt"     : round(risk_usdt, 2),
        "rr_ratio"      : round(TAKE_PROFIT_PCT / STOP_LOSS_PCT, 1),
    }

    logger.info(
        f"Position calculée — "
        f"Investissement : {result['position_usdt']} USDT ({result['position_btc']} BTC) | "
        f"SL : {result['stop_loss']} | TP : {result['take_profit']} | "
        f"Risque réel : {result['risk_usdt']} USDT | R:R = 1:{result['rr_ratio']}"
    )
    return result


def check_exit_conditions(
    entry_price: float,
    current_price: float,
    stop_loss: float,
    take_profit: float,
) -> str | None:
    """
    Vérifie si le prix actuel a touché le stop-loss ou le take-profit.

    Args:
        entry_price   : prix auquel on a acheté
        current_price : prix actuel du marché
        stop_loss     : niveau de stop-loss calculé
        take_profit   : niveau de take-profit calculé

    Returns:
        "STOP_LOSS"   → fermer la position en urgence (perte maîtrisée)
        "TAKE_PROFIT" → fermer la position (objectif atteint)
        None          → on reste en position
    """
    pnl_pct = ((current_price - entry_price) / entry_price) * 100

    if current_price <= stop_loss:
        logger.warning(
            f"STOP-LOSS DÉCLENCHÉ — Prix : {current_price:.2f} <= SL : {stop_loss:.2f} "
            f"| PnL : {pnl_pct:.2f}%"
        )
        return "STOP_LOSS"

    if current_price >= take_profit:
        logger.info(
            f"TAKE-PROFIT ATTEINT — Prix : {current_price:.2f} >= TP : {take_profit:.2f} "
            f"| PnL : {pnl_pct:.2f}%"
        )
        return "TAKE_PROFIT"

    logger.debug(
        f"Position ouverte — Prix : {current_price:.2f} | PnL : {pnl_pct:+.2f}% | "
        f"SL : {stop_loss:.2f} | TP : {take_profit:.2f}"
    )
    return None
