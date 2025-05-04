@app.route("/")
def index():
    return render_template("index.html")
from flask import Flask, request, jsonify, render_template
import requests
import gspread
from oauth2client.service_account import ServiceAccountCredentials

app = Flask(__name__, template_folder="templates")

# 🔑 Gemini API atslēga
api_key = "AIzaSyDdmyM4oQfJRy6k0U84DpcDSebRozXGx-s"  # ← šeit ieliec savu pareizo atslēgu

# 🔗 Google Sheet konfigurācija
scope = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
import json
import os

service_account_info = json.loads(os.environ["GOOGLE_SERVICE_ACCOUNT_JSON"])
creds = ServiceAccountCredentials.from_json_keyfile_dict(service_account_info, scope)

client = gspread.authorize(creds)
sheet = client.open_by_url("https://docs.google.com/spreadsheets/d/1dzvGI_uoFCJuwnhDj64hEmEwimTbLmW0XVfK54LUZRs")
lapas = sheet.worksheets()

@app.route("/")
def index():
    return render_template("index.html")

@app.route("/gemini", methods=["POST"])
def gemini_chat():
    # 📌 Nolasa Gemini Promt lapu (noteikumi, piemēri)
    noteikumi_lapa = lapas[-1]  # pieņemam, ka pēdējā lapa ir "Gemini Promt"
    noteikumi_rindas = noteikumi_lapa.get_all_values()[1:]  # skip header
    noteikumi = ""
for i, rinda in enumerate(noteikumi_rindas, start=1):
    if len(rinda) >= 3:
        noteikumi += f"{i}. ❓ {rinda[0]}\n   ❌ {rinda[1]}\n   ✅ {rinda[2]}\n\n"
    dati = request.get_json()
    jautajums = dati.get("jautajums")

    if not jautajums:
        return jsonify({"atbilde": "❗ Nav saņemts jautājums"}), 400

    # ✅ Savāc visus datus no Google Sheet lapām
    saturs = ""
    for lapa in lapas:
        saturs += f"\n--- Lapa: {lapa.title} ---\n"
        rindas = lapa.get_all_values()
        for rinda in rindas:
            saturs += " | ".join(rinda) + "\n"

    # 👇 Izveido pieprasījumu uz Gemini
    url = f"https://generativelanguage.googleapis.com/v1/models/gemini-1.5-pro:generateContent?key={api_key}"
    payload = {
    "contents": [
        {
            "parts": [
                {
                    "text": f"""Tavs uzdevums ir noteikt cenu drukai, balstoties uz šādiem piemēriem un tabulu (skatīt zemāk).
    Lūdzu, ņem vērā dotās kļūdas un pareizās atbildes.

    Noteikumi:
    {noteikumi}

    Tabulas:
    {saturs}

    Jautājums: {jautajums}"""
                    }
                ]
            }
        ]
    }

    print("==== PROMTS ====")
    print(f"{noteikumi}\n\n{saturs}\n\n{jautajums}")
    
    response = requests.post(url, json=payload)
    if response.status_code != 200:
        print("Gemini status:", response.status_code)
        print("Gemini atbilde:", response.text)
        return jsonify({"atbilde": "❌ Gemini kļūda"}), 500


    atbilde = response.json().get("candidates", [{}])[0].get("content", {}).get("parts", [{}])[0].get("text", "Nav atbildes")
    return jsonify({"atbilde": atbilde})

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5050)
