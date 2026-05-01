# app.py – Eisphora Lite (Streamlit)

import hashlib
import logging
import pandas as pd
import streamlit as st

# Désactivation complète de la journalisation pour éviter toute sortie console inutile.
logging.disable(logging.CRITICAL)

from core.France.calculator import (
    calculate_french_taxes,
    calculate_ir,
    get_exoneration_threshold,
    get_pfu_ir_rate,
    get_pfu_rate,
    get_pfu_ps_rate,
    get_ps_rate,
)
from core.France.extractor import parse_transaction_file

# ---------------------------------------------------------------------------
# Configuration de la page
# ---------------------------------------------------------------------------

st.set_page_config(
    page_title="Eisphora Lite",
    page_icon="🛡️",
    layout="wide",
)

PFU_RATE  = get_pfu_rate()
SEUIL_EXON = get_exoneration_threshold()

# ---------------------------------------------------------------------------
# Cache (performance critique)
# ---------------------------------------------------------------------------

@st.cache_data(show_spinner=False)
def load_transactions(file_name: str, file_bytes: bytes):
    """
    Cache basé sur le nom + contenu du fichier.
    On passe les bytes pour que le hash de cache soit déterministe.
    """
    import io
    virtual_file = io.BytesIO(file_bytes)
    virtual_file.name = file_name
    return parse_transaction_file(virtual_file)


@st.cache_data(show_spinner=True)
def compute_taxes(transactions: list):
    return calculate_french_taxes(transactions)


# ---------------------------------------------------------------------------
# Header
# ---------------------------------------------------------------------------

st.warning(
    "⚠️ **Eisphora-Lite** est un outil d'aide à la saisie du formulaire 2086. Les résultats sont fournis à titre indicatif et ne constituent pas un conseil fiscal ou juridique. L'auteur décline toute responsabilité en cas d'erreur de déclaration"
)

st.title("Eisphora-lite Tableau de Bord Fiscal Crypto")
st.caption(
    "Cette application ne crée pas de cookie de suivi et ne stocke aucune donnée utilisateur en dehors de la session temporaire Streamlit."
)
st.caption(
    "Consultez le menu Pages en haut à gauche pour accéder aux guides et aux mentions légales."
)

# ---------------------------------------------------------------------------
# Upload des fichiers
# ---------------------------------------------------------------------------

with st.container(border=True):
    st.subheader("📂 Importer vos fichiers CSV")

    uploaded_files = st.file_uploader(
        "Coinbase, Binance, Kraken…",
        type=["csv", "xls", "xlsx"],
        accept_multiple_files=True,
        label_visibility="collapsed",
        key="uploaded_files",
    )

    st.caption(
        "🔒 Traitement 100% local – Aucun compte, aucun cookie de suivi, aucune base de données. Vos fichiers sont traités en mémoire vive (RAM) et disparaissent dès que vous fermez cet onglet. Zéro log, zéro stockage."
)


def _dedupe_uploaded_files(files):
    seen_hashes = set()
    unique_files = []
    duplicate_names = []

    for file in files:
        file.seek(0)
        content = file.read()
        file_hash = hashlib.sha256(content).hexdigest()
        file.seek(0)

        if file_hash in seen_hashes:
            duplicate_names.append(file.name)
            continue

        seen_hashes.add(file_hash)
        unique_files.append((file, content))

    return unique_files, duplicate_names


# ---------------------------------------------------------------------------
# Traitement principal
# ---------------------------------------------------------------------------

has_saved_results = (
    "tax_results" in st.session_state
    and "edited_results" in st.session_state
    and st.session_state["edited_results"] is not None
)

if not uploaded_files and not has_saved_results:
    st.stop()

results = None
unique_files = []

if uploaded_files:
    unique_files, duplicate_names = _dedupe_uploaded_files(uploaded_files)
    if duplicate_names:
        st.warning(
            "Fichier(s) en double détecté(s) et ignoré(s) : "
            + ", ".join(sorted(set(duplicate_names)))
        )

    unique_file_names = [file.name for file, _ in unique_files]
    if st.session_state.get("last_upload") != unique_file_names:
        st.session_state.pop("edited_results", None)
        st.session_state["last_upload"] = unique_file_names

    # -- Extraction des transactions --
    all_transactions = []
    for file, file_bytes in unique_files:
        txs = load_transactions(file.name, file_bytes)
        if txs:
            all_transactions.extend(txs)

    if not all_transactions:
        st.error("❌ Impossible d'extraire des données depuis vos fichiers.")
        st.stop()

    # -- Calcul fiscal --
    with st.spinner("Analyse des cessions en cours…"):
        results = compute_taxes(all_transactions)
    st.session_state["tax_results"] = results
