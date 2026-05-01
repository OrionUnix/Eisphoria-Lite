import pandas as pd
import streamlit as st

st.set_page_config(
    page_title="Assistant déclaration 2086 - Eisphora",
    page_icon="🧾",
    layout="wide",
)

st.title("Assistant déclaration 2086")
st.write("Eisphora a tout calculé pour vous. Recopiez simplement les chiffres dans votre déclaration en ligne, vente par vente.")

st.warning(
    "Eisphora est un outil open source développé sur le temps libre d'un passionné. "
    "Les calculs sont fournis à titre indicatif uniquement."
)

st.markdown(
    """
### ⚠️ Disclaimer & Responsabilité

- Avant de soumettre votre déclaration, vérifiez chaque valeur avec vos relevés d'exchange.
- Consultez un expert-comptable ou un conseiller fiscal.
- Ou utilisez un logiciel fiscal agréé par un professionnel.

En utilisant cet assistant, vous acceptez d'en être l'unique responsable pour votre déclaration.
"""
)

st.header("Comment utiliser cet assistant ?")
st.write(
    "Chaque vente = une fiche. L'assistant lit la table de cession générée dans le tableau principal et vous indique ce que vous devez vérifier sur le portail impots.gouv.fr."
)

sales_total = None
if "edited_results" in st.session_state:
    try:
        df = st.session_state["edited_results"]
        if isinstance(df, pd.DataFrame) and "TOTAL CESSION (€)" in df.columns:
            sales_total = df["TOTAL CESSION (€)"].sum()
    except Exception:
        sales_total = None

if sales_total is not None:
    threshold_note = (
        "Le seuil d'exonération de 305 € n'est pas dépassé. Vos plus-values peuvent rester exonérées."
        if sales_total <= 305
        else "Le seuil d'exonération de 305 € étant dépassé, vos plus-values globales seront bien soumises à l'impôt (PFU ou barème)."
    )

    st.subheader("Volume total de vos cessions")
    st.write(f"Le montant cumulé de vos ventes (somme des lignes 213) s'élève à {sales_total:,.2f} €.")
    st.info(threshold_note)
else:
    st.info("Importez vos transactions dans le tableau principal pour afficher le volume total de vos cessions.")

def fiscal_round(amount: float) -> int:
    """Arrondi fiscal : 0,01-0,49 → inférieur, 0,50-0,99 → supérieur."""
    if pd.isna(amount):
        return 0
    sign = -1 if amount < 0 else 1
    absolute = abs(amount)
    euros = int(absolute)
    cents = absolute - euros
    if cents < 0.5:
        return sign * euros
    return sign * (euros + 1)


def format_money(value: float) -> str:
    return f"{value:,.2f} €"


def format_declared(value: float) -> str:
    return f"{fiscal_round(value):,d} €"


def format_fr_date(value) -> str:
    try:
        parsed = pd.to_datetime(value, dayfirst=True, errors="coerce")
        if pd.isna(parsed):
            return str(value)
        return parsed.strftime("%d/%m/%Y")
    except Exception:
        return str(value)


if "edited_results" not in st.session_state:
    st.info(
        "Importez vos transactions depuis le tableau principal pour que l'assistant puisse lire la table de cession et vous indiquer comment remplir votre déclaration."
    )
