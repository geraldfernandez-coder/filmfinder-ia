
import os
import re
import json
import html
import base64
import random
from pathlib import Path
from urllib.parse import quote

import requests
import streamlit as st
from dotenv import load_dotenv

# ================== CONFIG ==================
load_dotenv()

RAPIDAPI_KEY = os.getenv("RAPIDAPI_KEY", "").strip()
RAPIDAPI_HOST = os.getenv("RAPIDAPI_HOST", "streaming-availability.p.rapidapi.com").strip()
BASE_URL = "https://streaming-availability.p.rapidapi.com"
OMDB_API_KEY = os.getenv("OMDB_API_KEY", "").strip()
OLLAMA_URL = os.getenv("OLLAMA_URL", "http://localhost:11434").strip()
OLLAMA_MODEL = os.getenv("OLLAMA_MODEL", "llama3.2:3b").strip()

APP_DIR = Path(__file__).parent
PROFILE_PATH = APP_DIR / "profile.json"
BG_DIR = APP_DIR / "bg"

st.set_page_config(page_title="FilmFinder IA", layout="centered")

# ================== THEME ==================
VARIANT = "A"
THEMES = {
    "A": {
        "name": "Bulles Messenger",
        "accent": "#ff4f5f",
        "accent_soft": "rgba(255,79,95,0.12)",
        "bubble_bg": "rgba(255,255,255,0.94)",
        "bubble_border": "rgba(255,255,255,0.82)",
        "bubble_shadow": "0 12px 30px rgba(19, 24, 38, 0.10)",
        "bubble_radius": "24px",
        "card_bg": "rgba(255,255,255,0.95)",
        "card_border": "rgba(255,255,255,0.85)",
        "page_scrim": "linear-gradient(rgba(236,240,245,0.30), rgba(236,240,245,0.36))",
    },
    "B": {
        "name": "Compact Pro",
        "accent": "#ee4040",
        "accent_soft": "rgba(238,64,64,0.10)",
        "bubble_bg": "rgba(255,255,255,0.96)",
        "bubble_border": "rgba(205,214,227,0.92)",
        "bubble_shadow": "0 8px 18px rgba(20, 24, 35, 0.08)",
        "bubble_radius": "18px",
        "card_bg": "rgba(255,255,255,0.97)",
        "card_border": "rgba(208,216,228,0.96)",
        "page_scrim": "linear-gradient(rgba(237,241,246,0.88), rgba(237,241,246,0.90))",
    },
    "C": {
        "name": "Glass Chat",
        "accent": "#845ef7",
        "accent_soft": "rgba(132,94,247,0.14)",
        "bubble_bg": "rgba(255,255,255,0.72)",
        "bubble_border": "rgba(255,255,255,0.58)",
        "bubble_shadow": "0 14px 34px rgba(26, 31, 43, 0.16)",
        "bubble_radius": "26px",
        "card_bg": "rgba(255,255,255,0.78)",
        "card_border": "rgba(255,255,255,0.55)",
        "page_scrim": "linear-gradient(rgba(229,233,240,0.64), rgba(229,233,240,0.74))",
    },
}
THEME = THEMES[VARIANT]

# ================== SERVICES ==================
SERVICE_CATALOG = [
    {"id": "netflix", "name": "Netflix", "aliases": ["netflix"]},
    {"id": "prime", "name": "Prime Video", "aliases": ["prime", "prime video", "amazon prime", "amazon prime video"]},
    {"id": "disney", "name": "Disney+", "aliases": ["disney", "disney+"]},
    {"id": "max", "name": "HBO Max", "aliases": ["max", "hbo", "hbo max", "hbomax"]},
    {"id": "apple", "name": "Apple TV+", "aliases": ["apple", "apple tv", "apple tv+"]},
    {"id": "paramount", "name": "Paramount+", "aliases": ["paramount", "paramount+"]},
    {"id": "canal", "name": "Canal+", "aliases": ["canal", "canal+"]},
    {"id": "arte", "name": "Arte", "aliases": ["arte"]},
    {"id": "france.tv", "name": "France TV", "aliases": ["france tv", "francetv", "france.tv"]},
    {"id": "molotov", "name": "Molotov", "aliases": ["molotov"]},
    {"id": "rakuten", "name": "Rakuten TV", "aliases": ["rakuten", "rakuten tv"]},
    {"id": "youtube", "name": "YouTube", "aliases": ["youtube", "youtube movies"]},
]
SERVICE_BY_ID = {s["id"]: s for s in SERVICE_CATALOG}
SERVICE_NAMES = [s["name"] for s in SERVICE_CATALOG]
NAME_TO_ID = {s["name"]: s["id"] for s in SERVICE_CATALOG}

STOPWORDS = {
    "le","la","les","un","une","des","de","du","dans","sur","avec","sans","et","ou",
    "qui","que","quoi","dont","au","aux","en","a","à","pour","par","se","sa","son","ses",
    "je","tu","il","elle","on","nous","vous","ils","elles","toujours",
    "the","a","an","and","or","in","on","with","without","to","of","for","by","from"
}

GENRES = [
    "Action", "Aventure", "Animation", "Comédie", "Crime", "Documentaire", "Drame", "Famille",
    "Fantastique", "Guerre", "Horreur", "Mystère", "Romance", "Science-fiction", "Thriller", "Western"
]
YEARS = [str(y) for y in range(2025, 2009, -1)]

_COUNTRY_MAP = {
    "france":"FR","fr":"FR",
    "united states":"US","usa":"US","us":"US","etats unis":"US","états unis":"US",
    "united kingdom":"GB","uk":"GB","gb":"GB","royaume uni":"GB",
    "japan":"JP","japon":"JP","jp":"JP",
    "korea":"KR","south korea":"KR","corée":"KR","coree":"KR","kr":"KR",
    "spain":"ES","espagne":"ES","es":"ES",
    "italy":"IT","italie":"IT","it":"IT",
    "germany":"DE","allemagne":"DE","de":"DE",
    "canada":"CA","ca":"CA",
    "australia":"AU","au":"AU",
    "china":"CN","chine":"CN","cn":"CN",
    "india":"IN","inde":"IN","in":"IN",
    "brazil":"BR","bresil":"BR","brésil":"BR","br":"BR",
    "mexico":"MX","mexique":"MX","mx":"MX",
    "netherlands":"NL","pays bas":"NL","nl":"NL",
    "belgium":"BE","belgique":"BE","be":"BE",
    "switzerland":"CH","suisse":"CH","ch":"CH",
}

# ================== STATE ==================
st.session_state.setdefault("entered", False)
st.session_state.setdefault("page", "Accueil")
st.session_state.setdefault("do_search", False)
st.session_state.setdefault("last_results", None)
st.session_state.setdefault("last_query", "")
st.session_state.setdefault("last_mode", "Normal")
st.session_state.setdefault("sort_mode", "Pertinence")
st.session_state.setdefault("scroll_results", False)
st.session_state.setdefault("api_preview_notice", "")
st.session_state.setdefault("api_error_notice", "")
st.session_state.setdefault("bg_image_name", "")

