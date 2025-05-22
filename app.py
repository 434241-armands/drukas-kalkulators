import os
import re
import logging
import pandas as pd
import requests
from flask import Flask, request, jsonify

app = Flask(__name__)
app.logger.setLevel(logging.DEBUG)

# Gemini un Google Sheets iestatījumi
GEMINI_URL      = os.getenv("GEMINI_URL", "")
API_KEY         = os.getenv("API_KEY", "")
PRICE_SHEET_URL = os.getenv("PRICE_SHEET_URL", "")

if not PRICE_SHEET_URL:
    app.logger.error("Nav iestatīts vides mainīgais PRICE_SHEET_URL")
    raise SystemExit("Nenodrošināts PRICE_SHEET_URL")

# Nolasa cenu tabulu — atkarībā no formāta
app.logger.debug(f"Ielādēju cenas no: {PRICE_SHEET_URL}")
if PRICE_SHEET_URL.endswith("output=csv"):
    price_df = pd.read_csv(PRICE_SHEET_URL)
elif PRICE_SHEET_URL.endswith("output=xlsx") or PRICE_SHEET_URL.endswith("format=xlsx"):
    price_df = pd.read_excel(PRICE_SHEET_URL, engine="openpyxl")
else:
    # mēģinām CSV pēc noklusējuma
    try:
        price_df = pd.read_csv(PRICE_SHEET_URL)
    except Exception:
        price_df = pd.read_excel(PRICE_SHEET_URL, engine="openpyxl")

# Konvertē ciparu kolonnas
for col in ("MinQty", "MaxQty", "UnitPrice"):
    if col in price_df.columns:
        price_df[col] = pd.to_numeric(price_df[col], errors="coerce")
price_df["MaxQty"] = price_df["MaxQty"].fillna(float("inf"))

# Izveido tikai “Digital_Print” vai visu tabulu, ja nav Sheet kolonnas
digital_df = (
    price_df[price_df["Sheet"] == "Digital_Print"]
    if "Sheet" in price_df.columns
    else price_df
)
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
        "1) No lietotāja jautājuma izvelk daudzumu (gab.)\n"
        "2) Atrod rindu, kur MinQty ≤ qty ≤ MaxQty\n"
        "3) Aprēķina cenu: qty × UnitPrice\n"
        "4) Atbild formātā: “Cena: XX.XX EUR (Y.YYY EUR/gab.)”, ar 2 decimālpunktiem.\n"
    )

    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user",   "content": question}
    ]

    headers = {
        "Authorization": f"Bearer {API_KEY}",
        "Content-Type": "application/json"
    }
    payload = {
        "model": "gemini-advanced",
        "messages": messages,
        "temperature": 0.0
    }

    try:
        resp = requests.post(GEMINI_URL, headers=headers, json=payload, timeout=30)
        resp.raise_for_status()
        answer = resp.json()["choices"][0]["message"]["content"].strip()
        return jsonify({"answer": answer})
    except Exception as e:
        app.logger.exception("Kļūda zvanot Gemini AI")
        return jsonify({"error": "Servera kļūda", "detail": str(e)}), 500

if __name__ == "__main__":
    port = int(os.getenv("PORT", 5050))
    app.run(host="0.0.0.0", port=port)
