import os
import re
import json
import html
import base64
import random
from pathlib import Path
from urllib.parse import quote_plus
from datetime import datetime

import requests
import streamlit as st
from dotenv import load_dotenv

load_dotenv()

APP_DIR = Path(__file__).parent
PROFILE_PATH = APP_DIR / "profile.json"
BG_DIR = APP_DIR / "bg"

st.set_page_config(page_title="FilmFinder IA", layout="centered")

TMDB_API_KEY = os.getenv("TMDB_API_KEY", "").strip()
TMDB_BEARER_TOKEN = os.getenv("TMDB_BEARER_TOKEN", "").strip()
try:
    TMDB_API_KEY = st.secrets.get("TMDB_API_KEY", TMDB_API_KEY)
    TMDB_BEARER_TOKEN = st.secrets.get("TMDB_BEARER_TOKEN", TMDB_BEARER_TOKEN)
except Exception:
    pass

TMDB_BASE = "https://api.themoviedb.org/3"
TMDB_IMG = "https://image.tmdb.org/t/p"

SERVICE_CATALOG = [
    {"id": "netflix", "name": "Netflix", "aliases": ["netflix"], "tmdb": [8]},
    {"id": "prime", "name": "Prime Video", "aliases": ["prime", "prime video", "amazon prime", "amazon prime video"], "tmdb": [9, 10, 119]},
    {"id": "disney", "name": "Disney+", "aliases": ["disney", "disney+"], "tmdb": [337]},
    {"id": "max", "name": "HBO Max", "aliases": ["max", "hbo", "hbo max", "hbomax"], "tmdb": [1899, 384]},
    {"id": "apple", "name": "Apple TV+", "aliases": ["apple", "apple tv", "apple tv+"], "tmdb": [350]},
    {"id": "paramount", "name": "Paramount+", "aliases": ["paramount", "paramount+"], "tmdb": [531, 582]},
    {"id": "canal", "name": "Canal+", "aliases": ["canal", "canal+"], "tmdb": [381]},
    {"id": "arte", "name": "Arte", "aliases": ["arte"], "tmdb": []},
    {"id": "france.tv", "name": "France TV", "aliases": ["france tv", "francetv", "france.tv"], "tmdb": []},
    {"id": "molotov", "name": "Molotov", "aliases": ["molotov"], "tmdb": []},
    {"id": "rakuten", "name": "Rakuten TV", "aliases": ["rakuten", "rakuten tv"], "tmdb": [35]},
    {"id": "youtube", "name": "YouTube", "aliases": ["youtube", "youtube movies"], "tmdb": [192]},
]
SERVICE_BY_ID = {s["id"]: s for s in SERVICE_CATALOG}
SERVICE_NAMES = [s["name"] for s in SERVICE_CATALOG]
NAME_TO_ID = {s["name"]: s["id"] for s in SERVICE_CATALOG}

GENRES_MOVIE = {
    28: "Action", 12: "Aventure", 16: "Animation", 35: "Comédie", 80: "Crime", 99: "Documentaire",
    18: "Drame", 10751: "Famille", 14: "Fantastique", 36: "Histoire", 27: "Horreur", 10402: "Musique",
    9648: "Mystère", 10749: "Romance", 878: "Science-fiction", 10770: "Téléfilm", 53: "Thriller",
    10752: "Guerre", 37: "Western"
}
GENRES_TV = {
    10759: "Action", 16: "Animation", 35: "Comédie", 80: "Crime", 99: "Documentaire", 18: "Drame",
    10751: "Famille", 10762: "Enfants", 9648: "Mystère", 10763: "Actualités", 10764: "Téléréalité",
    10765: "Science-fiction", 10766: "Soap", 10767: "Talk", 10768: "Guerre", 37: "Western"
}
GENRES_UI = sorted({*GENRES_MOVIE.values(), *GENRES_TV.values()})
YEARS_UI = [str(y) for y in range(datetime.now().year, 1989, -1)]
STOPWORDS = {
    "le","la","les","un","une","des","de","du","dans","sur","avec","sans","et","ou",
    "qui","que","quoi","dont","au","aux","en","a","à","pour","par","se","sa","son","ses",
    "je","tu","il","elle","on","nous","vous","ils","elles","toujours","film","serie","série",
    "the","a","an","and","or","in","on","with","without","to","of","for","by","from"
}

st.session_state.setdefault("entered", False)
st.session_state.setdefault("page", "Accueil")
st.session_state.setdefault("q_main", "")
st.session_state.setdefault("q_more", "")
st.session_state.setdefault("mode", "Normal")
st.session_state.setdefault("sort_mode", "Pertinence")
st.session_state.setdefault("mine_only", False)
st.session_state.setdefault("selected_genres", [])
st.session_state.setdefault("selected_years", [])
st.session_state.setdefault("last_results", [])
st.session_state.setdefault("last_query", "")
st.session_state.setdefault("scroll_results", False)
st.session_state.setdefault("bg_name", "")
st.session_state.setdefault("notice", "")


def normalize_country(value):
    v = str(value or "FR").strip().upper()
    allowed = {"FR", "US", "GB", "CA", "BE", "CH"}
    return v if v in allowed else "FR"


def normalize_lang(value):
    v = str(value or "fr-FR").strip()
    mapping = {
        "fr": "fr-FR", "fr-fr": "fr-FR", "fr_FR": "fr-FR",
        "en": "en-US", "en-us": "en-US", "en_US": "en-US",
        "en-gb": "en-GB", "en_GB": "en-GB",
    }
    key = v.lower().replace("_", "-")
    return mapping.get(key, v if v in {"fr-FR", "en-US", "en-GB"} else "fr-FR")


