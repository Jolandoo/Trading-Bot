# =============================================================================
# data.py — Récupération des données de marché via CCXT
# =============================================================================
# CCXT est une librairie Python qui unifie les API de 100+ exchanges.
# On l'utilise pour récupérer les bougies OHLCV depuis Binance Testnet.
# Doc : https://docs.ccxt.com
# =============================================================================

import ccxt
import pandas as pd
import logging
from config import API_KEY, API_SECRET, SYMBOL, TIMEFRAME, LIMIT

logger = logging.getLogger(__name__)


def create_public_exchange() -> ccxt.binance:
    """
    Connexion Binance PUBLIQUE sans clé API.
    Donne accès aux prix réels du marché (OHLCV, ticker) en lecture seule.
    Utilisée par le paper trading pour avoir de vraies données de marché.
    """
    exchange = ccxt.binance({"enableRateLimit": True})
    logger.info(f"Exchange public initialisé : Binance Live | Paire : {SYMBOL}")
    return exchange


def create_exchange() -> ccxt.binance:
    """
    Crée et configure la connexion à Binance Testnet.
    Le Testnet est un environnement de test : tu reçois de vrais BTC/USDT
    fictifs et tu peux trader sans risque réel.
    """
    exchange = ccxt.binance({
        "apiKey": API_KEY,
        "secret": API_SECRET,
        "enableRateLimit": True,   # Respecte automatiquement les limites de l'API
        "options": {
            "defaultType": "spot",
            "adjustForTimeDifference": True,
        },
    })

    # ← Ligne clé : bascule sur le Testnet au lieu du vrai Binance
    exchange.set_sandbox_mode(True)

    logger.info(f"Exchange initialisé : Binance Testnet | Paire : {SYMBOL}")
    return exchange


def fetch_ohlcv(exchange: ccxt.binance) -> pd.DataFrame:
    """
    Récupère les dernières bougies OHLCV et les retourne en DataFrame.

    Colonnes retournées :
        timestamp  → horodatage de la bougie (datetime)
        open       → prix d'ouverture
        high       → plus haut atteint
        low        → plus bas atteint
        close      → prix de clôture  ← celui qu'on utilise le plus
        volume     → volume échangé

    Raises:
        RuntimeError si la récupération échoue.
    """
    try:
        raw = exchange.fetch_ohlcv(SYMBOL, timeframe=TIMEFRAME, limit=LIMIT)
        df = pd.DataFrame(raw, columns=["timestamp", "open", "high", "low", "close", "volume"])
        df["timestamp"] = pd.to_datetime(df["timestamp"], unit="ms")
        df.set_index("timestamp", inplace=True)
        logger.debug(f"Bougies récupérées : {len(df)} | Dernière clôture : {df['close'].iloc[-1]:.2f}")
        return df

    except ccxt.NetworkError as e:
        logger.error(f"Erreur réseau : {e}")
        raise RuntimeError("Impossible de joindre Binance Testnet") from e
    except ccxt.ExchangeError as e:
        logger.error(f"Erreur exchange : {e}")
        raise RuntimeError("Erreur côté Binance") from e


def get_current_price(exchange: ccxt.binance) -> float:
    """
    Retourne le prix actuel (last trade) de la paire configurée.
    Plus rapide que fetch_ohlcv pour une simple vérification de prix.
    """
    ticker = exchange.fetch_ticker(SYMBOL)
    price = float(ticker["last"])
    logger.debug(f"Prix actuel {SYMBOL} : {price:.2f}")
    return price


def get_balance(exchange: ccxt.binance) -> dict:
    """
    Retourne les soldes disponibles sur le compte Testnet.
    Exemple de retour : {"USDT": 10000.0, "BTC": 0.05}
    """
    balance = exchange.fetch_balance()
    usdt = float(balance["USDT"]["free"])
    btc  = float(balance["BTC"]["free"])
    logger.info(f"Soldes — USDT : {usdt:.2f} | BTC : {btc:.6f}")
    return {"USDT": usdt, "BTC": btc}
