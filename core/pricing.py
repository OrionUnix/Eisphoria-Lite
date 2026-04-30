# core/pricing.py

import logging
import pandas as pd
import requests
import time

logger = logging.getLogger(__name__)

def get_historical_price(symbol: str, timestamp_str: str, currency: str = "EUR") -> float:
    try:
        date_obj = pd.to_datetime(timestamp_str)
        ts = int(date_obj.timestamp())

        url = "https://min-api.cryptocompare.com/data/v2/histohour"
        params = {
            "fsym": symbol,
            "tsym": currency,
            "limit": 1,
            "toTs": ts,
        }

        r = requests.get(url, params=params, timeout=5)
        data = r.json()

        if data.get("Response") == "Success" and data.get("Data", {}).get("Data"):
            return float(data["Data"]["Data"][-1]["close"])

    except Exception as e:
        logger.debug(f"Price error {symbol}: {e}")

    return 0.0