else:
    df = st.session_state["edited_results"]
    if not isinstance(df, pd.DataFrame) or df.empty:
        st.info(
            "Aucune cession disponible. Vérifiez que vous avez bien importé vos fichiers dans le tableau principal."
        )
    else:
        st.header("Assistant déclaration 2086")
        st.write(
            "L'assistant récupère la table de cession générée dans le tableau principal et vous indique ligne par ligne ce que vous devez vérifier sur le portail impots.gouv.fr."
        )

        df = df.copy()

        st.markdown(
            "_Vous pouvez corriger la date, le montant de cession, les frais, la quantité ou le prix d'acquisition implicite directement dans chaque fiche. "
            "Les montants calculés sont ensuite mis à jour automatiquement._"
        )

        for index, row in df.iterrows():
            sale_number = index + 1
            date_key = f"assistant_2086_date_{index}"
            actif_key = f"assistant_2086_actif_{index}"
            quantite_key = f"assistant_2086_quantite_{index}"
            total_key = f"assistant_2086_total_{index}"
            frais_key = f"assistant_2086_frais_{index}"
            prix_acq_key = f"assistant_2086_prix_acq_{index}"

            if date_key not in st.session_state:
                st.session_state[date_key] = format_fr_date(row["DATE"])
            if actif_key not in st.session_state:
                st.session_state[actif_key] = row["ACTIF"]
            if quantite_key not in st.session_state:
                st.session_state[quantite_key] = float(row["QUANTITÉ"])
            if total_key not in st.session_state:
                st.session_state[total_key] = float(row["TOTAL CESSION (€)"])
            if frais_key not in st.session_state:
                st.session_state[frais_key] = float(row["FRAIS (€)"])
            if prix_acq_key not in st.session_state:
                st.session_state[prix_acq_key] = float(row["PRIX ACQ. UNIT. (€)"])

            with st.expander(f"Cession {sale_number} — {st.session_state[actif_key]}", expanded=True):
                st.text_input("211 — Date de la cession (JJ/MM/AAAA)", st.session_state[date_key], key=date_key)
                st.text_input("Actif", st.session_state[actif_key], key=actif_key)
                st.number_input(
                    "Quantité vendue",
                    value=st.session_state[quantite_key],
                    format="%.6f",
                    key=quantite_key,
                    help="Quantité cédée.",
                )
                st.number_input(
                    "213 — Prix de cession (avant frais)",
                    value=st.session_state[total_key],
                    format="%.2f",
                    key=total_key,
                    help="Prix brut reçu de la plateforme.",
                )
                st.number_input(
                    "214 — Frais de cession",
                    value=st.session_state[frais_key],
                    format="%.2f",
                    key=frais_key,
                    help="Frais supportés pour cette cession.",
                )
                st.number_input(
                    "PRIX ACQ. UNIT. (€)",
                    value=st.session_state[prix_acq_key],
                    format="%.4f",
                    key=prix_acq_key,
                    help="Quote-part du prix d'acquisition attribuée à cette cession.",
                )

                df.at[index, "DATE"] = st.session_state[date_key]
                df.at[index, "ACTIF"] = st.session_state[actif_key]
                df.at[index, "QUANTITÉ"] = st.session_state[quantite_key]
                df.at[index, "TOTAL CESSION (€)"] = st.session_state[total_key]
                df.at[index, "FRAIS (€)"] = st.session_state[frais_key]
                df.at[index, "PRIX ACQ. UNIT. (€)"] = st.session_state[prix_acq_key]

                line_213 = df.at[index, "TOTAL CESSION (€)"]
                line_214 = df.at[index, "FRAIS (€)"]
                line_215 = line_213 - line_214
                line_218 = line_215
                gain_value = line_213 - df.at[index, "PRIX ACQ. UNIT. (€)"] * df.at[index, "QUANTITÉ"]
                gain_label = "gain" if gain_value >= 0 else "moins-value"

                st.markdown(
                    f"""
**212 — Valeur globale du portefeuille au moment de la cession**  
Il s’agit de la valeur totale de votre portefeuille au moment de la cession, pas seulement de la crypto vendue.  
Complétez cette case uniquement si vous connaissez précisément ce montant.  

**213 — Prix de cession**  
Prix réel perçu ou valeur de la contrepartie obtenue par le cédant lors de la cession.  

{format_money(line_213)}  
À déclarer : {format_declared(line_213)}  

**214 — Frais de cession**  
Frais supportés pour cette cession, notamment ceux perçus par les plateformes et les mineurs.  

{format_money(line_214)}  
À déclarer : {format_declared(line_214)}  

**215 — Prix de cession net des frais**  
Calculé automatiquement : ligne 213 − ligne 214  

{format_money(line_215)}  
À déclarer : {format_declared(line_215)}  

**216 — Soulte reçue ou versée lors de la cession**  
Indiquez la soulte reçue ou versée. Ici, valeur par défaut 0,00 € pour les cas sans soulte.  

0,00 €  
À déclarer : 0 €  

**218 — Prix de cession net des frais et soultes**  
Calculé automatiquement : ligne 215 − ligne 216  

{format_money(line_218)}  
À déclarer : {format_declared(line_218)}  

**220 — Prix total d'acquisition du portefeuille**  
Le prix total d'acquisition du portefeuille est égal à la somme des prix payés en monnaie ayant cours légal pour l'ensemble des acquisitions d'actifs numériques, hors opérations d'échange à sursis, majoré des soultes reçues et minoré des fractions de capital initial.  
Cette valeur est calculée automatiquement par le portail impots.gouv.fr. Vous n'avez pas besoin de la ressaisir manuellement, vous vérifiez simplement qu'elle correspond à la valeur affichée par le site.  

**220 — Plus ou moins-value brute**  
Calculé selon la formule officielle : prix de cession − (prix total d'acquisition × prix de cession / valeur globale du portefeuille).  

{format_money(gain_value)}  
"""
                )

                st.info(
                    "Ne confondez pas « prix de vente » et « prix d'achat ». La case 213 est uniquement ce que vous avez reçu aujourd'hui, pas ce que vous avez payé à l'époque."
                )

                st.success(
                    "La partie 3 du formulaire 2086 est calculée automatiquement par le portail impots.gouv.fr ; vous vérifiez simplement que les valeurs présentées sont conformes aux résultats de cet assistant."
                )

        df["NET REÇU (€)"] = df["TOTAL CESSION (€)"] - df["FRAIS (€)"]
        df["GAIN/PERTE NETTE (€)"] = df["TOTAL CESSION (€)"] - df["PRIX ACQ. UNIT. (€)"] * df["QUANTITÉ"]

        st.markdown(
            "_Si vous rectifiez une erreur de saisie, les lignes calculées ci-dessous s'ajustent automatiquement selon vos nouvelles valeurs._"
        )

        total_sales = df["TOTAL CESSION (€)"].sum()
        st.subheader("Volume total de vos cessions")
        st.write(f"Le montant cumulé de vos ventes (somme des lignes 213) s'élève à {total_sales:,.2f} €.")
        if total_sales > 305:
            st.info(
                "Le seuil d'exonération de 305 € étant dépassé, vos plus-values globales seront bien soumises à l'impôt (PFU ou barème)."
            )
        else:
            st.info(
                "Le seuil d'exonération de 305 € n'est pas dépassé. Vos plus-values peuvent rester exonérées, mais la déclaration 2086 reste nécessaire si vous avez réalisé des cessions."
            )

        st.markdown(
            """
### 2 — Votre portefeuille crypto ce jour-là
212  
🌍 Valeur de TOUTES vos cryptos à ce moment  

Toutes plateformes confondues, en €, au jour de la vente  

> Attention : cette application ne fournit pas automatiquement la valeur du portefeuille pour chaque date de vente.
> Si vous connaissez la valeur totale de votre portefeuille ce jour-là, utilisez-la pour la case 212.
"""
        )

