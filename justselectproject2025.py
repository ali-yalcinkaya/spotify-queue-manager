from flask import Flask, redirect, request, session, url_for, render_template_string, make_response
import requests
import uuid
import time
import json
import os
from dotenv import load_dotenv

# .env yükleme (*render içinde envler olarak belirtildi ekstra .env yok)
load_dotenv()

app = Flask(__name__)
app.secret_key = str(uuid.uuid4())

CLIENT_ID = os.getenv("CLIENT_ID")
CLIENT_SECRET = os.getenv("CLIENT_SECRET")
REDIRECT_URI = os.getenv("REDIRECT_URI")
ADD_LIMIT_SECONDS = int(os.getenv("ADD_LIMIT_SECONDS", 60))
TOKENS_FILE = os.getenv("TOKENS_FILE", "tokens.json")

TOKEN_INFO = "token_info"

TOKENS_FILE = "tokens.json"
user_last_add_time = {}

# ------------------ Token Dosya Fonksiyonları ------------------
def save_tokens(token_info):
    with open(TOKENS_FILE, "w") as f:
        json.dump(token_info, f)

def load_tokens():
    if os.path.exists(TOKENS_FILE):
        with open(TOKENS_FILE, "r") as f:
            return json.load(f)
    return None

# ------------------ HTML Templates ------------------
HTML_TEMPLATE = """
<!DOCTYPE html>
<html lang="tr">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Spotify Queue Manager</title>
    <style>
        body { 
            font-family: 'Segoe UI', Arial, sans-serif; 
            margin: 0; 
            background-color: #121212; 
            color: #fff; 
        }
        header {
            background-color: #1DB954;
            padding: 15px;
            text-align: center;
            font-size: 1.5em;
            font-weight: bold;
            color: #fff;
        }
        main {
            padding: 20px;
            max-width: 800px;
            margin: auto;
        }
        form {
            display: flex;
            gap: 10px;
            flex-wrap: wrap;
            justify-content: center;
        }
        input {
            padding: 12px;
            flex: 1 1 250px;
            border: none;
            border-radius: 25px;
            outline: none;
        }
        button, a.btn {
            padding: 12px 20px;
            border: none;
            border-radius: 25px;
            background-color: #1DB954;
            color: white;
            font-weight: bold;
            cursor: pointer;
            text-decoration: none;
            transition: background 0.2s;
        }
        button:hover, a.btn:hover {
            background-color: #17a94b;
        }
        .track-grid {
            display: flex;
            flex-wrap: wrap;
            justify-content: center;
            gap: 15px;
            margin-top: 20px;
        }
        .track {
            background-color: #181818;
            padding: 10px;
            border-radius: 10px;
            width: 160px;
            text-align: center;
            transition: transform 0.2s;
        }
        .track:hover {
            transform: scale(1.05);
        }
        img {
            width: 100%;
            border-radius: 5px;
        }
        #popup {
            display: none;
            position: fixed;
            top: 20px; 
            left: 50%; 
            transform: translateX(-50%);
            background-color: #1DB954;
            color: white;
            padding: 15px 25px; 
            border-radius: 8px;
            font-weight: bold; 
            z-index: 9999;
        }
        #countdown {
            font-size: 18px; 
            color: #ff4c4c; 
            margin-top: 10px; 
            text-align: center;
        }
        @media (max-width: 500px) {
            .track { width: 45%; }
        }
    </style>
</head>
<body>
    <header>🎵 Spotify Queue Manager</header>
    <main>
        <div id="popup">✅ Şarkı eklendi!</div>
        <form action="/search">
            <input type="text" name="query" placeholder="Şarkı veya sanatçı ara" required>
            <button type="submit">Ara</button>
        </form>
        <p style="text-align:center;margin-top:10px;">
            <a class="btn" href="/queue">📜 İstek Listesini Gör</a>
        </p>
        {% if wait_time > 0 %}
            <div id="countdown"></div>
            <script>
                let remaining = {{ wait_time }};
                function updateCountdown() {
                    let minutes = Math.floor(remaining / 60);
                    let seconds = remaining % 60;
                    document.getElementById("countdown").innerHTML =
                        "⏳ Tekrar eklemek için: " + minutes + " dk " + seconds + " sn";
                    if (remaining > 0) {
                        remaining--;
                        setTimeout(updateCountdown, 1000);
                    } else {
                        location.reload();
                    }
                }
                updateCountdown();
            </script>
        {% endif %}
        <div class="track-grid">
            {% if tracks %}
                {% for t in tracks %}
                    <div class="track">
                        <img src="{{ t['image'] }}" alt="cover">
                        <p><b>{{ t['name'] }}</b><br><small>{{ t['artist'] }}</small></p>
                        {% if wait_time > 0 %}
                            <button disabled>Sıraya Ekle</button>
                        {% else %}
                            <a class="btn" href="/add_to_queue?uri={{ t['uri'] }}">Sıraya Ekle</a>
                        {% endif %}
                    </div>
                {% endfor %}
            {% endif %}
        </div>
    </main>
    <script>
        {% if added %}
            document.getElementById('popup').style.display = 'block';
            setTimeout(() => { document.getElementById('popup').style.display = 'none'; }, 2000);
        {% endif %}
    </script>
</body>
</html>
"""