# ================== PROFILE ==================
def load_profile():
    if PROFILE_PATH.exists():
        try:
            p = json.loads(PROFILE_PATH.read_text(encoding="utf-8"))
            p.setdefault("country", "fr")
            p.setdefault("lang", "fr")
            p.setdefault("show_type", "movie")
            p.setdefault("platform_ids", [])
            p.setdefault("show_elsewhere", False)
            if p.get("show_type") == "all":
                p["show_type"] = "movie"
            if p.get("show_type") not in ("movie", "series"):
                p["show_type"] = "movie"
            return p
        except Exception:
            pass
    return {
        "country": "fr",
        "lang": "fr",
        "show_type": "movie",
        "platform_ids": ["netflix", "prime", "disney", "max"],
        "show_elsewhere": False,
    }

def save_profile(profile):
    PROFILE_PATH.write_text(json.dumps(profile, ensure_ascii=False, indent=2), encoding="utf-8")

profile = load_profile()

# ================== HELPERS ==================
def norm_text(s: str) -> str:
    if not s:
        return ""
    s = s.lower().strip()
    s = re.sub(r"[’']", "'", s)
    s = re.sub(r"[^a-z0-9àâçéèêëîïôùûüÿñæœ'\s\-\.]", " ", s, flags=re.I)
    s = re.sub(r"\s+", " ", s).strip()
    return s

def escape(s: str) -> str:
    return html.escape(s or "", quote=True)

def stars_html(score_0_100):
    if score_0_100 is None:
        return ""
    try:
        pct = max(0.0, min(100.0, float(score_0_100)))
    except Exception:
        return ""
    return (
        f'<span class="ff-stars">'
        f'  <span class="top" style="width:{pct}%">★★★★★</span>'
        f'  <span class="bot">★★★★★</span>'
        f'</span>'
    )

def flag_from_iso2(code2: str) -> str:
    if not code2 or len(code2) != 2:
        return ""
    code2 = code2.upper()
    if not ("A" <= code2[0] <= "Z" and "A" <= code2[1] <= "Z"):
        return ""
    return chr(0x1F1E6 + ord(code2[0]) - ord("A")) + chr(0x1F1E6 + ord(code2[1]) - ord("A"))

def iso2_from_country_text(country_text: str) -> str:
    if not country_text:
        return ""
    first = country_text.split(",")[0].strip()
    if first.upper() == "USA":
        return "US"
    if first.upper() == "UK":
        return "GB"
    if len(first) == 2:
        return first.upper()
    return _COUNTRY_MAP.get(norm_text(first), "")

def extract_keywords(text: str, max_words: int = 10) -> str:
    words = re.findall(r"[a-zA-ZÀ-ÿ0-9']+", text.lower())
    words = [w for w in words if len(w) >= 4 and w not in STOPWORDS]
    out = []
    for w in words:
        if w not in out:
            out.append(w)
        if len(out) >= max_words:
            break
    return " ".join(out) if out else text.strip()

def heuristic_titles_from_query(q: str):
    nq = norm_text(q)
    titles = []
    time_loop = any(x in nq for x in ["boucle", "revit", "revivre", "meme journee", "même journée", "rena", "ressusc", "time loop", "loop"])
    tom = "tom cruise" in nq
    alien = any(x in nq for x in ["extraterrestre", "alien"])
    if time_loop:
        titles += ["Edge of Tomorrow", "Un jour sans fin", "Happy Death Day", "Palm Springs"]
    if tom:
        titles.insert(0, "Edge of Tomorrow")
        titles += ["Live Die Repeat"]
    if alien and time_loop and "Edge of Tomorrow" not in titles:
        titles.insert(0, "Edge of Tomorrow")
    out = []
    for t in titles:
        if t and t not in out:
            out.append(t)
    return out

def stable_id(sh: dict) -> str:
    return str(
        sh.get("id")
        or sh.get("imdbId")
        or sh.get("tmdbId")
        or (sh.get("title", "") + "_" + str(sh.get("releaseYear") or sh.get("firstAirYear") or ""))
    )

def dedupe_streaming_options(options):
    seen, out = set(), []
    for o in options or []:
        service = o.get("service") or {}
        sid = service.get("id") or service.get("name") or ""
        typ = o.get("type") or ""
        link = o.get("link") or o.get("videoLink") or ""
        key = (norm_text(str(sid)), norm_text(str(typ)), norm_text(str(link)))
        if key in seen:
            continue
        seen.add(key)
        out.append(o)
    return out

def normalize_service_tokens(value: str):
    text = norm_text(value).replace(".", " ").replace("_", " ")
    text = text.replace("subscription", " ").replace("addon", " ").replace("channel", " ")
    text = text.replace("amazon", "prime").replace("hbomax", "hbo max")
    text = re.sub(r"\s+", " ", text).strip()
    return set(text.split()) | {text}

def option_on_my_services(option: dict, selected_ids):
    service = option.get("service") or {}
    raw_candidates = [
        str(service.get("id") or ""),
        str(service.get("name") or ""),
        str(service.get("homePage") or ""),
    ]
    tokens = set()
    for raw in raw_candidates:
        tokens |= normalize_service_tokens(raw)
    for sid in selected_ids:
        meta = SERVICE_BY_ID.get(sid, {"aliases": [sid]})
        alias_tokens = set()
        for alias in meta.get("aliases", []):
            alias_tokens |= normalize_service_tokens(alias)
        alias_tokens |= normalize_service_tokens(meta.get("name", sid))
        if tokens & alias_tokens:
            return True
    return False

def get_poster_url(show: dict):
    try:
        vs = (show.get("imageSet") or {}).get("verticalPoster") or {}
        return vs.get("w240") or vs.get("w360") or vs.get("w480") or None
    except Exception:
        return None

def merge_results(items):
    merged = {}
    for sh in items:
        merged[stable_id(sh)] = sh
    return list(merged.values())

def relevance_score(sh: dict, q: str, actor_hint: str = "") -> float:
    hay = norm_text((sh.get("title") or "") + " " + (sh.get("overview") or ""))
    qn = norm_text(q)
    words = [w for w in qn.split() if len(w) >= 4 and w not in STOPWORDS]
    score = 0.0
    for w in set(words):
        if w in hay:
            score += 1.0
    if any(x in qn for x in ["boucle", "revit", "revivre", "meme journee", "même journée", "ressusc", "rena"]):
        if any(x in hay for x in ["loop", "time loop", "revit", "revivre", "ressusc", "rena", "day repeats", "repeat the day"]):
            score += 3.0
    if any(x in qn for x in ["extraterrestre", "alien"]):
        if any(x in hay for x in ["alien", "extraterrestre", "invasion", "space"]):
            score += 2.2
    title_n = norm_text(sh.get("title", ""))
    if "edge of tomorrow" in title_n or "live die repeat" in title_n:
        if any(x in qn for x in ["tom cruise", "extraterrestre", "revit", "rena", "ressusc", "journee", "journée", "loop"]):
            score += 4.0
    if actor_hint:
        actors = " ".join([norm_text(a) for a in actors_list_from_omdb(sh)])
        if actor_hint in actors:
            score += 4.0
    return score