st.markdown(
    """
### Texte de loi utile
Plus-values de cession d'actifs numériques 3AN et 3BN :

Les plus-values réalisées à compter du 1er janvier 2019 lors de la cession d'actifs numériques ou de droits s'y rapportant, à titre occasionnel par des personnes physiques, directement ou par personne interposée sont imposables au taux de 12,8 % (avec possibilité d'option pour l'imposition au barème progressif en cochant la case 3CN) et soumises aux prélèvements sociaux.

Les actifs numériques comprennent les jetons (représentant, sous forme numérique, un ou plusieurs droits, pouvant être émis, inscrits, conservés ou transférés au moyen d’un dispositif d’enregistrement électronique partagé) et les cryptomonnaies.

Les personnes réalisant des cessions d'actifs numériques dont le montant total n'excède pas 305 € au cours d'une année d'imposition sont exonérées (le dépôt de la déclaration no 2086 est toutefois nécessaire). Les personnes réalisant des cessions dont le montant total excède le seuil de 305 € sont imposées sur l'ensemble des cessions.

La plus-value nette imposable est déterminée après compensation entre les plus-values et moins-values de cessions d'actifs numériques et de droits s'y rapportant réalisées par l'ensemble des membres du foyer fiscal au cours d'une même année d'imposition.

Pour la déclaration 2086, vous ne faites que vérifier les valeurs calculées. La partie 3 du formulaire est traitée automatiquement par le portail impots.gouv.fr : vous n'avez pas à ressaisir ces montants manuellement.

La déclaration 2042-C est celle qui reçoit le total fiscal annuel. En cas de gain net, le montant global est reporté en 3AN ; en cas de perte nette, il est reporté en 3BN.

### Notice officielle 2086
Consultez la notice officielle du formulaire 2086 pour 2026 :
https://www.impots.gouv.fr/sites/default/files/formulaires/2086/2026/2086_5515.pdf

Source notice 2086 : https://www.impots.gouv.fr/sites/default/files/formulaires/2086/2026/2086_5515.pdf
"""
)

st.subheader("Règle d'or des arrondis fiscaux")
st.markdown(
    """
L'administration exige des nombres entiers. La règle est la suivante :

- De ,01 à ,49 : on arrondit à l'euro inférieur (ex : 12,49 € → 12 €).
- De ,50 à ,99 : on arrondit à l'euro supérieur (ex : 12,50 € → 13 €).

L'application calcule avec les valeurs exactes mais affiche en évidence la valeur arrondie que vous devez réellement recopier dans les cases.
"""
)
