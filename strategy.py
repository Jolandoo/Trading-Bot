# =============================================================================
# strategy.py — Logique de génération des signaux de trading
# =============================================================================
# Stratégie : Golden Cross / Death Cross filtré par RSI
#
# ACHAT  si : SMA_fast croise SMA_slow par le HAUT  +  RSI < 70
# VENTE  si : SMA_fast croise SMA_slow par le BAS   ou RSI > 70 en position
#
# Le "croisement" se détecte en comparant la bougie actuelle à la précédente :
#   - Avant : sma_fast < sma_slow  (bearish)
#   - Après  : sma_fast > sma_slow  (bullish) → c'est le golden cross !
# =============================================================================

import logging
from enum import Enum
from config import RSI_OVERSOLD, RSI_OVERBOUGHT

logger = logging.getLogger(__name__)


class Signal(Enum):
    """Les trois états possibles du signal à chaque itération."""
    BUY  = "BUY"
    SELL = "SELL"
    HOLD = "HOLD"    # Pas d'action — on reste dans l'état actuel


def check_signal(values: dict, in_position: bool) -> Signal:
    """
    Évalue les conditions et retourne le signal approprié.

    Args:
        values      : dict retourné par indicators.get_latest()
        in_position : True si le bot possède déjà du BTC

    Returns:
        Signal.BUY  → ouvrir une position (acheter)
        Signal.SELL → fermer la position (vendre)
        Signal.HOLD → ne rien faire
    """
    rsi       = values["rsi"]
    sma_fast  = values["sma_fast"]
    sma_slow  = values["sma_slow"]
    prev_fast = values["prev_sma_fast"]
    prev_slow = values["prev_sma_slow"]

    # --- Détection du Golden Cross ---
    # La SMA rapide passe AU-DESSUS de la SMA lente → tendance haussière
    golden_cross = (prev_fast <= prev_slow) and (sma_fast > sma_slow)

    # --- Détection du Death Cross ---
    # La SMA rapide passe EN-DESSOUS de la SMA lente → tendance baissière
    death_cross  = (prev_fast >= prev_slow) and (sma_fast < sma_slow)

    # -------------------------------------------------------
    # Logique d'ACHAT — seulement si on n'est PAS en position
    # -------------------------------------------------------
    if not in_position:
        if golden_cross and rsi < RSI_OVERBOUGHT:
            logger.info(
                f"SIGNAL BUY — Golden Cross détecté | "
                f"RSI={rsi:.1f} | SMA{9}={sma_fast:.2f} > SMA{21}={sma_slow:.2f}"
            )
            return Signal.BUY

    # -------------------------------------------------------
    # Logique de VENTE — seulement si on EST en position
    # -------------------------------------------------------
    else:
        if death_cross:
            logger.info(
                f"SIGNAL SELL — Death Cross détecté | "
                f"SMA{9}={sma_fast:.2f} < SMA{21}={sma_slow:.2f}"
            )
            return Signal.SELL

        if rsi > RSI_OVERBOUGHT:
            logger.info(f"SIGNAL SELL — RSI suracheté : {rsi:.1f} > {RSI_OVERBOUGHT}")
            return Signal.SELL

    # --- Pas de signal clair ---
    logger.debug(
        f"HOLD | RSI={rsi:.1f} | "
        f"SMA_fast={'>' if sma_fast > sma_slow else '<'} SMA_slow | "
        f"En position : {in_position}"
    )
    return Signal.HOLD
