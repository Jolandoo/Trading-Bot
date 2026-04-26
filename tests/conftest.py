# =============================================================================
# conftest.py — Configuration pytest : mock du module config
# =============================================================================
# Injecte un faux module config dans sys.modules AVANT que pytest importe
# les modules du projet. Cela permet de lancer les tests sans avoir de
# config.py local avec de vraies clés API.
# =============================================================================

import sys
import types

_cfg = types.ModuleType("config")
_cfg.API_KEY          = "test_key"
_cfg.API_SECRET       = "test_secret"
_cfg.SYMBOL           = "BTC/USDT"
_cfg.TIMEFRAME        = "4h"
_cfg.LIMIT            = 100
_cfg.RSI_PERIOD       = 14
_cfg.SMA_FAST         = 9
_cfg.SMA_SLOW         = 21
_cfg.RSI_OVERSOLD     = 30
_cfg.RSI_OVERBOUGHT   = 70
_cfg.RISK_PER_TRADE   = 0.01
_cfg.STOP_LOSS_PCT    = 0.03
_cfg.TAKE_PROFIT_PCT  = 0.06
_cfg.USE_SMA200_FILTER = True
_cfg.DRY_RUN          = True
_cfg.LOOP_INTERVAL    = 60
_cfg.LOG_LEVEL        = "WARNING"   # Silence les logs pendant les tests

# Écrase tout config.py existant pour garantir l'isolation des tests
sys.modules["config"] = _cfg
