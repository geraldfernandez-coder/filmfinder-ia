import json
import os
import random
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

st.set_page_config(page_title="FilmFinder IA", layout="centered")

# =========================================================
# THEMES
# =========================================================
THEMES = {
    "Auto": {},
    "Cinéma vintage": {
        "bg1": "#f7f1e1",
        "bg2": "#ffffff",
        "accent": "#b85c38",
        "text": "#111111",
        "muted": "rgba(0,0,0,0.65)",
        "card": "#ffffff",
        "border": "rgba(0,0,0,0.10)",
        "input_bg": "#ffffff",
        "input_text": "#111111",
        "button_bg": "#ffffff",
        "button_text": "#111111",
    },
    "Romance": {
        "bg1": "#fff0f3",
        "bg2": "#ffffff",
        "accent": "#ff4d6d",
        "text": "#111111",
        "muted": "rgba(0,0,0,0.65)",
        "card": "#ffffff",
        "border": "rgba(0,0,0,0.10)",
        "input_bg": "#ffffff",
        "input_text": "#111111",
        "button_bg": "#ffffff",
        "button_text": "#111111",
    },
    "Science-fiction": {
        "bg1": "#0b1020",
        "bg2": "#121a33",
        "accent": "#00d4ff",
        "text": "#f3f7ff",
        "muted": "rgba(255,255,255,0.72)",
        "card": "rgba(255,255,255,0.10)",
        "border": "rgba(255,255,255,0.18)",
        "input_bg": "rgba(255,255,255,0.12)",
        "input_text": "#ffffff",
        "button_bg": "#ffffff",
        "button_text": "#111111",
    },
    "Horreur": {
        "bg1": "#0a0a0a",
        "bg2": "#1a1a1a",
        "accent": "#ff0033",
        "text": "#fff5f7",
        "muted": "rgba(255,255,255,0.72)",
        "card": "rgba(255,255,255,0.08)",
        "border": "rgba(255,255,255,0.16)",
        "input_bg": "rgba(255,255,255,0.12)",
        "input_text": "#ffffff",
        "button_bg": "#ffffff",
        "button_text": "#111111",
    },
    "Été": {
        "bg1": "#fff7e6",
        "bg2": "#ffffff",
        "accent": "#ffb703",
        "text": "#111111",
        "muted": "rgba(0,0,0,0.65)",
        "card": "#ffffff",
        "border": "rgba(0,0,0,0.10)",
        "input_bg": "#ffffff",
        "input_text": "#111111",
        "button_bg": "#ffffff",
        "button_text": "#111111",
    },
    "Halloween": {
        "bg1": "#120b1f",
        "bg2": "#1c1230",
        "accent": "#ff7a00",
        "text": "#fff8f2",
        "muted": "rgba(255,255,255,0.72)",
        "card": "rgba(255,255,255,0.09)",
        "border": "rgba(255,255,255,0.16)",
        "input_bg": "rgba(255,255,255,0.12)",
        "input_text": "#ffffff",
        "button_bg": "#ffffff",
        "button_text": "#111111",
    },
    "Armistice": {
        "bg1": "#102038",
        "bg2": "#1b2b45",
        "accent": "#3a86ff",
        "text": "#f5f9ff",
        "muted": "rgba(255,255,255,0.72)",
        "card": "rgba(255,255,255,0.10)",
        "border": "rgba(255,255,255,0.16)",
        "input_bg": "rgba(255,255,255,0.12)",
        "input_text": "#ffffff",
        "button_bg": "#ffffff",
        "button_text": "#111111",
    },
    "Fête des mères": {
        "bg1": "#fff4e8",
        "bg2": "#ffffff",
        "accent": "#ff7aa2",
        "text": "#111111",
        "muted": "rgba(0,0,0,0.65)",
        "card": "#ffffff",
        "border": "rgba(0,0,0,0.10)",
        "input_bg": "#ffffff",
        "input_text": "#111111",
        "button_bg": "#ffffff",
        "button_text": "#111111",
    },
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
    if today.month == 2 and 10 <= today.day <= 15:
        return "Romance"
    if today.month == 11 and 8 <= today.day <= 12:
        return "Armistice"

    mothers_day = last_sunday_of_may(today.year)
    if mothers_day - timedelta(days=6) <= today <= mothers_day + timedelta(days=1):
        return "Fête des mères"

    return random.choice(
        ["Cinéma vintage", "Romance", "Science-fiction", "Horreur", "Été"]
    )


def apply_theme(theme_name: str) -> None:
    resolved_theme_name = theme_name
    if theme_name == "Auto":
        resolved_theme_name = choose_auto_theme_name()

    theme = THEMES[resolved_theme_name]

    st.markdown(
        f"""
        <style>
        :root {{
            color-scheme: light !important;
        }}

        html, body, .stApp, [data-testid="stAppViewContainer"] {{
            background: linear-gradient(180deg, {theme["bg1"]} 0%, {theme["bg2"]} 60%, {theme["bg2"]} 100%) !important;
            color: {theme["text"]} !important;
        }}

        [data-testid="stAppViewContainer"]::before {{
            content:"";
            position: fixed;
            inset: 0;
            pointer-events:none;
            background:
                radial-gradient(circle at 18% 10%, rgba(255,255,255,0.05), transparent 35%),
                radial-gradient(circle at 80% 22%, rgba(255,255,255,0.04), transparent 40%),
                repeating-linear-gradient(
                    0deg,
                    rgba(255,255,255,0.02),
                    rgba(255,255,255,0.02) 1px,
                    rgba(0,0,0,0.02) 2px,
                    rgba(0,0,0,0.02) 3px
                );
            opacity: 0.12;
            mix-blend-mode: overlay;
            z-index: 0;
        }}

        .main .block-container {{
            position: relative;
            z-index: 1;
            max-width: 1060px !important;
            margin: 12px auto !important;
            background: {theme["card"]} !important;
            border: 1px solid {theme["border"]} !important;
            border-radius: 18px !important;
            padding: 16px 18px 24px 18px !important;
            box-shadow: 0 14px 40px rgba(0,0,0,0.12) !important;
            backdrop-filter: blur(10px);
        }}

        [data-testid="stMarkdownContainer"], [data-testid="stMarkdownContainer"] * {{
            color: {theme["text"]} !important;
        }}

        label, p, span {{
            color: {theme["text"]} !important;
        }}

        .ff-muted {{
            color: {theme["muted"]} !important;
            font-size: 13px;
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

        .stButton > button, .stFormSubmitButton > button {{
            background: {theme["button_bg"]} !important;
            color: {theme["button_text"]} !important;
            border: 1px solid #d9d9d9 !important;
            border-radius: 12px !important;
            box-shadow: 0 1px 4px rgba(0,0,0,0.06);
        }}

        .stButton > button:hover, .stFormSubmitButton > button:hover {{
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

        .ff-linkbox a {{
            display: inline-block;
            padding: 2px 6px;
            margin: 2px 2px 2px 0;
            background: rgba(255,255,255,0.92);
            border: 1px solid #e4e4e4;
            border-radius: 8px;
            color: #111111 !important;
            text-decoration: none;
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

        .ff-x-btn button {{
            width: 100%;
            padding: 0.28rem 0.6rem !important;
            min-height: 0 !important;
            line-height: 1 !important;
        }}

        .actor-chip {{
            display:inline-block;
            padding:6px 10px;
            margin:4px 6px 0 0;
            border-radius:999px;
            border:1px solid {theme["border"]};
            background: rgba(255,255,255,0.90);
            color:#111111 !important;
            text-decoration:none;
            font-size: 13px;
        }}

        .theme-badge {{
            display:inline-block;
            padding:5px 10px;
            border-radius:999px;
            font-size:12px;
            font-weight:600;
            background: rgba(255,255,255,0.88);
            color:#111111 !important;
            border:1px solid {theme["border"]};
            margin-left:6px;
        }}

        [data-testid="stExpander"] {{
            border-radius: 14px !important;
        }}
        </style>
        """,
        unsafe_allow_html=True,
    )

    st.session_state["resolved_theme_name"] = resolved_theme_name


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
        encoding="utf-8"
    )


