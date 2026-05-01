# core/extractor.py

import io
import logging

import pandas as pd

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Constantes
# ---------------------------------------------------------------------------

# Types d'opérations normalisés
OP_BUY        = "buy"
OP_SELL       = "sell"
OP_STAKING    = "staking"
OP_WITHDRAWAL = "withdrawal"
OP_DEPOSIT    = "deposit"
OP_SWAP       = "swap"
OP_UNKNOWN    = "unknown"

# Encodages testés dans l'ordre
_ENCODINGS = ["utf-8-sig", "utf-8", "latin-1", "cp1252"]

# Nombre de lignes d'en-tête à scanner pour trouver le header réel
_HEADER_SCAN_LIMIT = 40


# ---------------------------------------------------------------------------
# Helpers internes
# ---------------------------------------------------------------------------

def _decode_bytes(raw_bytes: bytes) -> str | None:
    """Essaie plusieurs encodages et retourne le texte décodé ou None."""
    for enc in _ENCODINGS:
        try:
            return raw_bytes.decode(enc)
        except (UnicodeDecodeError, LookupError):
            continue
    return None


def _find_header_line(lines: list[str]) -> int:
    """
    Cherche l'index de la ligne de header dans les premières lignes.
    Retourne -1 si non trouvé.
    """
    for i, line in enumerate(lines[:_HEADER_SCAN_LIMIT]):
        low = line.lower()
        if (
            ("timestamp" in low and "asset" in low)
            or ("date" in low and "type" in low)
            or ("timestamp" in low and "type" in low)
            or ("date" in low and "asset" in low)
            or ("time" in low and "asset" in low)
            or ("time" in low and "type" in low)
        ):
            return i
    return -1


def _normalize_columns(df: pd.DataFrame) -> pd.DataFrame:
    """Nettoie les noms de colonnes (espaces, guillemets)."""
    df.columns = [
        str(c).strip().strip('"').strip("'").strip()
        for c in df.columns
    ]
    return df


def _find_col(cols_lower: dict, candidates: list[str]) -> str | None:
    """
    Retourne le nom réel de la première colonne trouvée parmi les candidats.
    La comparaison est insensible à la casse.
    """
    for candidate in candidates:
        key = candidate.lower().strip()
        if key in cols_lower:
            return cols_lower[key]
    return None


def _safe_numeric(raw: str) -> float:
    """
    Nettoie une chaîne et la convertit en float positif.
    Gère les symboles monétaires mal encodés (â‚¬ = €).
    """
    if not raw or raw.lower() in ("nan", "none", ""):
        return 0.0
    # Suppression des caractères mal encodés et symboles monétaires
    cleaned = raw.replace(",", ".")
    cleaned = "".join(
        c for c in cleaned
        if c.isdigit() or c in ".-"
    )
    # Gestion du double point / double moins pathologique
    try:
        return abs(float(cleaned)) if cleaned not in ("", ".", "-", "-.") else 0.0
    except ValueError:
        return 0.0


def _normalize_op_type(raw: str) -> str:
    """Normalise un type d'opération vers les constantes internes."""
    op = raw.lower().strip()

    if any(k in op for k in ["buy", "achat", "acquisition", "deposit_fiat"]):
        return OP_BUY
    if any(k in op for k in ["sell", "vente", "cession", "advanced trade sell"]):
        return OP_SELL
    if any(k in op for k in [
        "staking", "reward", "earn", "income", "interest",
        "learning reward", "intérêts", "cashback",
    ]):
        return OP_STAKING
    if any(k in op for k in [
        "withdrawal", "retrait", "send", "envoi",
        "fiat withdrawal", "crypto withdrawal",
    ]):
        return OP_WITHDRAWAL
    if any(k in op for k in [
        "deposit", "dépôt", "receive", "réception",
        "fiat deposit", "crypto deposit",
    ]):
        return OP_DEPOSIT
    if any(k in op for k in ["swap", "exchange", "convert", "echange", "échange"]):
        return OP_SWAP

    return OP_UNKNOWN


# ---------------------------------------------------------------------------
# Point d'entrée principal
# ---------------------------------------------------------------------------