def parse_year_value(show):
    year = show.get("releaseYear") or show.get("firstAirYear") or 0
    try:
        return int(year or 0)
    except Exception:
        return 0

# ================== BACKGROUND ==================
def list_bg_images():
    if not BG_DIR.exists() or not BG_DIR.is_dir():
        return []
    files = []
    for p in BG_DIR.iterdir():
        if p.suffix.lower() in {".jpg", ".jpeg", ".png", ".webp"}:
            files.append(p)
    return sorted(files)

def pick_bg_image():
    bg_files = list_bg_images()
    if not bg_files:
        return None
    saved_name = st.session_state.get("bg_image_name", "")
    chosen = None
    if saved_name:
        for f in bg_files:
            if f.name == saved_name:
                chosen = f
                break
    if chosen is None:
        chosen = random.choice(bg_files)
        st.session_state["bg_image_name"] = chosen.name
    return chosen

def file_to_data_uri(path: Path):
    try:
        ext = path.suffix.lower().lstrip(".")
        if ext == "jpg":
            ext = "jpeg"
        data = base64.b64encode(path.read_bytes()).decode("ascii")
        return f"data:image/{ext};base64,{data}"
    except Exception:
        return ""

def demo_bg_data_uri():
    svg = """
    <svg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 1080 1920'>
      <defs>
        <linearGradient id='bg' x1='0' y1='0' x2='1' y2='1'>
          <stop offset='0%' stop-color='#0f172a'/>
          <stop offset='38%' stop-color='#1e293b'/>
          <stop offset='100%' stop-color='#111827'/>
        </linearGradient>
        <radialGradient id='glow1'>
          <stop offset='0%' stop-color='#f59e0b' stop-opacity='0.65'/>
          <stop offset='100%' stop-color='#f59e0b' stop-opacity='0'/>
        </radialGradient>
        <radialGradient id='glow2'>
          <stop offset='0%' stop-color='#60a5fa' stop-opacity='0.55'/>
          <stop offset='100%' stop-color='#60a5fa' stop-opacity='0'/>
        </radialGradient>
        <radialGradient id='glow3'>
          <stop offset='0%' stop-color='#ec4899' stop-opacity='0.40'/>
          <stop offset='100%' stop-color='#ec4899' stop-opacity='0'/>
        </radialGradient>
        <filter id='blur24'><feGaussianBlur stdDeviation='24'/></filter>
        <filter id='blur40'><feGaussianBlur stdDeviation='40'/></filter>
        <filter id='posterBlur'><feGaussianBlur stdDeviation='8'/></filter>
      </defs>
      <rect width='1080' height='1920' fill='url(#bg)'/>
      <circle cx='160' cy='260' r='280' fill='url(#glow1)' filter='url(#blur40)'/>
      <circle cx='930' cy='360' r='280' fill='url(#glow2)' filter='url(#blur40)'/>
      <circle cx='780' cy='1480' r='240' fill='url(#glow3)' filter='url(#blur40)'/>
      <g opacity='0.46' filter='url(#posterBlur)'>
        <rect x='55' y='120' width='205' height='300' rx='16' fill='#7f1d1d'/>
        <rect x='290' y='90' width='220' height='330' rx='16' fill='#1d4ed8'/>
        <rect x='540' y='130' width='185' height='280' rx='16' fill='#6d28d9'/>
        <rect x='760' y='85' width='250' height='350' rx='16' fill='#0f766e'/>
        <rect x='85' y='500' width='200' height='300' rx='16' fill='#374151'/>
        <rect x='330' y='480' width='230' height='340' rx='16' fill='#9a3412'/>
        <rect x='610' y='520' width='195' height='290' rx='16' fill='#0f172a'/>
        <rect x='825' y='495' width='170' height='265' rx='16' fill='#a21caf'/>
        <rect x='70' y='885' width='210' height='320' rx='16' fill='#0f766e'/>
        <rect x='315' y='870' width='245' height='350' rx='16' fill='#1e3a8a'/>
        <rect x='610' y='900' width='190' height='300' rx='16' fill='#b91c1c'/>
        <rect x='830' y='860' width='185' height='280' rx='16' fill='#9333ea'/>
      </g>
      <rect x='0' y='0' width='1080' height='1920' fill='rgba(255,255,255,0.04)'/>
      <rect x='0' y='0' width='1080' height='1920' fill='rgba(0,0,0,0.18)'/>
    </svg>
    """.strip()
    data = base64.b64encode(svg.encode("utf-8")).decode("ascii")
    return f"data:image/svg+xml;base64,{data}"