QUEUE_TEMPLATE = """
<!DOCTYPE html>
<html lang="tr">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Spotify Queue</title>
    <style>
        body { font-family: 'Segoe UI', Arial, sans-serif; margin:0; background:#121212; color:white; }
        header { background:#1DB954; padding:15px; text-align:center; font-size:1.5em; font-weight:bold; }
        main { padding:20px; max-width:800px; margin:auto; }
        .btn { background:#1DB954; padding:10px 20px; border-radius:25px; color:white; text-decoration:none; font-weight:bold; }
        .track-grid { display:flex; flex-wrap:wrap; gap:15px; justify-content:center; }
        .track { background:#181818; padding:10px; border-radius:10px; width:160px; text-align:center; }
        img { width:100%; border-radius:5px; }
        @media (max-width:500px) {
            .track { width:45%; }
        }
    </style>
</head>
<body>
    <header>📜 İstek Listesi</header>
    <main>
        <p style="text-align:center;"><a class="btn" href="/">⬅ Ana Sayfa</a></p>
        <h2>🎶 Şu An Çalan</h2>
        {% if current %}
            <div class="track-grid">
                <div class="track">
                    <img src="{{ current['image'] }}" alt="cover">
                    <p><b>{{ current['name'] }}</b><br><small>{{ current['artist'] }}</small></p>
                </div>
            </div>
        {% else %}
            <p>Şu an çalan şarkı bulunamadı.</p>
        {% endif %}
        <h2>⏭ Sıradaki Şarkılar</h2>
        {% if queue %}
            <div class="track-grid">
                {% for t in queue %}
                    <div class="track">
                        <img src="{{ t['image'] }}" alt="cover">
                        <p><b>{{ t['name'] }}</b><br><small>{{ t['artist'] }}</small></p>
                    </div>
                {% endfor %}
            </div>
        {% else %}
            <p>İstek listesi boş.</p>
        {% endif %}
    </main>
</body>
</html>
"""

# ------------------ Yardımcı Fonksiyonlar ------------------
@app.before_request
def identify_user():
    user_id = request.cookies.get("user_id")
    if not user_id:
        new_id = str(uuid.uuid4())
        resp = make_response(redirect(request.url))
        resp.set_cookie("user_id", new_id, max_age=60*60*24*365)
        return resp
    request.user_id = user_id

def get_wait_time(user_id):
    now = time.time()
    last_time = user_last_add_time.get(user_id, 0)
    return max(0, ADD_LIMIT_SECONDS - int(now - last_time))

