# core/pricing.py

import logging
from datetime import datetime
from functools import lru_cache

import requests

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Stablecoins connus
# ---------------------------------------------------------------------------

# USD-pegged : prix en EUR ≈ taux EUR/USD du jour
STABLECOINS_USD = frozenset({
    "USDC", "USDT", "DAI", "BUSD", "TUSD", "USDD",
    "FRAX", "LUSD", "USDP", "GUSD", "CUSD", "SUSD",
    "MIM", "DOLA", "USDX", "FLEXUSD",
})

# EUR-pegged : prix ≈ 1 EUR
STABLECOINS_EUR = frozenset({
    "EURT", "EURS", "AGEUR", "CEUR", "EURC",
})


# ---------------------------------------------------------------------------
# Parsing de timestamp
# ---------------------------------------------------------------------------

def _parse_timestamp(timestamp_str: str) -> int:
    """Convertit une chaîne de date en timestamp UNIX (int)."""
    if not timestamp_str:
        raise ValueError("timestamp manquant")

    s = str(timestamp_str).strip()

    # Essai ISO 8601 avec timezone
    try:
        return int(datetime.fromisoformat(s.replace("Z", "+00:00")).timestamp())
    except ValueError:
        pass

    # Essai avec " UTC" en suffixe (format Coinbase)
    try:
        s_clean = s.replace(" UTC", "+00:00")
        return int(datetime.fromisoformat(s_clean).timestamp())
    except ValueError:
        pass

    # Essai date seule YYYY-MM-DD
    try:
        return int(datetime.strptime(s[:10], "%Y-%m-%d").timestamp())
    except ValueError as exc:
        raise ValueError(f"Impossible de parser la date : {timestamp_str!r}") from exc


# ---------------------------------------------------------------------------
# Appel CryptoCompare
# ---------------------------------------------------------------------------

def _fetch_cryptocompare(
    symbol: str,
    ts: int,
    currency: str,
    endpoint: str,
) -> float | None:
    """
    Interroge un endpoint CryptoCompare (histohour / histoday / histominute).
    Retourne le prix de clôture ou None si la réponse est invalide.
    """
    url = f"https://min-api.cryptocompare.com/data/v2/{endpoint}"
    params = {
        "fsym": symbol,
        "tsym": currency,
        "limit": 1,
        "toTs": ts,
    }
    try:
        r = requests.get(url, params=params, timeout=8)
        r.raise_for_status()
        data = r.json()

        if data.get("Response") == "Success":
            candles = data.get("Data", {}).get("Data", [])
            if candles:
                price = float(candles[-1]["close"])
                if price > 0:
                    return price

        logger.debug(
            "CryptoCompare %s [%s/%s] – réponse invalide : %s",
            endpoint, symbol, currency, data.get("Message", "?"),
        )
    except Exception as exc:
        logger.debug("CryptoCompare %s erreur pour %s : %s", endpoint, symbol, exc)

    return None


# ---------------------------------------------------------------------------
# Taux EUR/USD historique (utilisé pour valoriser les USD-stablecoins)
# ---------------------------------------------------------------------------

@lru_cache(maxsize=256)
def _fetch_usd_eur_rate(timestamp_str: str) -> float:
    """
    Retourne le taux EUR/USD à la date donnée (ex: 0.93).
    Utilise histoday en priorité (plus stable que histohour pour FX).
    Sanity-check : résultat attendu dans [0.65, 1.35].
    Fallback : 0.93 si aucune donnée exploitable.
    """
    try:
        ts = _parse_timestamp(timestamp_str)
    except ValueError:
        return 0.93

    for endpoint in ("histoday", "histohour"):
        price = _fetch_cryptocompare("USDC", ts, "EUR", endpoint)
        if price and 0.65 < price < 1.35:
            logger.debug("Taux EUR/USD @ %s = %.4f (via %s)", timestamp_str, price, endpoint)
            return price

    logger.warning(
        "Impossible de récupérer le taux EUR/USD @ %s – fallback 0.93", timestamp_str
    )
    return 0.93


@lru_cache(maxsize=256)
def get_fiat_to_eur_rate(currency: str, timestamp_str: str) -> float:
    """Retourne le taux de conversion d'une devise vers l'euro."""
    if not currency:
        return 1.0

    cur = str(currency).strip().upper()
    if cur == "EUR":
        return 1.0
    if cur in STABLECOINS_EUR:
        return 1.0
    if cur in STABLECOINS_USD or cur == "USD":
        return _fetch_usd_eur_rate(timestamp_str)

    try:
        ts = _parse_timestamp(timestamp_str)
    except ValueError:
        logger.warning(
            "Taux de conversion introuvable pour %s @ %s – timestamp invalide",
            currency,
            timestamp_str,
        )
        return 1.0

    price = _fetch_cryptocompare(cur, ts, "EUR", "histoday")
    if price is None:
        price = _fetch_cryptocompare(cur, ts, "EUR", "histohour")

    if price is None or price <= 0:
        logger.warning(
            "Taux de conversion introuvable pour %s @ %s – fallback 1.0",
            currency,
            timestamp_str,
        )
        return 1.0

    return price


# ---------------------------------------------------------------------------
# Point d'entrée principal
# ---------------------------------------------------------------------------

@lru_cache(maxsize=512)
def get_historical_price(
    symbol: str,
    timestamp_str: str,
    currency: str = "EUR",
) -> float:
    """
    Retourne le prix historique d'un actif crypto en `currency`.

    Ordre de résolution :
      1. EUR-stablecoins  → 1.0 directement
      2. USD-stablecoins  → taux EUR/USD historique
      3. API CryptoCompare : histohour → histoday (fallback)
      4. 0.0 si aucune donnée trouvée
    """
    sym = symbol.strip().upper()

    # -- Stablecoins EUR-pegged ----------------------------------------
    if sym in STABLECOINS_EUR:
        logger.debug("Stablecoin EUR %s → 1.0 EUR", sym)
        return 1.0

    # -- Stablecoins USD-pegged ----------------------------------------
    if sym in STABLECOINS_USD:
        rate = _fetch_usd_eur_rate(timestamp_str)
        logger.debug("Stablecoin USD %s @ %s → %.4f EUR", sym, timestamp_str, rate)
        return rate

    # -- Actifs classiques via CryptoCompare ---------------------------
    try:
        ts = _parse_timestamp(timestamp_str)
    except ValueError as exc:
        logger.warning("Timestamp invalide pour %s : %s", sym, exc)
        return 0.0

    for endpoint in ("histohour", "histoday"):
        price = _fetch_cryptocompare(sym, ts, currency, endpoint)
        if price is not None:
            logger.debug(
                "Prix %s @ %s = %.6f %s (via %s)",
                sym, timestamp_str, price, currency, endpoint,
            )
            return price

    logger.warning("Prix introuvable pour %s @ %s – retour 0.0", sym, timestamp_str)
    return 0.0