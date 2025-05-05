from flask import Flask, request, jsonify, render_template
import requests, json, traceback
import gspread
from oauth2client.service_account import ServiceAccountCredentials
import os

app = Flask(__name__, template_folder="templates")

# —– 1) Globālie
API_KEY = os.environ["API_KEY"]
GEMINI_URL = (
    f"https://generativelanguage.googleapis.com/"
    f"v1/models/gemini-1.5-pro:generateContent?key={API_KEY}"
)

# Google Sheets
SCOPE = [
    "https://spreadsheets.google.com/feeds",
    "https://www.googleapis.com/auth/drive"
]
CREDS = ServiceAccountCredentials.from_json_keyfile_name(
    "/etc/secrets/google-credentials.json",
    SCOPE
)
GC = gspread.authorize(CREDS)
SHEET = GC.open_by_url("https://docs.google.com/spreadsheets/d/1dzvGI_uoFCJuwnhDj64hEmEwimTbLmW0XVfK54LUZRs/edit?gid=0#gid=0")
LAPAS = SHEET.worksheets()


@app.route("/")
def index():
    return render_template("index.html")


@app.route("/gemini", methods=["POST"])
def gemini_chat():
    try:
        # ---- 1) Saņem jautājumu ----
        data      = request.get_json()
        jautajums = data.get("jautajums", "").strip()
        if not jautajums:
            return jsonify({"error": "Nav jautājuma"}), 400

        # ---- 2) Uztaisi `noteikumi` un `saturs` no Sheet ----
        noteikumi_lapa = LAPAS[0]   # piemēram, 1. lapa
        tabula_lapa    = LAPAS[1]   # un 2. lapa
        noteikumi = "\n".join(noteikumi_lapa.col_values(1))
        rows      = tabula_lapa.get_all_values()
        saturs    = "\n".join(["\t".join(r) for r in rows])

        # ---- 3) Sagatavo prompt teksta stringu ----
        prompt = (
            f"Tavs uzdevums ir noteikt cenu drukai, balstoties uz piemēriem un tabulu.\n"
            f"Noteikumi:\n{noteikumi}\n\n"
            f"Tabulas:\n{saturs}\n\n"
            f"Jautājums: {jautajums}"
        )

        # ---- 4) Payload ----
        payload = {
            "contents": [
                {"parts": [{"text": prompt}]}
            ]
        }

        # ---- 5) Zvani Gemini API ----
        resp = requests.post(GEMINI_URL, json=payload)
        if resp.status_code != 200:
            return jsonify({
                "error": f"Gemini kļūda: {resp.status_code}",
                "detail": resp.text
            }), 502

        # ---- 6) Iegūsti atbildi ----
        cand = resp.json().get("candidates", [])
        if not cand:
            return jsonify({"error": "Nav atbilžu no Gemini"}), 502
        atbilde = cand[0]["content"]["parts"][0]["text"]

        # ---- 7) Atgriež gala rezultātu ----
        return jsonify({"atbilde": atbilde})

    except Exception as e:
        # Izmet pilnu traceback Render logā
        print("❌ Exception in /gemini ❌")
        traceback.print_exc()
        # Atgriež JSON ar kļūdas tekstu front-endam
        return jsonify({"error": str(e)}), 500


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5050, debug=True)
