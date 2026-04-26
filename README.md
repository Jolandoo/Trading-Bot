# Trading Bot — BTC/USDT sur Binance

Bot de trading algorithmique en Python qui trade BTC/USDT sur Binance (Testnet ou réel) via une stratégie Golden Cross / Death Cross filtrée par le RSI.

---

## Stratégie

Le bot repose sur le croisement de deux moyennes mobiles simples (SMA), confirmé par le RSI :

| Signal | Condition |
|--------|-----------|
| **BUY** | SMA(9) croise SMA(21) à la hausse **ET** RSI < 55 |
| **SELL** | SMA(9) croise SMA(21) à la baisse **OU** RSI > 55 |

### Gestion du risque

- **Stop-Loss** : –3 % depuis le prix d'entrée (sortie automatique)
- **Take-Profit** : +6 % depuis le prix d'entrée (sortie automatique)
- **Taille de position** : `Capital × 1% / Stop-Loss %`  
  → Ex : 10 000 USDT → risque 100 USDT → position de 3 333 USDT

---

## Installation

### Prérequis

- Python 3.10+
- Compte Binance Testnet : [testnet.binance.vision](https://testnet.binance.vision/)

### Étapes

```bash
# 1. Cloner le dépôt
git clone https://github.com/ton-user/Trading-Bot.git
cd Trading-Bot

# 2. Créer un environnement virtuel
python -m venv .venv
source .venv/bin/activate        # Linux / macOS
.venv\Scripts\activate           # Windows

# 3. Installer les dépendances
pip install -r requirements.txt

# 4. Configurer le bot
cp config.example.py config.py
# → Édite config.py et renseigne tes clés API Testnet
```

### Obtenir des clés API Testnet Binance

1. Connecte-toi sur [testnet.binance.vision](https://testnet.binance.vision/) avec GitHub
2. Clique sur **"Generate HMAC_SHA256 Key"**
3. Copie `API_KEY` et `API_SECRET` dans `config.py`

---

## Configuration

Tous les paramètres se trouvent dans `config.py` :

```python
# Connexion
API_KEY    = "..."          # Clé Testnet
API_SECRET = "..."          # Secret Testnet

# Marché
SYMBOL     = "BTC/USDT"
TIMEFRAME  = "4h"           # Intervalle des bougies
LIMIT      = 100            # Nombre de bougies chargées

# Indicateurs
RSI_PERIOD   = 14
SMA_FAST     = 9
SMA_SLOW     = 21
RSI_OVERSOLD    = 30
RSI_OVERBOUGHT  = 55

# Risque
RISK_PER_TRADE   = 0.01    # 1 % du capital par trade
STOP_LOSS_PCT    = 0.03    # Stop-Loss à –3 %
TAKE_PROFIT_PCT  = 0.06    # Take-Profit à +6 %

# Comportement
DRY_RUN        = True      # True = simulation, False = ordres réels
LOOP_INTERVAL  = 60        # Secondes entre chaque itération
LOG_LEVEL      = "INFO"
```

> **`DRY_RUN = True`** par défaut — aucun ordre réel n'est envoyé, zéro risque financier.

---

## Lancement

```bash
# Mode simulation (recommandé pour débuter)
python main.py

# Backtesting sur 12 mois de données historiques
python backtest.py
```

### Exemple de sortie terminal

```
14:32:01 | INFO  | main      | BOT DE TRADING DÉMARRÉ [DRY RUN]
14:32:02 | INFO  | data      | Soldes — USDT : 10 000.00 | BTC : 0.000000
14:32:03 | INFO  | strategy  | SIGNAL BUY — Golden Cross détecté | RSI=52.3
14:32:03 | INFO  | risk      | Position calculée — 3 333 USDT | SL : 77 000 | TP : 84 800
14:32:03 | INFO  | main      | [DRY RUN] Position OUVERTE — Entrée : 79 381.00
14:36:04 | INFO  | risk      | TAKE-PROFIT atteint | PnL : +199.99 USDT
```

---

## Architecture

```
Trading-Bot/
├── main.py          # Orchestrateur — boucle principale + gestion d'état
├── data.py          # Connexion à Binance et récupération des bougies OHLCV
├── indicators.py    # Calcul du RSI et des SMA via pandas-ta
├── strategy.py      # Détection des signaux Golden/Death Cross
├── risk.py          # Calcul de position et vérification SL/TP
├── executor.py      # Envoi (ou simulation) des ordres marché
├── backtest.py      # Moteur de backtesting + Walk-Forward Analysis
├── metrics.py       # Sharpe, Sortino, Calmar, Profit Factor, Espérance
├── tests/           # Suite de tests unitaires (pytest, 57 tests)
├── logs/            # Logs rotatifs du bot (bot.log, généré automatiquement)
├── config.py        # Paramètres du bot (ignoré par git)
├── config.example.py
└── requirements.txt
```

### Flux d'exécution

```
Initialisation
    └── Connexion Binance Testnet
    └── Chargement du capital disponible
        │
        └── Boucle infinie (toutes les 60 s)
                ├── Récupération des 100 dernières bougies 4h
                ├── Calcul RSI, SMA(9), SMA(21)
                ├── [Si en position] Vérification SL / TP
                ├── Évaluation du signal stratégie
                ├── Exécution de l'ordre si signal détecté
                └── Attente 60 s → recommence
```

---

## Backtesting

```bash
python backtest.py [mode]
```

| Mode | Description |
|------|-------------|
| *(aucun)* ou `standard` | Backtest 12 mois (défaut) |
| `walkforward` | Walk-Forward Analysis (3 fenêtres indépendantes) |
| `periods` | Compare 1 an / 3 ans / 5 ans d'historique |
| `regimes` | Compare bull 2020-21 / bear 2022 / chop 2023 / bull 2024 |
| `timeframes` | Compare 1h / 4h / 1d sur la même période |
| `all` | Lance toutes les analyses ci-dessus |

**Métriques de base**
- PnL total (USDT et %), ratio gain/perte, espérance par trade
- Drawdown maximum, pertes consécutives maximales
- Comparaison vs Buy & Hold, détail des 20 derniers trades

**Métriques avancées** (annualisées selon le timeframe)
- **Sharpe ratio** — rendement ajusté à la volatilité totale
- **Sortino ratio** — ne pénalise que la volatilité baissière
- **Calmar ratio** — TCAM / drawdown maximum (> 1 = excellent)
- **Profit Factor** — somme des gains / somme des pertes (> 1.5 = bon)

**Walk-Forward Analysis**
Découpe en 3 fenêtres temporelles indépendantes — révèle si la stratégie
est robuste dans le temps ou dépendante d'une seule période favorable.

**Analyse par régimes de marché**
Teste séparément les phases bull (2020-21, 2024), bear (2022) et chop (2023)
pour identifier dans quel contexte la stratégie performe ou échoue.

**Analyse multi-timeframes**
Compare 1h / 4h / 1d avec des métriques Sharpe/Sortino correctement
annualisées par timeframe — pour trouver le réglage optimal.

### Résultats — BTC/USDT 4h (mai 2025 → avril 2026)

> Paramètres : capital 10 000 USDT · SL –3 % · TP +6 % · risque 1 %/trade · frais 0,1 %

| Métrique | Valeur |
|----------|--------|
| **Capital initial** | 10 000,00 USDT |
| **Capital final** | 10 568,89 USDT |
| **PnL total** | **+568,89 USDT (+5,69 %)** |
| **Buy & Hold sur la période** | –25,70 % |
| **Nombre de trades** | 19 |
| **Win rate** | 47,4 % |
| **Gain moyen / trade** | +186,08 USDT |
| **Perte moyenne / trade** | –104,20 USDT |
| **Ratio Gain/Perte** | 1,79 |
| **Drawdown maximum** | –4,42 % |
| **Sharpe ratio** | à recalculer avec `python backtest.py` |
| **Sortino ratio** | à recalculer avec `python backtest.py` |
| **Calmar ratio** | à recalculer avec `python backtest.py` |
| **Profit Factor** | à recalculer avec `python backtest.py` |

**Verdict : stratégie gagnante sur la période, et largement meilleure que le Buy & Hold (–25,7 %).**  
Le ratio gain/perte de 1,79 valide la logique SL/TP asymétrique (3 % / 6 %).

#### Détail des 19 trades

| Date entrée | Entrée (USDT) | Sortie (USDT) | PnL % | PnL USDT | Raison |
|-------------|---------------|---------------|-------|----------|--------|
| 2025-06-20 | 105 922 | 102 744 | –3,00 % | –103,23 | STOP_LOSS |
| 2025-07-25 | 118 313 | 114 764 | –3,00 % | –102,13 | STOP_LOSS |
| 2025-08-01 | 118 183 | 114 637 | –3,00 % | –101,04 | STOP_LOSS |
| 2025-08-11 | 114 493 | 121 363 | +6,00 % | +190,25 | TAKE_PROFIT |
| 2025-08-29 | 112 000 | 108 640 | –3,00 % | –101,90 | STOP_LOSS |
| 2025-09-12 | 109 237 | 115 792 | +6,00 % | +191,86 | TAKE_PROFIT |
| 2025-10-01 | 111 581 | 118 276 | +6,00 % | +195,57 | TAKE_PROFIT |
| 2025-10-14 | 115 793 | 112 319 | –3,00 % | –104,74 | STOP_LOSS |
| 2025-10-26 | 108 643 | 115 161 | +6,00 % | +197,22 | TAKE_PROFIT |
| 2025-11-03 | 110 300 | 106 991 | –3,00 % | –105,63 | STOP_LOSS |
| 2025-11-13 | 101 662 | 98 612 | –3,00 % | –104,50 | STOP_LOSS |
| 2025-11-28 | 86 830 | 92 040 | +6,00 % | +196,77 | TAKE_PROFIT |
| 2026-01-05 | 87 952 | 93 229 | +6,00 % | +200,57 | TAKE_PROFIT |
| 2026-01-25 | 89 770 | 87 077 | –3,00 % | –107,42 | STOP_LOSS |
| 2026-02-11 | 69 289 | 67 211 | –3,00 % | –106,28 | STOP_LOSS |
| 2026-02-23 | 68 020 | 65 979 | –3,00 % | –105,15 | STOP_LOSS |
| 2026-03-02 | 65 776 | 69 723 | +6,00 % | +197,97 | TAKE_PROFIT |
| 2026-04-07 | 67 680 | 71 741 | +6,00 % | +201,80 | TAKE_PROFIT |
| *(ouvert)* | 75 835 | 78 145 | +3,05 % | +102,73 | END_OF_DATA |

> **Note :** les SL et TP sont déclenchés sur le high/low de la bougie (simulation réaliste).  
> Les frais de 0,1 % par ordre sont appliqués à l'entrée et à la sortie.

---

## Tests

```bash
python -m pytest tests/ -v
```

57 tests unitaires couvrant l'ensemble des modules critiques :

| Module testé | Fichier | Tests |
|---|---|---|
| Signaux de trading | `tests/test_strategy.py` | Golden/Death Cross, RSI, HOLD |
| Gestion du risque | `tests/test_risk.py` | Position size, SL/TP math |
| Indicateurs techniques | `tests/test_indicators.py` | RSI bornes, SMA réactivité, immutabilité |
| Métriques | `tests/test_metrics.py` | Sharpe, Sortino, Calmar, PF, Espérance |
| Moteur backtest | `tests/test_backtest.py` | Structure, trades SL/TP, métriques |

Les tests s'exécutent sans clé API (mock automatique de `config.py` via `conftest.py`).

---

## Dépendances

| Package | Version | Usage |
|---------|---------|-------|
| `ccxt` | ≥ 4.2.0 | Connexion aux exchanges (Binance, +100 autres) |
| `pandas` | ≥ 2.0.0 | Manipulation des séries temporelles |
| `pandas-ta` | ≥ 0.3.14b | Calcul des indicateurs techniques |
| `numpy` | ≥ 1.24.0 | Calcul des métriques de performance |
| `pytest` | ≥ 7.4.0 | Suite de tests unitaires |

---

## Sécurité

- `config.py` est dans `.gitignore` — tes clés API ne sont **jamais** commitées
- Le mode `DRY_RUN = True` garantit qu'aucun ordre réel n'est envoyé tant que tu ne le passes pas à `False` explicitement
- Utilise exclusivement des clés **Testnet** pour les tests — elles n'ont aucune valeur réelle

---

## Passer en production

1. Crée des clés API sur [binance.com](https://www.binance.com/) (avec permission **Trade** uniquement, sans retrait)
2. Dans `config.py` : remplace les clés Testnet par les clés réelles
3. Dans `config.py` : passe `DRY_RUN = False`
4. Lance avec une petite somme pour valider le comportement en conditions réelles