def normalize_show_type(value):
    v = str(value or "movie").strip().lower()
    if v in {"film", "movie", "movies"}:
        return "movie"
    if v in {"serie", "série", "series", "tv", "show", "shows"}:
        return "tv"
    return "movie"


def normalize_platform_ids(values):
    out = []
    for raw in (values or []):
        if raw in SERVICE_BY_ID:
            sid = raw
        elif raw in NAME_TO_ID:
            sid = NAME_TO_ID[raw]
        else:
            sid = None
            n = norm_text(str(raw))
            for meta in SERVICE_CATALOG:
                if n == norm_text(meta["name"]) or n in [norm_text(a) for a in meta.get("aliases", [])]:
                    sid = meta["id"]
                    break
        if sid and sid not in out:
            out.append(sid)
    return out or ["netflix", "prime", "disney", "max"]


def load_profile():
    if PROFILE_PATH.exists():
        try:
            data = json.loads(PROFILE_PATH.read_text(encoding="utf-8"))
            return {
                "country": normalize_country(data.get("country", "FR")),
                "lang": normalize_lang(data.get("lang", "fr-FR")),
                "show_type": normalize_show_type(data.get("show_type", "movie")),
                "platform_ids": normalize_platform_ids(data.get("platform_ids", ["netflix", "prime", "disney", "max"])),
                "show_elsewhere": bool(data.get("show_elsewhere", False)),
            }
        except Exception:
            pass
    return {
        "country": "FR",
        "lang": "fr-FR",
        "show_type": "movie",
        "platform_ids": ["netflix", "prime", "disney", "max"],
        "show_elsewhere": False,
    }


def save_profile(profile):
    PROFILE_PATH.write_text(json.dumps(profile, ensure_ascii=False, indent=2), encoding="utf-8")


profile = load_profile()


def norm_text(s: str) -> str:
    if not s:
        return ""
    s = s.lower().strip()
    s = re.sub(r"[’']", "'", s)
    s = re.sub(r"[^a-z0-9àâçéèêëîïôùûüÿñæœ'\s\-\.]", " ", s, flags=re.I)
    return re.sub(r"\s+", " ", s).strip()


def escape(s: str) -> str:
    return html.escape(s or "", quote=True)


def list_bg_images():
    found = []
    if BG_DIR.exists() and BG_DIR.is_dir():
        for p in sorted(BG_DIR.rglob("*")):
            if p.is_file() and p.suffix.lower() in {".jpg", ".jpeg", ".png", ".webp"}:
                found.append(p)
    return found


def file_to_data_uri(path: Path):
    try:
        ext = path.suffix.lower().lstrip(".")
        if ext == "jpg":
            ext = "jpeg"
        raw = base64.b64encode(path.read_bytes()).decode("ascii")
        return f"data:image/{ext};base64,{raw}"
    except Exception:
        return ""


def demo_bg_data_uri():
    svg = """
    <svg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 1080 1920'>
      <defs>
        <linearGradient id='bg' x1='0' y1='0' x2='1' y2='1'>
          <stop offset='0%' stop-color='#0f172a'/>
          <stop offset='100%' stop-color='#0b1324'/>
        </linearGradient>
        <filter id='blur40'><feGaussianBlur stdDeviation='40'/></filter>
      </defs>
      <rect width='1080' height='1920' fill='url(#bg)'/>
      <g opacity='0.38' filter='url(#blur40)'>
        <rect x='45' y='120' width='210' height='320' rx='22' fill='#ef4444'/>
        <rect x='300' y='100' width='240' height='360' rx='22' fill='#3b82f6'/>
        <rect x='600' y='130' width='180' height='280' rx='22' fill='#8b5cf6'/>
        <rect x='820' y='90' width='220' height='340' rx='22' fill='#14b8a6'/>
        <rect x='70' y='540' width='200' height='300' rx='22' fill='#0ea5e9'/>
        <rect x='330' y='500' width='230' height='340' rx='22' fill='#f97316'/>
        <rect x='620' y='560' width='190' height='300' rx='22' fill='#64748b'/>
        <rect x='850' y='620' width='180' height='280' rx='22' fill='#ec4899'/>
      </g>
      <rect width='1080' height='1920' fill='rgba(0,0,0,0.32)'/>
    </svg>
    """.strip()
    raw = base64.b64encode(svg.encode("utf-8")).decode("ascii")
    return f"data:image/svg+xml;base64,{raw}"


def pick_bg():
    bg_files = list_bg_images()
    if bg_files:
        selected = next((p for p in bg_files if p.name == st.session_state.get("bg_name")), None)
        if selected is None:
            selected = random.choice(bg_files)
            st.session_state["bg_name"] = selected.name
        return file_to_data_uri(selected)
    st.session_state["bg_name"] = ""
    return demo_bg_data_uri()

def safe_index(options, value, default=0):
    try:
        return options.index(value)
    except Exception:
        return default