else:
    results = st.session_state["tax_results"]

st.header("Profil fiscal")
st.write(
    "Ce bloc est facultatif, mais il permet de déterminer votre tranche marginale d'imposition (TMI) "
    "pour comparer la Flat Tax et le barème progressif."
)

st.subheader("🌍 Pays / régime fiscal")
france = st.checkbox(
    "🇫🇷 France",
    value=True,
    help="Régime fiscal français actuellement implémenté.",
)
st.checkbox(
    "🇱🇺 Luxembourg",
    value=False,
    disabled=True,
    help="En préparation — disponible prochainement.",
)
st.checkbox(
    "🇧🇪 Belgique",
    value=False,
    disabled=True,
    help="En préparation — disponible prochainement.",
)

if not france:
    st.warning("Seul le régime français est disponible pour le moment.")

country = "France"
revenu_net = st.number_input(
    "Revenu imposable (1AJ)",
    value=0.0,
    step=100.0,
    help="Montant de la case 1AJ de votre déclaration de revenus.",
    key="revenu_net",
)

parts = st.number_input(
    "Parts fiscales",
    value=1.0,
    step=0.5,
    min_value=0.5,
    help="Nombre de parts du foyer fiscal (1 = célibataire, 2 = couple, +0.5 par enfant).",
    key="parts_fiscales",
)

st.divider()

if st.button("🗑️ Effacer tout les données", use_container_width=True, key="reset_button"):
    st.cache_data.clear()
    st.session_state["uploaded_files"] = None
    st.session_state.pop("last_upload", None)
    st.session_state.pop("edited_results", None)
    st.session_state.pop("tax_results", None)
    st.experimental_rerun()

st.divider()
st.caption(
    f"**PFU {get_pfu_rate():.1f}%** · "
    f"PFU PS {get_pfu_ps_rate():.1f}% · "
    f"PS barème {get_ps_rate():.1f}% · "
    f"Seuil exo. {SEUIL_EXON:.0f}€"
)

if not results["taxable_events"]:
    st.warning("Aucune cession imposable détectée dans vos fichiers.")
    st.info(
        f"PTA résiduel : **{results['remaining_acquisition_cost']:.2f}€**  |  "
        f"Portefeuille : {results['remaining_portfolio']}"
    )
    st.stop()

# ---------------------------------------------------------------------------
# Préparation du DataFrame
# ---------------------------------------------------------------------------

df_res = pd.DataFrame(results["taxable_events"])

# Colonnes affichées et leurs labels UI
DISPLAY_COLS = {
    "date":             "DATE",
    "crypto":           "ACTIF",
    "quantity":         "QUANTITÉ",
    "frais_cession":    "FRAIS (€)",
    "unit_acq":         "PRIX ACQ. UNIT. (€)",   # quote-part PAF / quantité
    "price_unit_vendu": "PRIX VENTE UNIT. (€)",
    "prix_cession_brut":"TOTAL CESSION (€)",
    "plus_value":       "GAIN/PERTE (€)",
}

# Valeurs par défaut si les colonnes n'existent pas
if "frais_cession" not in df_res.columns:
    df_res["frais_cession"] = 0.0

# Calcul de price_unit_vendu si manquant
if "price_unit_vendu" not in df_res.columns:
    df_res["price_unit_vendu"] = df_res.apply(
        lambda r: r["prix_cession_brut"] / r["quantity"] if r["quantity"] > 0 else 0.0,
        axis=1,
    )

df_to_edit = df_res[list(DISPLAY_COLS.keys())].copy()
df_to_edit.columns = list(DISPLAY_COLS.values())

if "edited_results" not in st.session_state:
    st.session_state["edited_results"] = df_to_edit.copy()
else:
    for col in df_to_edit.columns:
        if col not in st.session_state["edited_results"].columns:
            st.session_state["edited_results"][col] = df_to_edit[col]

# ---------------------------------------------------------------------------
# Placeholders (metrics et taxes en haut, table en bas)
# ---------------------------------------------------------------------------

metrics_placeholder = st.container()
taxes_placeholder   = st.container()

# ---------------------------------------------------------------------------
# Table éditable
# ---------------------------------------------------------------------------

st.divider()
st.header("⚡ Détail des Cessions")