# ================== THEME APPLY ==================
def apply_theme():
    bg_path = pick_bg_image()
    bg_uri = file_to_data_uri(bg_path) if bg_path else demo_bg_data_uri()
    if bg_uri:
        background_rule = f"background-image: {THEME['page_scrim']}, url('{bg_uri}'); background-size: cover; background-position: center center;"
    else:
        background_rule = f"background: {THEME['page_scrim']};"

    css = f"""
    <style>
    html, body, .stApp, [data-testid='stAppViewContainer'] {{
        background: transparent !important;
        color: #1f2940 !important;
    }}
    [data-testid='stAppViewContainer']::before {{
        content: '';
        position: fixed;
        inset: 0;
        z-index: -2;
        {background_rule}
        filter: saturate(1.03);
    }}
    [data-testid='stHeader'] {{
        background: rgba(0,0,0,0) !important;
    }}
    .main .block-container {{
        max-width: 1020px !important;
        padding-top: 16px !important;
        padding-bottom: 90px !important;
        background: transparent !important;
    }}
    .ff-title {{
        margin: 0 0 6px 0;
        color: #1f2940;
        font-size: 3rem;
        line-height: 1;
        font-weight: 800;
    }}
    .ff-subtitle {{
        color: rgba(31,41,64,0.64);
        margin-bottom: 14px;
    }}
    .ff-bubble, div[data-testid='stExpander'] {{
        background: {THEME['bubble_bg']} !important;
        border: 1px solid {THEME['bubble_border']} !important;
        border-radius: {THEME['bubble_radius']} !important;
        box-shadow: {THEME['bubble_shadow']} !important;
        backdrop-filter: blur(12px);
    }}
    .ff-card {{
        background: {THEME['card_bg']};
        border: 1px solid {THEME['card_border']};
        border-radius: calc({THEME['bubble_radius']} + 2px);
        box-shadow: {THEME['bubble_shadow']};
        padding: 16px 18px;
        backdrop-filter: blur(14px);
    }}
    .ff-inline-note {{
        background: {THEME['bubble_bg']};
        border: 1px solid {THEME['bubble_border']};
        border-radius: 16px;
        padding: 10px 14px;
        box-shadow: {THEME['bubble_shadow']};
        margin: 8px 0 10px 0;
        color: rgba(31,41,64,0.82);
    }}
    .ff-muted {{ color: rgba(31,41,64,0.70); font-size: 0.95rem; }}
    .ff-availability {{
        display: inline-block;
        margin: 10px 0 10px 0;
        padding: 8px 12px;
        border-radius: 999px;
        background: rgba(255,255,255,0.92);
        border: 1px solid rgba(210,216,226,0.84);
        font-weight: 600;
    }}
    .ff-links {{ margin: 6px 0 10px 0; display:flex; flex-wrap: wrap; gap: 8px; }}
    .ff-chip-link {{
        display:inline-block; padding:7px 11px; border-radius:999px;
        text-decoration:none !important; color:#17365d !important; font-weight:600;
        background: rgba(255,255,255,0.92); border:1px solid rgba(210,216,226,0.85);
    }}
    .ff-chip-link:hover {{ background: {THEME['accent_soft']}; }}
    .ff-actorline a {{ color:#0b57d0 !important; text-decoration:none !important; font-weight:600; }}
    .ff-actorline a:hover {{ text-decoration:underline !important; }}
    .ff-details {{ margin-top: 8px; }}
    .ff-details summary {{ cursor:pointer; font-weight:700; color:#1f2940; }}
    .ff-stars{{position:relative;display:inline-block;font-size:18px;line-height:1;letter-spacing:1px}}
    .ff-stars .bot{{color:#d0d0d0;display:block}}
    .ff-stars .top{{color:#f5c518;position:absolute;left:0;top:0;overflow:hidden;white-space:nowrap;display:block}}

    section[data-testid='stSidebar'] > div:first-child {{
        background: rgba(255,255,255,0.78) !important;
        backdrop-filter: blur(10px);
        border-right: 1px solid rgba(255,255,255,0.5);
    }}

    div[data-testid='stTextInput'] > div > div,
    div[data-testid='stTextArea'] > div > div,
    div[data-baseweb='select'] {{
        background: rgba(255,255,255,0.96) !important;
        border: 1px solid rgba(214,220,229,0.96) !important;
        border-radius: 18px !important;
        box-shadow: none !important;
    }}
    div[data-testid='stTextInput'] input,
    div[data-testid='stTextArea'] textarea {{
        color: #1f2940 !important;
        font-size: 1rem !important;
    }}
    div[data-testid='stTextArea'] textarea {{ min-height: 98px !important; }}

    div[data-testid='stCheckbox'] label,
    div[data-testid='stRadio'] label,
    div[data-testid='stSelectbox'] label,
    div[data-testid='stMultiSelect'] label,
    div[data-testid='stTextInput'] label,
    div[data-testid='stTextArea'] label {{
        color: #1f2940 !important;
        font-weight: 600 !important;
    }}

    .stButton > button, button[kind='secondary'], button[kind='tertiary'] {{
        border-radius: 16px !important;
        border: 1px solid rgba(212,218,228,0.96) !important;
        background: rgba(255,255,255,0.96) !important;
        color: #1f2940 !important;
        min-height: 46px !important;
        padding: 0 16px !important;
        box-shadow: {THEME['bubble_shadow']} !important;
        font-weight: 700 !important;
    }}
    .stButton > button[kind='primary'] {{
        background: {THEME['accent']} !important;
        border-color: {THEME['accent']} !important;
        color: white !important;
    }}

    .ff-field-label {{
        color: #1f2940 !important;
        font-weight: 600 !important;
        margin: 2px 0 4px 2px;
    }}
    .ff-clear-col button {{
        min-width: 40px !important;
        width: 40px !important;
        height: 40px !important;
        padding: 0 !important;
        font-size: 20px !important;
        border-radius: 14px !important;
    }}

    div[data-testid='stExpander'] details summary p {{ font-weight: 700 !important; color:#1f2940 !important; }}
    .stAlert {{ border-radius: 18px !important; }}

    .ff-panel-top {{
        background: {THEME['bubble_bg']};
        border: 1px solid {THEME['bubble_border']};
        border-radius: {THEME['bubble_radius']};
        box-shadow: {THEME['bubble_shadow']};
        backdrop-filter: blur(12px);
        padding: 8px 12px 12px 12px;
        margin-bottom: 14px;
    }}
    div[data-testid='stVerticalBlockBorderWrapper'] {{
        background: {THEME['bubble_bg']} !important;
        border: 1px solid {THEME['bubble_border']} !important;
        border-radius: {THEME['bubble_radius']} !important;
        box-shadow: {THEME['bubble_shadow']} !important;
        backdrop-filter: blur(12px);
        padding: 8px 10px 6px 10px !important;
        margin: 0 0 14px 0 !important;
    }}
    div[data-testid='stVerticalBlockBorderWrapper'] > div {{
        background: transparent !important;
    }}
    .ff-preview-note {{
        background: rgba(255, 245, 204, 0.82);
        color: #5a4606;
        border: 1px solid rgba(230, 198, 86, 0.65);
        border-radius: 16px;
        padding: 10px 12px;
        margin: 10px 0 8px 0;
    }}
    .ff-result-wrap {{ margin: 12px 0 20px 0; }}

    @media (max-width: 900px) {{
        .ff-title {{ font-size: 2.5rem; }}
        .main .block-container {{ padding-left: 12px !important; padding-right: 12px !important; }}
    }}
    @media (max-width: 520px) {{
        .ff-title {{ font-size: 2.2rem; }}
        .main .block-container {{ padding-left: 8px !important; padding-right: 8px !important; }}
        .ff-clear-col button {{
            min-width: 34px !important;
            width: 34px !important;
            height: 34px !important;
            font-size: 18px !important;
            border-radius: 12px !important;
        }}
        div[data-testid='stTextInput'] input,
        div[data-testid='stTextArea'] textarea {{
            font-size: 0.96rem !important;
        }}
        div[data-testid='stTextArea'] textarea {{ min-height: 84px !important; }}
    }}
    </style>
    """
    st.markdown(css, unsafe_allow_html=True)

apply_theme()

# ================== API ==================
def sa_get(path: str, params: dict):
    if not RAPIDAPI_KEY:
        raise RuntimeError("RAPIDAPI_KEY manquante")
    r = requests.get(
        f"{BASE_URL}{path}",
        headers={"X-RapidAPI-Key": RAPIDAPI_KEY, "X-RapidAPI-Host": RAPIDAPI_HOST},
        params=params,
        timeout=25,
    )
    if not r.ok:
        raise RuntimeError(f"API ERROR {r.status_code}: {r.text[:300]}")
    return r.json()

