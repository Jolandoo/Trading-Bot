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
from config import RSI_PERIOD, SMA_FAST, SMA_SLOW, USE_SMA200_FILTER

logger = logging.getLogger(__name__)


def add_indicators(df: pd.DataFrame) -> pd.DataFrame:
    """
    Enrichit le DataFrame avec les indicateurs techniques.

    Ajoute les colonnes :
        rsi       → Relative Strength Index (0–100)
        sma_fast  → Moyenne mobile simple courte (ex: 9 périodes)
        sma_slow  → Moyenne mobile simple longue (ex: 21 périodes)
        sma200    → SMA 200 périodes (filtre de tendance long terme)

    Args:
        df : DataFrame OHLCV issu de data.fetch_ohlcv()

    Returns:
        Le même DataFrame avec les colonnes d'indicateurs ajoutées.
    """
    df = df.copy()

    df["rsi"]      = ta.rsi(df["close"], length=RSI_PERIOD)
    df["sma_fast"] = ta.sma(df["close"], length=SMA_FAST)
    df["sma_slow"] = ta.sma(df["close"], length=SMA_SLOW)
    df["sma200"]   = ta.sma(df["close"], length=200)

    # Ne supprime que les lignes sans RSI/SMA de trading — sma200 peut rester NaN
    # si LIMIT < 200 (dégradation gracieuse : le filtre SMA200 ne s'applique pas)
    df.dropna(subset=["rsi", "sma_fast", "sma_slow"], inplace=True)

    sma200_last = df["sma200"].iloc[-1]
    sma200_str  = f"{float(sma200_last):.2f}" if pd.notna(sma200_last) else "N/A"
    logger.debug(
        f"Indicateurs calculés | RSI={df['rsi'].iloc[-1]:.1f} | "
        f"SMA{SMA_FAST}={df['sma_fast'].iloc[-1]:.2f} | "
        f"SMA{SMA_SLOW}={df['sma_slow'].iloc[-1]:.2f} | "
        f"SMA200={sma200_str}"
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
        "prev_sma_fast" : float(prev["sma_fast"]),
        "prev_sma_slow" : float(prev["sma_slow"]),
        "sma200"        : float(last["sma200"]) if pd.notna(last["sma200"]) else float("nan"),
    }

    logger.debug(f"Valeurs actuelles : {values}")
    return values
