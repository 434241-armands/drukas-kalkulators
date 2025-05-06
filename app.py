from flask import Flask, request, jsonify, render_template
import os
import json
import requests
import gspread
from oauth2client.service_account import ServiceAccountCredentials

app = Flask(__name__, template_folder="templates")

# 1. Load API key and model identifier
API_KEY = os.environ["API_KEY"]
MODEL   = "models/gemini-1.5-pro"
GENERATE_URL = f"https://generativelanguage.googleapis.com/v1/{MODEL}:generateContent?key={API_KEY}"

# 2. Google Sheets configuration (rules + table)
# 2.1 Nolasām Sheet ID no ENV un pārbaudām
SHEET_ID = os.getenv("SHEET_ID")
if not SHEET_ID:
    raise RuntimeError("VIDES MAINĪGAIS SHEET_ID NAV IESTATĪTS!")

# 2.2 Authorization izmantojot RGeender Secret File
CREDS_PATH = "/etc/secrets/google-credentials.json"
SCOPE      = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
creds      = ServiceAccountCredentials.from_json_keyfile_name(CREDS_PATH, SCOPE)
gc         = gspread.authorize(creds)

# 2.3 Atveram workbook pēc key un konkrēto cilni
wb        = gc.open_by_key(SHEET_ID)
worksheet = wb.worksheet("NRJ CENAS")

@app.route("/")
def index():
    return render_template("index.html")

@app.route("/gemini", methods=["POST"])
def gemini_chat():
    data     = request.get_json() or {}
    jautajums = data.get("jautajums", "").strip()
    if not jautajums:
        return jsonify({"error": "Nav saņemts jautājums"}), 400

    # 3. Build rules and table content
    rows = worksheet.get_all_values()[1:]  # skip header
    noteikumi = []
    tabulas    = []
    for r in rows:
        if len(r) >= 3:
            noteikumi.append(f"❌ {r[0]} → ✅ {r[2]}")
        if len(r) >= 2:
            tabulas.append(f"{r[0]}: {r[1]}")
    noteikumi_str = "\n".join(noteikumi)
    saturs_str    = "\n".join(tabulas)

    # 4. Construct prompt text
    tekst = (
        "Tavs uzdevums ir noteikt cenu drukai, balstoties uz šādiem piemēriem un tabulu.\n\n"
        f"Noteikumi:\n{noteikumi_str}\n\n"
        f"Tabula:\n{saturs_str}\n\n"
        f"Jautājums: {jautajums}"
    )

    payload = {
        "model": MODEL,
        "prompt": {"parts": [{"text": tekst}]},
        "temperature": 0.0,
        "maxOutputTokens": 512
    }

    # --- DEBUG: payload ---
    print("=== GEMINI PAYLOAD ===")
    print(json.dumps(payload, indent=2, ensure_ascii=False))

    response = requests.post(GENERATE_URL, json=payload)

    # --- DEBUG: raw response ---
    print("=== GEMINI RAW RESPONSE ===")
    print(response.status_code, response.text)
    try:
        err = response.json()
        print("=== PARSED JSON ERROR ===")
        print(json.dumps(err, indent=2, ensure_ascii=False))
    except Exception:
        pass

    if response.status_code != 200:
        return jsonify({"error": "Gemini API kļūda", "detail": response.text}), 500

    resp_json = response.json()
    candidates = resp_json.get("candidates", [])
    if not candidates:
        return jsonify({"error": "Nav atbilžu kandidātu"}), 500

    atbilde = candidates[0].get("content", {}).get("parts", [])[0].get("text", "")
    return jsonify({"atbilde": atbilde})

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5050))
    app.run(host="0.0.0.0", port=port)
