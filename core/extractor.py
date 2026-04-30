import pandas as pd
import logging
import io

logger = logging.getLogger(__name__)


def parse_transaction_file(file):
    """
    Lit un fichier CSV d'exchange et retourne une liste normalisée de transactions.
    Gère le saut de headers (Coinbase/Binance) et le fuzzy matching de colonnes.
    """
    try:
        # 1. Lecture brute pour trouver la ligne de header
        file.seek(0)
        raw_bytes = file.read()
        
        # Essai de plusieurs encodings
        content = None
        for enc in ['utf-8-sig', 'utf-8', 'latin-1', 'cp1252']:
            try:
                content = raw_bytes.decode(enc)
                break
            except Exception:
                continue
        
        if not content:
            logger.error("Impossible de décoder le fichier CSV")
            return []

        lines = content.splitlines()
        header_idx = -1
        # On cherche la ligne qui ressemble à un header de transactions
        for i, line in enumerate(lines[:30]):
            l = line.lower()
            if ("timestamp" in l and "asset" in l) or ("date" in l and "type" in l):
                header_idx = i
                break
        
        if header_idx == -1:
            # Fallback : on essaie quand même de lire tout le fichier
            file.seek(0)
            df = pd.read_csv(file, sep=None, engine='python', on_bad_lines='skip')
        else:
            # On lit à partir de la ligne de header identifiée
            data_text = "\n".join(lines[header_idx:])
            df = pd.read_csv(io.StringIO(data_text), sep=None, engine='python', on_bad_lines='skip')
        
        if df.empty:
            return []

        # Mapping des colonnes (Fuzzy matching étendu)
        # On nettoie les noms de colonnes (espaces, quotes)
        df.columns = [c.strip().strip('"').strip("'") for c in df.columns]
        cols = {c.lower().strip(): c for c in df.columns}
        
        def find_col(keys):
            for k in keys:
                if k.lower() in cols:
                    return cols[k.lower()]
            return None

        # Détection des colonnes clés avec plus de synonymes (Coinbase Retail/Advanced)
        col_date = find_col(["Date", "Timestamp", "Transaction Date", "Time", "Heure"])
        col_asset = find_col(["Asset", "Currency", "Symbol", "Token", "Cryptocurrency", "crypto_token", "Instrument", "Actif"])
        col_type = find_col(["Type", "Transaction Type", "Operation", "operation_type", "Type d'opération"])
        col_qty = find_col(["Amount", "Quantity", "Qty", "Size", "quantity", "Quantity Transacted", "Montant", "Quantité"])
        col_price = find_col(["Price", "Spot Price", "Price (EUR)", "Unit Price", "price", "Spot Price at Transaction", "Price at Transaction", "Prix unitaire"])
        col_fees = find_col(["Fee", "Fees", "Transaction Fee", "Commission", "fees", "Frais", "Fees and/or Spread"])
        col_currency = find_col(["Quote Currency", "Currency (Price)", "Market Currency", "currency", "Devise", "Spot Price Currency", "Price Currency"])
        col_product = find_col(["product_id", "market", "pair", "produit"])

        transactions = []

        for _, row in df.iterrows():
            try:
                # Extraction avec fallbacks
                date = str(row.get(col_date)) if col_date else None
                
                # Gestion de l'Asset (plus complexe si product_id ou si la colonne est nommée bizarrement)
                asset = None
                if col_asset:
                    asset = str(row.get(col_asset)).upper()
                elif col_product:
                    prod = str(row.get(col_product))
                    if "-" in prod: asset = prod.split("-")[0].upper()
                    elif "/" in prod: asset = prod.split("/")[0].upper()
                    else: asset = prod.upper()
                
                op_type = str(row.get(col_type)).lower() if col_type else "buy"
                
                # Nettoyage de la quantité (parfois des nombres avec virgules ou symboles bizarres)
                raw_qty = str(row.get(col_qty, "0")).replace(",", ".").strip()
                # On enlève les caractères non numériques sauf le point et le moins
                raw_qty = "".join(c for c in raw_qty if c.isdigit() or c in ".-")
                qty = abs(float(raw_qty)) if raw_qty else 0.0
                
                # Nettoyage prix
                raw_price = str(row.get(col_price, "0")).replace(",", ".").strip()
                raw_price = "".join(c for c in raw_price if c.isdigit() or c in ".-")
                price = float(raw_price) if raw_price else 0.0
                
                # Nettoyage frais
                raw_fees = str(row.get(col_fees, "0")).replace(",", ".").strip()
                raw_fees = "".join(c for c in raw_fees if c.isdigit() or c in ".-")
                fees = float(raw_fees) if raw_fees else 0.0
                
                currency = str(row.get(col_currency)).upper() if col_currency else "EUR"

                # Normalisation des types d'opérations
                if any(k in op_type for k in ["buy", "achat", "acquisition"]):
                    op_type = "buy"
                elif any(k in op_type for k in ["sell", "vente", "cession"]):
                    op_type = "sell"
                elif any(k in op_type for k in ["staking", "reward", "earn", "income", "intérêts"]):
                    op_type = "staking"
                elif any(k in op_type for k in ["withdrawal", "retrait", "send", "envoi"]):
                    op_type = "withdrawal"
                elif any(k in op_type for k in ["deposit", "dépôt", "receive", "réception"]):
                    op_type = "deposit"

                # Filtrage des lignes vides ou invalides
                if not asset or asset == "NAN" or asset == "NONE" or qty == 0:
                    continue

                transactions.append({
                    "date": date,
                    "crypto_token": asset,
                    "operation_type": op_type,
                    "quantity": qty,
                    "price": price,
                    "fees": fees,
                    "currency": currency
                })

            except Exception as e:
                logger.debug(f"Ligne ignorée: {e}")

        return transactions

    except Exception as e:
        logger.error(f"Erreur lecture fichier: {e}")
        return []