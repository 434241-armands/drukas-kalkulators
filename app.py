import os
import re
import logging

import pandas as pd
import requests
from flask import Flask, request, jsonify

app = Flask(__name__)
app.logger.setLevel(logging.DEBUG)

# Gemini API endpoint and key
GEMINI_URL      = os.getenv("GEMINI_URL", "")
API_KEY         = os.getenv("API_KEY", "")

# Public Google Sheets XLSX export URL (ensure it includes /export?format=xlsx)
PRICE_SHEET_URL = os.getenv("PRICE_SHEET_URL", "")

# Validate environment variable
if not PRICE_SHEET_URL:
    app.logger.error("Environment variable PRICE_SHEET_URL is not set.")
    raise SystemExit("PRICE_SHEET_URL is required and must be a Google Sheets export link.")

if "/export?format=xlsx" not in PRICE_SHEET_URL:
    app.logger.error("PRICE_SHEET_URL does not look like an XLSX export URL.")
    raise SystemExit("PRICE_SHEET_URL must include '/export?format=xlsx' for Google Sheets XLSX export.")

# Load all sheets from the workbook
app.logger.debug(f"Loading price data from: {PRICE_SHEET_URL}")
all_sheets = pd.read_excel(PRICE_SHEET_URL, sheet_name=None, engine="openpyxl")

# Name of the sheet that contains digital print prices
sheet_name = "digitāldruka"
if sheet_name not in all_sheets:
    app.logger.error(f"Sheet '{sheet_name}' not found in workbook.")
    raise SystemExit(f"Sheet '{sheet_name}' must exist in the Google Sheets document.")

price_df = all_sheets[sheet_name]

# Ensure required columns exist
required_cols = ["MinQty", "MaxQty", "Mode", "UnitPrice"]
for col in required_cols:
    if col not in price_df.columns:
        app.logger.error(f"Missing column '{col}' in sheet '{sheet_name}'.")
        raise SystemExit(f"Column '{col}' is required in sheet '{sheet_name}'.")

# Convert columns to numeric
price_df["MinQty"]    = pd.to_numeric(price_df["MinQty"], errors="coerce")
price_df["MaxQty"]    = pd.to_numeric(price_df["MaxQty"], errors="coerce").fillna(float("inf"))
price_df["UnitPrice"] = pd.to_numeric(price_df["UnitPrice"], errors="coerce")

# Create CSV string for inclusion in the system prompt
digital_csv = price_df.to_csv(index=False)

@app.route("/gemini", methods=["POST"])
def gemini():
    data = request.get_json(force=True)
    question = data.get("question", "").strip()
    if not question:
        return jsonify({"error": "Please provide a 'question' field"}), 400

    # Construct system prompt
    system_prompt = (
        "Tu esi precīzs digitālās drukas cenu kalkulators.\n"
        "Izmanto tieši šo cenu tabulu (EUR par A3 loksni):\n\n"
        + digital_csv +
        "\nAprēķina soļi:\n"
        "1) No jautājuma izvelk daudzumu (qty).\n"
        "2) Atrod rindu kur MinQty ≤ qty ≤ MaxQty un Mode atbilst.\n"
        "3) Aprēķina: total = qty × UnitPrice.\n"
        "4) Atbild: “Cena: XX.XX EUR (Y.YYY EUR/gab.)” ar 2 decimālpunktiem.\n"
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
        app.logger.exception("Error calling Gemini API")
        return jsonify({"error": "Server error", "detail": str(e)}), 500

if __name__ == "__main__":
    port = int(os.getenv("PORT", 5050))
    app.run(host="0.0.0.0", port=port)
