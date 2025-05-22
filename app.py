import os
import logging
import pandas as pd
import requests
from flask import Flask, request, jsonify

app = Flask(__name__)
logging.basicConfig(level=logging.DEBUG)

# Gemini API endpoint and key
GEMINI_URL = os.getenv("GEMINI_URL")
API_KEY = os.getenv("API_KEY")

# Public Google Sheets export URL (CSV or XLSX)
# CSV example: .../pub?gid=...&single=true&output=csv
# XLSX example: .../export?format=xlsx&gid=...
PRICE_SHEET_URL = os.getenv("PRICE_SHEET_URL")
SHEET_NAME = os.getenv("SHEET_NAME", "digitāldruka")

# Validate environment variables
if not GEMINI_URL or not API_KEY:
    logging.error("GEMINI_URL and API_KEY must be set")
    raise SystemExit("Missing GEMINI_URL or API_KEY environment variables")
if not PRICE_SHEET_URL:
    logging.error("PRICE_SHEET_URL must be set")
    raise SystemExit("Missing PRICE_SHEET_URL environment variable")

# Load price data
logging.debug(f"Loading price data from: {PRICE_SHEET_URL}")
if "output=csv" in PRICE_SHEET_URL:
    # Simple CSV with headers: MinQty,MaxQty,Mode,UnitPrice
    price_df = pd.read_csv(PRICE_SHEET_URL)
elif "export?format=xlsx" in PRICE_SHEET_URL:
    # Excel export: read raw sheet to detect header row
    raw_df = pd.read_excel(
        PRICE_SHEET_URL,
        sheet_name=SHEET_NAME,
        header=None,
        engine="openpyxl"
    )
    # Identify header row by matching 'Skaits' in second column
    header_rows = raw_df.index[raw_df.iloc[:,1].astype(str).str.strip() == 'Skaits'].tolist()
    if not header_rows:
        logging.error("Could not find header row with 'Skaits'")
        raise SystemExit("Header row with 'Skaits' not found in sheet")
    header_row = header_rows[0]
    config_row = header_row + 1
    # Extract quantity ranges and mode names
    ranges = raw_df.iloc[header_row, 2:].astype(str).tolist()
    modes = raw_df.iloc[config_row, 1:].astype(str).tolist()
    # Build structured DataFrame
    records = []
    for idx, qty_range in enumerate(ranges, start=2):
        if '–' in qty_range:
            minq, maxq = [q.strip() for q in qty_range.split('–',1)]
        else:
            minq, maxq = qty_range.strip(), ''
        mode = modes[idx-2]
        price = raw_df.iat[config_row, idx]
        if pd.isna(price):
            continue
        records.append({'MinQty': minq, 'MaxQty': maxq, 'Mode': mode, 'UnitPrice': price})
    price_df = pd.DataFrame(records)
else:
    logging.error("PRICE_SHEET_URL must include either 'output=csv' or 'export?format=xlsx'")
    raise SystemExit("PRICE_SHEET_URL format not recognized: must be CSV or XLSX export URL")

# Convert columns to numeric and handle missing MaxQty as infinity
to_numeric = lambda col: pd.to_numeric(price_df[col], errors='coerce')
price_df['MinQty'] = to_numeric('MinQty')
price_df['MaxQty'] = to_numeric('MaxQty').fillna(float('inf'))
price_df['UnitPrice'] = to_numeric('UnitPrice')

# Validate required columns
for col in ['MinQty','MaxQty','Mode','UnitPrice']:
    if col not in price_df.columns:
        logging.error(f"Column '{col}' missing in parsed data")
        raise SystemExit(f"Missing column: {col}")

# Prepare CSV snippet for system prompt
digital_csv = price_df.to_csv(index=False)

@app.route("/gemini", methods=["POST"])
def gemini():
    data = request.get_json(force=True)
    question = data.get('question','').strip()
    if not question:
        return jsonify({'error':'No question provided'}), 400

    system_prompt = (
        "Tu esi precīzs digitālās drukas cenu kalkulators.\n"
        "Izmanto šo cenu tabulu (EUR par A3 loksni):\n\n"
        + digital_csv +
        "\nAprēķina soļi:\n"
        "1) No jautājuma izvelk daudzumu (qty).\n"
        "2) Atrod rindu, kur MinQty ≤ qty ≤ MaxQty un Mode atbilst.\n"
        "3) Aprēķina: total = qty × UnitPrice.\n"
        "4) Atbild: 'Cena: XX.XX EUR (Y.YYY EUR/gab.)' ar 2 decimālpunktiem.\n"
    )
    messages = [
        {'role':'system','content':system_prompt},
        {'role':'user','content':question}
    ]

    headers = {'Authorization':f"Bearer {API_KEY}", 'Content-Type':'application/json'}
    payload = {'model':'gemini-advanced', 'messages':messages, 'temperature':0.0}
    try:
        resp = requests.post(GEMINI_URL, headers=headers, json=payload, timeout=30)
        resp.raise_for_status()
        answer = resp.json()['choices'][0]['message']['content'].strip()
        return jsonify({'answer':answer})
    except Exception as e:
        logging.exception("Gemini API call failed")
        return jsonify({'error':'Server error','detail':str(e)}), 500

if __name__ == "__main__":
    port = int(os.getenv('PORT',5050))
    app.run(host='0.0.0.0', port=port)
