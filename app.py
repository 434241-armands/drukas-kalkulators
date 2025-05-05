from flask import Flask, request, jsonify, render_template
import requests
import json
import gspread
from oauth2client.service_account import ServiceAccountCredentials
import os

app = Flask(__name__, template_folder="templates")

# ────── 1) Globālie objekti ──────
api_key = os.environ.get("API_KEY") or "tavs-api-key"
url     = f"https://generativelanguage.googleapis.com/v1/models/gemini-1.5-pro:generateContent?key={api_key}"

scope = [
  "https://spreadsheets.google.com/feeds",
  "https://www.googleapis.com/auth/drive"
]

creds  = ServiceAccountCredentials.from_json_keyfile_name(
  "/etc/secrets/google-credentials.json",
  scope
)
client = gspread.authorize(creds)

# ────── 2) Tavs endpoint ──────
@app.route("/", methods=["GET"])
def index():
    return render_template("index.html")
  
@app.route("/gemini", methods=["POST"])
def gemini_chat():
    data     = request.get_json()
    jautajums= data.get("jautajums", "")

    # … šeit iet tava loģika: nolasīt Google Sheet, sakraut `noteikumi` un `saturs` …

    payload = {
      "contents":[
        {"parts":[{"text": tekst}]}  # kur `tekst` ir saliktā prompta string
      ]
    }

    # ── Debug print ──
    print("===== GEMINI PAYLOAD =====")
    print(json.dumps(payload, indent=2, ensure_ascii=False))

    # ── Calls ──
    response = requests.post(url, json=payload)

    # ── Debug print atbilde ──
    print("===== GEMINI RAW RESPONSE =====")
    print("Status:", response.status_code)
    print(response.text)
    try:
        print("Parsed JSON:", json.dumps(response.json(), indent=2, ensure_ascii=False))
    except:
        print("Response not JSON.")

    # ── Gala atbilde ──
    cand = response.json().get("candidates", [{}])[0]
    text= cand.get("content", {}).get("parts", [])[0].get("text", "Nav atbildes")
    return jsonify({"atbilde": text})

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5050)
api_key = "AIzAsSyDdmqY40qJrY6k8U04DpCsBEboRzXGx-s"

scope = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]

# 🔑 Izmanto Render Secret File ar Google servisa konta atslēgu
creds = ServiceAccountCredentials.from_json_keyfile_name(
    "/etc/secrets/google-credentials.json",
    scope
)

client = gspread.authorize(creds)
sheet = client.open_by_url("https://docs.google.com/spreadsheets/d/1dzvGI_uoFCJoanbbjGeNbEnEfw1tL8WRKYkS4LUZRsY")
lapas = sheet.worksheets()

@app.route("/")
def index():
    return render_template("index.html")

@app.route("/gemini", methods=["POST"])
def gemini_chat():
    data = request.get_json()
    jautajums = data.get("jautajums")

    if not jautajums:
        return jsonify({"tablide": "❗ Nav saņemts jautājums"}), 400

    saturs = ""
    for lapa in lapas:
        saturs += f"--- {lapa.title} ---\n"
        rindas = lapa.get_all_values()
        for rinda in rindas:
            saturs += " | ".join(rinda) + "\n"

    teksts = f"""Tavs uzdevums ir noteikt cenu drukai, balstoties uz šādiem piemēriem un tabulu (skatīt zemāk).
Lūdzu, ņem vērā dotās kļūdas un pareizās atbildes.

Noteikumi:
Nav datu (vietturis)

Tabulas:
{saturs}

Jautājums: {jautajums}""".format(saturs=saturs, jautajums=jautajums)

    payload = {
        "contents": [
            {
                "parts": [
                    {
                        "text": teksts
                    }
                ]
            }
        ]
    }

    print("==== PROMTS ====")
    print(teksts)

    url = f"https://generativelanguage.googleapis.com/v1/models/gemini-1.5-pro:generateContent?key={api_key}"
    response = requests.post(url, json=payload)
    if response.status_code != 200:
        print("Gemini status:", response.status_code)
        print("Gemini atbilde:", response.text)
        return jsonify({"tablide": "❌ Gemini kļūda"}), 500

    atbilde = response.json().get("candidates", [{}])[0].get("content", {}).get("parts", [{}])[0].get("text", "Nav atbildes")
    return jsonify({"tablide": atbilde})

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5050)