col_info, _ = st.columns([3, 1])
with col_info:
    st.caption(
        "🟢 = Gain · 🔴 = Perte · "
        "**PRIX ACQ. UNIT.** = quote-part du PTA global allouée à cette cession "
        "(formule BOFIP §130), pas le prix d'achat spot. "
        "Vous pouvez modifier les colonnes éditables."
    )


EDITABLE_COLS = [
    "DATE", "ACTIF", "QUANTITÉ",
    "PRIX ACQ. UNIT. (€)", "PRIX VENTE UNIT. (€)", "TOTAL CESSION (€)",
]


def compute_gain(df: pd.DataFrame) -> pd.Series:
    """Calcule la plus-value nette : Total cession - (Prix acq unit × Quantité)."""
    return df["TOTAL CESSION (€)"] - df["PRIX ACQ. UNIT. (€)"] * df["QUANTITÉ"]


def format_gain(series: pd.Series) -> pd.Series:
    return series.apply(lambda v: f"{'🟢 +' if v >= 0 else '🔴 '}{v:,.2f} €")


def prepare_display_df(df: pd.DataFrame) -> pd.DataFrame:
    """Prépare le DataFrame avec GAIN/PERTE recalculé depuis l'état courant."""
    out = df.copy()
    out["GAIN/PERTE (€)"] = format_gain(compute_gain(out))
    return out


# Toujours afficher depuis l'état synchronisé (pas depuis edited_df de l'itération précédente)
display_df = prepare_display_df(st.session_state["edited_results"])

edited_df = st.data_editor(
    display_df,
    use_container_width=True,
    num_rows="dynamic",
    disabled=["FRAIS (€)", "GAIN/PERTE (€)"],
    column_config={
        "DATE": st.column_config.TextColumn(
            "DATE", width="medium", help="Date et heure UTC de la cession."
        ),
        "ACTIF": st.column_config.TextColumn(
            "ACTIF", width="small", help="Crypto-actif cédé."
        ),
        "QUANTITÉ": st.column_config.NumberColumn(
            "QUANTITÉ", format="%.6f", help="Quantité cédée."
        ),
        "FRAIS (€)": st.column_config.NumberColumn(
            "FRAIS (€)", format="%.2f €", help="Frais de cession convertis en euros."
        ),
        "PRIX ACQ. UNIT. (€)": st.column_config.NumberColumn(
            "PRIX ACQ. UNIT. (€)",
            format="%.4f €",
            help=(
                "Quote-part du Prix Total d'Acquisition (PTA) global allouée à "
                "cette cession, divisée par la quantité. "
                "Formule BOFIP §130 : PAF = PTA × (Prix_brut / VGP). "
                "Cette valeur est DIFFÉRENTE du prix d'achat spot initial."
            ),
        ),
        "PRIX VENTE UNIT. (€)": st.column_config.NumberColumn(
            "PRIX VENTE UNIT. (€)", format="%.4f €", help="Prix unitaire de cession."
        ),
        "TOTAL CESSION (€)": st.column_config.NumberColumn(
            "TOTAL CESSION (€)",
            format="%.2f €",
            help="Prix de cession brut = Quantité × Prix unitaire (ligne 211, formulaire 2086).",
        ),
        "GAIN/PERTE (€)": st.column_config.TextColumn(
            "GAIN/PERTE (€)", help="Plus-value ou moins-value nette de cette cession."
        ),
    },
    key="final_editor_v7",
)

# -- Synchronisation : détection de changement et rerun pour recalcul immédiat --
edited_data   = edited_df[EDITABLE_COLS].reset_index(drop=True)
current_data  = st.session_state["edited_results"][EDITABLE_COLS].reset_index(drop=True)

if not edited_data.equals(current_data):
    for col in EDITABLE_COLS:
        st.session_state["edited_results"][col] = edited_df[col].values
    st.rerun()

# -- Recalcul des métriques depuis l'état synchronisé --
current_df = st.session_state["edited_results"].copy()
current_df["_gain"] = compute_gain(current_df)

pv_totale    = current_df[current_df["_gain"] > 0]["_gain"].sum()
mv_totale    = abs(current_df[current_df["_gain"] < 0]["_gain"].sum())
solde_net    = pv_totale - mv_totale
total_cession = current_df["TOTAL CESSION (€)"].sum()

# ---------------------------------------------------------------------------
# Métriques (injectées dans le placeholder du haut)
# ---------------------------------------------------------------------------

