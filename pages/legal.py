import streamlit as st

st.set_page_config(
    page_title="Mentions légales - Eisphora",
    page_icon="⚖️",
    layout="wide",
)

st.title("⚖️ Mentions légales")

st.header("Avertissement légal")
st.write(
    "Eisphora est un outil de simulation open source fourni à titre purement indicatif."
)

st.subheader("Pas de Conseil Fiscal")
st.write(
    "L'utilisation de cet outil ne constitue en aucun cas un conseil fiscal, juridique ou financier. "
    "L'auteur n'est pas un expert-comptable ni un conseiller en investissements financiers (CIF)."
)

st.subheader("Projet de recherche et transparence logicielle")
st.write(
    "Eisphora est un projet de recherche et de transparence logicielle. Contrairement aux plateformes "
    "SaaS commerciales, Eisphora ne stocke aucune donnée, ne propose pas d'accompagnement personnalisé "
    "et ne gère pas la synchronisation automatique par API des plateformes d'échange."
)

st.header("🔐 Protection des données (RGPD)")

st.write("**Zéro Persistance** : Aucune donnée personnelle ou financière n'est stockée sur nos serveurs.")
st.write(
    "**Traitement en Mémoire** : Vos fichiers CSV sont traités uniquement dans la mémoire vive (RAM) "
    "de l'application pendant la durée de la session et sont instantanément effacés après le rendu du calcul."
)
st.write("**Pas de Cookies** : Nous n'utilisons aucun traceur publicitaire ou analytique intrusif.")
st.write(
    "**Conformité RGPD** : Cette application est conçue pour minimiser les données traitées et respecter le principe de "
    "protection des données personnelles. Veuillez vérifier la conformité spécifique à votre usage et à votre déploiement en Europe."
)

st.header("Responsabilité de l'utilisateur")

st.write(
    "Vous êtes seul responsable de l'exactitude des données importées et de vos déclarations auprès de "
    "l'administration fiscale (Direction Générale des Finances Publiques)."
)

st.write(
    "Vérification nécessaire : Les calculs de plus-values crypto sont complexes. Nous vous recommandons "
    "vivement de vérifier les résultats avec un professionnel ou de consulter la documentation officielle "
    "(Bulletin Officiel des Finances Publiques - BOFiP) avant toute télédéclaration."
)

st.header("Absence de garantie")

st.write(
    'L\'outil est fourni "en l\'état", sans garantie d\'aucune sorte quant à l\'exactitude, l\'exhaustivité ou '
    'l\'adéquation aux évolutions législatives récentes (ex: Loi de Finances 2026).'
)
