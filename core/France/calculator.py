# core/calculator.py

import json
import logging
import os
from datetime import datetime
from functools import lru_cache
from typing import Dict, List, Tuple

from .pricing import (
    get_fiat_to_eur_rate,
    get_historical_price,
    STABLECOINS_EUR,
    STABLECOINS_USD,
)

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

_TAX_CONFIG_PATH = os.path.join(os.path.dirname(__file__), "tax_config.json")

# Monnaies fiduciaires reconnues au sens fiscal français.
# Les stablecoins (USDC, USDT, DAI…) sont intentionnellement EXCLUS :
# un échange crypto → stablecoin est traité comme crypto→crypto (sursis d'imposition).
FIAT_CURRENCIES: frozenset = frozenset({
    "EUR", "USD", "GBP", "CHF", "JPY", "CAD", "AUD", "NZD",
    "NOK", "SEK", "DKK", "HKD", "SGD", "KRW", "BRL", "MXN",
    "PLN", "CZK", "HUF", "RON", "BGN", "TRY", "ZAR", "INR",
})

# Toutes les stablecoins (USD + EUR), pour initialiser leurs prix de référence
ALL_STABLECOINS = STABLECOINS_USD | STABLECOINS_EUR

# Seuil en dessous duquel une quantité est considérée nulle (poussière)
_DUST_THRESHOLD = 1e-8

# Prix de référence par défaut pour les stablecoins USD (EUR/USD moyen)
_USDC_DEFAULT_PRICE_EUR = 0.93


# ---------------------------------------------------------------------------
# Chargement de la configuration fiscale
# ---------------------------------------------------------------------------

