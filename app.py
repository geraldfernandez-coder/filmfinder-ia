import json
import os
import re
import unicodedata
from datetime import date, timedelta
from pathlib import Path
from urllib.parse import quote

import requests
import streamlit as st
import streamlit.components.v1 as components
from dotenv import load_dotenv

# =========================================================
# CONFIG
# =========================================================
load_dotenv()

RAPIDAPI_KEY = os.getenv("RAPIDAPI_KEY", "").strip()
RAPIDAPI_HOST = os.getenv(
    "RAPIDAPI_HOST", "streaming-availability.p.rapidapi.com"
).strip()
BASE_URL = "https://streaming-availability.p.rapidapi.com"

OLLAMA_URL = os.getenv("OLLAMA_URL", "http://localhost:11434").strip()
OLLAMA_MODEL = os.getenv("OLLAMA_MODEL", "llama3.2:3b").strip()

APP_DIR = Path(__file__).parent
PROFILE_PATH = APP_DIR / "profile.json"

st.set_page_config(page_title="FilmFinder IA", layout="wide")

# =========================================================
# THEMES
# =========================================================
THEMES = {
    "Auto": {},
    "Cinéma vintage": {
        "bg1": "#e8dcc7",
        "bg2": "#fff7ec",
        "accent": "#b85c38",
        "text": "#151515",
        "muted": "rgba(0,0,0,0.68)",
        "card": "rgba(255,255,255,0.92)",
        "border": "rgba(0,0,0,0.12)",
        "input_bg": "#ffffff",
        "input_text": "#111111",
        "emoji": "🎞️",
    },
    "Romance": {
        "bg1": "#ffe5ee",
        "bg2": "#fff9fb",
        "accent": "#ff4d6d",
        "text": "#151515",
        "muted": "rgba(0,0,0,0.68)",
        "card": "rgba(255,255,255,0.93)",
        "border": "rgba(0,0,0,0.10)",
        "input_bg": "#ffffff",
        "input_text": "#111111",
        "emoji": "💕",
    },
    "Science-fiction": {
        "bg1": "#06111f",
        "bg2": "#13233f",
        "accent": "#00d4ff",
        "text": "#f6fbff",
        "muted": "rgba(255,255,255,0.80)",
        "card": "rgba(255,255,255,0.10)",
        "border": "rgba(255,255,255,0.18)",
        "input_bg": "rgba(255,255,255,0.14)",
        "input_text": "#ffffff",
        "emoji": "🚀",
    },
    "Horreur": {
        "bg1": "#0a0a0a",
        "bg2": "#1c0d11",
        "accent": "#ff0033",
        "text": "#fff7f8",
        "muted": "rgba(255,255,255,0.80)",
        "card": "rgba(255,255,255,0.09)",
        "border": "rgba(255,255,255,0.16)",
        "input_bg": "rgba(255,255,255,0.14)",
        "input_text": "#ffffff",
        "emoji": "🩸",
    },
    "Été": {
        "bg1": "#fff1c7",
        "bg2": "#fffdf6",
        "accent": "#ffb703",
        "text": "#151515",
        "muted": "rgba(0,0,0,0.68)",
        "card": "rgba(255,255,255,0.94)",
        "border": "rgba(0,0,0,0.10)",
        "input_bg": "#ffffff",
        "input_text": "#111111",
        "emoji": "☀️",
    },
    "Halloween": {
        "bg1": "#140c20",
        "bg2": "#291938",
        "accent": "#ff7a00",
        "text": "#fff8f2",
        "muted": "rgba(255,255,255,0.80)",
        "card": "rgba(255,255,255,0.10)",
        "border": "rgba(255,255,255,0.16)",
        "input_bg": "rgba(255,255,255,0.14)",
        "input_text": "#ffffff",
        "emoji": "🎃",
    },
    "Armistice": {
        "bg1": "#0c1629",
        "bg2": "#163152",
        "accent": "#3a86ff",
        "text": "#f5f9ff",
        "muted": "rgba(255,255,255,0.80)",
        "card": "rgba(255,255,255,0.10)",
        "border": "rgba(255,255,255,0.16)",
        "input_bg": "rgba(255,255,255,0.14)",
        "input_text": "#ffffff",
        "emoji": "🇫🇷",
    },
    "Fête des mères": {
        "bg1": "#fff0ea",
        "bg2": "#fffdfb",
        "accent": "#ff7aa2",
        "text": "#151515",
        "muted": "rgba(0,0,0,0.68)",
        "card": "rgba(255,255,255,0.94)",
        "border": "rgba(0,0,0,0.10)",
        "input_bg": "#ffffff",
        "input_text": "#111111",
        "emoji": "🌷",
    },
    "Printemps": {
        "bg1": "#e7f5e7",
        "bg2": "#fafffa",
        "accent": "#4caf50",
        "text": "#151515",
        "muted": "rgba(0,0,0,0.68)",
        "card": "rgba(255,255,255,0.94)",
        "border": "rgba(0,0,0,0.10)",
        "input_bg": "#ffffff",
        "input_text": "#111111",
        "emoji": "🌿",
    },
}

THEME_SEED_TITLES = {
    "Cinéma vintage": ["Casablanca", "Vertigo", "The Godfather"],
    "Romance": ["The Notebook", "Titanic", "La La Land"],
    "Science-fiction": ["Interstellar", "Blade Runner 2049", "The Matrix"],
    "Horreur": ["The Shining", "It", "Halloween"],
    "Été": ["Mamma Mia!", "Jaws", "The Beach"],
    "Halloween": ["Halloween", "Scream", "Beetlejuice"],
    "Armistice": ["1917", "Dunkirk", "Saving Private Ryan"],
    "Fête des mères": ["Little Women", "Mamma Mia!", "The Blind Side"],
    "Printemps": ["Amélie", "The Secret Garden", "Big Fish"],
}


def last_sunday_of_may(year: int) -> date:
    d = date(year, 5, 31)
    while d.weekday() != 6:
        d -= timedelta(days=1)
    return d


def choose_auto_theme_name() -> str:
    today = date.today()

    if (today.month == 10 and today.day >= 15) or (today.month == 11 and today.day == 1):
        return "Halloween"
    if today.month in (6, 7, 8):
        return "Été"
    if today.month in (3, 4, 5):
        return "Printemps"
    if today.month == 2 and 10 <= today.day <= 15:
        return "Romance"
    if today.month == 11 and 8 <= today.day <= 12:
        return "Armistice"

    mothers_day = last_sunday_of_may(today.year)
    if mothers_day - timedelta(days=6) <= today <= mothers_day + timedelta(days=1):
        return "Fête des mères"

    pool = ["Cinéma vintage", "Romance", "Science-fiction", "Horreur", "Été"]
    return pool[today.toordinal() % len(pool)]


