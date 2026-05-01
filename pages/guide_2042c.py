import pandas as pd
import streamlit as st

st.set_page_config(
    page_title="Guide 2042-C - Eisphora",
    page_icon="🧾",
    layout="wide",
)

st.title("Guide de report — Formulaire 2042-C")
st.write("Section « Cession d'actifs numériques »")

st.warning(
    "Les résultats sont fournis à titre indicatif et ne constituent pas un conseil fiscal ou juridique. "
    "L'auteur décline toute responsabilité en cas d'erreur de déclaration."
)

st.header("2. Reporter le bilan sur le formulaire 2042-C")
st.write(
    "Sur impots.gouv.fr, ouvrez le formulaire 2042-C, rubrique « Plus-values et gains divers » → "
    "« Cession d'actifs numériques »."
)

amount_to_report = None
result_label = ""
case_label = ""
case_value = ""
other_case = ""

if "edited_results" in st.session_state:
    try:
        df = st.session_state["edited_results"]
        if isinstance(df, pd.DataFrame):
            gains = df["TOTAL CESSION (€)"] - df["PRIX ACQ. UNIT. (€)"] * df["QUANTITÉ"]
            amount_to_report = float(gains.sum())
    except Exception:
        amount_to_report = None

if amount_to_report is not None:
    rounded_amount = int(round(amount_to_report))
    if rounded_amount > 0:
        result_label = "GAIN (plus-value)"
        case_label = "3AN"
        case_value = f"{rounded_amount:,d} €"
        other_case = "3BN"
    elif rounded_amount < 0:
        result_label = "PERTE (moins-value)"
        case_label = "3BN"
        case_value = f"{abs(rounded_amount):,d} €"
        other_case = "3AN"
    else:
        result_label = "Résultat nul"
        case_label = "Aucune case à remplir"
        case_value = "0 €"
        other_case = "Aucune"

    st.markdown(
        f"""
**Votre résultat :** {result_label}  

**Case à remplir :** {case_label}  

**Montant à reporter :** {case_value}  

Laissez la case {other_case} vide. N'entrez jamais un montant dans les deux cases simultanément.
"""
    )
    if rounded_amount != 0:
        st.info(
            "Sur le formulaire officiel, reportez un montant en euros entiers uniquement. "
            "Arrondissez à l'euro le plus proche si nécessaire."
        )
else:
    st.markdown(
        """
**Votre résultat :** GAIN (plus-value)  

**Case à remplir :** 3AN  

**Montant à reporter :** (calculé dans le tableau principal)  

Laissez la case 3BN vide. N'entrez jamais un montant dans les deux cases simultanément.
"""
    )
    st.info(
        "Pour afficher le montant exact, commencez par importer vos transactions dans le tableau principal."
    )

st.info(
    "À savoir : Les moins-values crypto ne sont pas reportables sur les années suivantes. "
    "Elles servent uniquement à compenser les plus-values de la même année fiscale."
)

st.subheader("Conseil de lecture")
st.write(
    "Ce guide indique uniquement où reporter les chiffres crypto dans le formulaire 2042-C. "
    "Si vous avez d'autres actifs (actions, immobilier, métaux précieux, etc.), vous devez les déclarer séparément."
)

st.subheader("Textes de loi")
st.markdown(
    """
**Plus-values de cession d'actifs numériques — cases 3AN et 3BN**

Les plus-values réalisées à compter du 1er janvier 2019 lors de la cession d'actifs numériques ou de droits s'y rapportant, à titre occasionnel par des personnes physiques, directement ou par personne interposée sont imposables au taux de 12,8 % (avec possibilité d'option pour l'imposition au barème progressif en cochant la case 3CN) et soumises aux prélèvements sociaux.

Cette option expresse et irrévocable est globale et porte sur le total des plus-values de cession d'actifs numériques réalisées par le foyer fiscal durant l'année.

L'option pour l'imposition selon le barème progressif des plus-values sur cession d'actifs numériques est indépendante de celle pouvant être exercée pour la taxation des revenus de capitaux mobiliers et des plus-values sur cession de droits sociaux.

Les actifs numériques comprennent les jetons (représentant, sous forme numérique, un ou plusieurs droits, pouvant être émis, inscrits, conservés ou transférés au moyen d’un dispositif d’enregistrement électronique partagé) et les cryptomonnaies.

Les personnes réalisant des cessions d'actifs numériques dont le montant total n'excède pas 305 € au cours d'une année d'imposition sont exonérées (le dépôt de la déclaration no 2086 est toutefois nécessaire). Les personnes réalisant des cessions dont le montant total excède le seuil de 305 € sont imposées sur l'ensemble des cessions.

La plus-value nette imposable est déterminée après compensation entre les plus-values et moins-values de cessions d'actifs numériques et de droits s'y rapportant réalisées par l'ensemble des membres du foyer fiscal au cours d'une même année d'imposition.

Vous devez calculer la plus-value imposable sur la déclaration no 2086 et reporter ce montant case 3AN de la déclaration no 2042-C.

Si l'ensemble des cessions imposables réalisées par les membres du foyer fiscal en 2025 génèrent une moins-value, indiquez son montant case 3BN. Cette moins-value n'est pas imputable sur les plus-values de cession d'autres biens.

Source : formulaire 2042-C 2026 — https://www.impots.gouv.fr/sites/default/files/formulaires/2042/2026/2042_5477.pdf
"""
)


