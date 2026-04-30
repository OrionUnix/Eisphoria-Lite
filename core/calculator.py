import json
import os
import logging
from collections import defaultdict
from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple

from core.pricing import get_historical_price

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

_TAX_CONFIG_PATH = os.path.join(os.path.dirname(__file__), 'tax_config.json')

# Monnaies fiduciaires reconnues au sens fiscal français.
# USDT, USDC, DAI, etc. sont EXCLUS : un échange crypto → stablecoin
# est traité comme un échange crypto→crypto (sursis d'imposition).
FIAT_CURRENCIES: frozenset = frozenset({
    'EUR', 'USD', 'GBP', 'CHF', 'JPY', 'CAD', 'AUD', 'NZD',
    'NOK', 'SEK', 'DKK', 'HKD', 'SGD', 'KRW', 'BRL', 'MXN',
    'PLN', 'CZK', 'HUF', 'RON', 'BGN', 'TRY', 'ZAR', 'INR',
})

# Seuil en dessous duquel une quantité est considérée nulle (poussière)
_DUST_THRESHOLD = 1e-8


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def load_tax_config() -> dict:
    """Charge la configuration des taux fiscaux depuis tax_config.json."""
    try:
        with open(_TAX_CONFIG_PATH, 'r', encoding='utf-8') as f:
            return json.load(f)
    except Exception as exc:
        logger.warning("Impossible de charger tax_config.json : %s", exc)
        return {}


def get_pfu_rate() -> float:
    """Taux PFU (Prélèvement Forfaitaire Unique)."""
    config = load_tax_config()
    return config.get('pfu', {}).get('total_rate', 30.0)


def get_ps_rate() -> float:
    """Taux des prélèvements sociaux."""
    config = load_tax_config()
    return config.get('bareme_progressif', {}).get('ps_rate', 17.2)


def get_exoneration_threshold() -> float:
    """Seuil d'exonération annuelle (ex: 305€)."""
    config = load_tax_config()
    return float(config.get('exoneration_seuil', 305.0))


def calculate_ir(taxable_income: float, parts: float = 1.0) -> float:
    """
    Calcule l'impôt sur le revenu (IR) selon le barème progressif.
    Basé sur le quotient familial (taxable_income / parts).
    """
    config = load_tax_config()
    tranches = config.get('bareme_progressif', {}).get('tranches', [])
    
    if not tranches:
        return 0.0

    # Calcul de l'assiette par part
    qf = taxable_income / parts
    ir_par_part = 0.0
    
    for tranche in tranches:
        t_min = float(tranche.get('min', 0))
        t_max = tranche.get('max')
        rate = float(tranche.get('rate', 0)) / 100.0
        
        if qf > t_min:
            # Montant imposable dans cette tranche
            if t_max is not None:
                plafond = float(t_max)
                montant_tranche = min(qf, plafond) - t_min
            else:
                montant_tranche = qf - t_min
            
            ir_par_part += max(0.0, montant_tranche) * rate
        else:
            break
            
    return ir_par_part * parts


def _parse_date(tx: dict) -> datetime:
    """
    Convertit la valeur 'date' d'une transaction en objet datetime.
    Supporte ISO 8601 (avec ou sans 'Z') et le format 'YYYY-MM-DD'.
    Retourne datetime.min si la date est absente ou invalide.
    """
    raw = tx.get('date')
    if not raw:
        return datetime.min
    s = str(raw).strip()
    for fmt in ('%Y-%m-%dT%H:%M:%S%z', '%Y-%m-%dT%H:%M:%SZ', '%Y-%m-%d'):
        try:
            if fmt.endswith('%z') or fmt.endswith('Z'):
                return datetime.fromisoformat(s.replace('Z', '+00:00'))
            return datetime.strptime(s, fmt)
        except ValueError:
            continue
    logger.debug("Format de date non reconnu : %s", s)
    return datetime.min


def _safe_float(value, default: float = 0.0, minimum: float = 0.0) -> float:
    """Convertit une valeur en float positif, avec valeur par défaut."""
    try:
        return max(minimum, float(value or default))
    except (TypeError, ValueError):
        return default


# ---------------------------------------------------------------------------
# Pré-chargement des prix historiques (OPTIMISATION PERFORMANCE)
# ---------------------------------------------------------------------------