def api_is_quota_error(msg: str) -> bool:
    t = norm_text(msg)
    return "429" in t or "quota" in t or "monthly quota" in t or "too many requests" in t

@st.cache_data(show_spinner=False, ttl=86400)
def omdb_fetch(imdb_id: str):
    if not OMDB_API_KEY or not imdb_id:
        return None
    try:
        r = requests.get(
            "https://www.omdbapi.com/",
            params={"i": imdb_id, "apikey": OMDB_API_KEY, "tomatoes": "true"},
            timeout=20,
        )
        if not r.ok:
            return None
        data = r.json()
        if data.get("Response") == "True":
            return data
    except Exception:
        return None
    return None

def critic_score_and_sources(show: dict):
    api_rating = show.get("rating", None)
    api_score = float(api_rating) if isinstance(api_rating, (int, float)) else None

    imdb_id = show.get("imdbId") or show.get("imdbID") or None
    data = omdb_fetch(imdb_id) if imdb_id else None

    rt = None
    meta = None
    imdb = None
    if data:
        try:
            if data.get("imdbRating") and data.get("imdbRating") != "N/A":
                imdb = float(data["imdbRating"])
        except Exception:
            pass
        try:
            if data.get("Metascore") and data.get("Metascore") != "N/A":
                meta = int(data["Metascore"])
        except Exception:
            pass
        try:
            for r in data.get("Ratings", []) or []:
                if r.get("Source") == "Rotten Tomatoes":
                    v = r.get("Value", "")
                    if v.endswith("%"):
                        rt = int(v.replace("%", "").strip())
        except Exception:
            pass

    parts = []
    if imdb is not None:
        parts.append(f"IMDb {imdb:.1f}/10")
    if meta is not None:
        parts.append(f"Meta {meta}/100")
    if rt is not None:
        parts.append(f"RT {rt}%")
    if not parts and api_score is not None:
        parts.append(f"Score {int(api_score)}/100")

    if rt is not None:
        score = float(rt)
    elif meta is not None:
        score = float(meta)
    elif imdb is not None:
        score = float(imdb * 10.0)
    elif api_score is not None:
        score = float(api_score)
    else:
        score = None

    return score, (" · ".join(parts) if parts else "")

def actors_list_from_omdb(show: dict):
    imdb_id = show.get("imdbId") or show.get("imdbID") or None
    data = omdb_fetch(imdb_id) if imdb_id else None
    if not data:
        return []
    a = data.get("Actors")
    if isinstance(a, str) and a.strip() and a.strip().upper() != "N/A":
        return [x.strip() for x in a.split(",") if x.strip()]
    return []

def country_from_omdb(show: dict):
    imdb_id = show.get("imdbId") or show.get("imdbID") or None
    data = omdb_fetch(imdb_id) if imdb_id else None
    if not data:
        return ""
    c = data.get("Country")
    if isinstance(c, str) and c.strip() and c.strip().upper() != "N/A":
        return c.strip()
    return ""

def search_by_title(title: str, country: str, show_type: str, lang: str):
    data = sa_get("/shows/search/title", {
        "title": title,
        "country": country,
        "show_type": show_type,
        "series_granularity": "show",
        "output_language": lang,
    })
    return data if isinstance(data, list) else []

def search_by_keyword(keyword: str, country: str, show_type: str, lang: str):
    res = sa_get("/shows/search/filters", {
        "country": country,
        "show_type": show_type,
        "keyword": keyword,
        "series_granularity": "show",
        "output_language": lang,
    })
    return res.get("shows", []) if isinstance(res, dict) else []

# ================== OPTIONAL OLLAMA ==================
def ollama_is_up() -> bool:
    try:
        r = requests.get(f"{OLLAMA_URL}/api/tags", timeout=2)
        return r.ok
    except Exception:
        return False

def ollama_pack(description: str):
    prompt = f"""
Réponds UNIQUEMENT avec un JSON valide:
{{"titles":[...], "queries":[...]}}

Règles:
- Si tu reconnais le titre exact, mets-le en PREMIER dans titles.
- titles: 3 à 7 titres max.
- queries: 4 à 7 requêtes max, courtes.
- pas de phrases longues.

Souvenir: {description}
""".strip()
    r = requests.post(
        f"{OLLAMA_URL}/api/generate",
        json={
            "model": OLLAMA_MODEL,
            "prompt": prompt,
            "stream": False,
            "options": {"temperature": 0.2, "num_predict": 260}
        },
        timeout=45,
    )
    if not r.ok:
        raise RuntimeError(f"Ollama ERROR {r.status_code}: {r.text[:300]}")
    txt = (r.json().get("response", "") or "").strip()
    try:
        return json.loads(txt)
    except Exception:
        start = txt.find("{")
        end = txt.rfind("}")
        if start == -1 or end == -1 or end <= start:
            return {"titles": [], "queries": []}
        try:
            return json.loads(txt[start:end + 1])
        except Exception:
            return {"titles": [], "queries": []}

# ================== PREVIEW FALLBACK ==================
def build_mock_result(query: str, selected_ids, actor_name: str = ""):
    qn = norm_text(query)
    likely_edge = any(x in qn for x in ["extraterrestre", "alien", "boucle", "rena", "ressusc", "revit", "tom cruise", "edge of tomorrow", "live die repeat"]) or bool(actor_name)
    if actor_name:
        title = f"Films probables avec {actor_name}"
        overview = f"Aperçu visuel généré automatiquement pour la recherche acteur “{actor_name}”."
        actors = [actor_name, "Tom Cruise", "Emily Blunt"]
        links = [
            {"service": {"name": "Prime Video", "id": "prime"}, "type": "subscription", "link": "#"},
            {"service": {"name": "HBO Max", "id": "max"}, "type": "subscription", "link": "#"},
        ]
        year = 2014
        country = "United States"
    elif likely_edge:
        title = "Edge of Tomorrow"
        overview = "Dans un futur proche, un soldat meurt puis revit encore et encore la même journée au cœur d'une guerre contre des extraterrestres."
        actors = ["Tom Cruise", "Emily Blunt", "Bill Paxton"]
        links = [
            {"service": {"name": "Prime Video", "id": "prime"}, "type": "subscription", "link": "#"},
            {"service": {"name": "HBO Max", "id": "max"}, "type": "subscription", "link": "#"},
        ]
        year = 2014
        country = "United States"
    else:
        title = "Titre probable"
        overview = f"Aperçu visuel généré parce que l'API ne répond pas pour la requête “{query}”."
        actors = ["Acteur 1", "Actrice 2", "Acteur 3"]
        links = [{"service": {"name": "Netflix", "id": "netflix"}, "type": "subscription", "link": "#"}]
        year = 2020
        country = "France"

    return [{
        "show": {
            "title": title,
            "overview": overview,
            "releaseYear": year,
            "firstAirYear": year,
            "streamingOptions": {"fr": links, "be": links, "ch": links, "gb": links, "us": links},
            "imageSet": {},
            "imdbId": "",
            "id": f"preview_{title}",
            "previewActors": actors,
            "previewCountry": country,
        },
        "rel": 99.0,
        "year": year,
        "score100": 90.0 if likely_edge else 78.0,
        "sources": "Mode aperçu visuel",
        "is_mine": 1 if any(option_on_my_services(o, selected_ids) for o in links) else 0,
    }]

