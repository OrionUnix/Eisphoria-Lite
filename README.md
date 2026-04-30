# 🛡️ Eisphora Lite

> **The Stateless Crypto Tax Showcase.**  
> A lightweight, web-based version of the Eisphora tax engine, built for speed, privacy, and developers.

[![Streamlit App](https://static.streamlit.io/badges/streamlit_badge_black_white.svg)](https://eisphoria-lite.streamlit.app/)

---

## ✨ What it does

Eisphora Lite bridges the gap between complex tax laws and non-technical users. It provides a functional demonstration of our core engine:

*   **Upload your Exchange CSV**: Direct support for Coinbase, Binance, Kraken, and more.
*   **Instant FIFO Calculation**: Automated matching of acquisitions and disposals.
*   **Form 2086 Helper**: See your official French tax form filled line by line.
*   **Tax Optimization**: Compare **PFU (31.4%)** vs. **Barème Progressif** to save money.
*   **Portable Results**: Export your tax summary to PDF or CSV.

---

## 🔒 Privacy & Security

**Stateless Processing**: No data is ever written to disk or stored in a database. Files are processed in the **server's RAM** for the duration of your session only, then discarded. 

*Unlike the full version, this Lite demo does not use persistent encryption because it stores absolutely nothing.*

---

## ⚠️ Limitations

To keep this version lightweight and "stateless", some features are reserved for the main project:
*   **CSV Import Only**: No automated wallet address scanning or API sync.
*   **France Only**: US and Luxembourg jurisdictions are currently in development.
*   **No Persistence**: No user accounts. Your data is wiped as soon as you close the tab.
*   **For Production SaaS**: Check the [Eisphora Main Repo](https://github.com/OrionUnix/Eisphora).

---

## 🛠️ For Developers: The Boilerplate

This repository is a **functional boilerplate** licensed under **BSD-3-Clause**. 

We invite you to **fork it** to build your own alternatives to commercial tools like Waltio or ZenLedger. The code is modular, Python-based, and specifically designed to be extended into a full SaaS product.

---

## 🚀 Quick Start

### Run Locally
```bash
# Clone the repo
git clone https://github.com/OrionUnix/Eisphoria-Lite.git
cd Eisphoria-Lite

# Install dependencies
pip install -r requirements.txt

# Launch Streamlit
streamlit run app.py