import os
import json
import logging
import requests
import gspread
from flask import Flask, request, jsonify, render_template
from oauth2client.service_account import ServiceAccountCredentials

# Initialize Flask app and logger
tls = Flask(__name__, template_folder="templates")
tls.logger.setLevel(logging.DEBUG)

# Load environment variables
API_KEY = os.getenv("API_KEY")
SHEET_ID = os.getenv("SHEET_ID")
if not API_KEY:
    raise RuntimeError("Env var API_KEY nav iestatīts!")
if not SHEET_ID:
    raise RuntimeError("Env var SHEET_ID nav iestatīts!")

# Prepare Gemini URL
MODEL = "models/gemini-1.5-pro"
GENERATE_URL = f"https://generativelanguage.googleapis.com/v1/{MODEL}:generateContent?key={API_KEY}"

# Google Sheets authorization
SCOPE = [
    "https://spreadsheets.google.com/feeds",
    "https://www.googleapis.com/auth/drive"
]
CREDS_PATH = "/etc/secrets/google-credentials.json"
creds = ServiceAccountCredentials.from_json_keyfile_name(CREDS_PATH, SCOPE)
gc = gspread.authorize(creds)

# Open workbook and worksheet
workbook = gc.open_by_key(SHEET_ID)
tls.logger.debug("Available tabs: %r", [ws.title for ws in workbook.worksheets()])
TAB_NAME = "Gemini Promt"
worksheet = workbook.worksheet(TAB_NAME)
tls.logger.debug("Loaded worksheet: %s", worksheet.title)

@tls.route("/")
def index():
    return render_template("index.html")

@tls.route("/gemini", methods=["POST"])
def gemini_chat():
    try:
        data = request.get_json(force=True) or {}
        jautajums = data.get("jautajums", "").strip()
        if not jautajums:
            return jsonify({"error": "Nav saņemts jautājums"}), 400

        # Read sheet entries
        entries = worksheet.get_all_values()
        tls.logger.debug("Sheet entries: %r", entries)

        # Build prompt text
        tekst = (
            f"Tavs uzdevums ir noteikt cenu drukai, balstoties uz tabulas datiem.\n\n"
            f"Tabula:\n{json.dumps(entries, ensure_ascii=False, indent=2)}\n\n"
            f"Jautājums: {jautajums}"
        )
        tls.logger.debug("Prompt text:\n%s", tekst)

        # Build Gemini payload
        payload = {
            "contents": [
                {"parts": [{"text": tekst}]}
            ]
        }
        tls.logger.debug("Payload: %s", json.dumps(payload, ensure_ascii=False))

        # Send request to Gemini
        r = requests.post(GENERATE_URL, json=payload, timeout=30)
        tls.logger.debug("Gemini response status: %s", r.status_code)
        tls.logger.debug("Gemini raw response: %s", r.text)

        if r.status_code != 200:
            return jsonify({"error": f"Gemini kļūda: {r.status_code}"}), 502

        resp_json = r.json()
        candidates = resp_json.get("candidates", [])
        if not candidates:
            return jsonify({"error": "Nav kandidātu atbilžu"}), 502

        content = candidates[0].get("content", {})
        parts = content.get("parts", [])
        if not parts:
            return jsonify({"error": "Neatrasta atbilžu daļa"}), 502

        atbilde = parts[0].get("text", "").strip()
        return jsonify({"atbilde": atbilde})

    except Exception as e:
        tls.logger.exception("Neizdevās apstrādāt /gemini pieprasījumu")
        return jsonify({"error": "Servera kļūda", "detail": str(e)}), 500

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5050))
    tls.run(host="0.0.0.0", port=port)