with metrics_placeholder:
    st.header("📊 Résumé Fiscal")

    c1, c2, c3, c4 = st.columns(4)

    with c1:
        with st.container(border=True):
            st.caption("📂 Cessions taxables")
            st.title(f"{len(current_df)}")
            st.caption(f"Total cédé : {total_cession:,.2f} €")

    with c2:
        with st.container(border=True):
            st.caption("📈 Plus-values")
            st.title(f"+{pv_totale:,.0f} €")
            st.caption("Bénéfices réalisés")

    with c3:
        with st.container(border=True):
            st.caption("📉 Moins-values")
            st.title(f"-{mv_totale:,.0f} €")
            st.caption("Pertes réalisées")

    with c4:
        with st.container(border=True):
            st.caption("💰 Solde Net")
            st.title(f"{max(0.0, solde_net):,.0f} €")
            st.caption("Assiette imposable")

    # Infos complémentaires du moteur fiscal
    with st.expander("🔍 Détails du calcul (PTA résiduel & portefeuille)"):
        col_pta, col_pf = st.columns(2)
        with col_pta:
            st.metric(
                "PTA résiduel",
                f"{results['remaining_acquisition_cost']:,.2f} €",
                help="Prix Total d'Acquisition restant sur les actifs encore détenus.",
            )
        with col_pf:
            if results["remaining_portfolio"]:
                st.write("**Portefeuille résiduel :**")
                for asset, qty in results["remaining_portfolio"].items():
                    st.write(f"  • {asset} : {qty:.6f}")
            else:
                st.write("Portefeuille vide.")
        st.caption(results["note_fiscale"])

# ---------------------------------------------------------------------------
# Estimation de l'impôt
# ---------------------------------------------------------------------------

with taxes_placeholder:
    st.divider()
    st.subheader("⚖️ Estimation de l'impôt")

    if total_cession < SEUIL_EXON:
        st.success(
            f"🎉 **Exonération totale** : total des cessions ({total_cession:,.2f} €) "
            f"< seuil de {SEUIL_EXON:.0f} €."
        )
        pfu_tax = bareme_tax = 0.0
    else:
        assiette = max(0.0, solde_net)
        pfu_tax  = assiette * (PFU_RATE / 100)

        ir_avec  = calculate_ir(revenu_net + assiette, parts)
        ir_sans  = calculate_ir(revenu_net, parts)
        bareme_tax = (ir_avec - ir_sans) + (assiette * get_ps_rate() / 100)

    col_pfu, col_bar = st.columns(2)

    with col_pfu:
        is_best_pfu = (pfu_tax > 0) and (pfu_tax <= bareme_tax)
        with st.container(border=True):
            st.write("**Option PFU (Flat Tax)**")
            st.caption(
                f"{PFU_RATE}% tout compris (IR {get_pfu_ir_rate():.1f}% + PS {get_pfu_ps_rate():.1f}%)"
            )
            st.title(f"{pfu_tax:,.0f} €")
            if is_best_pfu:
                st.success("✨ Option la plus avantageuse")
            elif pfu_tax > 0:
                diff = pfu_tax - bareme_tax
                st.info(f"Surcoût de {diff:,.0f} € vs barème")

    with col_bar:
        is_best_bar = (bareme_tax > 0) and (bareme_tax < pfu_tax)
        with st.container(border=True):
            st.write("**Option Barème Progressif**")
            st.caption(f"TMI + PS {get_ps_rate()}%")
            st.title(f"{bareme_tax:,.0f} €")
            if is_best_bar:
                st.success("✨ Option la plus avantageuse")
            elif bareme_tax > 0:
                diff = bareme_tax - pfu_tax
                st.info(f"Surcoût de {diff:,.0f} € vs PFU")

    if pfu_tax == 0 and bareme_tax == 0 and total_cession >= SEUIL_EXON:
        st.info("ℹ️ Solde net nul ou négatif : pas d'impôt à payer.")

st.divider()

# ---------------------------------------------------------------------------
# Export CSV
# ---------------------------------------------------------------------------

st.divider()

export_df = st.session_state["edited_results"].copy()
export_df["GAIN/PERTE (€)"] = (
    export_df["TOTAL CESSION (€)"]
    - export_df["PRIX ACQ. UNIT. (€)"] * export_df["QUANTITÉ"]
).round(2)

csv_bytes = export_df.to_csv(index=False).encode("utf-8")

st.download_button(
    label="📥 Télécharger le rapport corrigé (CSV)",
    data=csv_bytes,
    file_name="eisphora_rapport_fiscal.csv",
    mime="text/csv",
    use_container_width=True,
)