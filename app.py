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
    data     = request.get_json() or {}
    jautajums = data.get("jautajums", "").strip()
    if not jautajums:
        return jsonify({"error": "Nav saņemts jautājums"}), 400

    # 1) Sagatavo Gemini payload
    payload = {
        "model": MODEL,
        "prompt": jautajums,
        # ... vēl atbilstoši Gemini API fieldu nosaukumi, ja tev ir
        # “generateContent” vai cita struktūra, tad pielāgo šeit
    }

    # 2) Sūti pieprasījumu
    r = requests.post(GENERATE_URL, json=payload)
    app.logger.debug("===== GEMINI RAW RESPONSE =====\n%s", r.text)

    # 3) Parsē JSON
    try:
        resp_json = r.json()
    except ValueError:
        return jsonify({"error": "Gemini atbilde nav derīgs JSON"}), 502

    app.logger.debug("===== GEMINI HTTP %s: %s", r.status_code, json.dumps(resp_json, ensure_ascii=False))

    # 4) Izvelc kandidātus
    cands = resp_json.get("candidates", [])
    if not cands:
        return jsonify({"error": f"Gemini kļūda: {r.status_code}"}), 502

    # 5) Iekš content → parts
    content = cands[0].get("content", {})
    parts   = content.get("parts", [])
    if not parts:
        return jsonify({"error": "Gemini neatgrieza atbilžu daļu"}), 502

    atbilde = parts[0].get("text", "").strip()
    return jsonify({"atbilde": atbilde})

# ––––––––––––––––––––––––––––––––––––––––––––––––––––––––––––––––––––––––––  
if __name__=="__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 5050)), debug=False)