def parse_transaction_file(file) -> list[dict]:
    """
    Lit un fichier CSV d'exchange (Coinbase Advanced, Binance, Kraken…)
    et retourne une liste normalisée de transactions.

    Chaque transaction est un dict avec les clés :
        date, crypto_token, operation_type, quantity, price, fees, currency
    """
    try:
        # ----------------------------------------------------------------
        # 1. Lecture brute + décodage
        # ----------------------------------------------------------------
        file.seek(0)
        raw_bytes = file.read()

        content = _decode_bytes(raw_bytes)
        if not content:
            logger.error("Impossible de décoder le fichier CSV (tous encodages échoués)")
            return []

        lines = content.splitlines()

        # ----------------------------------------------------------------
        # 2. Détection de la ligne de header
        # ----------------------------------------------------------------
        header_idx = _find_header_line(lines)

        if header_idx == -1:
            logger.warning("Header non détecté – lecture depuis le début du fichier")
            file.seek(0)
            df = pd.read_csv(file, sep=None, engine="python", on_bad_lines="skip")
        else:
            data_text = "\n".join(lines[header_idx:])
            df = pd.read_csv(
                io.StringIO(data_text),
                sep=None,
                engine="python",
                on_bad_lines="skip",
            )

        if df.empty:
            logger.warning("DataFrame vide après lecture")
            return []

        df = _normalize_columns(df)

        # ----------------------------------------------------------------
        # 3. Mapping des colonnes (fuzzy matching)
        # ----------------------------------------------------------------
        cols_lower = {c.lower(): c for c in df.columns}

        col_date = _find_col(cols_lower, [
            "Timestamp", "Date", "Transaction Date", "Time",
            "Heure", "datetime", "created at", "trade time",
        ])
        col_asset = _find_col(cols_lower, [
            "Asset", "Currency", "Symbol", "Token",
            "Cryptocurrency", "crypto_token", "Instrument",
            "Actif", "Base Currency", "base",
        ])
        col_type = _find_col(cols_lower, [
            "Transaction Type", "Type", "Operation",
            "operation_type", "Type d'opération", "side", "trade type",
        ])
        col_qty = _find_col(cols_lower, [
            "Quantity Transacted", "Amount", "Quantity", "Qty",
            "Size", "quantity", "Montant", "Quantité", "units",
        ])
        col_price = _find_col(cols_lower, [
            "Price at Transaction", "Spot Price at Transaction",
            "Price", "Spot Price", "Price (EUR)", "Unit Price",
            "price", "Prix unitaire", "rate",
        ])
        col_subtotal = _find_col(cols_lower, [
            "Subtotal", "subtotal", "Net Amount", "montant_net",
            "net proceeds", "proceeds",
        ])
        col_total = _find_col(cols_lower, [
            "Total (inclusive of fees and/or spread)",
            "Total", "total", "gross amount",
        ])
        col_fees = _find_col(cols_lower, [
            "Fees and/or Spread", "Fee", "Fees", "Transaction Fee",
            "Commission", "fees", "Frais", "trading fee",
        ])
        col_currency = _find_col(cols_lower, [
            "Price Currency", "Spot Price Currency",
            "Quote Currency", "Currency (Price)", "Market Currency",
            "currency", "Devise", "quote",
        ])
        col_product = _find_col(cols_lower, [
            "product_id", "market", "pair", "produit",
            "trading pair", "symbol",
        ])
        col_notes = _find_col(cols_lower, [
            "Notes", "notes", "description", "memo", "note",
        ])

        # ----------------------------------------------------------------
        # 4. Boucle de normalisation des lignes
        # ----------------------------------------------------------------
        transactions = []

        for _, row in df.iterrows():
            try:
                # -- Date ------------------------------------------------
                date = str(row[col_date]).strip() if col_date else None
                if not date or date.lower() in ("nan", "none", ""):
                    continue

                # -- Asset -----------------------------------------------
                asset = None
                if col_asset:
                    raw_asset = str(row[col_asset]).strip().upper()
                    if raw_asset not in ("NAN", "NONE", ""):
                        asset = raw_asset

                if not asset and col_product:
                    prod = str(row[col_product]).strip()
                    if "-" in prod:
                        asset = prod.split("-")[0].strip().upper()
                    elif "/" in prod:
                        asset = prod.split("/")[0].strip().upper()
                    else:
                        asset = prod.strip().upper()

                # Coinbase : parfois l'asset est dans les notes (Receive)
                if not asset and col_notes:
                    notes = str(row.get(col_notes, "")).strip()
                    # ex: "Received 60 USDC from..."
                    import re
                    m = re.search(r"(?:Received|Sent)\s+[\d.,]+\s+([A-Z]{2,10})", notes)
                    if m:
                        asset = m.group(1).upper()

                if not asset or asset in ("NAN", "NONE", ""):
                    continue

                # -- Type d'opération ------------------------------------
                raw_type = str(row[col_type]).strip() if col_type else "unknown"
                op_type = _normalize_op_type(raw_type)

                # -- Quantité --------------------------------------------
                raw_qty = str(row[col_qty]) if col_qty else "0"
                qty = _safe_numeric(raw_qty)
                if qty <= 0:
                    continue

                # -- Prix unitaire ---------------------------------------
                price = 0.0
                if col_price:
                    price = _safe_numeric(str(row[col_price]))

                # Fallback 1 : calcul depuis subtotal / total
                if price == 0.0 and qty > 0:
                    for col_fallback in [col_subtotal, col_total]:
                        if col_fallback:
                            sub_val = _safe_numeric(str(row[col_fallback]))
                            if sub_val > 0:
                                price = sub_val / qty
                                logger.debug(
                                    "Prix calculé depuis %s pour %s : %.6f",
                                    col_fallback, asset, price,
                                )
                                break

                # -- Frais -----------------------------------------------
                fees = _safe_numeric(str(row[col_fees])) if col_fees else 0.0

                # -- Devise de cotation ----------------------------------
                currency = "EUR"
                if col_currency:
                    raw_cur = str(row[col_currency]).strip().upper()
                    if raw_cur not in ("NAN", "NONE", ""):
                        currency = raw_cur

                # --------------------------------------------------------
                transactions.append({
                    "date": date,
                    "crypto_token": asset,
                    "operation_type": op_type,
                    "quantity": qty,
                    "price": price,
                    "fees": fees,
                    "currency": currency,
                })

            except Exception as exc:
                logger.debug("Ligne ignorée (%s) : %s", type(exc).__name__, exc)

        logger.info(
            "Fichier '%s' : %d transactions extraites",
            getattr(file, "name", "?"), len(transactions),
        )
        return transactions

    except Exception as exc:
        logger.error("Erreur lecture fichier : %s", exc, exc_info=True)
        return []