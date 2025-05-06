import os, json, requests, gspread
from flask import Flask, request, jsonify, render_template
from oauth2client.service_account import ServiceAccountCredentials

app = Flask(__name__, template_folder="templates")

# ———————— 1) Ielādē vides mainīgos un atslēgas ————————
API_KEY    = os.getenv("API_KEY")
MODEL      = "models/gemini-1.5-pro"
GENERATE_URL = f"https://generativelanguage.googleapis.com/v1/{MODEL}:generateContent?key={API_KEY}"

SHEET_ID   = os.getenv("SHEET_ID")
if not SHEET_ID:
    raise RuntimeError("VIDES MAINĪGAIS SHEET_ID NAV IESTATĪTS!")

# ———————— 2) Google Sheets autorizācija ————————
SCOPE      = [
    "https://spreadsheets.google.com/feeds",
    "https://www.googleapis.com/auth/drive"
]
CREDS_PATH = "/etc/secrets/google-credentials.json"  # Secret File mount ceļš
creds      = ServiceAccountCredentials.from_json_keyfile_name(CREDS_PATH, SCOPE)
gc         = gspread.authorize(creds)

# ———————— 3) Atver workbook un worksheet (ješi tikai vienreiz) ————————
workbook   = gc.open_by_key(SHEET_ID)
print(">>> Available tabs:", [ws.title for ws in workbook.worksheets()])   # debug
worksheet  = workbook.worksheet("Gemini Promt")                             # TAB nosaukums *precīzi* tāpat!
print(">>> Loaded worksheet:", worksheet.title)

# ———————— 4) Route definīcija ————————
@app.route("/")
def index():
    return render_template("index.html")

@app.route("/gemini", methods=["POST"])
def gemini_chat():
    data     = request.get_json() or {}
    jautajums= data.get("jautajums", "").strip()
    if not jautajums:
        return jsonify({"error":"Nav saņemts jautājums"}), 400

    # 4a) Nolasām tabulas datus
    entries = worksheet.get_all_values()
    print(">>> Table entries:", entries)

    # 4b) Gatavojam promptu
    tekst = (
        f"Tavs uzdevums ir ...\n\n"
        f"Noteikumi:\n{entries[0]}\n\n"     # piem. pirma rinda
        f"Jautājums: {jautajums}"
    )
    print(">>> PROMPT:\n", tekst)

    # 4c) Sūtām pieprasījumu uz Gemini
    payload  = {
        "contents":[{"parts":[{"text": tekst}]}]
    }
    response = requests.post(GENERATE_URL, json=payload)
    print(">>> Gemini status:", response.status_code)
    print(">>> Gemini raw:", response.text)

    if response.status_code != 200:
        return jsonify({"error":"Gemini kļūda: "+str(response.status_code)}), 500

    try:
        candidate = response.json()["candidates"][0]["parts"][0]["text"]
    except Exception as e:
        print(">>> Parse error:", e)
        return jsonify({"error":"Neizdevās nolasīt atbildi"}), 500

    return jsonify({"atbilde": candidate})

if __name__=="__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT",5050)))