def _collect_price_needs(
    transactions: List[Dict[str, Any]],
) -> Dict[Tuple[str, str], float]:
    """
    Parcourt les transactions une première fois pour identifier
    tous les (asset, date) qui auront besoin d'un prix historique.

    Retourne un dict {(asset, date_str): 0.0} à remplir ensuite.
    """
    needs: Dict[Tuple[str, str], float] = {}

    for tx in transactions:
        op = str(tx.get('operation_type', '')).lower().strip()
        crypto = str(tx.get('crypto_token', '')).strip().upper()
        date = str(tx.get('date', '')).strip()

        if not crypto or not date:
            continue

        unit_price = _safe_float(tx.get('price'))

        # Achat sans prix → besoin du prix historique
        if op in ('achat', 'buy', 'acquisition', 'deposit_fiat') and unit_price == 0:
            needs[(crypto, date)] = 0.0

        # Staking sans prix → besoin du prix historique
        if op in ('staking', 'reward', 'earn', 'income') and unit_price == 0:
            needs[(crypto, date)] = 0.0

        # Vente → besoin des prix de TOUS les actifs du portefeuille à cette date.
        # On ne peut pas tous les lister ici sans simuler le portefeuille, donc
        # on marque un besoin générique ; ils seront résolus à la volée mais
        # mis en cache pour éviter les doublons.

    return needs


def _batch_fetch_prices(
    needs: Dict[Tuple[str, str], float],
) -> Dict[Tuple[str, str], float]:
    """
    Récupère en une passe tous les prix historiques identifiés.
    Les erreurs sont silencieuses (prix = 0.0 en fallback).
    """
    cache: Dict[Tuple[str, str], float] = {}
    for (asset, date_str), _ in needs.items():
        try:
            price = get_historical_price(asset, date_str) or 0.0
            cache[(asset, date_str)] = max(0.0, float(price))
        except Exception as exc:
            logger.debug("Impossible de récupérer le prix de %s au %s : %s", asset, date_str, exc)
            cache[(asset, date_str)] = 0.0
    return cache


def _get_cached_price(
    asset: str,
    date_str: str,
    cache: Dict[Tuple[str, str], float],
) -> float:
    """
    Retourne le prix depuis le cache.
    Si absent (cas des actifs du portefeuille au moment d'une vente),
    lance une requête et stocke le résultat dans le cache.
    """
    key = (asset, date_str)
    if key not in cache:
        try:
            price = get_historical_price(asset, date_str) or 0.0
            cache[key] = max(0.0, float(price))
        except Exception as exc:
            logger.debug("Prix non trouvé pour %s au %s : %s", asset, date_str, exc)
            cache[key] = 0.0
    return cache[key]
