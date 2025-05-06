import os, json, logging
import requests
import gspread
from flask import Flask, request, jsonify, render_template
from oauth2client.service_account import ServiceAccountCredentials

# ––––––––––––––––––––––––––––––––––––––––––––––––––––––––––––––––––––––––––  
# 1) Flask un logger
# ––––––––––––––––––––––––––––––––––––––––––––––––––––––––––––––––––––––––––
app = Flask(__name__, template_folder="templates")
app.logger.setLevel(logging.DEBUG)

# ––––––––––––––––––––––––––––––––––––––––––––––––––––––––––––––––––––––––––  
# 2) Ielādē vides mainīgos
# ––––––––––––––––––––––––––––––––––––––––––––––––––––––––––––––––––––––––––
API_KEY  = os.getenv("API_KEY", "")
SHEET_ID = os.getenv("SHEET_ID", "")

if not API_KEY:
    raise RuntimeError("Env var API_KEY nav iestatīts!")
if not SHEET_ID:
    raise RuntimeError("Env var SHEET_ID nav iestatīts!")

MODEL        = "models/gemini-1.5-pro"
GENERATE_URL = f"https://generativelanguage.googleapis.com/v1/{MODEL}:generateContent?key={API_KEY}"

# ––––––––––––––––––––––––––––––––––––––––––––––––––––––––––––––––––––––––––  
# 3) Google Sheets autorizācija (vienreiz)
# ––––––––––––––––––––––––––––––––––––––––––––––––––––––––––––––––––––––––––
SCOPE      = ["https://spreadsheets.google.com/feeds","https://www.googleapis.com/auth/drive"]
CREDS_PATH = "/etc/secrets/google-credentials.json"  # tālāk render secret file
creds      = ServiceAccountCredentials.from_json_keyfile_name(CREDS_PATH, SCOPE)
gc         = gspread.authorize(creds)

workbook   = gc.open_by_key(SHEET_ID)
app.logger.debug("Available tabs: %r", [ws.title for ws in workbook.worksheets()])

# Precīzs TAB nosaukums (jāpārkopē no loga!)
TAB_NAME   = "Gemini Promt"
worksheet  = workbook.worksheet(TAB_NAME)
app.logger.debug("Loaded worksheet: %s", worksheet.title)

# ––––––––––––––––––––––––––––––––––––––––––––––––––––––––––––––––––––––––––  
# 4) Index lapa
# ––––––––––––––––––––––––––––––––––––––––––––––––––––––––––––––––––––––––––
@app.route("/")
def index():
    return render_template("index.html")

# ––––––––––––––––––––––––––––––––––––––––––––––––––––––––––––––––––––––––––  
# 5) Gemini endpoint ar pilnu debug
# ––––––––––––––––––––––––––––––––––––––––––––––––––––––––––––––––––––––––––
@app.route("/gemini", methods=["POST"])
def gemini_chat():
    try:
        data      = request.get_json(force=True) or {}
        jautajums = data.get("jautajums", "").strip()
        if not jautajums:
            return jsonify({"error":"Nav saņemts jautājums"}), 400

        # 5a) nolasām Google Sheet
        entries = worksheet.get_all_values()
        app.logger.debug("Sheet entries: %r", entries)

        # 5b) saliekam promptu
        tekst = (
            f"Tavs uzdevums ir noteikt cenu drukai...\n\n"
            f"Google Tabulas dati:\n{json.dumps(entries, ensure_ascii=False, indent=2)}\n\n"
            f"Jautājums: {jautajums}"
        )
        app.logger.debug("Prompt:\n%s", tekst)

        # 5c) sūtām uz Gemini
        payload  = {"contents":[{"parts":[{"text": tekst}]}]}
        resp     = requests.post(GENERATE_URL, json=payload, timeout=30)
        app.logger.debug("Gemini HTTP %s: %s", resp.status_code, resp.text)

        if resp.status_code != 200:
            return jsonify({"error":f"Gemini kļūda: {resp.status_code}"}), 502

        j = resp.json()
        candidate = j["candidates"][0]["parts"][0]["text"]
        return jsonify({"atbilde": candidate})

    except Exception as e:
        app.logger.exception("Neizdevās apstrādāt /gemini pieprasījumu")
        return jsonify({"error":"Servera kļūda","detail":str(e)}), 500

# ––––––––––––––––––––––––––––––––––––––––––––––––––––––––––––––––––––––––––  
if __name__=="__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 5050)), debug=False)
