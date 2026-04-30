import streamlit as st
from core.engine import calculate_taxes  # Import propre depuis ton dossier core
from core.parsers import parse_csv

st.title("🛡️ Eisphora Lite")

uploaded_file = st.file_uploader("Upload exchange CSV", type="csv")

if uploaded_file:
    # 1. Nettoyage des données
    data = parse_csv(uploaded_file)
    
    # 2. Calcul
    results = calculate_taxes(data)
    
    # 3. Affichage
    st.metric("Total Gains", f"{results['gains']} €")
    st.dataframe(data)