# ================== RENDER ==================
def actor_links_html(actors):
    pieces = []
    for actor in actors:
        label = escape(actor)
        href = f"?actor={quote(actor)}"
        pieces.append(f'<a href="{href}" target="_self">{label}</a>')
    return ", ".join(pieces)

def platform_links_html(options):
    links = []
    for o in options[:5]:
        service = o.get("service") or {}
        name = escape(str(service.get("name") or service.get("id") or "Service"))
        typ = escape(str(o.get("type") or ""))
        link = o.get("link") or o.get("videoLink") or "#"
        links.append(f'<a class="ff-chip-link" href="{escape(link)}" target="_blank">{name}{(" · " + typ) if typ else ""}</a>')
    return "".join(links)

def render_result(item, profile, actor_mode=False):
    show = item["show"]
    title = show.get("title", "Sans titre")
    year = item.get("year") or parse_year_value(show)
    poster = get_poster_url(show)
    score100 = item.get("score100")
    sources = item.get("sources") or ""
    overview = show.get("overview") or ""

    country = profile.get("country", "fr")
    selected_ids = set(profile.get("platform_ids", []))
    show_elsewhere = bool(profile.get("show_elsewhere", False))

    opts_all = ((show.get("streamingOptions") or {}).get(country) or [])
    opts_all = dedupe_streaming_options(opts_all)
    opts_mine = [o for o in opts_all if option_on_my_services(o, selected_ids)]
    opts_mine = dedupe_streaming_options(opts_mine)

    actors = actors_list_from_omdb(show)
    if not actors:
        actors = show.get("previewActors") or []

    country_text = country_from_omdb(show) if OMDB_API_KEY else ""
    if not country_text:
        country_text = show.get("previewCountry") or ""
    iso = iso2_from_country_text(country_text) if country_text else ""
    flag = flag_from_iso2(iso) if iso else ""
    country_label = country_text.split(",")[0].strip() if country_text else ""

    availability = "✅ Dispo sur tes applis" if opts_mine else "❌ Pas dispo sur tes applis"
    availability_class = "ff-availability"
    links_html = ""
    if opts_mine:
        links_html = f'<div class="ff-links">{platform_links_html(opts_mine)}</div>'
    elif show_elsewhere and opts_all:
        links_html = f'<div class="ff-links">{platform_links_html(opts_all)}</div>'

    star = stars_html(score100)
    score5 = ""
    if score100 is not None:
        score5 = f'<span class="ff-muted" style="margin-left:8px">({round(float(score100)/20.0, 1)}/5)</span>'
    flag_html = f'<span class="ff-muted" style="margin-left:10px">{flag} {escape(country_label)}</span>' if (flag or country_label) else ""
    meta_line = f'{star}{score5}{flag_html}' if star else (flag_html if flag_html else "")

    actors_html = ""
    if actors:
        actors_html = f'<div class="ff-actorline ff-muted" style="margin-top:10px">Acteurs : {actor_links_html(actors[:8])}</div>'

    details_parts = []
    if sources:
        details_parts.append(f'<div class="ff-muted" style="margin-top:8px">{escape(sources)}</div>')
    if overview:
        details_parts.append(f'<div style="margin-top:8px; line-height:1.7">{escape(overview)}</div>')
    if actors_html:
        details_parts.append(actors_html)
    details_block = ""
    if details_parts:
        details_block = '<details class="ff-details"><summary>Détails</summary>' + "".join(details_parts) + '</details>'

    card_html = f"""
    <div class="ff-card">
        <h3 style="margin:0 0 8px 0; font-size:2rem; line-height:1.15;">{escape(title)}{f' ({year})' if year else ''}</h3>
        <div>{meta_line}</div>
        <div class="{availability_class}">{availability}</div>
        {links_html}
        {details_block}
    </div>
    """

    st.markdown("<div class='ff-result-wrap'>", unsafe_allow_html=True)
    if poster:
        c1, c2 = st.columns([1, 4])
        with c1:
            st.image(poster, width=140)
        with c2:
            st.markdown(card_html, unsafe_allow_html=True)
    else:
        st.markdown(card_html, unsafe_allow_html=True)
    st.markdown("</div>", unsafe_allow_html=True)

def scroll_to_results():
    st.markdown(
        """
        <script>
        (function() {
            const go = () => {
                const anchor = window.parent.document.getElementById('ff-results-anchor') || document.getElementById('ff-results-anchor');
                if (anchor) {
                    anchor.scrollIntoView({behavior: 'smooth', block: 'start'});
                }
                const active = window.parent.document.activeElement || document.activeElement;
                if (active && typeof active.blur === 'function') active.blur();
            };
            setTimeout(go, 120);
            setTimeout(go, 420);
        })();
        </script>
        """,
        unsafe_allow_html=True,
    )

# ================== QUERY PARAMS / SIDEBAR ==================
qp_actor = st.query_params.get("actor", "")
if isinstance(qp_actor, list):
    qp_actor = qp_actor[0] if qp_actor else ""
if qp_actor and qp_actor != st.session_state.get("last_query", ""):
    st.session_state["actor_search"] = str(qp_actor)
    st.session_state["do_search"] = True
    st.session_state["sort_mode"] = "Note (haute)"
else:
    st.session_state.setdefault("actor_search", "")

with st.sidebar:
    st.markdown(f"### FilmFinder IA")
    st.caption(THEME["name"])
    if st.session_state["entered"]:
        st.radio("Menu", ["Recherche", "Profil"], key="page")
    else:
        st.caption("Accueil")
    if st.session_state.get("bg_image_name"):
        st.caption(f"Fond : {st.session_state['bg_image_name']}")
        if st.button("Changer le fond"):
            st.session_state["bg_image_name"] = ""
            st.rerun()

