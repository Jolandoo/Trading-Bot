# 1. Installer les dépendances
pip install -r requirements.txt

# 2. Récupérer tes clés sur https://testnet.binance.vision/
#    → Se connecter avec GitHub → "Generate HMAC_SHA256 Key"

# 3. Coller tes clés dans config.py (lignes API_KEY et API_SECRET)

# 4. Lancer le bot (DRY_RUN = True par défaut, aucun risque)
python main.py
```

**Ce que fait chaque fichier, en une phrase :**

- `config.py` — tous les paramètres au même endroit, tu ne touches qu'à lui pour régler le bot
- `data.py` — se connecte au Testnet et récupère les bougies OHLCV
- `indicators.py` — calcule RSI et SMA en une ligne grâce à `pandas-ta`
- `strategy.py` — détecte les golden cross / death cross et génère les signaux
- `risk.py` — calcule combien investir et où placer le stop-loss / take-profit
- `executor.py` — envoie (ou simule) les ordres sur Binance
- `main.py` — orchestre tout dans une boucle infinie avec gestion d'état

**Ce que le bot va afficher dans ton terminal :**
```
14:32:01 | INFO     | main         | BOT DE TRADING DÉMARRÉ [DRY RUN]
14:32:02 | INFO     | data         | Soldes — USDT : 10000.00 | BTC : 0.000000
14:32:03 | INFO     | strategy     | SIGNAL BUY — Golden Cross détecté | RSI=52.3
14:32:03 | INFO     | risk         | Position calculée — 333 USDT | SL : 77 000 | TP : 84 800
14:32:03 | INFO     | main         | [DRY RUN] Position OUVERTE — Entrée : 79 381.00