def apply_theme():
    bg = pick_bg()
    css = f"""
    <style>
    html, body, .stApp, [data-testid='stAppViewContainer'] {{
        background: transparent !important;
        color: #17233b !important;
    }}
    [data-testid='stAppViewContainer']::before {{
        content: '';
        position: fixed;
        inset: 0;
        z-index: -2;
        background-image: linear-gradient(rgba(18,23,34,0.28), rgba(18,23,34,0.22)), url('{bg}');
        background-size: cover;
        background-position: center center;
        filter: saturate(1.04);
    }}
    [data-testid='stHeader'] {{ background: transparent !important; }}
    .main .block-container {{
        max-width: 980px !important;
        padding-top: 14px !important;
        padding-bottom: 90px !important;
        background: transparent !important;
    }}

    .ff-title-pill,
    .ff-pill,
    .ff-inline-note,
    .ff-checkbox-shell {{
        display: inline-block;
        background: rgba(255,255,255,0.94);
        border: 1px solid rgba(255,255,255,0.82);
        border-radius: 22px;
        box-shadow: 0 12px 30px rgba(19, 24, 38, 0.10);
        backdrop-filter: blur(12px);
        color: #17233b;
    }}
    .ff-title-pill {{
        padding: 10px 18px;
        margin: 0 0 10px 0;
        border-radius: 20px;
    }}
    .ff-title {{
        margin: 0;
        color: #17233b;
        font-size: 2.45rem;
        line-height: 1;
        font-weight: 800;
    }}
    .ff-subtitle {{
        display: inline-block;
        padding: 10px 14px;
        border-radius: 18px;
        background: rgba(255,255,255,0.80);
        color: rgba(23,35,59,0.82);
        margin: 0 0 14px 0;
        box-shadow: 0 10px 22px rgba(19,24,38,0.08);
        backdrop-filter: blur(10px);
    }}
    .ff-pill {{
        padding: 6px 12px;
        margin: 6px 0 6px 0;
        color: #17233b;
        font-weight: 700;
        border-radius: 999px;
    }}
    .ff-inline-note {{
        padding: 9px 12px;
        margin: 4px 0 10px 0;
        color: rgba(23,35,59,0.88);
        border-radius: 18px;
    }}
    .ff-bubble {{
        display:block;
        width: fit-content;
        max-width: 100%;
        padding: 10px 14px;
        background: rgba(255,255,255,0.94);
        border: 1px solid rgba(255,255,255,0.82);
        border-radius: 20px;
        box-shadow: 0 12px 30px rgba(19, 24, 38, 0.10);
        backdrop-filter: blur(12px);
    }}
    .ff-wide {{ width: 100%; }}
    .ff-note {{ font-size: 0.98rem; color: #223455; }}
    .ff-small {{ font-size: 0.92rem; opacity: 0.9; }}
    .ff-actorline a {{ color:#0b57d0 !important; text-decoration:none !important; font-weight:600; }}
    .ff-actorline a:hover {{ text-decoration:underline !important; }}
    .ff-platforms {{ display:flex; flex-wrap:wrap; gap:8px; margin:8px 0 10px 0; }}
    .ff-chip {{ display:inline-flex; align-items:center; gap:6px; padding:6px 10px; border-radius:999px; background:rgba(255,255,255,0.92); border:1px solid rgba(255,255,255,0.72); box-shadow:0 10px 24px rgba(12,18,31,0.08); }}
    .ff-chip.mine {{ background: rgba(255,79,95,0.16); border-color: rgba(255,79,95,0.30); color:#8b1220; font-weight:700; }}
    .ff-result-card {{ background: rgba(255,255,255,0.93); border:1px solid rgba(255,255,255,0.80); border-radius:28px; box-shadow:0 14px 34px rgba(12,18,31,0.12); backdrop-filter: blur(12px); padding:16px; margin-bottom:18px; }}
    .ff-result-title {{ font-size: 2rem; font-weight:800; color:#17233b; margin:0 0 10px 0; }}
    .ff-meta {{ color:#31415f; font-size:0.98rem; margin-bottom:8px; }}
    .ff-stars .bot {{ color:#d1d5db; }}
    .ff-stars .top {{ color:#fbbf24; position:absolute; overflow:hidden; white-space:nowrap; left:0; top:0; }}
    .ff-stars {{ position:relative; display:inline-block; letter-spacing:2px; font-size:1rem; line-height:1; margin-right:8px; }}

    section[data-testid='stSidebar'] > div:first-child {{
        background: rgba(255,255,255,0.78) !important;
        backdrop-filter: blur(10px);
        border-right: 1px solid rgba(255,255,255,0.5);
    }}

    div[data-testid='stTextInput'] > div > div,
    div[data-testid='stTextArea'] > div > div,
    div[data-baseweb='select'],
    div[data-testid='stMultiSelect'] [data-baseweb='select'] {{
        background: rgba(255,255,255,0.96) !important;
        border: 1px solid rgba(214,220,229,0.96) !important;
        border-radius: 18px !important;
        box-shadow: 0 8px 18px rgba(20, 24, 35, 0.06) !important;
    }}
    div[data-testid='stTextInput'],
    div[data-testid='stTextArea'] {{
        max-width: 360px;
    }}
    div[data-testid='stTextInput'] input,
    div[data-testid='stTextArea'] textarea {{
        color: #17233b !important;
        font-size: 1rem !important;
    }}
    div[data-testid='stTextArea'] textarea {{ min-height: 94px !important; }}

    div[data-testid='stCheckbox'] {{
        display: inline-block;
        background: rgba(255,255,255,0.94);
        border: 1px solid rgba(255,255,255,0.82);
        border-radius: 18px;
        box-shadow: 0 10px 22px rgba(19,24,38,0.08);
        backdrop-filter: blur(10px);
        padding: 6px 12px 6px 10px;
        margin-top: 8px;
    }}

    div[data-testid='stRadio'] > label,
    div[data-testid='stSelectbox'] label,
    div[data-testid='stMultiSelect'] label,
    div[data-testid='stTextInput'] label,
    div[data-testid='stTextArea'] label {{
        color: #17233b !important;
        font-weight: 600 !important;
    }}

    div[data-testid='stRadio'] [role='radiogroup'] {{
        display: inline-flex !important;
        flex-wrap: wrap !important;
        gap: 16px !important;
        background: rgba(255,255,255,0.94) !important;
        border: 1px solid rgba(255,255,255,0.82) !important;
        border-radius: 22px !important;
        box-shadow: 0 10px 22px rgba(19,24,38,0.08) !important;
        backdrop-filter: blur(10px) !important;
        padding: 10px 14px !important;
    }}

    .stButton > button, button[kind='secondary'], button[kind='tertiary'] {{
        border-radius: 16px !important;
        border: 1px solid rgba(212,218,228,0.96) !important;
        background: rgba(255,255,255,0.96) !important;
        color: #17233b !important;
        min-height: 46px !important;
        padding: 0 16px !important;
        box-shadow: 0 10px 22px rgba(19,24,38,0.08) !important;
        font-weight: 700 !important;
    }}
    .stButton > button[kind='primary'] {{
        background: #ff4f5f !important;
        border-color: #ff4f5f !important;
        color: white !important;
    }}
    .ff-clear-col button {{
        min-width: 34px !important;
        width: 34px !important;
        height: 34px !important;
        padding: 0 !important;
        font-size: 17px !important;
        border-radius: 12px !important;
        margin-top: 2px !important;
    }}

    div[data-testid='stExpander'] {{
        background: transparent !important;
        border: none !important;
        box-shadow: none !important;
    }}
    div[data-testid='stExpander'] details {{
        background: rgba(255,255,255,0.94) !important;
        border: 1px solid rgba(255,255,255,0.82) !important;
        border-radius: 22px !important;
        box-shadow: 0 10px 22px rgba(19,24,38,0.08) !important;
        backdrop-filter: blur(10px) !important;
        overflow: hidden;
    }}
    div[data-testid='stExpander'] details summary {{
        padding-top: 2px !important;
        padding-bottom: 2px !important;
    }}
    div[data-testid='stExpander'] details summary p {{ font-weight: 700 !important; color:#17233b !important; }}
    .stAlert {{ border-radius: 18px !important; }}
    .ff-preview-note {{
        background: rgba(255, 245, 204, 0.86);
        color: #5a4606;
        border: 1px solid rgba(230, 198, 86, 0.65);
        border-radius: 16px;
        padding: 10px 12px;
        margin: 10px 0 8px 0;
    }}

    @media (max-width: 900px) {{
        .ff-title {{ font-size: 2.25rem; }}
        .main .block-container {{ padding-left: 12px !important; padding-right: 12px !important; }}
    }}
    @media (max-width: 520px) {{
        .ff-title {{ font-size: 2rem; }}
        .main .block-container {{ padding-left: 8px !important; padding-right: 8px !important; }}
        .ff-title-pill {{ padding: 8px 14px; border-radius: 18px; }}
        .ff-pill {{ padding: 5px 11px; margin: 4px 0 5px 0; }}
        .ff-inline-note {{ padding: 8px 10px; }}
        div[data-testid='stHorizontalBlock'] {{
            flex-wrap: nowrap !important;
            align-items: flex-start !important;
            gap: 8px !important;
        }}
        div[data-testid='stTextInput'],
        div[data-testid='stTextArea'] {{
            max-width: 300px !important;
            min-width: 0 !important;
        }}
        .ff-clear-col button {{
            min-width: 30px !important;
            width: 30px !important;
            height: 30px !important;
            font-size: 15px !important;
            border-radius: 10px !important;
        }}
        div[data-testid='stTextInput'] input,
        div[data-testid='stTextArea'] textarea {{
            font-size: 0.95rem !important;
        }}
        div[data-testid='stTextArea'] textarea {{ min-height: 94px !important; }}
        div[data-testid='stRadio'] [role='radiogroup'] {{ gap: 10px !important; padding: 9px 12px !important; }}
    }}
    </style>
    """
    st.markdown(css, unsafe_allow_html=True)