# ================== HOME ==================
if st.session_state["page"] == "Accueil":
    st.markdown("<h1 class='ff-title'>FilmFinder IA</h1>", unsafe_allow_html=True)
    st.markdown("<div class='ff-subtitle'>Souvenir flou → titres probables → où regarder.</div>", unsafe_allow_html=True)

    with st.form("signup_form"):
        c1, c2, c3, c4 = st.columns(4)
        with c1:
            country = st.selectbox("Pays", ["fr", "be", "ch", "gb", "us"], index=["fr","be","ch","gb","us"].index(profile.get("country","fr")))
        with c2:
            lang = st.selectbox("Langue", ["fr", "en"], index=["fr","en"].index(profile.get("lang","fr")))
        with c3:
            typ = st.selectbox("Type", ["Film", "Série"], index=0 if profile.get("show_type","movie") == "movie" else 1)
        with c4:
            show_elsewhere = st.checkbox("Ailleurs", value=bool(profile.get("show_elsewhere", False)))

        default_names = [SERVICE_BY_ID[sid]["name"] for sid in profile.get("platform_ids", []) if sid in SERVICE_BY_ID]
        chosen_names = st.multiselect("Tes plateformes", options=SERVICE_NAMES, default=default_names)
        platform_ids = [NAME_TO_ID[name] for name in chosen_names]

        enter_btn = st.form_submit_button("Entrer", type="primary")

    if enter_btn:
        if not platform_ids:
            st.warning("Coche au moins 1 plateforme 🙂")
        else:
            new_profile = {
                "country": country,
                "lang": lang,
                "show_type": "movie" if typ == "Film" else "series",
                "platform_ids": platform_ids,
                "show_elsewhere": bool(show_elsewhere),
            }
            save_profile(new_profile)
            st.session_state["entered"] = True
            st.session_state["page"] = "Recherche"
            st.rerun()
    st.stop()

# ================== PROFILE ==================
if st.session_state["page"] == "Profil":
    st.markdown("<h1 class='ff-title' style='font-size:2.4rem'>Profil</h1>", unsafe_allow_html=True)
    with st.form("profile_form"):
        c1, c2, c3, c4 = st.columns(4)
        with c1:
            country = st.selectbox("Pays", ["fr", "be", "ch", "gb", "us"], index=["fr","be","ch","gb","us"].index(profile.get("country","fr")))
        with c2:
            lang = st.selectbox("Langue", ["fr", "en"], index=["fr","en"].index(profile.get("lang","fr")))
        with c3:
            typ = st.selectbox("Type", ["Film", "Série"], index=0 if profile.get("show_type","movie") == "movie" else 1)
        with c4:
            show_elsewhere = st.checkbox("Ailleurs", value=bool(profile.get("show_elsewhere", False)))
        default_names = [SERVICE_BY_ID[sid]["name"] for sid in profile.get("platform_ids", []) if sid in SERVICE_BY_ID]
        chosen_names = st.multiselect("Tes plateformes", options=SERVICE_NAMES, default=default_names)
        platform_ids = [NAME_TO_ID[name] for name in chosen_names]
        ok_btn = st.form_submit_button("Enregistrer", type="primary")

    if ok_btn:
        if not platform_ids:
            st.warning("Coche au moins 1 plateforme 🙂")
        else:
            new_profile = {
                "country": country,
                "lang": lang,
                "show_type": "movie" if typ == "Film" else "series",
                "platform_ids": platform_ids,
                "show_elsewhere": bool(show_elsewhere),
            }
            save_profile(new_profile)
            st.success("Profil enregistré.")
            st.rerun()
    st.stop()

# ================== SEARCH ==================
profile = load_profile()

if not profile.get("platform_ids"):
    st.warning("Crée ton profil avant de chercher.")
    st.stop()

MODE_PRESETS = {
    "Rapide":  {"titles_max": 2, "queries_max": 2, "en_if_under": 6,  "pool": 40,  "omdb_top": 12},
    "Normal":  {"titles_max": 4, "queries_max": 4, "en_if_under": 8,  "pool": 70,  "omdb_top": 18},
    "Profond": {"titles_max": 7, "queries_max": 7, "en_if_under": 999, "pool": 120, "omdb_top": 25},
}

def trigger_search():
    st.session_state["do_search"] = True

q_main_default = "" if st.session_state.get("actor_search") else st.session_state.get("last_typed_main", "")
q_more_default = st.session_state.get("last_typed_more", "")
st.session_state.setdefault("q_main", q_main_default)
st.session_state.setdefault("q_more", q_more_default)

title_box = st.container(border=True)
with title_box:
    st.markdown("<h1 class='ff-title' style='font-size:2.8rem; margin-bottom:0;'>Recherche</h1>", unsafe_allow_html=True)

mode_box = st.container(border=True)
with mode_box:
    mode = st.radio("Mode", ["Rapide", "Normal", "Profond"], horizontal=True, index=1)
    preset = MODE_PRESETS[mode]

if st.session_state.get("actor_search"):
    actor_box = st.container(border=True)
    with actor_box:
        actor = st.session_state["actor_search"]
        st.markdown(f"<div class='ff-inline-note' style='margin:0; box-shadow:none;'>Recherche acteur : <b>{escape(actor)}</b> — recherche automatique des films de cet acteur.</div>", unsafe_allow_html=True)
        if st.button("Retour recherche normale"):
            st.session_state["actor_search"] = ""
            st.session_state["last_results"] = None
            st.session_state["api_preview_notice"] = ""
            st.session_state["api_error_notice"] = ""
            try:
                st.query_params.clear()
            except Exception:
                pass
            st.rerun()

souvenir_box = st.container(border=True)
with souvenir_box:
    st.markdown("<div class='ff-field-label'>Ton souvenir (Entrée lance)</div>", unsafe_allow_html=True)
    col1, col2 = st.columns([12, 1], gap="small")
    with col1:
        q_main = st.text_input(
            "Ton souvenir (Entrée lance)",
            key="q_main",
            label_visibility="collapsed",
            on_change=trigger_search,
            placeholder="Ex: homme extraterrestre renaît",
        )
    with col2:
        st.markdown("<div class='ff-clear-col'>", unsafe_allow_html=True)
        if st.button("✕", key="clear_q_main", help="Vider le souvenir"):
            st.session_state["q_main"] = ""
            st.rerun()
        st.markdown("</div>", unsafe_allow_html=True)

if st.button("Trouver", type="primary"):
    st.session_state["do_search"] = True

details_box = st.container(border=True)
with details_box:
    st.markdown("<div class='ff-field-label'>Détails (optionnel)</div>", unsafe_allow_html=True)
    col3, col4 = st.columns([12, 1], gap="small")
    with col3:
        q_more = st.text_area(
            "Détails (optionnel)",
            key="q_more",
            label_visibility="collapsed",
            placeholder="Acteur/actrice · année approx · pays · plateforme · scène marquante · ambiance · SF/space…",
        )
    with col4:
        st.markdown("<div class='ff-clear-col'>", unsafe_allow_html=True)
        if st.button("✕", key="clear_q_more", help="Vider les détails"):
            st.session_state["q_more"] = ""
            st.rerun()
        st.markdown("</div>", unsafe_allow_html=True)

filters_box = st.container(border=True)
with filters_box:
    with st.expander("Filtres", expanded=False):
        left, right = st.columns(2)
        selected_genres = []
        selected_years = []
        with left:
            st.caption("Genres")
            for g in GENRES:
                if st.checkbox(g, key=f"genre_{g}"):
                    selected_genres.append(g)
        with right:
            st.caption("Années")
            for y in YEARS:
                if st.checkbox(y, key=f"year_{y}"):
                    selected_years.append(int(y))