def refresh_access_token():
    token_info = session.get(TOKEN_INFO) or load_tokens()
    if not token_info or "refresh_token" not in token_info:
        return None

    # Token hâlâ geçerliyse
    if time.time() < token_info.get("expires_at", 0):
        return token_info["access_token"]

    print("🔄 Access token yenileniyor...")
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

# ------------------ ROUTES ------------------
@app.route("/")
def index():
    token_info = session.get(TOKEN_INFO) or load_tokens()
    if not token_info:
        return redirect(url_for("login"))

    wait_time = get_wait_time(request.user_id)
    added = request.args.get("added", False)
    return render_template_string(
        HTML_TEMPLATE,
        added=bool(added),
        wait_time=wait_time,
        tracks=[]
    )

@app.route("/login")
def login():
    auth_url = (
        "https://accounts.spotify.com/authorize"
        "?response_type=code"
        f"&client_id={CLIENT_ID}"
        f"&scope=user-modify-playback-state user-read-playback-state"
        f"&redirect_uri={REDIRECT_URI}"
    )
    return redirect(auth_url)

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

    # Önceki token varsa yükle
    existing = load_tokens() or {}

    # refresh_token dönmediyse eskisini koru
    if "refresh_token" not in token_data and "refresh_token" in existing:
        token_data["refresh_token"] = existing["refresh_token"]

    save_tokens(token_data)
    session[TOKEN_INFO] = token_data
    return redirect(url_for("index"))

@app.route("/search")
def search():
    access_token = refresh_access_token()
    if not access_token:
        return redirect(url_for("login"))

    query = request.args.get("query")
    wait_time = get_wait_time(request.user_id)

    res = requests.get(
        "https://api.spotify.com/v1/search",
        headers={"Authorization": f"Bearer {access_token}"},
        params={"q": query, "type": "track", "limit": 5}
    )
    results = res.json()
    tracks = [{
        "name": item["name"],
        "artist": item["artists"][0]["name"],
        "uri": item["uri"],
        "image": item["album"]["images"][1]["url"] if item["album"]["images"] else ""
    } for item in results.get("tracks", {}).get("items", [])]

    return render_template_string(
        HTML_TEMPLATE,
        tracks=tracks or [],
        wait_time=wait_time,
        added=False
    )

@app.route("/add_to_queue")
def add_to_queue():
    access_token = refresh_access_token()
    if not access_token:
        return redirect(url_for("login"))

    uri = request.args.get("uri")
    wait_time = get_wait_time(request.user_id)
    if wait_time > 0:
        return redirect(url_for("index"))

    response = requests.post(
        "https://api.spotify.com/v1/me/player/queue",
        headers={"Authorization": f"Bearer {access_token}"},
        params={"uri": uri}
    )

    if response.status_code in (200, 204):
        user_last_add_time[request.user_id] = time.time()
        return redirect(url_for("index", added=True))
    else:
        return f"❌ Sıraya eklenemedi. Kod: {response.status_code}, Detay: {response.text}"

@app.route("/queue")
def view_queue():
    access_token = refresh_access_token()
    if not access_token:
        return redirect(url_for("login"))

    res = requests.get(
        "https://api.spotify.com/v1/me/player/queue",
        headers={"Authorization": f"Bearer {access_token}"}
    )
    if res.status_code != 200:
        return f"❌ Liste alınamadı. Kod: {res.status_code}, Detay: {res.text}"

    data = res.json()
    current = None
    if data.get("currently_playing"):
        current = {
            "name": data["currently_playing"]["name"],
            "artist": data["currently_playing"]["artists"][0]["name"],
            "image": data["currently_playing"]["album"]["images"][1]["url"]
        }

    queue = [{
        "name": item["name"],
        "artist": item["artists"][0]["name"],
        "image": item["album"]["images"][1]["url"]
    } for item in data.get("queue", [])]

    return render_template_string(QUEUE_TEMPLATE, current=current, queue=queue)

if __name__ == "__main__":
    app.run(debug=True)