def stars_html(score_10):
    if score_10 is None:
        return ""
    try:
        pct = max(0.0, min(100.0, float(score_10) * 10))
        score_txt = f"{float(score_10):.1f}/10"
    except Exception:
        return ""
    return f"<span class='ff-stars'><span class='top' style='width:{pct}%' >★★★★★</span><span class='bot'>★★★★★</span></span> <span class='ff-small'>({escape(score_txt)})</span>"


def tmdb_headers():
    headers = {"accept": "application/json"}
    if TMDB_BEARER_TOKEN:
        headers["Authorization"] = f"Bearer {TMDB_BEARER_TOKEN}"
    return headers


def tmdb_get(path: str, params=None):
    if not TMDB_API_KEY and not TMDB_BEARER_TOKEN:
        raise RuntimeError("TMDb non configuré")
    params = dict(params or {})
    if TMDB_API_KEY and not TMDB_BEARER_TOKEN:
        params["api_key"] = TMDB_API_KEY
    r = requests.get(f"{TMDB_BASE}{path}", headers=tmdb_headers(), params=params, timeout=18)
    if r.status_code >= 400:
        raise RuntimeError(f"TMDb {r.status_code}: {r.text[:250]}")
    return r.json()


@st.cache_data(show_spinner=False, ttl=3600)
def get_movie_genres(lang: str):
    try:
        data = tmdb_get("/genre/movie/list", {"language": lang})
        return {g["id"]: g["name"] for g in data.get("genres", [])}
    except Exception:
        return GENRES_MOVIE.copy()


