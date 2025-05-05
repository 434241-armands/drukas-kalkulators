from flask import Flask, request, jsonify, render_template
import requests
import json
import traceback
import gspread
from oauth2client.service_account import ServiceAccountCredentials
import os

app = Flask(__name__, template_folder="templates")

# —– 1) Globālie objekti —–
api_key = os.environ["API_KEY"]  # vai kā tu to noliki
url = f"https://generativelanguage.googleapis.com/v1/models/gemini-1.5-pro:generateContent?key={api_key}"

# Google Sheets credentials
scope = [
    "https://spreadsheets.google.com/feeds",
    "https://www.googleapis.com/auth/drive"
]
creds = ServiceAccountCredentials.from_json_keyfile_name(
    "/etc/secrets/google-credentials.json",
    scope
)
client = gspread.authorize(creds)
sheet = client.open_by_url("TAVS_SHEET_URL")
lapas = sheet.worksheets()

@app.route("/")
def index():
    return render_template("index.html")

@app.route("/gemini", methods=["POST"])
def gemini_chat():
    try:
        # — 1) Saņem jautājumu no front-end
        data      = request.get_json()
        jautajums = data.get("jautajums", "").strip()
        if not jautajums:
            return jsonify({"error": "Nav jautājuma"}), 400

        # — 2) Uztaisi noteikumu un tabulu strings no Google Sheet
        #    Pieņemsim, ka pirmajā lapā ir tabula, otrajā ir noteikumi utt.
        noteikumi_lapa = lapas[0]
        tabula_lapa    = lapas[1]
        # Izveido noteikumu stringu (piemēram, apvieno visu kolonnas A saturu):
        noteikumi = "\n".join(noteikumi_lapa.col_values(1))
        # Izveido tabulas stringu (piem., katra rinda ar tabulatoru):
        rows = tabula_lapa.get_all_values()
        saturs = "\n".join(["\t".join(r) for r in rows])

        # — 3) Saliek pilnu prompt tekstu
        tekst = (
            f"Tavs uzdevums ir noteikt cenu drukai, balstoties uz šādiem piemēriem un tabulu.\n"
            f"Lūdzu, ņem vērā kļūdas un pareizās atbildes.\n\n"
            f"Noteikumi:\n{noteikumi}\n\n"
            f"Tabulas:\n{saturs}\n\n"
            f"Jautājums: {jautajums}"
        )

        # — 4) Sagatavo payload
        payload = {
            "contents": [
                {
                    "parts": [
                        {"text": tekst}
                    ]
                }
            ]
        }

        # — 5) Sūti pieprasījumu uz Gemini API
        response = requests.post(url, json=payload)
        if response.status_code != 200:
            return jsonify({"error": f"Gemini kļūda: {response.status_code}"}), 502

        # — 6) Izvelk atbildi no API JSON
        candidates = response.json().get("candidates", [])
        if not candidates:
            return jsonify({"error": "Nav atbilžu no Gemini"}), 502

        atbilde = candidates[0]\
            .get("content", {})\
            .get("parts", [])[0]\
            .get("text", "")

        # — 7) Atgriež back-front
        return jsonify({"atbilde": atbilde})

    except Exception as e:
        # Izmet traceback Render logs
        print("❌ GEMINI HANDLER ERROR ❌")
        traceback.print_exc()
        return jsonify({"error": str(e)}), 500

if __name__ == "__main__":
    # debug=True lokāli, bet Render var darboties arī bez tā
    app.run(host="0.0.0.0", port=5050, debug=True)
