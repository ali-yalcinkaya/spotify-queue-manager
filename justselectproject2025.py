from flask import Flask, redirect, request, session, url_for, render_template_string, make_response
import requests
import uuid
import time

app = Flask(__name__)
app.secret_key = str(uuid.uuid4())

CLIENT_ID = "f338bc70b18c49ce9ea3bd3b77465f45"
CLIENT_SECRET = "afd7ef9e569643ad851e258332a50a2b"
REDIRECT_URI = "https://spotify-queue-manager.onrender.com/callback"
TOKEN_INFO = "token_info"

user_last_add_time = {}
ADD_LIMIT_SECONDS = 600  # 10 dakika

# ----------------- TOKEN YENİLEME -----------------
def get_token():
    token_info = session.get(TOKEN_INFO)
    if not token_info:
        return None

    now = int(time.time())
    is_expired = token_info.get("expires_at") - now < 60

    if is_expired:
        refresh_token = token_info.get("refresh_token")
        if not refresh_token:
            return None

        res = requests.post(
            "https://accounts.spotify.com/api/token",
            data={
                "grant_type": "refresh_token",
                "refresh_token": refresh_token,
                "client_id": CLIENT_ID,
                "client_secret": CLIENT_SECRET
            }
        )
        if res.status_code != 200:
            return None

        new_tokens = res.json()
        token_info["access_token"] = new_tokens["access_token"]
        token_info["expires_at"] = int(time.time()) + new_tokens.get("expires_in", 3600)
        # refresh_token genelde değişmez ama Spotify bazen yenileyebilir
        if "refresh_token" in new_tokens:
            token_info["refresh_token"] = new_tokens["refresh_token"]

        session[TOKEN_INFO] = token_info

    return token_info
# ---------------------------------------------------

HTML_TEMPLATE = """..."""  # senin HTML kodun değişmedi
QUEUE_TEMPLATE = """..."""  # senin HTML kodun değişmedi

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

@app.route("/")
def index():
    token_info = get_token()
    if not token_info:
        return redirect(url_for("login"))
    wait_time = get_wait_time(request.user_id)
    added = request.args.get("added")
    return render_template_string(HTML_TEMPLATE, added=added, wait_time=wait_time, tracks=None)

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
    token_json = res.json()
    token_json["expires_at"] = int(time.time()) + token_json.get("expires_in", 3600)
    session[TOKEN_INFO] = token_json
    return redirect(url_for("index"))

@app.route("/search")
def search():
    query = request.args.get("query")
    token_info = get_token()
    if not token_info:
        return redirect(url_for("login"))

    wait_time = get_wait_time(request.user_id)

    access_token = token_info["access_token"]
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

    return render_template_string(HTML_TEMPLATE, tracks=tracks, wait_time=wait_time, added=False)

@app.route("/add_to_queue")
def add_to_queue():
    uri = request.args.get("uri")
    token_info = get_token()
    if not token_info:
        return redirect(url_for("login"))

    wait_time = get_wait_time(request.user_id)
    if wait_time > 0:
        return redirect(url_for("index"))

    access_token = token_info["access_token"]
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
    token_info = get_token()
    if not token_info:
        return redirect(url_for("login"))

    access_token = token_info["access_token"]
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