@st.cache_data(show_spinner=False, ttl=3600)
def get_tv_genres(lang: str):
    try:
        data = tmdb_get("/genre/tv/list", {"language": lang})
        return {g["id"]: g["name"] for g in data.get("genres", [])}
    except Exception:
        return GENRES_TV.copy()


def extract_keywords(text: str, max_words: int = 8):
    words = re.findall(r"[a-zA-ZÀ-ÿ0-9']+", text.lower())
    words = [w for w in words if len(w) >= 4 and w not in STOPWORDS]
    out = []
    for w in words:
        if w not in out:
            out.append(w)
        if len(out) >= max_words:
            break
    return " ".join(out)


def heuristic_titles(query: str):
    q = norm_text(query)
    out = []
    if any(x in q for x in ["boucle", "revit", "revivre", "meme journee", "même journée", "rena", "ressusc", "time loop"]):
        out += ["Edge of Tomorrow", "Palm Springs", "Un jour sans fin", "Happy Death Day"]
    if "tom cruise" in q:
        out.insert(0, "Edge of Tomorrow")
    if any(x in q for x in ["extraterrestre", "alien"]) and any(x in q for x in ["boucle", "revit", "journee", "journée", "rena"]):
        out.insert(0, "Edge of Tomorrow")
    uniq = []
    for t in out:
        if t not in uniq:
            uniq.append(t)
    return uniq


def normalize_provider_name(name: str):
    t = norm_text(name).replace(".", " ").replace("+", " + ")
    t = re.sub(r"\s+", " ", t).strip()
    return t


def provider_matches_selected(provider: dict, selected_ids):
    provider_id = provider.get("provider_id")
    provider_name = normalize_provider_name(provider.get("provider_name", ""))
    for sid in selected_ids:
        meta = SERVICE_BY_ID.get(sid)
        if not meta:
            continue
        if provider_id in meta.get("tmdb", []):
            return True
        aliases = [normalize_provider_name(a) for a in meta.get("aliases", [])] + [normalize_provider_name(meta.get("name", sid))]
        if any(a and (a in provider_name or provider_name in a) for a in aliases):
            return True
    return False


@st.cache_data(show_spinner=False, ttl=1800)
def fetch_details(media_type: str, tmdb_id: int, lang: str, country: str):
    detail = tmdb_get(f"/{media_type}/{tmdb_id}", {"language": lang})
    try:
        providers_raw = tmdb_get(f"/{media_type}/{tmdb_id}/watch/providers")
        providers = (((providers_raw or {}).get("results") or {}).get(country) or {})
    except Exception:
        providers = {}
    return {"detail": detail, "providers": providers}


def build_item(hit: dict, lang: str, country: str, selected_ids):
    media_type = hit.get("media_type")
    if media_type not in {"movie", "tv"}:
        return None
    tmdb_id = hit.get("id")
    enriched = fetch_details(media_type, tmdb_id, lang, country)
    detail = enriched["detail"]
    providers = enriched["providers"]
    title = detail.get("title") or detail.get("name") or hit.get("title") or hit.get("name") or "Sans titre"
    year = (detail.get("release_date") or detail.get("first_air_date") or "")[:4]
    genres_map = get_movie_genres(lang) if media_type == "movie" else get_tv_genres(lang)
    genre_names = [genres_map.get(gid, "") for gid in detail.get("genre_ids", []) or []]
    if not genre_names:
        genre_names = [g.get("name", "") for g in detail.get("genres", [])]
    cast = [c.get("name", "") for c in (detail.get("credits", {}) or {}).get("cast", [])[:8]] if detail.get("credits") else []
    if not cast:
        try:
            credits = tmdb_get(f"/{media_type}/{tmdb_id}/credits", {"language": lang})
            cast = [c.get("name", "") for c in credits.get("cast", [])[:8]]
        except Exception:
            cast = []
    provider_list = []
    for key in ["flatrate", "ads", "free", "rent", "buy"]:
        for p in providers.get(key, []) or []:
            if not any(x.get("provider_id") == p.get("provider_id") for x in provider_list):
                provider_list.append(p)
    mine = any(provider_matches_selected(p, selected_ids) for p in provider_list)
    country_txt = ""
    if media_type == "movie":
        pcs = detail.get("production_countries") or []
        if pcs:
            country_txt = pcs[0].get("name", "")
    else:
        oc = detail.get("origin_country") or []
        if oc:
            country_txt = oc[0]
    imdb_id = detail.get("imdb_id")
    external_link = f"https://www.themoviedb.org/{'movie' if media_type=='movie' else 'tv'}/{tmdb_id}"
    if imdb_id:
        external_link = f"https://www.imdb.com/title/{imdb_id}/"
    return {
        "id": f"{media_type}:{tmdb_id}",
        "media_type": media_type,
        "tmdb_id": tmdb_id,
        "title": title,
        "year": year,
        "overview": detail.get("overview") or hit.get("overview") or "",
        "vote": detail.get("vote_average"),
        "poster": f"{TMDB_IMG}/w342{detail.get('poster_path')}" if detail.get("poster_path") else "",
        "backdrop": f"{TMDB_IMG}/w780{detail.get('backdrop_path')}" if detail.get("backdrop_path") else "",
        "genres": [g for g in genre_names if g],
        "cast": [c for c in cast if c],
        "providers": provider_list,
        "is_mine": mine,
        "country": country_txt,
        "link": external_link,
    }


