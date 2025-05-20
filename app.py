import os
import re
import logging
import pandas as pd
import requests
from flask import Flask, request, jsonify

app = Flask(__name__)
app.logger.setLevel(logging.DEBUG)

# Gemini konfigurācija
GEMINI_URL      = os.getenv("GEMINI_URL", "")
API_KEY         = os.getenv("API_KEY", "")

# Google Sheets CSV public URL
PRICE_SHEET_URL = os.getenv("PRICE_SHEET_URL", "")
if not PRICE_SHEET_URL:
    app.logger.error("Environment variable PRICE_SHEET_URL is missing")
    raise SystemExit("PRICE_SHEET_URL required")

# Nolasa cenu tabulu tieši no Google Sheets CSV
app.logger.debug(f"Ielādēju cenas no Google Sheets CSV: {PRICE_SHEET_URL}")
price_df = pd.read_csv(PRICE_SHEET_URL)

# Konvertē kolonnas uz skaitliskiem tipiem
for col in ("MinQty", "MaxQty", "UnitPrice"):
    price_df[col] = pd.to_numeric(price_df[col], errors="coerce")
price_df["MaxQty"] = price_df["MaxQty"].fillna(float("inf"))

# Izvēlamies tikai digitālās drukas datus
digital_df = price_df[price_df["Sheet"] == "Digital_Print"] if "Sheet" in price_df else price_df
digital_csv = digital_df.to_csv(index=False)

@app.route("/gemini", methods=["POST"])
def gemini():
    data = request.get_json(force=True)
    question = data.get("question", "").strip()
    if not question:
        return jsonify({"error": "Nav jautājuma laukā `question`"}), 400

    system_prompt = (
        "Tu esi precīzs digitālās drukas cenu kalkulators. "
        "Izmanto šo cenu tabulu (EUR par A3 loksni):\n\n"
        + digital_csv +
        "\nAprēķina soļi:\n"
        "1) Izvelk daudzumu (gab.) no jautājuma\n"
        "2) Izvēlas rindu kur MinQty ≤ qty ≤ MaxQty\n"
        "3) Aprēķina: qty × UnitPrice\n"
        "4) Atbild formātā: “Cena: XX.XX EUR (Y.YYY EUR/gab.)” ar 2 dec.\n"
    )
    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user",   "content": question}
    ]

    headers = {
        "Authorization": f"Bearer {API_KEY}",
        "Content-Type": "application/json"
    }
    payload = {"model": "gemini-advanced", "messages": messages, "temperature": 0.0}
    resp = requests.post(GEMINI_URL, headers=headers, json=payload, timeout=30)
    resp.raise_for_status()
    answer = resp.json()["choices"][0]["message"]["content"].strip()

    return jsonify({"answer": answer})

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.getenv("PORT", 5050)))
