# =============================================================================
# test_indicators.py — Tests unitaires du module indicators
# =============================================================================

import pytest
import numpy as np
import pandas as pd
from indicators import add_indicators, get_latest


# ── Helpers ───────────────────────────────────────────────────────────────────

def _make_ohlcv(n: int = 100, price: float = 50_000.0, trend: float = 0.0, seed: int = 42) -> pd.DataFrame:
    """
    Crée un DataFrame OHLCV synthétique avec tendance optionnelle.
    trend > 0  → prix monte de `trend` USDT par bougie
    trend < 0  → prix descend
    seed       → reproductibilité du bruit aléatoire
    """
    rng = np.random.default_rng(seed)
    idx = pd.date_range("2024-01-01", periods=n, freq="4h")
    closes = [price + i * trend + rng.normal(0, price * 0.001) for i in range(n)]
    df = pd.DataFrame({
        "open"  : closes,
        "high"  : [c * 1.005 for c in closes],
        "low"   : [c * 0.995 for c in closes],
        "close" : closes,
        "volume": 100.0,
    }, index=idx)
    return df


# ── add_indicators — colonnes créées ─────────────────────────────────────────

def test_add_indicators_creates_rsi_column():
    df = add_indicators(_make_ohlcv())
    assert "rsi" in df.columns


def test_add_indicators_creates_sma_fast_column():
    df = add_indicators(_make_ohlcv())
    assert "sma_fast" in df.columns


def test_add_indicators_creates_sma_slow_column():
    df = add_indicators(_make_ohlcv())
    assert "sma_slow" in df.columns


def test_add_indicators_does_not_corrupt_ohlcv():
    """Les colonnes OHLCV originales doivent rester intactes."""
    df = add_indicators(_make_ohlcv())
    for col in ("open", "high", "low", "close", "volume"):
        assert col in df.columns


# ── add_indicators — valeurs ──────────────────────────────────────────────────

def test_rsi_bounded_between_0_and_100():
    df = add_indicators(_make_ohlcv(200))
    assert (df["rsi"] >= 0).all(), "RSI ne doit pas être négatif"
    assert (df["rsi"] <= 100).all(), "RSI ne doit pas dépasser 100"


def test_no_nan_after_add_indicators():
    """dropna() doit éliminer toutes les valeurs manquantes des indicateurs."""
    df = add_indicators(_make_ohlcv(100))
    assert df.isna().sum().sum() == 0


def test_add_indicators_drops_initial_rows():
    """Les premières bougies (sans assez d'historique) doivent être supprimées."""
    raw = _make_ohlcv(100)
    result = add_indicators(raw)
    assert len(result) < len(raw), "Les lignes NaN initiales auraient dû être retirées"


def test_sma_fast_above_sma_slow_in_strong_uptrend():
    """
    Dans une forte tendance haussière, SMA_FAST (9) doit finir au-dessus de
    SMA_SLOW (21) car elle réagit plus vite aux prix récents.
    """
    df = add_indicators(_make_ohlcv(n=200, price=50_000, trend=500))
    assert df["sma_fast"].iloc[-1] > df["sma_slow"].iloc[-1]


def test_sma_fast_below_sma_slow_in_strong_downtrend():
    """
    Dans une forte tendance baissière, SMA_FAST (9) doit finir en dessous de
    SMA_SLOW (21).
    """
    df = add_indicators(_make_ohlcv(n=200, price=80_000, trend=-300))
    assert df["sma_fast"].iloc[-1] < df["sma_slow"].iloc[-1]


def test_sma_values_are_smooth():
    """SMA_SLOW doit varier moins que SMA_FAST (lissage plus fort)."""
    df = add_indicators(_make_ohlcv(n=200, price=50_000, trend=0))
    volatility_fast = df["sma_fast"].std()
    volatility_slow = df["sma_slow"].std()
    assert volatility_slow <= volatility_fast, "SMA_SLOW devrait être plus lisse que SMA_FAST"


# ── add_indicators — immutabilité ─────────────────────────────────────────────

def test_add_indicators_does_not_modify_original_dataframe():
    """add_indicators doit travailler sur une copie et ne pas modifier l'original."""
    raw = _make_ohlcv(100)
    original_cols = set(raw.columns)
    original_len  = len(raw)
    add_indicators(raw)
    assert set(raw.columns) == original_cols, "Les colonnes originales ont été modifiées"
    assert len(raw) == original_len, "Des lignes ont été supprimées dans le DataFrame original"


# ── get_latest — structure ────────────────────────────────────────────────────

def test_get_latest_returns_all_required_keys():
    df = add_indicators(_make_ohlcv(100))
    values = get_latest(df)
    required = ["close", "rsi", "sma_fast", "sma_slow", "prev_sma_fast", "prev_sma_slow"]
    for key in required:
        assert key in values, f"Clé manquante : {key}"


def test_get_latest_values_are_floats():
    df = add_indicators(_make_ohlcv(100))
    values = get_latest(df)
    for key, val in values.items():
        assert isinstance(val, float), f"'{key}' devrait être un float, obtenu {type(val)}"


def test_get_latest_close_matches_last_row():
    df = add_indicators(_make_ohlcv(100))
    values = get_latest(df)
    assert values["close"] == pytest.approx(float(df["close"].iloc[-1]))


def test_get_latest_prev_sma_differs_from_current():
    """
    Les valeurs prev_sma_* doivent correspondre à l'avant-dernière bougie,
    donc être différentes des valeurs courantes (prix non stationnaire).
    """
    df = add_indicators(_make_ohlcv(n=200, price=50_000, trend=100))
    values = get_latest(df)
    assert values["sma_fast"]      != values["prev_sma_fast"]
    assert values["sma_slow"]      != values["prev_sma_slow"]


def test_get_latest_rsi_bounded():
    df = add_indicators(_make_ohlcv(100))
    values = get_latest(df)
    assert 0 <= values["rsi"] <= 100


# ── Minimum de données ────────────────────────────────────────────────────────

def test_add_indicators_with_minimum_viable_data():
    """50 bougies suffisent pour calculer SMA21 + RSI14 (minimum viable)."""
    df = add_indicators(_make_ohlcv(50))
    assert len(df) > 0, "Le résultat ne doit pas être vide avec 50 bougies"
    assert "rsi" in df.columns