def relevance_score(item: dict, query: str):
    q = norm_text(query)
    hay = norm_text(" ".join([
        item.get("title", ""),
        item.get("overview", ""),
        " ".join(item.get("genres", [])),
        " ".join(item.get("cast", [])),
    ]))
    words = [w for w in q.split() if len(w) >= 4 and w not in STOPWORDS]
    score = 0.0
    for w in set(words):
        if w in hay:
            score += 1.0
    if any(x in q for x in ["boucle", "revit", "rena", "ressusc", "time loop"]):
        if any(x in hay for x in ["loop", "day", "repeat", "boucle", "tempore"]):
            score += 2.0
    if "edge of tomorrow" in norm_text(item.get("title", "")) and any(x in q for x in ["tom cruise", "alien", "extraterrestre", "boucle", "rena"]):
        score += 3.0
    if item.get("is_mine"):
        score += 0.4
    return score


def search_tmdb_free(main_query: str, more: str, show_type: str, lang: str, country: str, selected_ids, mode: str):
    if not TMDB_API_KEY and not TMDB_BEARER_TOKEN:
        raise RuntimeError("Ajoute TMDB_API_KEY ou TMDB_BEARER_TOKEN dans les Secrets Streamlit pour activer la recherche réelle.")

    search_paths = []
    if show_type == "movie":
        search_paths = ["movie"]
    elif show_type == "tv":
        search_paths = ["tv"]
    else:
        search_paths = ["movie", "tv"]

    query_full = " ".join(x for x in [main_query.strip(), more.strip()] if x.strip()).strip()
    queries = [main_query.strip()]
    if mode in {"Normal", "Profond"}:
        kw = extract_keywords(query_full)
        if kw and kw not in queries:
            queries.append(kw)
    if mode == "Profond":
        for t in heuristic_titles(query_full):
            if t not in queries:
                queries.append(t)

    hits = {}
    page_limit = 1 if mode == "Rapide" else 2 if mode == "Normal" else 3
    for q in queries[: 1 if mode == "Rapide" else 3]:
        for path in search_paths:
            for page in range(1, page_limit + 1):
                try:
                    data = tmdb_get(f"/search/{path}", {"query": q, "language": lang, "page": page, "include_adult": False})
                except Exception:
                    continue
                for r in data.get("results", []):
                    r["media_type"] = "movie" if path == "movie" else "tv"
                    hits[(r["media_type"], r["id"])] = r

    items = []
    for r in list(hits.values())[: (10 if mode == "Rapide" else 20 if mode == "Normal" else 28)]:
        try:
            item = build_item(r, lang, country, selected_ids)
            if item:
                item["score"] = relevance_score(item, query_full)
                items.append(item)
        except Exception:
            continue
    return items


def search_actor_movies(actor_name: str, show_type: str, lang: str, country: str, selected_ids):
    if not actor_name.strip():
        return []
    data = tmdb_get("/search/person", {"query": actor_name, "language": lang, "include_adult": False})
    people = data.get("results", [])
    if not people:
        return []
    person = people[0]
    credits = tmdb_get(f"/person/{person['id']}/combined_credits", {"language": lang})
    all_credits = credits.get("cast", [])
    wanted = []
    wanted_type = "movie" if show_type == "movie" else "tv" if show_type == "tv" else None
    for c in all_credits:
        if c.get("media_type") not in {"movie", "tv"}:
            continue
        if wanted_type and c.get("media_type") != wanted_type:
            continue
        wanted.append(c)
    wanted.sort(key=lambda x: (x.get("vote_count", 0), x.get("popularity", 0)), reverse=True)
    items = []
    seen = set()
    for c in wanted[:24]:
        key = (c.get("media_type"), c.get("id"))
        if key in seen:
            continue
        seen.add(key)
        try:
            item = build_item(c, lang, country, selected_ids)
            if item:
                item["score"] = (item.get("vote") or 0) + (0.4 if item.get("is_mine") else 0)
                items.append(item)
        except Exception:
            continue
    return items


def apply_filters_and_sort(items, selected_genres, selected_years, mine_only, sort_mode):
    out = []
    sel_genres = set(selected_genres or [])
    sel_years = set(selected_years or [])
    for it in items:
        if mine_only and not it.get("is_mine"):
            continue
        if sel_genres and not (set(it.get("genres", [])) & sel_genres):
            continue
        if sel_years and (it.get("year") not in sel_years):
            continue
        out.append(it)

    if sort_mode == "Note (haute)":
        out.sort(key=lambda x: (x.get("vote") or 0, x.get("is_mine"), x.get("year") or ""), reverse=True)
    elif sort_mode == "Année (récente)":
        out.sort(key=lambda x: (x.get("year") or "", x.get("is_mine"), x.get("vote") or 0), reverse=True)
    else:
        out.sort(key=lambda x: (x.get("score") or 0, x.get("is_mine"), x.get("vote") or 0), reverse=True)
    return out


