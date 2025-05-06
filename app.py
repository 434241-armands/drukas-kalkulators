from flask import Flask, request, jsonify, render_template
import os
import json
import logging
import requests
import gspread
from oauth2client.service_account import ServiceAccountCredentials

# --- Konfigurācija un autentifikācija -----------------------------------------
logging.basicConfig(level=logging.DEBUG)

# 1. Google Sheets autentifikācija
SCOPE      = [
    "https://spreadsheets.google.com/feeds",
    "https://www.googleapis.com/auth/drive",
]
CREDS_PATH = "/etc/secrets/google-credentials.json"  # Render Secret Files mount
creds      = ServiceAccountCredentials.from_json_keyfile_name(CREDS_PATH, SCOPE)
gc         = gspread.authorize(creds)

# 2. Load API key un modelis
API_KEY    = os.environ.get("API_KEY")
if not API_KEY:
    raise RuntimeError("VIDES MAINĪGAIS API_KEY NAV IESTATĪTS!")
MODEL      = os.environ.get("MODEL", "models/gemini-1.5-pro")
GENERATE_URL = f"https://generativelanguage.googleapis.com/v1/{MODEL}:generateContent?key={API_KEY}"

# 3. Load Google Sheet ID
SHEET_ID   = os.environ.get("SHEET_ID")
if not SHEET_ID:
    raise RuntimeError("VIDES MAINĪGAIS SHEET_ID NAV IESTATĪTS!")

# 4. Atver workbook un parāda pieejamās lapas
workbook = gc.open_by_key(SHEET_ID)
available_tabs = [ws.title for ws in workbook.worksheets()]
logging.debug(f"Available tabs: {available_tabs}")

# 5. Funkcija, lai izvēlētos pareizo lapu pēc jautājuma
def pick_sheet_for(query: str):
    q = query.lower()
    if "kreklu" in q:
        name = "kreklu apdruka"
    elif "papīra" in q or "a4" in q:
        name = "PAPĪRA CENAS"
    else:
        name = "Gemini Promt"
    logging.debug(f"Picking tab for '{query}': {name}")
    return workbook.worksheet(name)

# ------------------------------------------------------------------------------

app = Flask(__name__, template_folder="templates")

@app.route("/")
def index():
    return render_template("index.html")

@app.route("/gemini", methods=["POST"])
def gemini_chat():
    data     = request.get_json() or {}
    question = data.get("jautajums", "").strip()
    if not question:
        return jsonify({"error": "Nav saņemts jautājums"}), 400

    # 1) Izvēlamies tabulu pēc jautājuma satura
    try:
        sheet    = pick_sheet_for(question)
        entries  = sheet.get_all_values()
    except Exception as e:
        logging.error(f"Error loading sheet for '{question}': {e}")
        return jsonify({"error": "Neizdevās piekļūt datiem no Google Sheets"}), 500

    # 2) Veidojam promptu Gemini modelim
    prompt = (
        "Tavs uzdevums ir noteikt cenu drukai, balstoties uz tabulas datiem.\n\n"
        "Tabula:\n" + json.dumps(entries, ensure_ascii=False, indent=2) + "\n\n"
        f"Jautājums: {question}"
    )
    payload = {"contents": [{"parts": [{"text": prompt}]}]}
    logging.debug(f"Payload: {json.dumps(payload, ensure_ascii=False)}")

    # 3) Nosūtām pieprasījumu uz Gemini API
    try:
        resp = requests.post(GENERATE_URL, json=payload)
        logging.debug(f"Gemini response status: {resp.status_code}")
        raw  = resp.json()
        logging.debug(f"Gemini raw response: {json.dumps(raw, ensure_ascii=False)}")
    except Exception as e:
        logging.error(f"Gemini HTTP error: {e}")
        return jsonify({"error": "Kļūda pieprasot atbildi no Gemini modela"}), 502

    if resp.status_code != 200:
        return jsonify({"error": "Gemini kļūda", "detail": raw}), 502

    # 4) Izvelkam atbildi no kandidātiem
    try:
        text = raw["candidates"][0]["content"]["parts"][0]["text"]
    except Exception as e:
        logging.error(f"Failed to parse Gemini response: {e}")
        return jsonify({"error": "Neizdevās apstrādāt Gemini atbildi"}), 500

    return jsonify({"atbilde": text})

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 10000))
    app.run(host="0.0.0.0", port=port)
