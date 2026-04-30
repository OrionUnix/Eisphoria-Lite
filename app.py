import streamlit as st
import pandas as pd

from core.pricing import get_historical_price
from core.calculator import calculate_french_taxes, get_exoneration_threshold, calculate_ir, get_ps_rate
from core.extractor import parse_transaction_file

# ------------------------------------------------------------------
# CONFIG
# ------------------------------------------------------------------

st.set_page_config(
    page_title="Eisphora Lite",
    page_icon="🛡️",
    layout="wide"
)

PFU_RATE = 31.4  # 🔥 Mise à jour 2026
SEUIL_EXON = get_exoneration_threshold()

# ------------------------------------------------------------------
# CACHE (PERF CRITIQUE)
# ------------------------------------------------------------------

@st.cache_data(show_spinner=False)
def load_transactions(file):
    return parse_transaction_file(file)


@st.cache_data(show_spinner=True)
def compute_taxes(transactions):
    return calculate_french_taxes(transactions)


# ------------------------------------------------------------------
# HEADER
# ------------------------------------------------------------------

st.warning(
    "⚠️ **Eisphora est un outil open source fourni à titre indicatif.** "
    "Vérifiez vos calculs et consultez un professionnel si nécessaire."
)

st.title("🛡️ Tableau de Bord Fiscal Crypto")

# ------------------------------------------------------------------
# SIDEBAR
# ------------------------------------------------------------------

with st.sidebar:
    st.header("👤 Profil Fiscal")

    revenu_net = st.number_input(
        "Revenu imposable (1AJ)",
        value=0.0,
        step=100.0
    )

    parts = st.number_input(
        "Parts fiscales",
        value=1.0,
        step=0.5
    )

    st.divider()

    if st.button("🗑️ Réinitialiser", use_container_width=True):
        st.cache_data.clear()
        st.session_state.clear()
        st.rerun()

# ------------------------------------------------------------------
# UPLOAD
# ------------------------------------------------------------------

with st.container(border=True):
    st.subheader("📂 Importer vos fichiers CSV")

    uploaded_files = st.file_uploader(
        "Coinbase, Binance, Kraken...",
        type=["csv"],
        accept_multiple_files=True,
        label_visibility="collapsed"
    )

    st.caption("🔒 Traitement local – aucun fichier n'est stocké.")

# ------------------------------------------------------------------
# PROCESS
# ------------------------------------------------------------------