def render_result(item: dict):
    c1, c2 = st.columns([1.0, 2.6], vertical_alignment="top")
    with c1:
        if item.get("poster"):
            st.image(item["poster"], use_container_width=True)
    with c2:
        st.markdown(f"<div class='ff-result-title'>{escape(item['title'])}{' (' + escape(item['year']) + ')' if item.get('year') else ''}</div>", unsafe_allow_html=True)
        meta_bits = []
        if item.get("vote"):
            meta_bits.append(stars_html(item.get("vote")))
        if item.get("country"):
            meta_bits.append(f"<span class='ff-small'>{escape(item['country'])}</span>")
        if item.get("media_type"):
            meta_bits.append(f"<span class='ff-small'>{'Film' if item['media_type']=='movie' else 'Série'}</span>")
        if meta_bits:
            st.markdown("<div class='ff-meta'>" + " &nbsp; ".join(meta_bits) + "</div>", unsafe_allow_html=True)

        providers = item.get("providers", [])
        if providers:
            chips = []
            for p in providers:
                cls = "ff-chip mine" if item.get("is_mine") and provider_matches_selected(p, profile.get("platform_ids", [])) else "ff-chip"
                chips.append(f"<span class='{cls}'>{escape(p.get('provider_name',''))}</span>")
            st.markdown("<div class='ff-platforms'>" + "".join(chips[:8]) + "</div>", unsafe_allow_html=True)
        else:
            txt = "✅ Dispo sur tes applis" if item.get("is_mine") else "❌ Pas de plateforme détectée"
            st.markdown(f"<div class='ff-bubble ff-note'>{txt}</div>", unsafe_allow_html=True)

        with st.expander("Détails"):
            if item.get("overview"):
                st.write(item["overview"])
            if item.get("genres"):
                st.caption("Genres : " + ", ".join(item["genres"]))
            if item.get("cast"):
                links = []
                for actor in item["cast"][:6]:
                    links.append(f"<a href='?actor={quote_plus(actor)}#results'>{escape(actor)}</a>")
                st.markdown("<div class='ff-actorline'>Acteurs : " + ", ".join(links) + "</div>", unsafe_allow_html=True)
            st.markdown(f"[Ouvrir la fiche]({item['link']})")


def scroll_to_results():
    st.markdown(
        """
        <script>
        setTimeout(function(){
          const a = window.parent.document.getElementById('results-anchor');
          if(a){ a.scrollIntoView({behavior:'smooth', block:'start'}); }
          const active = window.parent.document.activeElement;
          if(active && typeof active.blur === 'function'){ active.blur(); }
        }, 180);
        </script>
        """,
        unsafe_allow_html=True,
    )


def clear_q_main():
    st.session_state["q_main"] = ""


def clear_q_more():
    st.session_state["q_more"] = ""


def run_search():
    st.session_state["last_query"] = " ".join(x for x in [st.session_state.get("q_main", ""), st.session_state.get("q_more", "")] if x.strip())
    st.session_state["scroll_results"] = True


def actor_mode_name():
    qp = st.query_params
    val = qp.get("actor")
    if isinstance(val, list):
        val = val[0] if val else ""
    return str(val or "")


def clear_actor_mode():
    qp = st.query_params
    qp.clear()
    st.rerun()


apply_theme()

# ---------- PAGE 1: ACCUEIL ----------
if not st.session_state["entered"]:
    st.markdown("<div class='ff-title-pill'><h1>FilmFinder IA</h1></div>", unsafe_allow_html=True)
    st.markdown("<div class='ff-subtitle'>Souvenir flou → titres probables → où regarder.</div>", unsafe_allow_html=True)

    with st.form("profile_form"):
        st.markdown("<div class='ff-bubble ff-wide'>", unsafe_allow_html=True)
        c1, c2, c3, c4 = st.columns([1, 1, 1, 0.7])
        with c1:
            country_options = ["FR", "US", "GB", "CA", "BE", "CH"]
            country = st.selectbox("Pays", country_options, index=safe_index(country_options, normalize_country(profile.get("country")), 0))
        with c2:
            lang_options = ["fr-FR", "en-US", "en-GB"]
            lang = st.selectbox("Langue", lang_options, index=safe_index(lang_options, normalize_lang(profile.get("lang")), 0))
        with c3:
            show_type_ui = st.selectbox("Type", ["Film", "Série"], index=0 if normalize_show_type(profile.get("show_type")) == "movie" else 1)
        with c4:
            show_elsewhere = st.checkbox("Ailleurs", value=profile.get("show_elsewhere", False))

        selected_names = [SERVICE_BY_ID[sid]["name"] for sid in profile.get("platform_ids", []) if sid in SERVICE_BY_ID]
        platforms = st.multiselect("Tes plateformes", SERVICE_NAMES, default=selected_names)
        submit = st.form_submit_button("Entrer")
        st.markdown("</div>", unsafe_allow_html=True)

    if submit:
        profile["country"] = country
        profile["lang"] = lang
        profile["show_type"] = "movie" if show_type_ui == "Film" else "tv"
        profile["platform_ids"] = [NAME_TO_ID[x] for x in platforms if x in NAME_TO_ID]
        profile["show_elsewhere"] = show_elsewhere
        save_profile(profile)
        st.session_state["entered"] = True
        st.rerun()
    st.stop()

# ---------- PAGE 2: RECHERCHE ----------
actor_name = actor_mode_name()
st.markdown("<div class='ff-title-pill'><h1 class='ff-title' style='font-size:2.35rem;'>Recherche</h1></div>", unsafe_allow_html=True)

st.markdown("<div class='ff-pill'>Mode</div>", unsafe_allow_html=True)
st.session_state["mode"] = st.radio(
    "Mode",
    ["Rapide", "Normal", "Profond"],
    index=["Rapide", "Normal", "Profond"].index(st.session_state.get("mode", "Normal")),
    horizontal=True,
    label_visibility="collapsed",
)