@lru_cache(maxsize=1)
def load_tax_config() -> dict:
    try:
        with open(_TAX_CONFIG_PATH, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception as exc:
        logger.warning("Impossible de charger tax_config.json : %s", exc)
        return {}


def get_pfu_rate() -> float:
    config = load_tax_config().get("pfu", {})
    if "total_rate" in config:
        return float(config["total_rate"])
    logger.warning("PFU total_rate absent dans tax_config.json")
    return 0.0


def get_pfu_ps_rate() -> float:
    config = load_tax_config().get("pfu", {})
    if "ps_rate" in config:
        return float(config["ps_rate"])
    logger.warning("PFU ps_rate absent dans tax_config.json")
    return 0.0


def get_pfu_ir_rate() -> float:
    config = load_tax_config().get("pfu", {})
    if "ir_rate" in config:
        return float(config["ir_rate"])
    total = config.get("total_rate")
    ps = config.get("ps_rate")
    if total is not None and ps is not None:
        return float(total) - float(ps)
    logger.warning("PFU ir_rate absent dans tax_config.json")
    return 0.0


def get_ps_rate() -> float:
    config = load_tax_config().get("bareme_progressif", {})
    if "ps_rate" in config:
        return float(config["ps_rate"])
    logger.warning("PS rate du barème absent dans tax_config.json")
    return 0.0


def get_exoneration_threshold() -> float:
    return float(load_tax_config().get("exoneration_seuil", 305.0))


def calculate_ir(taxable_income: float, parts: float = 1.0) -> float:
    """
    Calcule l'impôt sur le revenu selon le barème progressif (quotient familial).
    """
    config = load_tax_config()
    tranches = config.get("bareme_progressif", {}).get("tranches", [])
    if not tranches:
        return 0.0

    qf = taxable_income / max(parts, 0.5)
    ir_par_part = 0.0

    for tranche in tranches:
        t_min = float(tranche.get("min", 0))
        t_max = tranche.get("max")
        rate = float(tranche.get("rate", 0)) / 100.0

        if qf <= t_min:
            break

        plafond = float(t_max) if t_max is not None else float("inf")
        montant = min(qf, plafond) - t_min
        ir_par_part += max(0.0, montant) * rate

    return ir_par_part * parts


# ---------------------------------------------------------------------------
# Helpers internes
# ---------------------------------------------------------------------------

def _parse_date(tx: dict) -> datetime:
    raw = tx.get("date")
    if not raw:
        return datetime.min
    s = str(raw).strip()

    # Essai ISO 8601 / avec " UTC"
    for variant in (s, s.replace(" UTC", "+00:00"), s.replace("Z", "+00:00")):
        try:
            return datetime.fromisoformat(variant)
        except ValueError:
            pass

    # Essai date seule
    try:
        return datetime.strptime(s[:10], "%Y-%m-%d")
    except ValueError:
        pass

    logger.debug("Format de date non reconnu : %s", s)
    return datetime.min


def _safe_float(value, default: float = 0.0, minimum: float = 0.0) -> float:
    try:
        return max(minimum, float(value or default))
    except (TypeError, ValueError):
        return default


def _get_cached_price(
    asset: str,
    date_str: str,
    price_cache: Dict[Tuple[str, str], float],
    last_known_prices: Dict[str, float],
) -> float:
    """
    Retourne le prix depuis le cache (CSV ou API).
    Stratégie de résolution :
      1. Cache exact (asset, date_str)
      2. Cache journalier (asset, date_jour)
      3. Dernier prix connu dans le CSV
      4. Appel API (mis en cache ensuite)
    """
    if not date_str:
        return 0.0

    date_day = date_str[:10]
    exact_key = (asset, date_str)
    day_key = (asset, date_day)

    # 1 & 2 : cache chaud
    if exact_key in price_cache:
        return price_cache[exact_key]
    if day_key in price_cache:
        return price_cache[day_key]

    # 3 : dernier prix connu sans appel API (évite un appel inutile pour les stablecoins)
    if asset in last_known_prices and last_known_prices[asset] > 0:
        p = last_known_prices[asset]
        price_cache[exact_key] = p
        price_cache[day_key] = p
        return p

    # 4 : appel API
    try:
        price = get_historical_price(asset, date_str) or 0.0
        price = max(0.0, float(price))
    except Exception as exc:
        logger.debug("Prix non trouvé pour %s au %s : %s", asset, date_str, exc)
        price = 0.0

    price_cache[exact_key] = price
    price_cache.setdefault(day_key, price)
    if price > 0:
        last_known_prices[asset] = price

    return price


def _init_stablecoin_prices(
    transactions: list,
    price_cache: Dict,
    last_known_prices: Dict,
) -> None:
    """
    Pré-remplit le cache de prix pour les stablecoins connus.
    Utilise le premier prix trouvé dans le CSV, sinon le prix par défaut.
    Cela évite une VGP nulle quand USDC est dans le portefeuille.
    """
    for tx in transactions:
        crypto = str(tx.get("crypto_token") or "").strip().upper()
        if crypto not in ALL_STABLECOINS:
            continue

        date_str = str(tx.get("date", ""))
        day = date_str[:10]
        price = _safe_float(tx.get("price"))

        if price > 0:
            # Prix CSV fiable → on l'utilise directement
            key_exact = (crypto, date_str)
            key_day = (crypto, day)
            price_cache.setdefault(key_exact, price)
            price_cache.setdefault(key_day, price)
            last_known_prices.setdefault(crypto, price)

    # Pour les stablecoins USD sans aucun prix dans le CSV,
    # on initialise avec le prix par défaut pour ne pas biaiser la VGP
    for stable in STABLECOINS_USD:
        if stable not in last_known_prices:
            last_known_prices[stable] = _USDC_DEFAULT_PRICE_EUR

    for stable in STABLECOINS_EUR:
        if stable not in last_known_prices:
            last_known_prices[stable] = 1.0


# ---------------------------------------------------------------------------
# Moteur fiscal principal
# ---------------------------------------------------------------------------

def calculate_french_taxes(transactions: List[Dict]) -> Dict:
    """
    Calcule les plus-values imposables crypto selon l'art. 150 VH bis du CGI.

    Formule BOFIP §130 :
      PAF = PTA × (Prix_cession_BRUT / VGP)
      PV  = Prix_cession_BRUT − PAF − Frais_de_cession

    Retourne un dict contenant :
      - total_plus_value_imposable   : bilan net (PV − MV)
      - total_prix_cession_imposable : somme des prix bruts de cession
      - taxable_events               : détail de chaque cession imposable
      - remaining_acquisition_cost   : PTA résiduel
      - remaining_portfolio          : portefeuille final par actif
      - note_fiscale                 : rappel du régime
    """

    # ------------------------------------------------------------------
    # 1. Tri chronologique
    # ------------------------------------------------------------------
    transactions = sorted(transactions, key=_parse_date)

    # ------------------------------------------------------------------
    # 2. Pré-remplissage du cache de prix depuis le CSV
    # ------------------------------------------------------------------
    price_cache: Dict[Tuple[str, str], float] = {}
    last_known_prices: Dict[str, float] = {}

    for tx in transactions:
        crypto = str(tx.get("crypto_token") or tx.get("asset") or "").strip().upper()
        date_str = str(tx.get("date", ""))
        day = date_str[:10]
        price = _safe_float(tx.get("price"))
        currency = str(tx.get("currency") or tx.get("quote_currency") or "EUR").upper().strip()

        if price > 0 and crypto:
            fx_rate = get_fiat_to_eur_rate(currency, date_str) if date_str else 1.0
            price_eur = price * fx_rate
            price_cache[(crypto, date_str)] = price_eur
            price_cache[(crypto, day)] = price_eur
            last_known_prices[crypto] = price_eur

    # Initialisation spéciale pour les stablecoins
    _init_stablecoin_prices(transactions, price_cache, last_known_prices)

    # ------------------------------------------------------------------
    # 3. État initial
    # ------------------------------------------------------------------
    portfolio: Dict[str, float] = {}
    # Prix d'acquisition unitaire moyen par actif (informatif, pour affichage)
    unit_acq_tracker: Dict[str, dict] = {}  # {crypto: {qty, total_cost}}

    total_acquisition_cost: float = 0.0   # PTA global (art. 150 VH bis)
    total_prix_cession_brut: float = 0.0
    global_plus_value: float = 0.0
    taxable_events: List[Dict] = []
    vgp_cache: Dict[str, float] = {}       # cache VGP par jour

    # ------------------------------------------------------------------
    # 4. Boucle principale
    # ------------------------------------------------------------------
    for idx, tx in enumerate(transactions):
        crypto = str(tx.get("crypto_token") or tx.get("asset") or "").strip().upper()
        if not crypto:
            continue

        try:
            qty        = _safe_float(tx.get("quantity") or tx.get("amount"))
            unit_price = _safe_float(tx.get("price"))
            fees       = _safe_float(tx.get("fees"))
            date_str   = str(tx.get("date", "")).strip()
            currency   = str(tx.get('currency') or tx.get('quote_currency') or 'EUR').upper().strip()
            op         = str(tx.get('operation_type') or tx.get('type') or '').lower().strip()
        except Exception as exc:
            logger.debug("Transaction #%d ignorée : %s", idx + 1, exc)
            tx["remaining_quantity"] = portfolio.get(crypto, 0.0)
            continue

        fx_rate = get_fiat_to_eur_rate(currency, date_str)
        fees_eur = fees * fx_rate if fees > 0 else 0.0

        if unit_price == 0 and date_str:
            unit_price = _get_cached_price(crypto, date_str, price_cache, last_known_prices)
            unit_price_eur = unit_price
        else:
            unit_price_eur = unit_price * fx_rate if unit_price > 0 else 0.0

        if qty <= _DUST_THRESHOLD:
            tx["remaining_quantity"] = portfolio.get(crypto, 0.0)
            continue

        # ==============================================================
        # ACHAT (Fiat → Crypto)
        # ==============================================================
        if op in ("achat", "buy", "acquisition", "deposit_fiat"):

            # Récupération du prix si manquant dans le CSV
            if unit_price == 0 and date_str:
                unit_price = _get_cached_price(crypto, date_str, price_cache, last_known_prices)
                unit_price_eur = unit_price
                tx['price'] = unit_price

            cost = (qty * unit_price_eur) + fees_eur
            total_acquisition_cost += cost
            portfolio[crypto] = portfolio.get(crypto, 0.0) + qty

            tracker = unit_acq_tracker.setdefault(crypto, {"qty": 0.0, "cost": 0.0})
            tracker["qty"] += qty
            tracker["cost"] += cost

            tx["remaining_quantity"] = portfolio[crypto]

        # ==============================================================
        # VENTE (Crypto → Fiat RÉEL uniquement)
        # Art. 150 VH bis : seule une cession contre monnaie d'État est taxable.
        # ==============================================================
        elif op in ("vente", "sell", "cession", "fiat_withdrawal"):

            currency = str(
                tx.get("currency") or tx.get("quote_currency") or "EUR"
            ).upper().strip()

            # -- Contrepartie non-fiat → sursis d'imposition -----------
            if currency not in FIAT_CURRENCIES:
                available = portfolio.get(crypto, 0.0)
                portfolio[crypto] = max(0.0, available - min(qty, available))
                if portfolio.get(crypto, 0.0) <= _DUST_THRESHOLD:
                    portfolio.pop(crypto, None)
                tx["remaining_quantity"] = portfolio.get(crypto, 0.0)
                tx["_skipped_reason"] = (
                    f"Cession vers {currency} (non-fiat) → sursis d'imposition"
                )
                continue

            # -- Récupération du prix de cession si manquant -----------
            if unit_price == 0 and date_str:
                unit_price = _get_cached_price(crypto, date_str, price_cache, last_known_prices)
                unit_price_eur = unit_price
                tx['price'] = unit_price

            # A. Prix de cession BRUT et NET (en EUR)
            prix_cession_brut = qty * unit_price_eur
            prix_cession_net  = prix_cession_brut - fees_eur
            total_prix_cession_brut += prix_cession_brut

            # B. Valeur Globale du Portefeuille (VGP) au jour J
            date_day = date_str[:10]
            if date_day in vgp_cache:
                valeur_globale = vgp_cache[date_day]
            else:
                valeur_globale = 0.0
                for asset, asset_qty in portfolio.items():
                    if asset_qty <= _DUST_THRESHOLD:
                        continue

                    # Cherche le prix dans le cache (exact → journalier → dernier connu → API)
                    p = (
                        price_cache.get((asset, date_str))
                        or price_cache.get((asset, date_day))
                        or last_known_prices.get(asset, 0.0)
                    )

                    # Si toujours 0, on tente l'API (sauf pour les micro-poussières)
                    if p == 0.0 and asset_qty > _DUST_THRESHOLD * 100:
                        p = _get_cached_price(asset, date_str, price_cache, last_known_prices)

                    valeur_globale += asset_qty * p

                # Garde-fou : VGP ne peut pas être nulle
                if valeur_globale <= 0:
                    valeur_globale = prix_cession_brut if prix_cession_brut > 0 else 1e-6
                    logger.warning(
                        "VGP nulle au %s – fallback = prix de cession (%.2f€)",
                        date_day, valeur_globale,
                    )

                vgp_cache[date_day] = valeur_globale

            # C. Prix d'Acquisition Fractionné (PAF) – formule BOFIP §130
            manual_acq = _safe_float(tx.get("acq_price"))
            if manual_acq > 0:
                prix_acq_fractionne = qty * manual_acq
            else:
                fraction = min(1.0, max(0.0, prix_cession_brut / valeur_globale))
                prix_acq_fractionne = total_acquisition_cost * fraction

            # D. Plus-Value (ou Moins-Value) nette
            pv = prix_cession_brut - prix_acq_fractionne - fees_eur

            # E. Mise à jour du PTA
            pta_avant_cession = total_acquisition_cost
            total_acquisition_cost = max(0.0, total_acquisition_cost - prix_acq_fractionne)

            # F. Accumulation nette
            global_plus_value += pv

            # G. Mise à jour du portefeuille
            available = portfolio.get(crypto, 0.0)
            qty_consumed = min(qty, available)
            portfolio[crypto] = available - qty_consumed
            if portfolio.get(crypto, 0.0) <= _DUST_THRESHOLD:
                portfolio.pop(crypto, None)
            tx["remaining_quantity"] = portfolio.get(crypto, 0.0)

            # H. Prix d'acquisition unitaire réel (pour affichage)
            #    = PAF / quantité cédée (quote-part du PTA consommée par unité)
            unit_acq_display = round(prix_acq_fractionne / qty, 6) if qty > 0 else 0.0

            # Prix de vente unitaire réel
            price_unit_vendu = round(unit_price, 6)

            # I. Enregistrement de l'événement imposable
            taxable_events.append({
                "id": tx.get("index") or idx + 1,
                "date": date_str,
                "type": "Cession imposable",
                "crypto": crypto,
                "currency": currency,
                "conversion_rate": round(fx_rate, 6),
                "quantity": qty,
                # Affiché dans le tableau principal
                "unit_acq": unit_acq_display,
                "price_unit_vendu": round(unit_price_eur, 6),
                # Ligne 211 (formulaire 2086) : Prix de cession brut
                "prix_cession_brut": round(prix_cession_brut, 2),
                # Ligne 212 : Frais de cession (en EUR)
                "frais_cession": round(fees_eur, 2),
                # Ligne 213 : Prix de cession net
                "prix_cession_net": round(prix_cession_net, 2),
                # Ligne 215 : Valeur globale du portefeuille
                "valeur_globale": round(valeur_globale, 2),
                # Ligne 216 : PTA avant cession
                "montant_global_acquisition": round(pta_avant_cession, 2),
                # Ligne 217 : PAF
                "prix_acq_fractionne": round(prix_acq_fractionne, 2),
                # Ligne 218 : PV / MV
                "plus_value": round(pv, 2),
            })

        # ==============================================================
        # ÉCHANGE (Crypto → Crypto) – Sursis d'imposition
        # ==============================================================
        elif op in ("echange", "swap", "exchange", "transfert crypto", "crypto_to_crypto"):

            available = portfolio.get(crypto, 0.0)
            if available < qty - _DUST_THRESHOLD:
                logger.warning(
                    "Échange [%s] : insuffisant (dispo=%.8f, demandé=%.8f) – on échange ce qui est disponible",
                    crypto, available, qty,
                )
                qty = available

            if qty <= _DUST_THRESHOLD:
                tx["remaining_quantity"] = portfolio.get(crypto, 0.0)
                continue

            portfolio[crypto] = portfolio.get(crypto, 0.0) - qty
            if portfolio[crypto] <= _DUST_THRESHOLD:
                portfolio.pop(crypto, None)

            received_token = str(tx.get("received_token", "")).strip().upper()
            received_qty   = _safe_float(tx.get("received_quantity"))
            if received_token and received_qty > _DUST_THRESHOLD:
                portfolio[received_token] = portfolio.get(received_token, 0.0) + received_qty

            # PTA inchangé (sursis d'imposition)
            tx["remaining_quantity"] = portfolio.get(crypto, 0.0)

        # ==============================================================
        # DÉPÔT / RÉCEPTION (entrée dans le patrimoine)
        # ==============================================================
        elif op in ("depot", "deposit", "receive"):

            if unit_price == 0 and date_str:
                unit_price = _get_cached_price(crypto, date_str, price_cache, last_known_prices)
                unit_price_eur = unit_price
                tx["price"] = unit_price

            if unit_price_eur > 0:
                cost = (qty * unit_price_eur) + fees_eur
                total_acquisition_cost += cost

                tracker = unit_acq_tracker.setdefault(crypto, {"qty": 0.0, "cost": 0.0})
                tracker["qty"] += qty
                tracker["cost"] += cost

            portfolio[crypto] = portfolio.get(crypto, 0.0) + qty
            tx["remaining_quantity"] = portfolio[crypto]

        # ==============================================================
        # GAINS PASSIFS (Staking, Rewards, Intérêts)
        # ==============================================================
        elif op in ("staking", "reward", "earn", "income"):

            if unit_price == 0 and date_str:
                unit_price = _get_cached_price(crypto, date_str, price_cache, last_known_prices)
                unit_price_eur = unit_price
                tx["price"] = unit_price

            if unit_price_eur > 0:
                cost = (qty * unit_price_eur) + fees_eur
                total_acquisition_cost += cost

                tracker = unit_acq_tracker.setdefault(crypto, {"qty": 0.0, "cost": 0.0})
                tracker["qty"] += qty
                tracker["cost"] += cost

            portfolio[crypto] = portfolio.get(crypto, 0.0) + qty
            tx["remaining_quantity"] = portfolio[crypto]
            tx["_is_staking_reward"] = True

        # ==============================================================
        # RETRAIT / ENVOI (wallet personnel – PTA inchangé)
        # ==============================================================
        elif op in ("retrait", "withdrawal", "send", "envoi"):

            available = portfolio.get(crypto, 0.0)
            portfolio[crypto] = max(0.0, available - min(qty, available))
            if portfolio[crypto] <= _DUST_THRESHOLD:
                portfolio.pop(crypto, None)
            tx["remaining_quantity"] = portfolio.get(crypto, 0.0)

        # ==============================================================
        # TRANSFERT INTERNE (ex: Staking/Unstaking Coinbase Retail)
        # ==============================================================
        elif op in ("transfert_interne",):
            tx["remaining_quantity"] = portfolio.get(crypto, 0.0)
            tx["_skipped_reason"] = (
                "Transfert interne plateforme – aucun impact fiscal (PTA inchangé)."
            )

        # ==============================================================
        # OPÉRATIONS INCONNUES
        # ==============================================================
        else:
            logger.debug("Opération non reconnue : %r (tx #%d)", op, idx + 1)
            tx["remaining_quantity"] = portfolio.get(crypto, 0.0)

    # ------------------------------------------------------------------
    # 5. Nettoyage du portefeuille (micro-poussières)
    # ------------------------------------------------------------------
    portfolio = {k: v for k, v in portfolio.items() if v > _DUST_THRESHOLD}

    # ------------------------------------------------------------------
    # 6. Résultat
    # ------------------------------------------------------------------
    return {
        "total_plus_value_imposable":   round(global_plus_value, 2),
        "total_prix_cession_imposable": round(total_prix_cession_brut, 2),
        "taxable_events":               taxable_events,
        "remaining_acquisition_cost":   round(total_acquisition_cost, 2),
        "remaining_portfolio":          {k: round(v, 8) for k, v in portfolio.items()},
        "note_fiscale": (
            "Régime art. 150 VH bis CGI – "
            "Formule BOFIP §130 (fraction au prix brut). "
            "Échanges crypto↔crypto non imposables (sursis d'imposition). "
            "MV de l'année compensées sur les PV de l'année."
        ),
    }