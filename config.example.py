# =============================================================================
# config.py — Configuration centrale du bot
# =============================================================================
# Mets tes clés API Binance Testnet ici.
# Pour les obtenir : https://testnet.binance.vision/
# Crée un compte testnet → Generate HMAC_SHA256 Key
# =============================================================================

# --- Clés API Binance Testnet ---
API_KEY    = "REMPLACE_PAR_TA_CLE_TESTNET"
API_SECRET = "REMPLACE_PAR_TON_SECRET_TESTNET"

# --- Marché ---
SYMBOL     = "BTC/USDT"   # Paire tradée
TIMEFRAME  = "1h"          # Intervalle des bougies : 1m, 5m, 15m, 1h, 4h, 1d
LIMIT      = 100           # Nombre de bougies à récupérer pour les calculs

# --- Indicateurs ---
RSI_PERIOD    = 14    # Période standard du RSI
SMA_FAST      = 9     # Moyenne mobile rapide
SMA_SLOW      = 21    # Moyenne mobile lente
RSI_OVERSOLD  = 30    # En dessous → marché survendu (signal achat possible)
RSI_OVERBOUGHT= 70    # Au dessus  → marché suracheté (signal vente possible)

# --- Gestion du risque ---
RISK_PER_TRADE = 0.01   # 1% du capital risqué par trade (règle d'or)
STOP_LOSS_PCT  = 0.03   # Stop-loss à -3% du prix d'entrée
TAKE_PROFIT_PCT= 0.06   # Take-profit à +6% du prix d'entrée (ratio R:R = 2)

# --- Comportement du bot ---
DRY_RUN        = True    # True = simulation pure (aucun ordre réel envoyé)
LOOP_INTERVAL  = 60      # Secondes entre chaque itération de la boucle
LOG_LEVEL      = "INFO"  # DEBUG pour plus de détails, INFO pour l'essentiel