def resolve_theme_name(theme_name: str) -> str:
    return choose_auto_theme_name() if theme_name == "Auto" else theme_name


def apply_theme(theme_name: str) -> str:
    theme_name = resolve_theme_name(theme_name)
    theme = THEMES[theme_name]

    st.markdown(
        f"""
        <style>
        :root {{
            color-scheme: light !important;
        }}

        html, body, .stApp, [data-testid="stAppViewContainer"] {{
            background: linear-gradient(180deg, {theme["bg1"]} 0%, {theme["bg2"]} 65%, {theme["bg2"]} 100%) !important;
            color: {theme["text"]} !important;
        }}

        [data-testid="stAppViewContainer"]::before {{
            content:"";
            position: fixed;
            inset: 0;
            pointer-events:none;
            background:
                radial-gradient(circle at 18% 10%, rgba(255,255,255,0.08), transparent 30%),
                radial-gradient(circle at 82% 24%, rgba(255,255,255,0.05), transparent 34%),
                repeating-linear-gradient(
                    0deg,
                    rgba(255,255,255,0.015),
                    rgba(255,255,255,0.015) 1px,
                    rgba(0,0,0,0.015) 2px,
                    rgba(0,0,0,0.015) 3px
                );
            opacity: 0.12;
            mix-blend-mode: overlay;
            z-index: 0;
        }}

        .main .block-container {{
            position: relative;
            z-index: 1;
            max-width: 1360px !important;
            margin: 12px auto !important;
            background: {theme["card"]} !important;
            border: 1px solid {theme["border"]} !important;
            border-radius: 20px !important;
            padding: 18px 20px 26px 20px !important;
            box-shadow: 0 16px 42px rgba(0,0,0,0.12) !important;
            backdrop-filter: blur(10px);
        }}

        [data-testid="stSidebar"] > div:first-child {{
            background: {theme["card"]} !important;
            border-right: 1px solid {theme["border"]} !important;
        }}

        [data-testid="stMarkdownContainer"],
        [data-testid="stMarkdownContainer"] * {{
            color: {theme["text"]} !important;
        }}

        label, p, span, small {{
            color: {theme["text"]} !important;
        }}

        .ff-muted {{
            color: {theme["muted"]} !important;
            font-size: 13px;
        }}

        .ff-hero {{
            border: 1px solid {theme["border"]};
            border-radius: 20px;
            padding: 18px 18px 18px 18px;
            margin-bottom: 16px;
            box-shadow: 0 10px 24px rgba(0,0,0,0.10);
            overflow: hidden;
            position: relative;
            min-height: 180px;
            display: flex;
            align-items: end;
            background: rgba(255,255,255,0.18);
        }}

        .ff-hero-bg {{
            position: absolute;
            inset: 0;
            background-size: cover;
            background-position: center;
            filter: blur(0.5px);
            transform: scale(1.03);
        }}

        .ff-hero-overlay {{
            position: absolute;
            inset: 0;
            background:
                linear-gradient(180deg, rgba(0,0,0,0.12), rgba(0,0,0,0.55)),
                linear-gradient(90deg, rgba(255,255,255,0.02), rgba(255,255,255,0.00));
        }}

        .ff-hero-content {{
            position: relative;
            z-index: 2;
            background: linear-gradient(180deg, rgba(255,255,255,0.92), rgba(255,255,255,0.88));
            color: #111111 !important;
            padding: 12px 14px;
            border-radius: 16px;
            max-width: 620px;
            border: 1px solid rgba(255,255,255,0.92);
            box-shadow: 0 6px 18px rgba(0,0,0,0.12);
        }}

        .ff-hero-title {{
            font-size: 28px;
            font-weight: 800;
            color: #111111 !important;
            margin-bottom: 4px;
        }}

        .ff-hero-sub {{
            font-size: 14px;
            color: #111111 !important;
            opacity: 0.90;
        }}

        .ff-labelbox {{
            display: inline-block;
            padding: 3px 8px;
            border-radius: 10px;
            background: linear-gradient(180deg, rgba(255,255,255,0.96), rgba(245,245,245,0.94));
            color: #111111 !important;
            border: 1px solid rgba(220,220,220,0.95);
            margin-bottom: 6px;
        }}

        input, textarea {{
            background: {theme["input_bg"]} !important;
            color: {theme["input_text"]} !important;
            border: 1px solid {theme["border"]} !important;
            border-radius: 12px !important;
        }}

        [data-baseweb="select"] > div {{
            background: {theme["input_bg"]} !important;
            color: {theme["input_text"]} !important;
            border: 1px solid {theme["border"]} !important;
            border-radius: 12px !important;
        }}

        [data-baseweb="select"] * {{
            color: {theme["input_text"]} !important;
        }}

        .stButton > button,
        .stFormSubmitButton > button {{
            background: linear-gradient(180deg, rgba(255,255,255,0.98), rgba(242,242,242,0.95)) !important;
            color: #111111 !important;
            border: 1px solid #d9d9d9 !important;
            border-radius: 12px !important;
            box-shadow: 0 3px 10px rgba(0,0,0,0.10);
            font-weight: 600 !important;
        }}

        .stButton > button:hover,
        .stFormSubmitButton > button:hover {{
            border-color: {theme["accent"]} !important;
        }}

        .ff-card {{
            border: 1px solid {theme["border"]};
            background: {theme["card"]};
            border-radius: 16px;
            padding: 12px;
            margin-top: 10px;
            box-shadow: 0 10px 22px rgba(0,0,0,0.08);
        }}

        .ff-linkbox {{
            display: inline-block;
            padding: 4px 8px;
            margin: 3px 4px 3px 0;
            background: rgba(255,255,255,0.97);
            border: 1px solid #e3e3e3;
            border-radius: 10px;
            color: #111111 !important;
            text-decoration: none !important;
        }}

        .ff-stars {{
            position: relative;
            display: inline-block;
            font-size: 16px;
            line-height: 1;
            letter-spacing: 1px;
        }}

        .ff-stars .bot {{
            color: #d0d0d0;
            display: block;
        }}

        .ff-stars .top {{
            color: {theme["accent"]};
            position: absolute;
            left: 0;
            top: 0;
            overflow: hidden;
            white-space: nowrap;
            display: block;
        }}

        /* croix visuellement dans le champ */
        .ff-x-holder {{
            margin-left: -54px;
            z-index: 10;
            position: relative;
            top: 2px;
        }}

        .ff-x-holder button {{
            width: 42px !important;
            min-width: 42px !important;
            min-height: 36px !important;
            height: 36px !important;
            border-radius: 10px !important;
            padding: 0 !important;
            font-size: 18px !important;
        }}
        </style>
        """,
        unsafe_allow_html=True,
    )
    return theme_name


