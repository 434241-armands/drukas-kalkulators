import os
import re
import json
import logging
import pandas as pd
import requests
from flask import Flask, request, jsonify

app = Flask(__name__)
app.logger.setLevel(logging.DEBUG)

# —————————————— Konfigurācija ——————————————
# API galapunkts un atslēga
GEMINI_URL   = os.getenv("GEMINI_URL",   "https://api.gemini.example/v1/chat")
API_KEY      = os.getenv("API_KEY",      "")
# Ceļš uz pilno cenu CSV (vienā tabulā ar Sheet kolonu) vai atsevišķām CSV
PRICE_CSV    = os.getenv("PRICE_CSV",    "price_sheet_full.csv")

# ———————————— Ielāde un priekšapstrāde ————————————
app.logger.debug(f"Ielādēju cenas no {PRICE_CSV!r}")
price_df = pd.read_csv(PRICE_CSV)

# Pārliecināmies, ka ciparu kolonnas
for col in ("MinQty","MaxQty","UnitPrice"):
    price_df[col] = pd.to_numeric(price_df[col], errors="coerce")
# Neierobežots MaxQty => inf
price_df["MaxQty"] = price_df["MaxQty"].fillna(float("inf"))

# Samazinam cenu tabulu uz digitāldrukas daļu kā piemēru
digital_df = price_df[price_df.Sheet == "Digital_Print"][["MinQty","MaxQty","Mode","UnitPrice"]]

# Konvertē DataFrame uz CSV-string, lai ērti iekopēt promptā
digital_csv = digital_df.to_csv(index=False)

# —————————————— Flask endpoint ——————————————
@app.route("/gemini", methods=["POST"])
def gemini():
    try:
        data = request.get_json()
        question = data.get("question", "").strip()
        if not question:
            return jsonify({"error": "Nav jautājuma laukā `question`"}), 400

        # 1) Sagatavo ziņojumu sarakstu Gemini
        messages = [
            {
                "role": "system",
                "content": (
                    "Tu esi precīzs drukas cenu kalkulators. "
                    "Izmanto tieši šo cenu tabulu digitālajai drukai (EUR par A3 loksni):\n"
                    + digital_csv +
                    "\nAprēķinus veic šādi:\n"
                    "1. Izvelk no jautājuma daudzumu (gab.)\n"
                    "2. Pārbauda, vai min_qty ≤ qty ≤ max_qty\n"
                    "3. Cena = qty × UnitPrice\n"
                    "4. Atbild: “Cena: XX.XX EUR (Y.YYY EUR/gab.)” ar 2 decimālpunktu precizitāti."
                )
            },
            {
                "role": "user",
                "content": question
            }
        ]

        # 2) Nosūta pieprasījumu Gemini AI
        headers = {
            "Authorization": f"Bearer {API_KEY}",
            "Content-Type": "application/json"
        }
        payload = {
            "model": "gemini-advanced",
            "messages": messages,
            "temperature": 0.0
        }

        app.logger.debug("Sūtu pieprasījumu Gemini: %s", json.dumps(payload))
        resp = requests.post(GEMINI_URL, headers=headers, json=payload, timeout=30)
        resp.raise_for_status()

        result = resp.json()
        # Pieņemam, ka atbilde nāk šādā struktūrā
        # {"choices":[{"message":{"content":"…"}}, …]}
        ats = result["choices"][0]["message"]["content"].strip()
        return jsonify({"answer": ats})

    except Exception as e:
        app.logger.exception("Kļūda `/gemini` galā")
        return jsonify({
            "error": "Servera kļūda",
            "detail": str(e)
        }), 500

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5050))
    app.run(host="0.0.0.0", port=port)
