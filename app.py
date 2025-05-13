import os
import json
import logging
import requests
import gspread
from flask import Flask, request, jsonify, render_template
from oauth2client.service_account import ServiceAccountCredentials

# Initialize Flask app and logger
app = Flask(__name__, template_folder="templates")
app.logger.setLevel(logging.DEBUG)

# Load environment variables
API_KEY             = os.getenv("API_KEY")
SHEET_ID            = os.getenv("SHEET_ID")
GOOGLE_CREDS_JSON   = os.getenv("GOOGLE_SERVICE_ACCOUNT_JSON")  # JSON string
CREDS_PATH          = "/etc/secrets/google-credentials.json"     # fallback path

# Validate env vars
if not API_KEY:
    raise RuntimeError("Env var API_KEY nav iestatīts!")
if not SHEET_ID:
    raise RuntimeError("Env var SHEET_ID nav iestatīts!")
if not GOOGLE_CREDS_JSON and not os.path.exists(CREDS_PATH):
    raise RuntimeError("Nav pieejami Google credentials! Iestatiet GOOGLE_SERVICE_ACCOUNT_JSON vai mountējiet failu.")

# Prepare Gemini URL
MODEL        = "models/gemini-1.5-pro"
GENERATE_URL = f"https://generativelanguage.googleapis.com/v1/{MODEL}:generateContent?key={API_KEY}"

# Google Sheets authorization
SCOPE = [
    "https://spreadsheets.google.com/feeds",
    "https://www.googleapis.com/auth/drive",
]
if GOOGLE_CREDS_JSON:
    creds_dict = json.loads(GOOGLE_CREDS_JSON)
    creds      = ServiceAccountCredentials.from_json_keyfile_dict(creds_dict, SCOPE)
else:
    creds      = ServiceAccountCredentials.from_json_keyfile_name(CREDS_PATH, SCOPE)
gc = gspread.authorize(creds)

# Open workbook and rules worksheet
workbook    = gc.open_by_key(SHEET_ID)
app.logger.debug("Available tabs: %r", [ws.title for ws in workbook.worksheets()])
RULES_SHEET = "Gemini Promt"
rules_ws    = workbook.worksheet(RULES_SHEET)
app.logger.debug("Loaded rules worksheet: %s", rules_ws.title)

@app.route("/")
def index():
    return render_template("index.html")

@app.route("/gemini", methods=["POST"])
def gemini_chat():
    try:
        data      = request.get_json(force=True) or {}
        jautajums = data.get("jautajums", "").strip()
        if not jautajums:
            return jsonify({"error": "Nav saņemts jautājums"}), 400

        # Read up to 5 last examples from sheet: Question, Wrong, Correct
        values   = rules_ws.get_all_values()
        examples = []
        for row in values:
            if len(row) >= 5:
                q, wrong, correct = row[2].strip(), row[3].strip(), row[4].strip()
                if q and wrong and correct:
                    examples.append({"q": q, "wrong": wrong, "correct": correct})
        examples = examples[-5:]

        # Build prompt
        prompt_lines = [
            "Tavs uzdevums: analizēt jautājumu un dot pareizu drukas cenu.",
            "Izmanto vienīgi tabulas datus un mūsu piemērus—nedod nekādas atrunas!",
            "Šeit vairāki piemēri (jautājums → kļūdaina atbilde → pareiza atbilde):"
        ]
        for ex in examples:
            prompt_lines.append(
                f"Q: {ex['q']}\nWrong: {ex['wrong']}\nCorrect: {ex['correct']}"
            )
        prompt_lines.append(f"Jauns jautājums: {jautajums}")
        prompt_text = "\n\n".join(prompt_lines)
        app.logger.debug("Built prompt (len %d):\n%s", len(prompt_text), prompt_text)

        # Send to Gemini
        payload = {"contents": [{"parts": [{"text": prompt_text}]}]}
        app.logger.debug("Sending payload: %s", json.dumps(payload)[:200])
        r = requests.post(GENERATE_URL, json=payload, timeout=15)
        app.logger.debug("Gemini status %s, raw: %s", r.status_code, r.text)

        if r.status_code != 200:
            return jsonify({"error": f"Gemini kļūda: {r.status_code}"}), 502

        resp_json   = r.json()
        cands       = resp_json.get("candidates", [])
        if not cands:
            return jsonify({"error": "Nav kandidātu atbilžu"}), 502

        parts = cands[0].get("content", {}).get("parts", [])
        if not parts:
            return jsonify({"error": "Neatrasta atbilžu daļa"}), 502

        atbilde = parts[0].get("text", "").strip()
        return jsonify({"atbilde": atbilde})

    except Exception as e:
        app.logger.exception("Error in /gemini")
        return jsonify({"error": "Servera kļūda", "detail": str(e)}), 500

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5050))
    app.run(host="0.0.0.0", port=port)