profile = load_profile()
apply_theme(profile.get("ui_theme", "Auto"))

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
}

RULE_HINTS = [
    {
        "if_any": ["super heros vert", "super héros vert", "green superhero", "heros vert", "héros vert"],
        "add_entities": ["Hulk", "The Incredible Hulk", "Green Lantern"],
    },
    {
        "if_any": ["seul au monde", "cast away", "crash avion ile", "crash avion île", "survivant avion ile", "survivant avion île", "homme seul ile", "île déserte crash avion"],
        "add_entities": ["Seul au monde", "Cast Away"],
    },
    {
        "if_any": ["a nous 4", "à nous 4", "a nous quatre", "à nous quatre", "jumelles separees naissance", "jumelles séparées naissance", "twins separated birth"],
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


def set_query_params_safe(**kwargs) -> None:
    if hasattr(st, "query_params"):
        try:
            st.query_params.clear()
            for k, v in kwargs.items():
                st.query_params[k] = v
            return
        except Exception:
            pass
    if hasattr(st, "experimental_set_query_params"):
        try:
            st.experimental_set_query_params(**kwargs)
        except Exception:
            pass


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
# API
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

    def best_rank(g):
        ranks = [TYPE_PRIORITY.get(o["type"], 999) for o in g["opts"]]
        return min(ranks) if ranks else 999

    out.sort(key=lambda g: (best_rank(g), g["name"].lower()))
    return out


# =========================================================
# OLLAMA / IA
# =========================================================
def ollama_available() -> bool:
    try:
        r = requests.get(f"{OLLAMA_URL}/api/tags", timeout=2)
        return r.ok
    except Exception:
        return False


def ollama_generate(prompt: str) -> str:
    try:
        r = requests.post(
            f"{OLLAMA_URL}/api/generate",
            json={
                "model": OLLAMA_MODEL,
                "prompt": prompt,
                "stream": False,
            },
            timeout=25,
        )
        if not r.ok:
            return ""
        data = r.json()
        return (data.get("response") or "").strip()
    except Exception:
        return ""


def ai_expand_query(user_text: str) -> list[str]:
    user_text = user_text.strip()
    if not user_text:
        return []

    base = norm_loose(fr_numbers_to_words(user_text))
    expansions = []

    for word in base.split():
        expansions.append(word)
        for syn in SYNONYMS.get(word, []):
            expansions.append(syn)

    joined = " ".join(dict.fromkeys(expansions)).strip()

    found_entities = []
    for rule in RULE_HINTS:
        if any(norm_loose(x) in base for x in rule["if_any"]):
            for ent in rule["add_entities"]:
                if ent not in found_entities:
                    found_entities.append(ent)

    candidates = []
    if user_text not in candidates:
        candidates.append(user_text)

    if joined and joined not in candidates:
        candidates.append(joined)

    kw = extract_keywords(base, 8)
    if kw and kw not in candidates:
        candidates.append(kw)

    candidates.extend(found_entities)

    if ollama_available():
        prompt = f"""
Tu aides à retrouver un film ou une série à partir d'une requête en français.
Rends UNIQUEMENT un JSON valide avec cette forme :
{{
  "queries": ["...", "...", "..."],
  "titles": ["...", "..."]
}}

Règles :
- 3 à 6 variantes max
- privilégie titres exacts probables si tu en déduis un
- ajoute variantes FR/EN si évident
- pas d'explication

Requête utilisateur :
{user_text}
"""
        raw = ollama_generate(prompt)
        if raw:
            try:
                data = json.loads(raw)
                for q in data.get("queries", []) or []:
                    if q and q not in candidates:
                        candidates.append(q)
                for t in data.get("titles", []) or []:
                    if t and t not in candidates:
                        candidates.append(t)
            except Exception:
                pass

    deduped = []
    seen = set()
    for c in candidates:
        c = re.sub(r"\s+", " ", str(c).strip())
        if not c:
            continue
        key = norm_loose(c)
        if key in seen:
            continue
        seen.add(key)
        deduped.append(c)

    return deduped[:8]


# =========================================================
# RECHERCHE / SCORE
# =========================================================
def title_variants(title: str) -> set[str]:
    variants = set()
    if not title:
        return variants
    t = norm_loose(fr_numbers_to_words(title))
    variants.add(t)
    variants.add(t.replace("'", " "))
    variants.add(re.sub(r"[^a-z0-9]", "", t))
    return {v.strip() for v in variants if v.strip()}


def exact_title_match_score(query: str, title: str) -> int:
    qvars = title_variants(query)
    tvars = title_variants(title)
    if qvars & tvars:
        return 1000

    q = norm_loose(fr_numbers_to_words(query))
    t = norm_loose(fr_numbers_to_words(title))
    if q == t:
        return 1000

    if q and t:
        if q in t or t in q:
            return 220
    return 0


def tokenize(text: str) -> list[str]:
    text = norm_loose(fr_numbers_to_words(text))
    words = re.findall(r"[a-z0-9']+", text)
    return [w for w in words if w and w not in STOPWORDS]


def compute_match_score(show: dict, user_query: str) -> int:
    title = show.get("title") or ""
    original_title = show.get("originalTitle") or ""
    overview = show.get("overview") or ""
    release_year = str(show.get("releaseYear") or show.get("firstAirYear") or "")
    cast_list = show.get("cast") or []

    score = 0
    score += exact_title_match_score(user_query, title)
    score += exact_title_match_score(user_query, original_title)

    q_tokens = tokenize(user_query)
    title_blob = " ".join([title, original_title, release_year])
    title_blob_norm = norm_loose(title_blob)
    overview_norm = norm_loose(overview)
    cast_norm = " ".join(norm_loose(c) for c in cast_list if c)

    for tok in q_tokens:
        if tok in title_blob_norm:
            score += 80
        elif tok in cast_norm:
            score += 40
        elif tok in overview_norm:
            score += 18

    q_norm = norm_loose(user_query)

    if "seul au monde" in q_norm or "cast away" in q_norm:
        if "cast away" in norm_loose(title) or "seul au monde" in norm_loose(title):
            score += 600

    if "ile" in q_norm or "île" in user_query.lower():
        if "island" in overview_norm or "île" in overview.lower() or "ile" in overview_norm:
            score += 25

    if "avion" in q_norm or "plane" in q_norm:
        if "plane" in overview_norm or "airplane" in overview_norm or "avion" in overview.lower():
            score += 25

    if "surviv" in q_norm or "rescap" in q_norm or "naufrag" in q_norm:
        if "surviv" in overview_norm or "castaway" in overview_norm:
            score += 30

    score += min(len(cast_list), 8)

    return score


def merge_unique_shows(shows: list[dict]) -> list[dict]:
    out = []
    seen = set()
    for s in shows:
        sid = stable_id(s)
        if sid in seen:
            continue
        seen.add(sid)
        out.append(s)
    return out


def enrich_show_for_scoring(show: dict, country: str, show_type: str, lang: str) -> dict:
    details = get_show_details(str(show.get("id") or ""), country, show_type, lang)
    if not details:
        return show

    merged = dict(show)
    for k, v in details.items():
        if k not in merged or not merged.get(k):
            merged[k] = v

    cast_names = []
    for person in details.get("cast", []) or []:
        if isinstance(person, dict):
            name = person.get("name")
        else:
            name = str(person)
        if name:
            cast_names.append(name)

    if cast_names:
        merged["cast"] = cast_names

    streaming_options = details.get("streamingOptions") or show.get("streamingOptions") or {}
    if isinstance(streaming_options, dict):
        country_opts = streaming_options.get(country) or []
    else:
        country_opts = []

    merged["_streaming_options_country"] = dedupe_streaming_options(country_opts)
    return merged


def search_candidates(country: str, show_type: str, lang: str, user_query: str) -> list[dict]:
    candidates = []
    expansions = ai_expand_query(user_query)

    # 1) Recherche directe par titre exact / probable
    for q in expansions:
        candidates.extend(search_by_title(country, show_type, lang, q))

    # 2) Recherche par filtres pour résumé / mots-clés
    keyword_queries = []
    keyword_queries.append(extract_keywords(user_query, 8))
    keyword_queries.extend(extract_keywords(q, 8) for q in expansions[:4])

    clean_keywords = []
    for q in keyword_queries:
        q = re.sub(r"\s+", " ", q).strip()
        if q and q not in clean_keywords:
            clean_keywords.append(q)

    for q in clean_keywords[:4]:
        try:
            candidates.extend(collect_shows(country, show_type, lang, q, max_items=35, max_pages=2))
        except Exception:
            pass

    candidates = merge_unique_shows(candidates)

    enriched = []
    for show in candidates[:60]:
        enriched.append(enrich_show_for_scoring(show, country, show_type, lang))

    enriched = merge_unique_shows(enriched)

    scored = []
    for show in enriched:
        score = compute_match_score(show, user_query)
        show["_score"] = score
        scored.append(show)

    scored.sort(
        key=lambda s: (
            -(s.get("_score") or 0),
            -(s.get("releaseYear") or s.get("firstAirYear") or 0),
            (s.get("title") or "").lower(),
        )
    )
    return scored


# =========================================================
# AFFICHAGE
# =========================================================
def render_actor_links(cast_names: list[str]) -> None:
    if not cast_names:
        return

    chips = []
    for name in cast_names[:12]:
        qp = quote(name)
        chips.append(
            f'<a class="actor-chip" href="?q={qp}&actor=1">{name}</a>'
        )
    st.markdown("".join(chips), unsafe_allow_html=True)


def render_streaming_links(options: list[dict]) -> None:
    groups = group_options_by_service(options)
    if not groups:
        st.markdown('<div class="ff-muted">Aucune disponibilité trouvée pour ce pays.</div>', unsafe_allow_html=True)
        return

    pieces = []
    labels = {
        "subscription": "Abonnement",
        "free": "Gratuit",
        "addon": "Addon",
        "rent": "Location",
        "buy": "Achat",
    }

    for g in groups:
        types = []
        first_link = ""
        for opt in sorted(g["opts"], key=lambda x: TYPE_PRIORITY.get(x["type"], 999)):
            typ = labels.get(opt["type"], opt["type"] or "Voir")
            if typ not in types:
                types.append(typ)
            if not first_link and opt["link"]:
                first_link = opt["link"]

        txt = f"{g['name']} — {', '.join(types)}"
        if first_link:
            pieces.append(f'<a href="{first_link}" target="_blank">{txt}</a>')
        else:
            pieces.append(f"<span>{txt}</span>")

    st.markdown(
        '<div class="ff-linkbox">' + "".join(pieces) + "</div>",
        unsafe_allow_html=True
    )


def render_result_card(show: dict, country: str, show_type: str, lang: str) -> None:
    title = show.get("title") or "Sans titre"
    year = show.get("releaseYear") or show.get("firstAirYear") or ""
    overview = show.get("overview") or ""
    imdb_rating = None
    imdb_votes = None

    ratings = show.get("rating") or show.get("ratings") or {}
    if isinstance(ratings, dict):
        imdb = ratings.get("imdb") or {}
        if isinstance(imdb, dict):
            imdb_rating = imdb.get("value")
            imdb_votes = imdb.get("votes")
        elif isinstance(imdb, (int, float)):
            imdb_rating = imdb

    if imdb_rating is None:
        imdb_score = show.get("imdbRating")
        if isinstance(imdb_score, (int, float)):
            imdb_rating = imdb_score

    star_pct = None
    if imdb_rating is not None:
        try:
            star_pct = float(imdb_rating) * 10
        except Exception:
            star_pct = None

    poster = get_poster_url(show)
    cast_names = show.get("cast") or []
    if cast_names and isinstance(cast_names[0], dict):
        cast_names = [c.get("name") for c in cast_names if isinstance(c, dict) and c.get("name")]

    options = show.get("_streaming_options_country")
    if options is None:
        details = get_show_details(str(show.get("id") or ""), country, show_type, lang)
        streaming_options = details.get("streamingOptions") or {}
        country_opts = streaming_options.get(country) or []
        options = dedupe_streaming_options(country_opts)

    with st.container():
        st.markdown('<div class="ff-card">', unsafe_allow_html=True)
        c1, c2 = st.columns([1, 2.2], gap="medium")

        with c1:
            if poster:
                st.image(poster, use_container_width=True)
            else:
                st.markdown("🎬")

        with c2:
            st.markdown(f"### {title} {f'({year})' if year else ''}")
            if star_pct is not None:
                stars = stars_html(star_pct)
                votes_txt = f" · {imdb_votes} votes" if imdb_votes else ""
                st.markdown(
                    f"{stars} &nbsp; IMDb {imdb_rating}/10{votes_txt}",
                    unsafe_allow_html=True
                )

            if overview:
                st.write(prettify_sentence(overview))

            if cast_names:
                st.markdown("**Acteurs :**")
                render_actor_links(cast_names)

            st.markdown("**Où regarder :**")
            render_streaming_links(options)

        st.markdown("</div>", unsafe_allow_html=True)


# =========================================================
# JS / UX MOBILE
# =========================================================
def inject_scroll_to_results():
    components.html(
        """
        <script>
        (function() {
          function go() {
            const target = window.parent.document.getElementById("results-anchor");
            if (target) {
              target.scrollIntoView({behavior: "smooth", block: "start"});
            }
          }
          setTimeout(go, 80);
          setTimeout(go, 250);
          setTimeout(go, 600);
        })();
        </script>
        """,
        height=0,
    )


def inject_blur_active_element():
    components.html(
        """
        <script>
        (function() {
          function blurNow() {
            const d = window.parent.document;
            if (d && d.activeElement) {
              d.activeElement.blur();
            }
          }
          setTimeout(blurNow, 30);
          setTimeout(blurNow, 150);
          setTimeout(blurNow, 400);
        })();
        </script>
        """,
        height=0,
    )


# =========================================================
# ETAT SESSION
# =========================================================
if "q" not in st.session_state:
    st.session_state["q"] = ""

if "show_type" not in st.session_state:
    st.session_state["show_type"] = "movie"

if "results" not in st.session_state:
    st.session_state["results"] = []

if "last_error" not in st.session_state:
    st.session_state["last_error"] = ""

if "scroll_to_results" not in st.session_state:
    st.session_state["scroll_to_results"] = False

if "pending_actor_search" not in st.session_state:
    st.session_state["pending_actor_search"] = False


# =========================================================
# PARAMS URL (acteurs cliquables)
# =========================================================
params = get_query_params()
qp_q = params.get("q")
if isinstance(qp_q, list):
    qp_q = qp_q[0] if qp_q else ""
qp_actor = params.get("actor")
if isinstance(qp_actor, list):
    qp_actor = qp_actor[0] if qp_actor else ""

if qp_q and qp_q != st.session_state.get("q"):
    st.session_state["q"] = qp_q
    st.session_state["pending_actor_search"] = True
    clear_query_params()


# =========================================================
# SIDEBAR
# =========================================================
with st.sidebar:
    st.header("⚙️ Réglages")

    country = st.text_input("Pays", value=profile.get("country", "fr")).strip().lower() or "fr"
    lang = st.text_input("Langue", value=profile.get("lang", "fr")).strip().lower() or "fr"

    theme_names = list(THEMES.keys())
    current_theme = profile.get("ui_theme", "Auto")
    if current_theme not in theme_names:
        current_theme = "Auto"

    selected_theme = st.selectbox(
        "Thème",
        theme_names,
        index=theme_names.index(current_theme)
    )

    resolved = st.session_state.get("resolved_theme_name", selected_theme)
    if selected_theme == "Auto":
        st.markdown(
            f'**Thème appliqué :** <span class="theme-badge">{resolved}</span>',
            unsafe_allow_html=True
        )
    else:
        st.markdown(
            f'**Thème appliqué :** <span class="theme-badge">{selected_theme}</span>',
            unsafe_allow_html=True
        )

    platform_ids_default = ", ".join(profile.get("platform_ids", []))
    platform_ids_text = st.text_input(
        "IDs plateformes à privilégier (optionnel, séparés par virgule)",
        value=platform_ids_default,
        help="Exemple : netflix, prime, disney, canal"
    )

    if st.button("💾 Enregistrer le profil"):
        profile["country"] = country
        profile["lang"] = lang
        profile["ui_theme"] = selected_theme
        profile["platform_ids"] = [
            x.strip() for x in platform_ids_text.split(",") if x.strip()
        ]
        save_profile(profile)
        st.success("Profil enregistré.")
        st.rerun()

    with st.expander("Plateformes disponibles dans ce pays"):
        try:
            services = get_services(country, lang)
            if services:
                for svc in services[:200]:
                    name = svc.get("name") or svc.get("id") or "?"
                    sid = svc.get("id") or "?"
                    st.write(f"- {name} ({sid})")
            else:
                st.caption("Aucune plateforme chargée.")
        except Exception as e:
            st.caption(f"Impossible de charger les plateformes : {e}")


# =========================================================
# HEADER
# =========================================================
st.title("🎬 FilmFinder IA")
st.caption("Trouve un film ou une série par titre, acteur ou résumé.")

# =========================================================
# BARRE DE RECHERCHE
# =========================================================
qcol, xcol = st.columns([20, 1], gap="small")

with qcol:
    query = st.text_input(
        "Recherche",
        value=st.session_state.get("q", ""),
        placeholder='Exemple : "Seul au monde" ou "homme rescapé d’un crash d’avion sur une île"',
        key="search_input_main",
        label_visibility="collapsed"
    )

with xcol:
    st.markdown('<div class="ff-x-btn">', unsafe_allow_html=True)
    if st.button("✕", key="clear_search_btn", help="Effacer la recherche"):
        st.session_state["q"] = ""
        st.session_state["results"] = []
        st.session_state["last_error"] = ""
        st.session_state["scroll_to_results"] = False
        clear_query_params()
        st.rerun()
    st.markdown("</div>", unsafe_allow_html=True)

st.session_state["q"] = query

type_col, button_col = st.columns([2, 1], gap="small")
with type_col:
    selected_type = st.radio(
        "Type",
        options=["movie", "series"],
        index=0 if st.session_state.get("show_type", "movie") == "movie" else 1,
        format_func=lambda x: "Films" if x == "movie" else "Séries",
        horizontal=True
    )
    st.session_state["show_type"] = selected_type

with button_col:
    search_clicked = st.button("🔎 Rechercher", use_container_width=True)

# Enter sur acteur cliquable ou chargement URL
if st.session_state.get("pending_actor_search"):
    search_clicked = True
    st.session_state["pending_actor_search"] = False

# =========================================================
# LANCEMENT RECHERCHE
# =========================================================
if search_clicked:
    inject_blur_active_element()
    st.session_state["last_error"] = ""
    st.session_state["results"] = []

    user_query = st.session_state.get("q", "").strip()

    if not user_query:
        st.session_state["last_error"] = "Tape une recherche."
    else:
        try:
            with st.spinner("Recherche en cours..."):
                results = search_candidates(
                    country=profile.get("country", country),
                    show_type=st.session_state["show_type"],
                    lang=profile.get("lang", lang),
                    user_query=user_query,
                )

                preferred_platforms = [
                    x.strip().lower()
                    for x in profile.get("platform_ids", [])
                    if str(x).strip()
                ]

                if preferred_platforms:
                    def pref_score(show):
                        options = show.get("_streaming_options_country") or []
                        service_ids = [
                            ((opt.get("service") or {}).get("id") or "").lower()
                            for opt in options
                        ]
                        return any(pid in service_ids for pid in preferred_platforms)

                    results.sort(
                        key=lambda s: (
                            not pref_score(s),
                            -(s.get("_score") or 0),
                            -(s.get("releaseYear") or s.get("firstAirYear") or 0),
                        )
                    )

                st.session_state["results"] = results[:20]
                st.session_state["scroll_to_results"] = True
        except Exception as e:
            st.session_state["last_error"] = str(e)

# =========================================================
# MESSAGES
# =========================================================
if st.session_state.get("last_error"):
    st.error(st.session_state["last_error"])

# =========================================================
# RESULTATS
# =========================================================
st.markdown('<div id="results-anchor"></div>', unsafe_allow_html=True)

results = st.session_state.get("results", [])

if results:
    st.subheader(f"Résultats ({len(results)})")

    if st.session_state.get("scroll_to_results"):
        inject_scroll_to_results()
        st.session_state["scroll_to_results"] = False

    for show in results:
        render_result_card(
            show=show,
            country=profile.get("country", country),
            show_type=st.session_state["show_type"],
            lang=profile.get("lang", lang),
        )

elif st.session_state.get("q", "").strip() and not st.session_state.get("last_error"):
    st.info("Aucun résultat trouvé.")