if actor_name:
    st.markdown(f"<div class='ff-inline-note'>Recherche acteur : <b>{escape(actor_name)}</b> — recherche automatique des {'films' if profile['show_type']=='movie' else 'séries'} de cet acteur.</div>", unsafe_allow_html=True)
    if st.button("Retour recherche normale"):
        clear_actor_mode()

st.markdown("<div class='ff-pill'>Ton souvenir (Entrée lance)</div>", unsafe_allow_html=True)
col1, col2 = st.columns([9.0, 1.05], gap="small")
with col1:
    st.text_input(
        "Ton souvenir (Entrée lance)",
        key="q_main",
        label_visibility="collapsed",
        on_change=run_search,
        placeholder="Ex: homme extraterrestre renaît",
    )
with col2:
    st.markdown("<div class='ff-clear-col'>", unsafe_allow_html=True)
    st.button("✕", key="clear_main", help="Vider le souvenir", on_click=clear_q_main)
    st.markdown("</div>", unsafe_allow_html=True)

st.markdown("<div style='height:2px'></div>", unsafe_allow_html=True)
if st.button("Trouver", type="primary"):
    run_search()

st.markdown("<div class='ff-pill'>Détails (optionnel)</div>", unsafe_allow_html=True)
col3, col4 = st.columns([9.0, 1.05], gap="small")
with col3:
    st.text_area(
        "Détails (optionnel)",
        key="q_more",
        label_visibility="collapsed",
        placeholder="Acteur/actrice · année approx · pays · plateforme · scène marquante · ambiance · SF/space…",
    )
with col4:
    st.markdown("<div class='ff-clear-col'>", unsafe_allow_html=True)
    st.button("✕", key="clear_more", help="Vider les détails", on_click=clear_q_more)
    st.markdown("</div>", unsafe_allow_html=True)

with st.expander("Filtres", expanded=False):
    fg, fy = st.columns(2)
    with fg:
        selected_genres = [g for g in GENRES_UI if st.checkbox(g, value=g in st.session_state.get("selected_genres", []), key=f"genre_{g}")]
    with fy:
        selected_years = [y for y in YEARS_UI[:18] if st.checkbox(y, value=y in st.session_state.get("selected_years", []), key=f"year_{y}")]
    st.session_state["selected_genres"] = selected_genres
    st.session_state["selected_years"] = selected_years

st.markdown("<div class='ff-pill'>Trier par</div>", unsafe_allow_html=True)
st.session_state["sort_mode"] = st.selectbox(
    "Trier par",
    ["Pertinence", "Note (haute)", "Année (récente)"],
    index=["Pertinence", "Note (haute)", "Année (récente)"].index(st.session_state.get("sort_mode", "Pertinence")),
    label_visibility="collapsed",
)

st.markdown("<div class='ff-pill'>Uniquement sur mes applis</div>", unsafe_allow_html=True)
st.session_state["mine_only"] = st.checkbox(
    "Uniquement sur mes applis",
    value=st.session_state.get("mine_only", False),
    label_visibility="collapsed",
)

# Search execution
results = []
error_text = ""
search_needed = bool(st.session_state.get("last_query")) or bool(actor_name)
if search_needed:
    try:
        if actor_name:
            base = search_actor_movies(actor_name, profile["show_type"], profile["lang"], profile["country"], profile.get("platform_ids", []))
        else:
            main_query = st.session_state.get("q_main", "").strip()
            if main_query:
                base = search_tmdb_free(main_query, st.session_state.get("q_more", ""), profile["show_type"], profile["lang"], profile["country"], profile.get("platform_ids", []), st.session_state.get("mode", "Normal"))
            else:
                base = []
        results = apply_filters_and_sort(base, st.session_state.get("selected_genres", []), st.session_state.get("selected_years", []), st.session_state.get("mine_only", False), st.session_state.get("sort_mode", "Pertinence"))
        st.session_state["last_results"] = results
    except Exception as e:
        error_text = str(e)
        results = st.session_state.get("last_results", []) or []
else:
    results = st.session_state.get("last_results", []) or []

st.markdown("<div id='results-anchor' class='ff-scroll-anchor'></div>", unsafe_allow_html=True)
if st.session_state.get("scroll_results"):
    scroll_to_results()
    st.session_state["scroll_results"] = False

if error_text:
    st.markdown(f"<div class='ff-bubble ff-note'>⚠️ {escape(error_text)}</div>", unsafe_allow_html=True)

if not TMDB_API_KEY and not TMDB_BEARER_TOKEN:
    st.markdown("<div class='ff-bubble ff-note'>ℹ️ V1 gratuite prête : ajoute d'abord <b>TMDB_API_KEY</b> dans les Secrets Streamlit pour activer la recherche réelle.</div>", unsafe_allow_html=True)

if search_needed:
    query_label = actor_name if actor_name else st.session_state.get("last_query", "")
    st.markdown(f"<div class='ff-bubble ff-note'>Requête : {escape(query_label)} — Mode : {escape(st.session_state.get('mode','Normal'))}</div>", unsafe_allow_html=True)
    st.markdown(f"<div class='ff-bubble ff-note'>✅ Résultats : {len(results)}</div>", unsafe_allow_html=True)

for item in results:
    st.markdown("<div class='ff-result-card'>", unsafe_allow_html=True)
    render_result(item)
    st.markdown("</div>", unsafe_allow_html=True)
