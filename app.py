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

# Load and clean the 'digitāldruka' sheet from the workbook
app.logger.debug(f"Loading raw sheet '{sheet_name}' from: {PRICE_SHEET_URL}")
raw_df = pd.read_excel(PRICE_SHEET_URL, sheet_name=sheet_name, header=None, engine="openpyxl")

# Identify header row where second column equals 'Skaits'
header_idx = raw_df.index[raw_df.iloc[:,1] == 'Skaits'].tolist()
if not header_idx:
    app.logger.error("Header row with 'Skaits' not found in sheet")
    raise SystemExit("Cannot locate header row in digitāldruka sheet.")
header_row = header_idx[0]
config_row = header_row + 1

# Extract column ranges from the header row (from third column onwards)
ranges = raw_df.iloc[header_row, 2:].astype(str).tolist()

# Build cleaned price_df from subsequent row
records = []
mode_names = raw_df.iloc[config_row, 1:].astype(str).tolist()
for idx, mode in enumerate(mode_names, start=1):
    prices = raw_df.iloc[config_row, 2+idx-1]
# Actually iterate per range
for col_idx, mode in enumerate(raw_df.iloc[config_row,1:].astype(str), start=1):
    price_vals = raw_df.iloc[config_row, col_idx+1]
# Simplify: use previous logic as function
records = []
for col_idx, rng in enumerate(ranges, start=2):
    for row_offset in header_idx:
        # use only config_row
        break
# Let's implement correctly
records = []
# Single config row expected: header_row for ranges, config_row for prices
for col_idx, qty_range in enumerate(ranges, start=2):
    minq, maxq = qty_range.split('–') if '–' in qty_range else (qty_range, '')
    for r in [config_row]:
        mode = str(raw_df.iloc[r,1]).strip()
        price = raw_df.iloc[r, col_idx]
        records.append({
            'MinQty': minq.strip(),
            'MaxQty': maxq.strip(),
            'Mode': mode,
            'UnitPrice': price
        })
price_df = pd.DataFrame(records)

# Convert columns to numeric and set MaxQty infinity
price_df['MinQty'] = pd.to_numeric(price_df['MinQty'], errors='coerce')
price_df['MaxQty'] = pd.to_numeric(price_df['MaxQty'], errors='coerce').fillna(float('inf'))
price_df['UnitPrice'] = pd.to_numeric(price_df['UnitPrice'], errors='coerce')

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