sort_box = st.container(border=True)
with sort_box:
    sort_mode = st.selectbox(
        "Trier par",
        ["Pertinence", "Année (récent)", "Note (haute)"],
        index=["Pertinence", "Année (récent)", "Note (haute)"].index(st.session_state.get("sort_mode", "Pertinence")),
    )
    st.session_state["sort_mode"] = sort_mode

apps_box = st.container(border=True)
with apps_box:
    only_my_apps = st.checkbox("Uniquement sur mes applis", value=False)

# ================== SEARCH ACTION ==================
if st.session_state["do_search"]:
    st.session_state["do_search"] = False
    st.session_state["api_preview_notice"] = ""
    st.session_state["api_error_notice"] = ""

    country = profile["country"]
    lang = profile["lang"]
    show_type = profile["show_type"]

    if st.session_state.get("actor_search"):
        show_type = "movie"
        q = st.session_state["actor_search"].strip()
    else:
        q = ((st.session_state.get("q_main", "").strip()) + " " + (st.session_state.get("q_more", "").strip())).strip()
        st.session_state["last_typed_main"] = st.session_state.get("q_main", "")
        st.session_state["last_typed_more"] = st.session_state.get("q_more", "")

    if not q:
        st.warning("Écris au moins une phrase 🙂")
        st.stop()

    titles = heuristic_titles_from_query(q)
    queries = []
    if ollama_is_up() and not st.session_state.get("actor_search"):
        try:
            pack = ollama_pack(q)
            titles += pack.get("titles", []) or []
            queries = pack.get("queries", []) or []
        except Exception:
            pass
    if not queries:
        queries = [extract_keywords(q), q]

    qn = norm_text(q)
    actor_hint = ""
    if "tom cruise" in qn:
        actor_hint = "tom cruise"
    else:
        bigrams = re.findall(r"[a-z]+ [a-z]+", qn)
        if bigrams:
            actor_hint = bigrams[0]

    titles = [x for i, x in enumerate(titles) if x and x not in titles[:i]]
    queries = [x for i, x in enumerate(queries) if x and x not in queries[:i]]

    found = []
    errors = []

    for t in titles[:preset["titles_max"]]:
        try:
            found += search_by_title(t, country, show_type, lang)
        except Exception as e:
            errors.append(str(e))
    for kw in queries[:preset["queries_max"]]:
        try:
            found += search_by_keyword(kw, country, show_type, lang)
        except Exception as e:
            errors.append(str(e))
    if (not st.session_state.get("actor_search")) and len(found) < preset["en_if_under"]:
        for kw in queries[:preset["queries_max"]]:
            try:
                found += search_by_keyword(kw, country, show_type, "en")
            except Exception as e:
                errors.append(str(e))

    found = merge_results(found)

    allowed_services = set(profile.get("platform_ids", []))
    enriched = []
    for i, sh in enumerate(found):
        opts_all = ((sh.get("streamingOptions") or {}).get(country) or [])
        opts_all = dedupe_streaming_options(opts_all)
        opts_mine = [o for o in opts_all if option_on_my_services(o, allowed_services)]
        opts_mine = dedupe_streaming_options(opts_mine)
        is_mine = 1 if opts_mine else 0
        rel = relevance_score(sh, q, actor_hint=actor_hint) + 0.30 * is_mine
        year = parse_year_value(sh)
        score100, sources = (None, "")
        if i < preset["omdb_top"]:
            score100, sources = critic_score_and_sources(sh)
        elif isinstance(sh.get("rating"), (int, float)):
            score100 = float(sh["rating"])
            sources = f"Score {int(score100)}/100"
        enriched.append({
            "show": sh,
            "rel": rel,
            "year": year,
            "score100": score100,
            "sources": sources,
            "is_mine": is_mine,
        })

    if selected_genres:
        wanted = {norm_text(g) for g in selected_genres}
        keep = []
        for item in enriched:
            genres = item["show"].get("genres") or []
            norm_genres = {norm_text(g) for g in genres}
            if wanted & norm_genres:
                keep.append(item)
        enriched = keep

    if selected_years:
        enriched = [item for item in enriched if item.get("year") in selected_years]

    if only_my_apps:
        keep = [x for x in enriched if x["is_mine"] == 1]
        enriched = keep if keep else enriched

    if sort_mode == "Pertinence":
        enriched.sort(key=lambda x: (x["rel"], x["is_mine"]), reverse=True)
    elif sort_mode == "Année (récent)":
        enriched.sort(key=lambda x: (x["year"], x["is_mine"]), reverse=True)
    else:
        enriched.sort(key=lambda x: ((x["score100"] is not None), (x["score100"] or -1), x["is_mine"]), reverse=True)

    if enriched:
        st.session_state["last_results"] = enriched[:preset["pool"]]
    else:
        if errors:
            joined = " | ".join(dict.fromkeys(errors))
            if api_is_quota_error(joined):
                st.session_state["api_preview_notice"] = "Mode aperçu visuel : quota API atteint. Je t'affiche une carte d'exemple pour tester l'interface."
            else:
                st.session_state["api_preview_notice"] = "Mode aperçu visuel : l'API n'a pas répondu correctement. Je t'affiche une carte d'exemple pour tester l'interface."
            st.session_state["api_error_notice"] = joined[:400]
            st.session_state["last_results"] = build_mock_result(q, allowed_services, st.session_state.get("actor_search", ""))
        else:
            st.session_state["last_results"] = []

    st.session_state["last_query"] = q
    st.session_state["last_mode"] = mode
    st.session_state["scroll_results"] = True

# ================== DISPLAY RESULTS ==================
results = st.session_state.get("last_results")
if results is not None:
    st.markdown("<div id='ff-results-anchor'></div>", unsafe_allow_html=True)
    st.markdown(
        f"<div class='ff-inline-note'>Requête : <b>{escape(st.session_state.get('last_query', ''))}</b> — Mode : <b>{escape(st.session_state.get('last_mode', ''))}</b></div>",
        unsafe_allow_html=True,
    )
    if st.session_state.get("api_preview_notice"):
        st.markdown(f"<div class='ff-preview-note'>{escape(st.session_state['api_preview_notice'])}</div>", unsafe_allow_html=True)
    if st.session_state.get("api_error_notice"):
        st.caption(st.session_state["api_error_notice"])

    st.markdown(
        f"<div class='ff-inline-note'>✅ Résultats : {min(len(results), 20)} / {len(results)}</div>",
        unsafe_allow_html=True,
    )

    if not results:
        st.info("Aucun résultat pour ces critères.")
    else:
        for item in results[:20]:
            render_result(item, profile, actor_mode=bool(st.session_state.get("actor_search")))

    if st.session_state.get("scroll_results"):
        scroll_to_results()
        st.session_state["scroll_results"] = False