# Moteur de calcul fiscal principal
# ---------------------------------------------------------------------------
def calculate_french_taxes(transactions: List[Dict]) -> Dict:
    """
    Calcule les plus-values imposables crypto selon l'art. 150 VH bis du CGI.

    Paramètres
    ----------
    transactions : liste de dicts représentant chaque opération crypto.

    Retourne
    --------
    dict avec :
      - total_plus_value_imposable   : bilan net (PV - MV) de l'année
      - total_prix_cession_imposable : somme des prix bruts des cessions taxables
      - taxable_events               : détail de chaque cession imposable
      - remaining_acquisition_cost   : PTA résiduel (stock non encore cédé)
      - remaining_portfolio          : portefeuille final par actif
      - note_fiscale                 : rappel du régime applicable
    """

    # ------------------------------------------------------------------
    # 1. Tri chronologique
    # ------------------------------------------------------------------
    transactions = sorted(transactions, key=_parse_date)

    # 2. Indexation massive des prix du CSV (Vitesse éclair)
    price_cache: Dict[Tuple[str, str], float] = {}
    last_known_prices: Dict[str, float] = {}
    
    for tx in transactions:
        crypto = str(tx.get('crypto_token') or tx.get('asset') or '').strip().upper()
        date_str = str(tx.get('date', ''))
        day = date_str[:10] 
        price = _safe_float(tx.get('price'))
        
        if price > 0:
            price_cache[(crypto, day)] = price
            price_cache[(crypto, date_str)] = price
            last_known_prices[crypto] = price

    # 3. État du portefeuille et compteurs fiscaux
    portfolio: Dict[str, float] = {}
    total_acquisition_cost: float = 0.0
    total_prix_cession_brut: float = 0.0
    global_plus_value: float = 0.0
    taxable_events: List[Dict] = []
    vgp_cache: Dict[str, float] = {}

    # ------------------------------------------------------------------
    # 4. Boucle principale de traitement
    # ------------------------------------------------------------------
    for idx, tx in enumerate(transactions):
        crypto = str(tx.get('crypto_token') or tx.get('asset') or '').strip().upper()

        if not crypto:
            continue

        # --- Lecture et validation avec fallbacks de clés ---
        try:
            qty = _safe_float(tx.get('quantity') or tx.get('amount'))
            unit_price = _safe_float(tx.get('price'))
            fees = _safe_float(tx.get('fees'))
            date_str = str(tx.get('date', '')).strip()
            op = str(tx.get('operation_type') or tx.get('type') or '').lower().strip()
        except Exception:
            tx['remaining_quantity'] = portfolio.get(crypto, 0.0)
            continue

        if qty <= _DUST_THRESHOLD:
            tx['remaining_quantity'] = portfolio.get(crypto, 0.0)
            continue

        # ==============================================================
        # ACHAT (Fiat → Crypto)
        # ==============================================================
        if op in ('achat', 'buy', 'acquisition', 'deposit_fiat'):

            if unit_price == 0 and date_str:
                unit_price = _get_cached_price(crypto, date_str, price_cache)
                tx['price'] = unit_price  # mise à jour pour l'affichage

            cost = (qty * unit_price) + fees
            total_acquisition_cost += cost
            portfolio[crypto] = portfolio.get(crypto, 0.0) + qty
            tx['remaining_quantity'] = portfolio[crypto]

        # ==============================================================
        # VENTE (Crypto → Fiat RÉEL uniquement)
        # Art. 150 VH bis : seule une cession contre monnaie d'État est taxable.
        # Cession vers stablecoin = sursis d'imposition (voir bloc suivant).
        # ==============================================================
        elif op in ('vente', 'sell', 'cession', 'fiat_withdrawal'):

            currency = str(
                tx.get('currency') or tx.get('quote_currency') or 'EUR'
            ).upper().strip()

            # --- Contrepartie non-fiat → sursis d'imposition ---
            if currency not in FIAT_CURRENCIES:
                available = portfolio.get(crypto, 0.0)
                qty_to_sub = min(qty, available)
                portfolio[crypto] = available - qty_to_sub
                if portfolio.get(crypto, 0.0) <= _DUST_THRESHOLD:
                    portfolio.pop(crypto, None)
                tx['remaining_quantity'] = portfolio.get(crypto, 0.0)
                tx['_skipped_reason'] = (
                    f"Cession vers {currency} (non-fiat) → sursis d'imposition"
                )
                continue

            # --- Cession imposable contre fiat réel ---

            # A. Prix de cession BRUT et NET
            #    Le BRUT sert au calcul de la fraction (formule BOFIP §130).
            #    Le NET (brut − frais) est le montant réellement encaissé.
            prix_cession_brut = qty * unit_price
            prix_cession_net = prix_cession_brut - fees
            total_prix_cession_brut += prix_cession_brut

            # B. Valeur Globale du Portefeuille (VGP)
            date_day = date_str[:10]
            if date_day in vgp_cache:
                valeur_globale = vgp_cache[date_day]
            else:
                valeur_globale = 0.0
                for asset, asset_qty in portfolio.items():
                    if asset_qty <= _DUST_THRESHOLD: continue
                    
                    # On cherche dans le cache (rempli par le CSV)
                    p = price_cache.get((asset, date_str)) or price_cache.get((asset, date_day))
                    
                    # Fallback sur le dernier prix connu dans le CSV si pas de match exact
                    if p is None:
                        p = last_known_prices.get(asset, 0.0)
                    
                    valeur_globale += asset_qty * p
                
                if valeur_globale <= 0:
                    valeur_globale = prix_cession_brut if prix_cession_brut > 0 else 1e-6
                
                vgp_cache[date_day] = valeur_globale

            # C. Prix d'Acquisition Fractionné
            #    Formule BOFIP §130 :
            #      PAF = PTA × (Prix_cession_BRUT / VGP)
            manual_acq = _safe_float(tx.get('acq_price'))
            if manual_acq > 0:
                # Possibilité de surcharger manuellement le prix d'acquisition
                prix_acq_fractionne = qty * manual_acq
            else:
                fraction = prix_cession_brut / valeur_globale
                fraction = min(1.0, max(0.0, fraction))
                prix_acq_fractionne = total_acquisition_cost * fraction

            # D. Plus-Value (ou Moins-Value) nette
            #    PV = Prix_cession_BRUT − Prix_acq_fractionné − Frais_cession
            pv = prix_cession_brut - prix_acq_fractionne - fees

            # E. Mise à jour du PTA (on retire la fraction consommée)
            pta_avant_cession = total_acquisition_cost
            total_acquisition_cost = max(0.0, total_acquisition_cost - prix_acq_fractionne)

            # F. Accumulation nette (les MV compensent les PV de la même année)
            global_plus_value += pv

            # G. Mise à jour du portefeuille
            available = portfolio.get(crypto, 0.0)
            qty_consumed = min(qty, available)
            portfolio[crypto] = available - qty_consumed
            if portfolio.get(crypto, 0.0) <= _DUST_THRESHOLD:
                portfolio.pop(crypto, None)
            tx['remaining_quantity'] = portfolio.get(crypto, 0.0)

            # H. Enregistrement de l'événement imposable (formulaire 2086)
            taxable_events.append({
                'id': tx.get('index') or idx + 1,
                'date': date_str,
                'type': 'Cession imposable',
                'crypto': crypto,
                'currency': currency,
                'quantity': qty,
                # Ligne 211 (formulaire 2086) : Prix de cession brut
                'prix_cession_brut': round(prix_cession_brut, 2),
                # Ligne 212 : Frais de cession
                'frais_cession': round(fees, 2),
                # Ligne 213 : Prix de cession net (= brut − frais)
                'prix_cession_net': round(prix_cession_net, 2),
                # Ligne 215 : Valeur globale du portefeuille
                'valeur_globale': round(valeur_globale, 2),
                # Ligne 216 : Montant global d'acquisition (PTA avant cession)
                'montant_global_acquisition': round(pta_avant_cession, 2),
                # Ligne 217 : Prix d'acquisition fractionné
                'prix_acq_fractionne': round(prix_acq_fractionne, 2),
                # Prix unitaire d'acquisition (informatif)
                'unit_acq': round(prix_acq_fractionne / qty, 6) if qty > 0 else 0,
                # Ligne 218 : Plus-value ou moins-value
                'plus_value': round(pv, 2),
            })

        # ==============================================================
        # ÉCHANGE (Crypto → Crypto) – Sursis d'imposition
        # ==============================================================
        elif op in ('echange', 'swap', 'exchange', 'transfert crypto', 'crypto_to_crypto'):

            available = portfolio.get(crypto, 0.0)
            if available < qty - _DUST_THRESHOLD:
                logger.warning(
                    "Échange [%s] : quantité insuffisante (dispo=%.8f, demandé=%.8f)",
                    crypto, available, qty,
                )
                # On ne bloque pas le calcul : on échange ce qu'on a
                qty = available

            if qty <= _DUST_THRESHOLD:
                tx['remaining_quantity'] = portfolio.get(crypto, 0.0)
                continue

            # Retrait de la crypto cédée
            portfolio[crypto] = portfolio.get(crypto, 0.0) - qty
            if portfolio[crypto] <= _DUST_THRESHOLD:
                portfolio.pop(crypto, None)

            # Ajout de la crypto reçue
            received_token = str(tx.get('received_token', '')).strip().upper()
            received_qty = _safe_float(tx.get('received_quantity'))
            if received_token and received_qty > _DUST_THRESHOLD:
                portfolio[received_token] = portfolio.get(received_token, 0.0) + received_qty

            # IMPORTANT : le PTA global ne change PAS lors d'un échange crypto→crypto.
            # (art. 150 VH bis – sursis d'imposition)

            tx['remaining_quantity'] = portfolio.get(crypto, 0.0)

        # ==============================================================
        # DÉPÔT / TRANSFERT ENTRANT (Entrée dans le patrimoine)
        # ==============================================================
        elif op in ('depot', 'deposit', 'receive'):
            # Si le prix est dans le CSV, on l'utilise pour augmenter le PTA.
            # Sinon on le récupère via le cache sécurisé.
            if unit_price == 0 and date_str:
                unit_price = _get_cached_price(crypto, date_str, price_cache)
                tx['price'] = unit_price

            if unit_price > 0:
                cost = (qty * unit_price) + fees
                total_acquisition_cost += cost

            portfolio[crypto] = portfolio.get(crypto, 0.0) + qty
            tx['remaining_quantity'] = portfolio[crypto]

        # ==============================================================
        # GAINS PASSIFS (Staking, Rewards, Intérêts, Airdrops)
        # ==============================================================
        elif op in ('staking', 'reward', 'earn', 'income'):
            # Les nouveaux tokens reçus entrent dans le PTA au prix du marché.
            # Pas d'événement imposable au titre de l'art. 150 VH bis
            # (ces revenus peuvent relever d'un autre régime, ex. BNC).
            if unit_price == 0 and date_str:
                unit_price = _get_cached_price(crypto, date_str, price_cache)
                tx['price'] = unit_price

            if unit_price > 0:
                cost = (qty * unit_price) + fees
                total_acquisition_cost += cost

            portfolio[crypto] = portfolio.get(crypto, 0.0) + qty
            tx['remaining_quantity'] = portfolio[crypto]
            tx['_is_staking_reward'] = True

        # ==============================================================
        # RETRAIT / ENVOI EXTERNE (toujours vers un wallet personnel)
        # ==============================================================
        elif op in ('retrait', 'withdrawal', 'send', 'envoi'):
            # La crypto reste dans le patrimoine ; le PTA ne change PAS.
            available = portfolio.get(crypto, 0.0)
            qty_to_sub = min(qty, available)
            portfolio[crypto] = available - qty_to_sub
            if portfolio[crypto] <= _DUST_THRESHOLD:
                portfolio.pop(crypto, None)
            tx['remaining_quantity'] = portfolio.get(crypto, 0.0)

        # ==============================================================
        # TRANSFERT INTERNE (ex: Retail Staking/Unstaking Transfer Coinbase)
        # ==============================================================
        elif op in ('transfert_interne',):
            # Mouvements comptables internes entre sous-comptes d'une même
            # plateforme (ex: Coinbase Retail Staking Transfer).
            # Ces opérations arrivent toujours par paires (+qty / -qty) qui
            # se neutralisent. Elles n'ont aucune réalité fiscale :
            #   • Pas de cession → pas d'événement imposable
            #   • Pas d'acquisition → le PTA ne change PAS
            #   • Le portefeuille fiscal global reste inchangé
            tx['remaining_quantity'] = portfolio.get(crypto, 0.0)
            tx['_skipped_reason'] = (
                "Transfert interne plateforme (ex: Retail Staking/Unstaking Transfer) "
                "– aucun impact fiscal (PTA et portefeuille inchangés)."
            )

        # ==============================================================
        # OPÉRATIONS INCONNUES / NEUTRES
        # ==============================================================
        else:
            logger.debug("Opération non reconnue : '%s' (tx #%d)", op, idx + 1)
            tx['remaining_quantity'] = portfolio.get(crypto, 0.0)

    # ------------------------------------------------------------------
    # 5. Nettoyage final du portefeuille (suppression des micro-poussières)
    # ------------------------------------------------------------------
    portfolio = {k: v for k, v in portfolio.items() if v > _DUST_THRESHOLD}

    # ------------------------------------------------------------------
    # 6. Construction du résultat
    # ------------------------------------------------------------------
    return {
        # Bilan net de l'année (PV − MV cumulées) → base imposable
        'total_plus_value_imposable': round(global_plus_value, 2),
        # Somme des prix de cession bruts (informatif / formulaire 2086)
        'total_prix_cession_imposable': round(total_prix_cession_brut, 2),
        # Détail de chaque cession imposable
        'taxable_events': taxable_events,
        # PTA résiduel sur les actifs encore détenus
        'remaining_acquisition_cost': round(total_acquisition_cost, 2),
        # Portefeuille final (quantités par actif)
        'remaining_portfolio': {k: round(v, 8) for k, v in portfolio.items()},
        # Rappel du régime fiscal
        'note_fiscale': (
            "Régime art. 150 VH bis du CGI – "
            "Formule BOFIP §130 appliquée (fraction au prix brut). "
            "Échanges crypto↔crypto non imposables (sursis d'imposition). "
            "Les moins-values de l'année compensent les plus-values de l'année."
        ),
    }