if uploaded_files:
    # On réinitialise l'état si de nouveaux fichiers sont chargés
    if "last_upload" not in st.session_state or st.session_state.last_upload != [f.name for f in uploaded_files]:
        if "edited_results" in st.session_state:
            del st.session_state.edited_results
        st.session_state.last_upload = [f.name for f in uploaded_files]

    all_transactions = []

    for file in uploaded_files:
        txs = load_transactions(file)
        if txs:
            all_transactions.extend(txs)

    if not all_transactions:
        st.error("❌ Impossible d'extraire des données depuis vos fichiers.")
        st.stop()

    # ----------------------------
    # CALCUL INITIAL
    # ----------------------------

    with st.spinner("Analyse des cessions..."):
        results = compute_taxes(all_transactions)

    if results["taxable_events"]:
        # Préparation du DataFrame pour l'édition des résultats
        df_res = pd.DataFrame(results["taxable_events"])
        
        display_cols = {
            "date": "DATE",
            "crypto": "ACTIF",
            "quantity": "QUANTITÉ",
            "unit_acq": "PRIX ACQ.",
            "price_unit_vendu": "PRIX UNIT.",
            "prix_cession_brut": "TOTAL (€)",
            "plus_value": "GAIN/PERTE (€)"
        }
        
        if "price_unit_vendu" not in df_res.columns:
            df_res["price_unit_vendu"] = df_res["prix_cession_brut"] / df_res["quantity"]

        df_to_edit = df_res[list(display_cols.keys())].copy()
        df_to_edit.columns = list(display_cols.values())

        if "edited_results" not in st.session_state:
            st.session_state.edited_results = df_to_edit

        # ----------------------------
        # PLACEHOLDERS (Pour affichage en haut)
        # ----------------------------
        metrics_placeholder = st.container()
        taxes_placeholder = st.container()

        # ----------------------------
        # TABLE (EN BAS AVEC INDICATEURS)
        # ----------------------------
        st.divider()
        st.header("⚡ Détail des Cessions")
        st.caption("Modifiez les prix pour ajuster les gains. 🟢 = Gain, 🔴 = Perte.")

        def prepare_display_df(df):
            display_df = df.copy()
            # On s'assure que le gain est à jour pour l'affichage
            display_df["GAIN/PERTE (€)"] = display_df["TOTAL (€)"] - (display_df["PRIX ACQ."] * display_df["QUANTITÉ"])
            display_df["GAIN/PERTE (€)"] = display_df["GAIN/PERTE (€)"].apply(
                lambda v: f"{'🟢 +' if v >= 0 else '🔴 '}{v:.2f} €"
            )
            return display_df

        edited_df = st.data_editor(
            prepare_display_df(st.session_state.edited_results),
            use_container_width=True,
            num_rows="dynamic",
            disabled=["GAIN/PERTE (€)"],
            column_config={
                "DATE": st.column_config.TextColumn("DATE", width="medium"),
                "ACTIF": st.column_config.TextColumn("ACTIF", width="small"),
                "QUANTITÉ": st.column_config.NumberColumn("QUANTITÉ", format="%.6f"),
                "PRIX ACQ.": st.column_config.NumberColumn("PRIX ACQ.", format="%.2f €"),
                "PRIX UNIT.": st.column_config.NumberColumn("PRIX UNIT.", format="%.2f €"),
                "TOTAL (€)": st.column_config.NumberColumn("TOTAL (€)", format="%.2f €"),
                "GAIN/PERTE (€)": st.column_config.TextColumn("GAIN/PERTE (€)"),
            },
            key="final_editor_v6"
        )
        
        # MISE À JOUR DE L'ÉTAT ET RECALCUL DES MÉTRIQUES
        for col in ["DATE", "ACTIF", "QUANTITÉ", "PRIX ACQ.", "PRIX UNIT.", "TOTAL (€)"]:
            st.session_state.edited_results[col] = edited_df[col]
        
        current_df = st.session_state.edited_results
        current_df["GAIN/PERTE (€)"] = current_df["TOTAL (€)"] - (current_df["PRIX ACQ."] * current_df["QUANTITÉ"])
        
        pv_totale = current_df[current_df["GAIN/PERTE (€)"] > 0]["GAIN/PERTE (€)"].sum()
        mv_totale = abs(current_df[current_df["GAIN/PERTE (€)"] < 0]["GAIN/PERTE (€)"].sum())
        solde_net = pv_totale - mv_totale
        total_cession = current_df["TOTAL (€)"].sum()

        # INJECTION DANS LES PLACEHOLDERS DU HAUT
        with metrics_placeholder:
            st.header("📊 Résumé Fiscal")
            c1, c2, c3, c4 = st.columns(4)
            
            with c1:
                with st.container(border=True):
                    st.caption("📂 Cessions")
                    st.title(f"{len(current_df)}")
                    st.caption("Taxables sur l'année")

            with c2:
                with st.container(border=True):
                    st.caption("📈 Plus-values")
                    st.title(f"+{pv_totale:.0f}€")
                    st.caption("Bénéfices réalisés")

            with c3:
                with st.container(border=True):
                    st.caption("📉 Moins-values")
                    st.title(f"-{mv_totale:.0f}€")
                    st.caption("Pertes réalisées")

            with c4:
                with st.container(border=True):
                    st.caption("💰 Solde Net")
                    color = "normal" if solde_net >= 0 else "inverse"
                    st.title(f"{max(0, solde_net):.0f}€")
                    st.caption("Assiette imposable")

        with taxes_placeholder:
            st.divider()
            st.subheader("⚖️ Estimation de l'impôt (sur solde net)")
            col_pfu, col_bar = st.columns(2)

            if total_cession < SEUIL_EXON:
                st.success(f"🎉 Exonération : total des cessions ({total_cession:.2f}€) < {SEUIL_EXON}€")
                pfu_tax, bareme_tax = 0, 0
            else:
                pfu_tax = max(0, solde_net * (PFU_RATE / 100))
                ir_avec = calculate_ir(revenu_net + solde_net, parts)
                ir_sans = calculate_ir(revenu_net, parts)
                bareme_tax = (ir_avec - ir_sans) + (solde_net * get_ps_rate() / 100)

            with col_pfu:
                is_best_pfu = pfu_tax <= bareme_tax and pfu_tax > 0
                with st.container(border=True):
                    st.write("**Option PFU (Flat Tax)**")
                    st.caption(f"{PFU_RATE}% (IR + PS)")
                    st.title(f"{pfu_tax:.0f} €")
                    if is_best_pfu:
                        st.success("✨ Option la plus avantageuse")
                    elif pfu_tax > 0:
                        st.info(f"Surcoût de {pfu_tax - bareme_tax:.0f}€")

            with col_bar:
                is_best_bar = bareme_tax < pfu_tax and bareme_tax > 0
                with st.container(border=True):
                    st.write("**Option Barème Progressif**")
                    st.caption(f"TMI + PS ({get_ps_rate()}%)")
                    st.title(f"{bareme_tax:.0f} €")
                    if is_best_bar:
                        st.success("✨ Option la plus avantageuse")
                    elif bareme_tax > 0:
                        st.info(f"Surcoût de {bareme_tax - pfu_tax:.0f}€")

        # Bouton export
        csv = st.session_state.edited_results.to_csv(index=False).encode('utf-8')
        st.download_button("📥 Télécharger mon rapport corrigé", csv, "eisphora_fiscal_report.csv", "text/csv")

    else:
        st.warning("Aucune cession imposable détectée dans vos fichiers.")