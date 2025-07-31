from flask import Flask, redirect, request, session, url_for, render_template_string, make_response
import requests
import uuid
import time
import json
import os

app = Flask(__name__)
app.secret_key = str(uuid.uuid4())

# --- Spotify API bilgilerimiz ENV değişkenlerinden geliyor ---
CLIENT_ID = os.getenv("CLIENT_ID")
CLIENT_SECRET = os.getenv("CLIENT_SECRET")
REDIRECT_URI = os.getenv("REDIRECT_URI")

if not all([CLIENT_ID, CLIENT_SECRET, REDIRECT_URI]):
    raise ValueError("❌ CLIENT_ID, CLIENT_SECRET ve REDIRECT_URI environment değişkenleri eksik!")

TOKEN_INFO = "token_info"
TOKENS_FILE = "tokens.json"
user_last_add_time = {}
ADD_LIMIT_SECONDS = 60  # saniye

# --- Token dosya fonksiyonları ---
def save_tokens(token_info):
    with open(TOKENS_FILE, "w") as f:
        json.dump(token_info, f)

def load_tokens():
    if os.path.exists(TOKENS_FILE):
        with open(TOKENS_FILE, "r") as f:
            return json.load(f)
    return None

# --- Kullanıcı tanıma ---
@app.before_request
def identify_user():
    user_id = request.cookies.get("user_id")
    if not user_id:
        new_id = str(uuid.uuid4())
        resp = make_response(redirect(request.url))
        resp.set_cookie("user_id", new_id, max_age=60*60*24*365)
        return resp
    request.user_id = user_id

# --- Ekleme limiti ---
def get_wait_time(user_id):
    now = time.time()
    last_time = user_last_add_time.get(user_id, 0)
    return max(0, ADD_LIMIT_SECONDS - int(now - last_time))

# --- Token yenileme ---
def refresh_access_token():
    token_info = session.get(TOKEN_INFO) or load_tokens()
    if not token_info or "refresh_token" not in token_info:
        return None

    # Hâlâ geçerli mi?
    if time.time() < token_info.get("expires_at", 0):
        return token_info["access_token"]

    res = requests.post(
        "https://accounts.spotify.com/api/token",
        data={
            "grant_type": "refresh_token",
            "refresh_token": token_info["refresh_token"],
            "client_id": CLIENT_ID,
            "client_secret": CLIENT_SECRET
        }
    )

    if res.status_code != 200:
        print("⚠️ Token yenileme başarısız:", res.text)
        return None

    new_tokens = res.json()
    token_info["access_token"] = new_tokens["access_token"]
    token_info["expires_at"] = time.time() + new_tokens.get("expires_in", 3600)

    save_tokens(token_info)
    session[TOKEN_INFO] = token_info
    return token_info["access_token"]

# --- HTML Template (basit test için) ---
HTML_TEMPLATE = """
<h1>🎵 Spotify Queue Manager</h1>
<form action="/search">
    <input type="text" name="query" placeholder="Şarkı ara" required>
    <button type="submit">Ara</button>
</form>
{% if tracks %}
    <h3>Sonuçlar:</h3>
    <ul>
    {% for t in tracks %}
        <li>{{ t['name'] }} - {{ t['artist'] }} 
            <a href="/add_to_queue?uri={{ t['uri'] }}">Sıraya Ekle</a>
        </li>
    {% endfor %}
    </ul>
{% endif %}
"""

# --- Ana sayfa ---
@app.route("/")
def index():
    token_info = session.get(TOKEN_INFO) or load_tokens()
    if not token_info:
        return redirect(url_for("login"))
    return render_template_string(HTML_TEMPLATE, tracks=[])

# --- Login ---
@app.route("/login")
def login():
    auth_url = (
        "https://accounts.spotify.com/authorize"
        "?response_type=code"
        f"&client_id={CLIENT_ID}"
        "&scope=user-modify-playback-state user-read-playback-state"
        f"&redirect_uri={REDIRECT_URI}"
    )
    return redirect(auth_url)

# --- Callback ---
@app.route("/callback")
def callback():
    code = request.args.get("code")
    res = requests.post(
        "https://accounts.spotify.com/api/token",
        data={
            "grant_type": "authorization_code",
            "code": code,
            "redirect_uri": REDIRECT_URI,
            "client_id": CLIENT_ID,
            "client_secret": CLIENT_SECRET
        }
    )
    token_data = res.json()
    token_data["expires_at"] = time.time() + token_data.get("expires_in", 3600)

    existing = load_tokens() or {}
    if "refresh_token" not in token_data and "refresh_token" in existing:
        token_data["refresh_token"] = existing["refresh_token"]

    save_tokens(token_data)
    session[TOKEN_INFO] = token_data
    return redirect(url_for("index"))

# --- Şarkı arama ---
@app.route("/search")
def search():
    access_token = refresh_access_token()
    if not access_token:
        return redirect(url_for("login"))

    query = request.args.get("query")
    res = requests.get(
        "https://api.spotify.com/v1/search",
        headers={"Authorization": f"Bearer {access_token}"},
        params={"q": query, "type": "track", "limit": 5}
    )
    tracks = [{
        "name": item["name"],
        "artist": item["artists"][0]["name"],
        "uri": item["uri"]
    } for item in res.json().get("tracks", {}).get("items", [])]

    return render_template_string(HTML_TEMPLATE, tracks=tracks)

# --- Sıraya ekleme ---
@app.route("/add_to_queue")
def add_to_queue():
    access_token = refresh_access_token()
    if not access_token:
        return redirect(url_for("login"))

    uri = request.args.get("uri")
    wait_time = get_wait_time(request.user_id)
    if wait_time > 0:
        return f"⏳ Tekrar eklemek için {wait_time} saniye bekle."

    res = requests.post(
        "https://api.spotify.com/v1/me/player/queue",
        headers={"Authorization": f"Bearer {access_token}"},
        params={"uri": uri}
    )

    if res.status_code in (200, 204):
        user_last_add_time[request.user_id] = time.time()
        return redirect(url_for("index"))
    else:
        return f"❌ Eklenemedi. Kod: {res.status_code} - {res.text}"

if __name__ == "__main__":
    app.run(debug=True)
