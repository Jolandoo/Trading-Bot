# =============================================================================
# indicators.py — Calcul des indicateurs techniques
# =============================================================================
# pandas-ta (Technical Analysis) calcule RSI, SMA, MACD, Bollinger Bands…
# en une seule ligne. On l'applique directement sur notre DataFrame OHLCV.
# Doc : https://github.com/twopirllc/pandas-ta
# =============================================================================

import pandas as pd
import pandas_ta as ta
import logging
from config import RSI_PERIOD, SMA_FAST, SMA_SLOW

logger = logging.getLogger(__name__)


def add_indicators(df: pd.DataFrame) -> pd.DataFrame:
    """
    Enrichit le DataFrame avec les indicateurs techniques.

    Ajoute les colonnes :
        rsi       → Relative Strength Index (0–100)
        sma_fast  → Moyenne mobile simple courte (ex: 9 périodes)
        sma_slow  → Moyenne mobile simple longue (ex: 21 périodes)

    Args:
        df : DataFrame OHLCV issu de data.fetch_ohlcv()

    Returns:
        Le même DataFrame avec les colonnes d'indicateurs ajoutées.
    """
    df = df.copy()

    # RSI — mesure si le marché est suracheté (>70) ou survendu (<30)
    # Formula : RSI = 100 - 100/(1 + RS) où RS = moyenne gains / moyenne pertes
    df["rsi"] = ta.rsi(df["close"], length=RSI_PERIOD)

    # SMA — Simple Moving Average : moyenne des N dernières clôtures
    # SMA rapide réagit vite, SMA lente est plus "smooth"
    df[f"sma_fast"] = ta.sma(df["close"], length=SMA_FAST)
    df[f"sma_slow"] = ta.sma(df["close"], length=SMA_SLOW)

    # Supprime les lignes du début où les indicateurs ne sont pas encore calculés
    # (ex: les 21 premières bougies n'ont pas encore assez de données pour SMA21)
    df.dropna(inplace=True)

    logger.debug(
        f"Indicateurs calculés | RSI={df['rsi'].iloc[-1]:.1f} | "
        f"SMA{SMA_FAST}={df['sma_fast'].iloc[-1]:.2f} | "
        f"SMA{SMA_SLOW}={df['sma_slow'].iloc[-1]:.2f}"
    )
    return df


def get_latest(df: pd.DataFrame) -> dict:
    """
    Extrait les valeurs actuelles (dernière bougie) de tous les indicateurs.

    Returns:
        dict avec les clés : close, rsi, sma_fast, sma_slow,
                             prev_sma_fast, prev_sma_slow
        Les clés "prev_*" servent à détecter les croisements.
    """
    last  = df.iloc[-1]   # Bougie actuelle (en cours ou dernière clôturée)
    prev  = df.iloc[-2]   # Bougie précédente — nécessaire pour détecter un croisement

    values = {
        "close"         : float(last["close"]),
        "rsi"           : float(last["rsi"]),
        "sma_fast"      : float(last["sma_fast"]),
        "sma_slow"      : float(last["sma_slow"]),
        "prev_sma_fast" : float(prev["sma_fast"]),   # ← SMA rapide de la bougie d'avant
        "prev_sma_slow" : float(prev["sma_slow"]),   # ← SMA lente de la bougie d'avant
    }

    logger.debug(f"Valeurs actuelles : {values}")
    return values
