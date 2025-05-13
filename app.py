@tls.route("/gemini", methods=["POST"])
def gemini_chat():
    data = request.get_json(force=True) or {}
    jautajums = data.get("jautajums","").strip()
    if not jautajums:
        return jsonify({"error":"Nav saņemts jautājums"}), 400

    # 1. Nolasi “system” noteikumus no tabulas
    rules_rows = rules_ws.get_all_values()
    rules_text = "\n".join(r[0] for r in rules_rows if r and r[0].strip())

    # 2. Uzbūvē chat-style ziņojumus
    prompt_text = f"Jauns jautājums: {jautajums}"
    messages = [
        {"role": "system", "content": rules_text},
        {"role": "user",   "content": prompt_text}
    ]

    # 3. Sagatavo payload un headers
    payload = {
        "model": MODEL,
        "messages": messages,
        "temperature": 0.0
    }
    headers = {
        "Content-Type": "application/json",
        "X-Goog-Api-Key": API_KEY
    }

    # 4. Pošam pieprasījumu
    r = requests.post(GENERATE_URL, headers=headers, json=payload, timeout=15)
    tls.logger.debug("Gemini status %s, raw: %s", r.status_code, r.text)

    if r.status_code != 200:
        return jsonify({"error": f"Gemini kļūda: {r.status_code}"}), 502

    resp = r.json()
    cand = resp.get("candidates", [{}])[0]
    answer = cand.get("message", {}).get("content", "").strip()

    return jsonify({"atbilde": answer})