# =========================================================
# PROFILE
# =========================================================
def load_profile() -> dict:
    if PROFILE_PATH.exists():
        try:
            data = json.loads(PROFILE_PATH.read_text(encoding="utf-8"))
            data.setdefault("country", "fr")
            data.setdefault("lang", "fr")
            data.setdefault("platform_ids", [])
            data.setdefault("ui_theme", "Auto")
            return data
        except Exception:
            pass
    return {"country": "fr", "lang": "fr", "platform_ids": [], "ui_theme": "Auto"}


def save_profile(profile: dict) -> None:
    PROFILE_PATH.write_text(
        json.dumps(profile, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


profile = load_profile()
ACTIVE_THEME_NAME = apply_theme(profile.get("ui_theme", "Auto"))

# =========================================================
# NORMALISATION
# =========================================================
STOPWORDS = {
    "le", "la", "les", "un", "une", "des", "de", "du", "dans", "sur", "avec", "sans",
    "et", "ou", "qui", "que", "quoi", "dont", "au", "aux", "en", "a", "à", "pour",
    "par", "se", "sa", "son", "ses", "je", "tu", "il", "elle", "on", "nous", "vous",
    "ils", "elles", "the", "a", "an", "and", "or", "in", "on", "with", "without", "to",
    "of", "for", "by", "from"
}

FR_NUM = {
    "0": "zéro", "1": "un", "2": "deux", "3": "trois", "4": "quatre", "5": "cinq",
    "6": "six", "7": "sept", "8": "huit", "9": "neuf", "10": "dix", "11": "onze",
    "12": "douze", "13": "treize", "14": "quatorze", "15": "quinze", "16": "seize",
    "17": "dix-sept", "18": "dix-huit", "19": "dix-neuf", "20": "vingt"
}

SYNONYMS = {
    "ecole": ["school"],
    "école": ["school"],
    "maternelle": ["kindergarten", "school"],
    "flic": ["cop", "police"],
    "infiltre": ["undercover"],
    "infiltré": ["undercover"],
    "super": ["super"],
    "heros": ["hero", "superhero"],
    "héros": ["hero", "superhero"],
    "vert": ["green"],
    "jumelles": ["twins"],
    "separees": ["separated"],
    "séparées": ["separated"],
    "naissance": ["birth"],
    "avion": ["plane", "airplane"],
    "crash": ["crash"],
    "ile": ["island"],
    "île": ["island"],
    "deserte": ["deserted", "island"],
    "déserte": ["deserted", "island"],
    "rescape": ["survivor"],
    "rescapé": ["survivor"],
    "naufrage": ["castaway", "survivor"],
    "naufragé": ["castaway", "survivor"],
    "perdu": ["lost"],
}

EXACT_ALIASES = {
    "seul au monde": ["Seul au monde", "Cast Away"],
    "cast away": ["Cast Away", "Seul au monde"],
    "a nous quatre": ["À nous quatre", "The Parent Trap"],
    "à nous quatre": ["À nous quatre", "The Parent Trap"],
}

RULE_HINTS = [
    {
        "if_any": ["super heros vert", "super héros vert", "green superhero", "heros vert", "héros vert"],
        "add_entities": ["Hulk", "The Incredible Hulk", "Green Lantern"],
    },
    {
        "if_any": [
            "seul au monde",
            "cast away",
            "crash avion ile",
            "crash avion île",
            "survivant avion ile",
            "survivant avion île",
            "homme seul ile",
            "homme seul île",
            "ile deserte crash avion",
            "île déserte crash avion",
        ],
        "add_entities": ["Seul au monde", "Cast Away"],
    },
    {
        "if_any": ["a nous 4", "à nous 4", "a nous quatre", "à nous quatre", "jumelles separees naissance", "jumelles séparées naissance"],
        "add_entities": ["À nous quatre", "The Parent Trap"],
    },
    {
        "if_any": ["flic maternelle", "cop kindergarten", "undercover kindergarten", "infiltre maternelle", "infiltré maternelle"],
        "add_entities": ["Un flic à la maternelle", "Kindergarten Cop", "Un flic à la maternelle 2", "Kindergarten Cop 2"],
    },
]

TYPE_PRIORITY = {
    "subscription": 0,
    "free": 1,
    "addon": 2,
    "rent": 3,
    "buy": 4,
}


def strip_accents(text: str) -> str:
    if not text:
        return ""
    return "".join(
        c for c in unicodedata.normalize("NFD", text)
        if unicodedata.category(c) != "Mn"
    )


def norm_text(text: str) -> str:
    if not text:
        return ""
    text = text.strip().lower().replace("’", "'")
    text = re.sub(r"\s+", " ", text)
    return text


def norm_loose(text: str) -> str:
    text = strip_accents(norm_text(text))
    text = re.sub(r"[^a-z0-9'\s-]", " ", text)
    text = re.sub(r"\s+", " ", text).strip()
    return text


def fr_numbers_to_words(text: str) -> str:
    def repl(match):
        return FR_NUM.get(match.group(0), match.group(0))
    return re.sub(r"\b(0|1|2|3|4|5|6|7|8|9|10|11|12|13|14|15|16|17|18|19|20)\b", repl, text)


def titlecase_name(text: str) -> str:
    text = re.sub(r"\s+", " ", text.strip())
    return " ".join(w[:1].upper() + w[1:].lower() for w in text.split(" ") if w)


def prettify_sentence(text: str) -> str:
    text = text.strip()
    if not text:
        return ""
    text = re.sub(r"\s+", " ", text)
    text = text[:1].upper() + text[1:]
    if text[-1] not in ".!?":
        text += "."
    return text


def stable_id(show: dict) -> str:
    return str(
        show.get("id")
        or show.get("imdbId")
        or show.get("tmdbId")
        or f"{show.get('title','')}_{show.get('releaseYear') or show.get('firstAirYear') or ''}"
    )


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


def stars_html(score_0_100):
    if score_0_100 is None:
        return ""
    try:
        pct = max(0.0, min(100.0, float(score_0_100)))
    except Exception:
        return ""
    return (
        f'<span class="ff-stars">'
        f'<span class="top" style="width:{pct}%">★★★★★</span>'
        f'<span class="bot">★★★★★</span>'
        f'</span>'
    )


# =========================================================
# STREAMLIT QUERY PARAMS
# =========================================================
def get_query_params() -> dict:
    if hasattr(st, "query_params"):
        try:
            return dict(st.query_params)
        except Exception:
            return {}
    if hasattr(st, "experimental_get_query_params"):
        try:
            return st.experimental_get_query_params()
        except Exception:
            return {}
    return {}


def clear_query_params() -> None:
    if hasattr(st, "query_params"):
        try:
            st.query_params.clear()
        except Exception:
            pass
        return
    if hasattr(st, "experimental_set_query_params"):
        try:
            st.experimental_set_query_params()
        except Exception:
            pass


# =========================================================
# RAPIDAPI
# =========================================================
def sa_get(path: str, params: dict) -> dict:
    if not RAPIDAPI_KEY:
        raise RuntimeError("RAPIDAPI_KEY manquante dans .env")

    response = requests.get(
        f"{BASE_URL}{path}",
        headers={
            "X-RapidAPI-Key": RAPIDAPI_KEY,
            "X-RapidAPI-Host": RAPIDAPI_HOST,
        },
        params=params,
        timeout=25,
    )
    if not response.ok:
        raise RuntimeError(f"RapidAPI {response.status_code}: {response.text[:200]}")
    return response.json()


@st.cache_data(show_spinner=False, ttl=3600)
def get_services(country: str, lang: str):
    data = sa_get(f"/countries/{country}", {"output_language": lang})
    return data.get("services", []) or []


def dedupe_streaming_options(options):
    seen = set()
    out = []
    for opt in options or []:
        sid = ((opt.get("service") or {}).get("id") or "")
        typ = opt.get("type") or ""
        link = opt.get("link") or opt.get("videoLink") or ""
        key = (sid, typ, link)
        if key in seen:
            continue
        seen.add(key)
        out.append(opt)
    return out


def get_poster_url(show: dict):
    try:
        vs = (show.get("imageSet") or {}).get("verticalPoster") or {}
        return vs.get("w240") or vs.get("w360") or vs.get("w480") or None
    except Exception:
        return None


def search_by_title(country: str, show_type: str, lang: str, title: str):
    try:
        data = sa_get(
            "/shows/search/title",
            {
                "country": country,
                "title": title,
                "show_type": show_type,
                "output_language": lang,
            },
        )
        return data.get("shows", []) or []
    except Exception:
        return []


def search_filters_page(country: str, show_type: str, lang: str, keyword: str, cursor=None):
    params = {
        "country": country,
        "show_type": show_type,
        "keyword": keyword,
        "series_granularity": "show",
        "output_language": lang,
    }
    if cursor:
        params["cursor"] = cursor
    return sa_get("/shows/search/filters", params)


def collect_shows(country: str, show_type: str, lang: str, keyword: str, max_items: int, max_pages: int):
    shows = []
    cursor = None
    for _ in range(max_pages):
        res = search_filters_page(country, show_type, lang, keyword, cursor)
        chunk = res.get("shows", []) if isinstance(res, dict) else []
        shows.extend(chunk)
        if len(shows) >= max_items:
            break
        if not res.get("hasMore"):
            break
        cursor = res.get("nextCursor")
        if not cursor:
            break
    return shows[:max_items]


@st.cache_data(show_spinner=False, ttl=3600)
def get_show_details(show_id: str, country: str, show_type: str, lang: str):
    if not show_id:
        return {}
    try:
        return sa_get(
            f"/shows/{show_id}",
            {
                "country": country,
                "show_type": show_type,
                "output_language": lang,
            },
        )
    except Exception:
        return {}


def group_options_by_service(options: list):
    groups = {}
    for opt in options or []:
        service = opt.get("service") or {}
        sid = (service.get("id") or "").strip()
        name = (service.get("name") or sid or "").strip()
        if not name:
            continue
        typ = (opt.get("type") or "").strip().lower()
        link = (opt.get("link") or opt.get("videoLink") or "").strip()

        key = sid if sid else name
        if key not in groups:
            groups[key] = {"id": sid, "name": name, "opts": []}
        groups[key]["opts"].append({"type": typ, "link": link})

    out = list(groups.values())
    for g in out:
        seen = set()
        ded = []
        for item in g["opts"]:
            key = (item["type"], item["link"])
            if key in seen:
                continue
            seen.add(key)
            ded.append(item)
        ded.sort(key=lambda x: TYPE_PRIORITY.get(x["type"], 99))
        g["opts"] = ded

    out.sort(key=lambda x: x["name"].lower())
    return out


def pick_primary_option(opts: list):
    if not opts:
        return None, []
    for opt in opts:
        if opt["type"] == "subscription":
            return opt, [x for x in opts if x != opt]
    return opts[0], opts[1:]


# =========================================================
# THEME POSTER
# =========================================================
@st.cache_data(show_spinner=False, ttl=86400)
def get_theme_background_poster(theme_name: str, country: str, lang: str):
    seed_titles = THEME_SEED_TITLES.get(theme_name, [])
    for title in seed_titles:
        try:
            results = search_by_title(country, "movie", lang, title)
            if not results:
                results = search_by_title("us", "movie", lang, title)
            for item in results:
                poster = get_poster_url(item)
                if poster:
                    return poster
        except Exception:
            continue
    return ""


# =========================================================
# BANDE-ANNONCE DIRECTE YOUTUBE
# =========================================================
@st.cache_data(show_spinner=False, ttl=86400)
def trailer_direct_url(title: str, year=None):
    if not title:
        return ""

    query = f"{title} {year if year else ''} official trailer bande annonce"
    headers = {
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/122.0.0.0 Safari/537.36"
        )
    }

    try:
        response = requests.get(
            "https://www.youtube.com/results",
            params={"search_query": query},
            headers=headers,
            timeout=12,
        )
        text = response.text
        ids = re.findall(r"watch\\?v=([A-Za-z0-9_-]{11})", text)
        if not ids:
            ids = re.findall(r'"videoId":"([A-Za-z0-9_-]{11})"', text)
        seen = set()
        ids = [x for x in ids if not (x in seen or seen.add(x))]
        if ids:
            return f"https://www.youtube.com/watch?v={ids[0]}"
    except Exception:
        return ""

    return ""


# =========================================================
# OLLAMA INTERNE
# =========================================================
@st.cache_data(show_spinner=False, ttl=3600)
def ollama_infer_entities(story: str, actor: str):
    story = (story or "").strip()
    actor = (actor or "").strip()
    if not story and not actor:
        return {"entities": [], "queries": []}

    prompt = f"""
Réponds UNIQUEMENT en JSON strict :
{{"entities":[...], "queries":[...]}}

- entities: 3 à 8 titres/franchises/personnages probables
- queries: 4 à 8 requêtes courtes FR+EN

Souvenir: {story}
Acteur: {actor}
JSON:
""".strip()

    try:
        response = requests.post(
            f"{OLLAMA_URL}/api/generate",
            json={"model": OLLAMA_MODEL, "prompt": prompt, "stream": False},
            timeout=45,
        )
        if not response.ok:
            return {"entities": [], "queries": []}
        txt = response.json().get("response", "") or ""
        match = re.search(r"\{.*\}", txt, flags=re.S)
        if not match:
            return {"entities": [], "queries": []}
        data = json.loads(match.group(0))

        def clean_list(values, limit):
            out = []
            seen = set()
            if not isinstance(values, list):
                return out
            for value in values:
                if isinstance(value, str) and value.strip():
                    key = norm_loose(value)
                    if key not in seen:
                        seen.add(key)
                        out.append(value.strip())
            return out[:limit]

        return {
            "entities": clean_list(data.get("entities", []), 8),
            "queries": clean_list(data.get("queries", []), 8),
        }
    except Exception:
        return {"entities": [], "queries": []}


# =========================================================
# SEARCH LOGIC
# =========================================================
def merge_results(items):
    out = {}
    for show in items:
        out[stable_id(show)] = show
    return list(out.values())


def showtype_to_list(choice: str):
    if choice == "Films":
        return ["movie"]
    if choice == "Séries":
        return ["series"]
    return ["movie", "series"]


def exact_alias_titles(query: str):
    q = norm_loose(query)
    titles = [query]
    for k, vals in EXACT_ALIASES.items():
        if q == norm_loose(k):
            titles.extend(vals)
    out = []
    seen = set()
    for t in titles:
        key = norm_loose(t)
        if key not in seen:
            seen.add(key)
            out.append(t)
    return out


def apply_rule_hints(story: str):
    story_loose = norm_loose(story)
    out = []
    seen = set()
    for rule in RULE_HINTS:
        for trig in rule.get("if_any", []):
            if norm_loose(trig) in story_loose:
                for ent in rule.get("add_entities", []):
                    key = norm_loose(ent)
                    if key not in seen:
                        seen.add(key)
                        out.append(ent)
                break
    return out


def build_query_variants(story: str, actor: str, mode: str):
    story = (story or "").strip()
    actor = (actor or "").strip()
    variants = []

    if story:
        story_words = fr_numbers_to_words(story)
        variants.extend(
            [
                story,
                story_words,
                strip_accents(story),
                strip_accents(story_words),
                f'"{story}"',
                f'"{story_words}"',
                extract_keywords(story),
                extract_keywords(story_words),
            ]
        )

        words = [norm_loose(w) for w in re.findall(r"[A-Za-zÀ-ÿ0-9']+", story)]
        translated = []
        for w in words:
            if w in SYNONYMS:
                translated.extend(SYNONYMS[w])
        if translated:
            variants.append(" ".join(translated))

        variants.extend(apply_rule_hints(story))

    if actor:
        variants.extend([actor, strip_accents(actor), f"{actor} film", f"{actor} movie"])

    if mode != "Rapide":
        ai = ollama_infer_entities(story, actor)
        variants.extend(ai.get("entities", []))
        variants.extend(ai.get("queries", []))

    out = []
    seen = set()
    for v in variants:
        v = (v or "").strip()
        if not v:
            continue
        key = norm_loose(v)
        if key not in seen:
            seen.add(key)
            out.append(v)
    return out


def exact_title_match_score(title: str, query: str) -> int:
    t = norm_loose(title)
    q = norm_loose(query)
    if not t or not q:
        return 0
    if t == q:
        return 3
    if q in t or t in q:
        return 1
    return 0


def relevance_score(show: dict, user_text: str):
    title = norm_loose(show.get("title", ""))
    overview = norm_loose(show.get("overview", ""))
    hay = f"{title} {overview}".strip()
    q = norm_loose(user_text)

    score = 0.0
    if q and (q in title or title in q):
        score += 10.0

    words = [w for w in q.split() if len(w) >= 4 and w not in STOPWORDS]
    for w in set(words):
        if w in hay:
            score += 1.2
    return score


def build_raw_items(story: str, actor: str, mode: str, prof: dict, show_types: list):
    country = prof["country"]
    lang = prof["lang"]
    allowed = set(prof.get("platform_ids", []))

    presets = {
        "Rapide": {"pool": 80, "max_pages": 1, "variants_max": 6},
        "Normal": {"pool": 160, "max_pages": 2, "variants_max": 8},
        "Profond": {"pool": 240, "max_pages": 3, "variants_max": 10},
    }
    pre = presets.get(mode, presets["Normal"])

    story = (story or "").strip()
    actor = (actor or "").strip()
    if not story and not actor:
        return []

    if story:
        story = fr_numbers_to_words(story)

    found = []
    source_country = {}

    def add_chunk(ctry: str, shows: list):
        for show in shows:
            sid = stable_id(show)
            if sid not in source_country:
                source_country[sid] = ctry
        return shows

    # 1) titre exact + alias d'abord
    if story:
        for title_candidate in exact_alias_titles(story):
            for stype in show_types:
                exact = search_by_title(country, stype, lang, title_candidate)
                if not exact:
                    exact = search_by_title("us", stype, lang, title_candidate)
                if exact:
                    found += add_chunk(country, exact)

    # 2) variantes
    variants = build_query_variants(story, actor, mode)[: pre["variants_max"]]

    for stype in show_types:
        for kw in variants:
            found += add_chunk(
                country,
                collect_shows(
                    country,
                    stype,
                    lang,
                    kw,
                    max_items=pre["pool"],
                    max_pages=pre["max_pages"],
                ),
            )
            if len(found) >= pre["pool"]:
                break

    # 3) fallback us/gb
    if len(found) < 12:
        for stype in show_types:
            for kw in variants[: min(4, len(variants))]:
                found += add_chunk(
                    "us",
                    collect_shows("us", stype, lang, kw, max_items=pre["pool"], max_pages=1),
                )
                found += add_chunk(
                    "gb",
                    collect_shows("gb", stype, lang, kw, max_items=pre["pool"], max_pages=1),
                )

    shows = merge_results(found)
    user_text = story if story else actor

    raw = []
    for show in shows:
        sid = stable_id(show)
        discovered_in = source_country.get(sid, country)

        year = show.get("releaseYear") or show.get("firstAirYear") or None
        try:
            year = int(year) if year else None
        except Exception:
            year = None

        opts_all = []
        if discovered_in == country:
            opts_all = ((show.get("streamingOptions") or {}).get(country) or [])
            opts_all = dedupe_streaming_options(opts_all)

        opts_mine = [o for o in opts_all if ((o.get("service") or {}).get("id") in allowed)]
        opts_mine = dedupe_streaming_options(opts_mine)

        score100 = show.get("rating")
        try:
            score100 = float(score100) if score100 is not None else None
        except Exception:
            score100 = None

        exact_flag = exact_title_match_score(show.get("title", ""), user_text)

        raw.append(
            {
                "show": show,
                "api_id": show.get("id"),
                "title": show.get("title") or "Sans titre",
                "year": year,
                "poster": get_poster_url(show),
                "overview": show.get("overview") or "",
                "cast": show.get("cast") or [],
                "score100": score100,
                "opts_all": opts_all,
                "is_mine": 1 if opts_mine else 0,
                "rel": relevance_score(show, user_text),
                "exact_flag": exact_flag,
            }
        )

    raw.sort(
        key=lambda x: (
            x["exact_flag"],
            x["rel"],
            x["is_mine"],
            x["score100"] if x["score100"] is not None else -1,
        ),
        reverse=True,
    )
    return raw[: pre["pool"]]


def apply_filters_and_sort(items, sort_mode, only_my_apps, platform_filter, year_range):
    out = list(items)

    if only_my_apps:
        keep = [x for x in out if x["is_mine"] == 1]
        out = keep if keep else out

    if platform_filter != "Toutes":
        def ok_platform(item):
            for opt in item["opts_all"]:
                svc = opt.get("service") or {}
                name = (svc.get("name") or svc.get("id") or "").strip()
                if name == platform_filter:
                    return True
            return False

        filtered = [x for x in out if ok_platform(x)]
        out = filtered if filtered else out

    if year_range:
        y0, y1 = year_range
        out = [x for x in out if x["year"] is None or (x["year"] >= y0 and x["year"] <= y1)]

    if sort_mode == "Pertinence":
        out.sort(
            key=lambda x: (
                x["exact_flag"],
                x["rel"],
                x["is_mine"],
                x["score100"] if x["score100"] is not None else -1,
            ),
            reverse=True,
        )
    elif sort_mode == "Année (récent)":
        out.sort(key=lambda x: ((x["year"] is not None), x["year"] or -1, x["exact_flag"]), reverse=True)
    elif sort_mode == "Année (ancien)":
        out.sort(key=lambda x: ((x["year"] is not None), -(x["year"] or 9999), x["exact_flag"]), reverse=True)
    else:
        out.sort(key=lambda x: ((x["score100"] is not None), x["score100"] or -1, x["exact_flag"]), reverse=True)

    return out


# =========================================================
# SESSION
# =========================================================
st.session_state.setdefault("did_enter", False)
st.session_state.setdefault("page", "Accueil" if not st.session_state["did_enter"] else "Recherche")
st.session_state.setdefault("raw_items", [])
st.session_state.setdefault("raw_query", "")
st.session_state.setdefault("story_input", "")
st.session_state.setdefault("actor_input", "")
st.session_state.setdefault("show_choice", "Films et séries")
st.session_state.setdefault("auto_search", False)
st.session_state.setdefault("do_search_now", False)
st.session_state.setdefault("open_details_id", None)
st.session_state.setdefault("scroll_to_results", False)
st.session_state.setdefault("restore_card_id", None)

# clic acteur
qp = get_query_params()
if "actor" in qp:
    val = qp.get("actor")
    actor_param = val[0] if isinstance(val, list) and val else (val if isinstance(val, str) else "")
    clear_query_params()

    st.session_state["actor_input"] = actor_param
    st.session_state["story_input"] = ""
    st.session_state["show_choice"] = "Films"
    st.session_state["did_enter"] = True
    st.session_state["page"] = "Recherche"
    st.session_state["auto_search"] = True


# =========================================================
# SIDEBAR
# =========================================================
with st.sidebar:
    st.markdown("## FilmFinder IA")
    if st.session_state["did_enter"]:
        nav = st.radio(
            "Menu",
            ["Recherche", "Profil"],
            index=0 if st.session_state["page"] == "Recherche" else 1,
            key="nav",
        )
        st.session_state["page"] = nav
    else:
        st.caption("Démarrage")

page = st.session_state["page"]

# =========================================================
# ACCUEIL
# =========================================================
if page == "Accueil":
    st.markdown("# FilmFinder IA")

    actual_theme = resolve_theme_name(profile.get("ui_theme", "Auto"))
    emoji = THEMES[actual_theme]["emoji"]
    hero_poster = get_theme_background_poster(actual_theme, profile.get("country", "fr"), profile.get("lang", "fr"))

    hero_style = f"background-image:url('{hero_poster}');" if hero_poster else ""
    st.markdown(
        f"""
        <div class="ff-hero">
            <div class="ff-hero-bg" style="{hero_style}"></div>
            <div class="ff-hero-overlay"></div>
            <div class="ff-hero-content">
                <div class="ff-hero-title">{emoji} Thème actif : {actual_theme}</div>
                <div class="ff-hero-sub">Choisis tes plateformes une fois, puis entre.</div>
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )

    if not RAPIDAPI_KEY:
        st.error("RAPIDAPI_KEY manquante dans .env")
        st.stop()

    theme_pick = st.selectbox(
        "Thème",
        list(THEMES.keys()),
        index=list(THEMES.keys()).index(profile.get("ui_theme", "Auto")),
    )
    if theme_pick != profile.get("ui_theme", "Auto"):
        profile["ui_theme"] = theme_pick
        save_profile(profile)
        st.rerun()

    with st.form("welcome_profile"):
        c1, c2 = st.columns(2)
        with c1:
            country = st.selectbox(
                "Pays",
                ["fr", "be", "ch", "gb", "us"],
                index=["fr", "be", "ch", "gb", "us"].index(profile.get("country", "fr")),
            )
        with c2:
            lang = st.selectbox(
                "Langue",
                ["fr", "en"],
                index=["fr", "en"].index(profile.get("lang", "fr")),
            )

        services = get_services(country, lang)
        name_to_id = {
            (s.get("name") or s.get("id")): s.get("id")
            for s in services
            if (s.get("name") or s.get("id")) and s.get("id")
        }
        id_to_name = {v: k for k, v in name_to_id.items()}
        default_names = [id_to_name[i] for i in profile.get("platform_ids", []) if i in id_to_name]

        chosen = st.multiselect(
            "Tes plateformes",
            options=sorted(name_to_id.keys()),
            default=sorted(set(default_names)),
        )
        platform_ids = [name_to_id[n] for n in chosen]

        enter = st.form_submit_button("Entrer 🍿")

    if enter:
        if not platform_ids:
            st.warning("Coche au moins 1 plateforme.")
        else:
            profile["country"] = country
            profile["lang"] = lang
            profile["platform_ids"] = platform_ids
            save_profile(profile)
            st.session_state["did_enter"] = True
            st.session_state["page"] = "Recherche"
            st.rerun()

    st.stop()

# =========================================================
# PROFIL
# =========================================================
if page == "Profil":
    st.markdown("# Profil")
    st.caption("Modifie pays, langue et plateformes.")

    with st.form("profile_form"):
        c1, c2 = st.columns(2)
        with c1:
            country = st.selectbox(
                "Pays",
                ["fr", "be", "ch", "gb", "us"],
                index=["fr", "be", "ch", "gb", "us"].index(profile.get("country", "fr")),
            )
        with c2:
            lang = st.selectbox(
                "Langue",
                ["fr", "en"],
                index=["fr", "en"].index(profile.get("lang", "fr")),
            )

        services = get_services(country, lang)
        name_to_id = {
            (s.get("name") or s.get("id")): s.get("id")
            for s in services
            if (s.get("name") or s.get("id")) and s.get("id")
        }
        id_to_name = {v: k for k, v in name_to_id.items()}
        default_names = [id_to_name[i] for i in profile.get("platform_ids", []) if i in id_to_name]

        chosen = st.multiselect(
            "Tes plateformes",
            options=sorted(name_to_id.keys()),
            default=sorted(set(default_names)),
        )
        platform_ids = [name_to_id[n] for n in chosen]

        save_btn = st.form_submit_button("✅ Enregistrer")

    if save_btn:
        if not platform_ids:
            st.warning("Coche au moins 1 plateforme.")
        else:
            profile["country"] = country
            profile["lang"] = lang
            profile["platform_ids"] = platform_ids
            save_profile(profile)
            st.success("OK")
            st.rerun()

    if st.button("↩️ Revenir à l'accueil"):
        st.session_state["did_enter"] = False
        st.session_state["page"] = "Accueil"
        st.rerun()

    st.stop()

# =========================================================
# RECHERCHE
# =========================================================
st.markdown("# Recherche")

actual_theme = resolve_theme_name(profile.get("ui_theme", "Auto"))
emoji = THEMES[actual_theme]["emoji"]
theme_poster = get_theme_background_poster(
    actual_theme,
    profile.get("country","fr"),
    profile.get("lang","fr")
)

hero_style = f"background-image:url('{theme_poster}');" if theme_poster else ""

st.markdown(f"""
<div class="ff-hero" style="background-image:url('{theme_poster}');background-size:cover;background-position:center;">
<div style="
background:linear-gradient(180deg,rgba(0,0,0,0.2),rgba(0,0,0,0.8));
padding:20px;
border-radius:16px;
">

<div style="
background:white;
padding:10px 14px;
border-radius:12px;
display:inline-block;
">

<b>🎬 Thème : {actual_theme}</b>

</div>

</div>
</div>
""",unsafe_allow_html=True)

theme_pick = st.selectbox(
    "Thème",
    list(THEMES.keys()),
    index=list(THEMES.keys()).index(profile.get("ui_theme", "Auto")),
)
if theme_pick != profile.get("ui_theme", "Auto"):
    profile["ui_theme"] = theme_pick
    save_profile(profile)
    st.rerun()

ACTIVE_THEME_NAME = apply_theme(profile.get("ui_theme", "Auto"))

if not profile.get("platform_ids"):
    st.warning("Choisis au moins 1 plateforme dans Accueil/Profil.")
    st.session_state["did_enter"] = False
    st.session_state["page"] = "Accueil"
    st.rerun()

row_top1, row_top2 = st.columns(2)
with row_top1:
    show_choice = st.selectbox(
        "Je cherche :",
        ["Films", "Séries", "Films et séries"],
        key="show_choice",
    )
with row_top2:
    mode = st.radio("Mode", ["Rapide", "Normal", "Profond"], horizontal=True, index=1)

show_types = showtype_to_list(show_choice)

st.markdown(
    "<div class='ff-muted'>Astuce • Acteur seul = OK • Clique acteur = films</div>",
    unsafe_allow_html=True,
)


def request_search():
    st.session_state["do_search_now"] = True


def clear_story():
    st.session_state["story_input"] = ""


def clear_actor():
    st.session_state["actor_input"] = ""


c_story, c_x1 = st.columns([0.965, 0.035])
with c_story:
    st.text_input(
        "Histoire / souvenir / titre exact",
        key="story_input",
        placeholder="Ex: Seul au monde ou un homme rescapé d'un crash avion sur une île déserte",
        on_change=request_search,
    )
with c_x1:
    st.markdown('<div class="ff-x-holder">', unsafe_allow_html=True)
    st.button("✕", key="clear_story_btn", help="Effacer", on_click=clear_story)
    st.markdown("</div>", unsafe_allow_html=True)

c_actor, c_x2 = st.columns([0.965, 0.035])
with c_actor:
    st.text_input(
        "Acteur/actrice (optionnel)",
        key="actor_input",
        placeholder="Ex: Tom Hanks",
        on_change=request_search,
    )
with c_x2:
    st.markdown('<div class="ff-x-holder">', unsafe_allow_html=True)
    st.button("✕", key="clear_actor_btn", help="Effacer", on_click=clear_actor)
    st.markdown("</div>", unsafe_allow_html=True)

if st.button("Chercher", key="search_btn"):
    request_search()


def do_search(story_text: str, actor_text: str):
    raw = build_raw_items(story_text, actor_text, mode=mode, prof=profile, show_types=show_types)
    st.session_state["raw_items"] = raw
    st.session_state["raw_query"] = story_text.strip() if story_text.strip() else actor_text.strip()
    st.session_state["open_details_id"] = None
    st.session_state["scroll_to_results"] = True
    st.session_state["restore_card_id"] = None


story_raw = st.session_state.get("story_input", "").strip()
actor_raw = st.session_state.get("actor_input", "").strip()

story_suggest = prettify_sentence(fr_numbers_to_words(story_raw)) if story_raw else ""
actor_suggest = titlecase_name(actor_raw) if actor_raw else ""

if story_suggest and story_suggest != story_raw:
    c1, c2 = st.columns([5, 1])
    with c1:
        st.markdown(
            f"<div class='ff-muted'>Suggestion histoire : <b>{story_suggest}</b></div>",
            unsafe_allow_html=True,
        )
    with c2:
        if st.button("Utiliser", key="use_story_fix"):
            st.session_state["story_input"] = story_suggest
            st.rerun()

if actor_suggest and actor_suggest != actor_raw:
    c1, c2 = st.columns([5, 1])
    with c1:
        st.markdown(
            f"<div class='ff-muted'>Suggestion acteur : <b>{actor_suggest}</b></div>",
            unsafe_allow_html=True,
        )
    with c2:
        if st.button("Utiliser", key="use_actor_fix"):
            st.session_state["actor_input"] = actor_suggest
            st.rerun()

auto = st.session_state.pop("auto_search", False)
manual = st.session_state.pop("do_search_now", False)

if auto or manual:
    s = st.session_state.get("story_input", "").strip()
    a = st.session_state.get("actor_input", "").strip()
    if not s and not a:
        st.warning("Mets une histoire OU un acteur.")
    else:
        do_search(s, a)

raw_items = st.session_state.get("raw_items", [])

services = get_services(profile["country"], profile["lang"])
id_to_name = {s.get("id"): (s.get("name") or s.get("id")) for s in services}
platform_choices = ["Toutes"] + sorted(
    [id_to_name.get(i, i) for i in profile.get("platform_ids", [])]
)

sort_mode = "Pertinence"
platform_filter = "Toutes"
only_my_apps = False
year_range = None

f1, f2, f3 = st.columns(3)
with f1:
    sort_mode = st.selectbox(
        "Trier par",
        ["Pertinence", "Année (récent)", "Année (ancien)", "Note (haute)"],
        index=0,
    )
with f2:
    platform_filter = st.selectbox("Plateforme", platform_choices, index=0)
with f3:
    only_my_apps = st.checkbox("Seulement mes applis", value=False)

years = sorted({x["year"] for x in raw_items if x.get("year")})
if years and min(years) != max(years):
    year_range = st.slider(
        "Plage d'année",
        min_value=int(min(years)),
        max_value=int(max(years)),
        value=(int(min(years)), int(max(years))),
    )

if not raw_items:
    st.markdown(
        "<div class='ff-muted'>Tape une histoire, un titre exact ou un acteur puis Entrée / Chercher.</div>",
        unsafe_allow_html=True,
    )
    st.stop()

view = apply_filters_and_sort(raw_items, sort_mode, only_my_apps, platform_filter, year_range)

# ancre sur le premier film
st.markdown('<div id="first-result-anchor"></div>', unsafe_allow_html=True)
st.write(f"✅ Résultats : {min(len(view), 20)} / {len(view)}")

if st.session_state.pop("scroll_to_results", False):
    components.html(
        """
        <script>
        setTimeout(function(){
          try{
            if(document.activeElement && document.activeElement.blur){
              document.activeElement.blur();
            }
            const fields = document.querySelectorAll("input, textarea");
            fields.forEach(el => { try { el.blur(); } catch(e){} });
            if(document.body && document.body.focus){
              document.body.focus();
            }
          }catch(e){}

          const el = document.getElementById("first-result-anchor");
          if(el){
            el.scrollIntoView({behavior:"smooth", block:"start"});
          }
        }, 180);
        </script>
        """,
        height=0,
    )

restore_card_id = st.session_state.pop("restore_card_id", None)
if restore_card_id:
    components.html(
        f"""
        <script>
        setTimeout(function(){{
          const el = document.getElementById("card-{restore_card_id}");
          if(el){{
            el.scrollIntoView({{behavior:"auto", block:"start"}});
          }}
        }}, 80);
        </script>
        """,
        height=0,
    )

allowed_ids = set(profile.get("platform_ids", []))


def details_fr_links(show_id: str):
    data = get_show_details(show_id, profile["country"], "movie", profile["lang"])
    if not data:
        data = get_show_details(show_id, profile["country"], "series", profile["lang"])
    opts = ((data.get("streamingOptions") or {}).get(profile["country"]) or []) if data else []
    return dedupe_streaming_options(opts)


for idx, item in enumerate(view[:20]):
    show_id = str(item.get("api_id") or "")
    card_id = stable_id(item.get("show") or {}) if item.get("show") else (show_id or item["title"])

    st.markdown(f'<div id="card-{card_id}"></div>', unsafe_allow_html=True)
    st.markdown('<div class="ff-card">', unsafe_allow_html=True)

    c_img, c_txt = st.columns([1, 3])
    with c_img:
        if item.get("poster"):
            st.image(item["poster"], width=160)

        trailer_url = trailer_direct_url(item["title"], item.get("year"))
        if trailer_url:
            st.markdown(
                f'<a class="ff-linkbox" href="{trailer_url}" target="_blank">Bande-annonce</a>',
                unsafe_allow_html=True,
            )

    with c_txt:
        st.markdown(f"### {item['title']} ({item['year'] if item['year'] else ''})")

        if item.get("score100") is not None:
            stars = stars_html(item["score100"])
            score5 = round(float(item["score100"]) / 20.0, 1)
            st.markdown(
                f"{stars}<span class='ff-muted' style='margin-left:8px'>({score5}/5)</span>",
                unsafe_allow_html=True,
            )

        opts_all = item.get("opts_all") or []
        if not opts_all and show_id:
            opts_all = details_fr_links(show_id)

        groups = group_options_by_service(opts_all)
        mine = [g for g in groups if g["id"] in allowed_ids]
        other = [g for g in groups if g["id"] not in allowed_ids]

        if mine:
            st.markdown("<div class='ff-muted'>✅ Dispo sur tes applis</div>", unsafe_allow_html=True)
            st.markdown("**Tes plateformes :**")
            for g in mine:
                primary, rest = pick_primary_option(g["opts"])
                label = f"**{g['name']}** ({primary['type'] if primary else ''})"
                link = primary["link"] if primary and primary.get("link") else "*(lien non fourni)*"
                st.markdown(f"{label} → {link}")
                if rest:
                    with st.expander(f"… autres options sur {g['name']}"):
                        for opt in rest:
                            st.markdown(f"- ({opt['type']}) → {opt['link'] or '*(lien non fourni)*'}")
        else:
            st.markdown("<div class='ff-muted'>❌ Pas dispo sur tes applis</div>", unsafe_allow_html=True)

        if other:
            with st.expander(f"… Autres plateformes ({len(other)})"):
                for g in other:
                    primary, rest = pick_primary_option(g["opts"])
                    label = primary["type"] if primary else ""
                    link = primary["link"] if primary and primary["link"] else "*(lien non fourni)*"
                    st.markdown(f"**{g['name']}** ({label}) → {link}")
                    if rest:
                        with st.expander(f"… autres options sur {g['name']}"):
                            for opt in rest:
                                st.markdown(f"- ({opt['type']}) → {opt['link'] or '*(lien non fourni)*'}")

        if st.button("Détails", key=f"details_btn_{card_id}"):
            st.session_state["open_details_id"] = (
                card_id if st.session_state["open_details_id"] != card_id else None
            )
            st.session_state["restore_card_id"] = card_id
            st.rerun()

        if st.session_state.get("open_details_id") == card_id:
            if item.get("overview"):
                st.write(item["overview"])

            cast = item.get("cast") or []
            if cast:
                links = [f'<a class="ff-linkbox" href="?actor={quote(a)}">{a}</a>' for a in cast[:12]]
                st.markdown("**Acteurs :** " + " ".join(links), unsafe_allow_html=True)

    st.markdown("</div>", unsafe_allow_html=True)