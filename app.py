import html
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
# PROFILE
# =========================================================
def load_profile() -> dict:
    if PROFILE_PATH.exists():
        try:
            data = json.loads(PROFILE_PATH.read_text(encoding="utf-8"))
            data.setdefault("country", "fr")
            data.setdefault("lang", "fr")
            data.setdefault("platform_ids", [])
            return data
        except Exception:
            pass
    return {"country": "fr", "lang": "fr", "platform_ids": []}


def save_profile(profile: dict) -> None:
    PROFILE_PATH.write_text(
        json.dumps(profile, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


profile = load_profile()

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


def esc(text):
    return html.escape("" if text is None else str(text), quote=True)


def safe_css_url(url: str) -> str:
    if not url:
        return ""
    return html.escape(url.replace('"', "%22").replace("'", "%27"), quote=True)

# =========================================================
# QUERY PARAMS
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
# THÈME AUTO
# =========================================================
THEMES = {
    "Cinéma vintage": {
        "accent": "#b85c38",
        "panel_bg": "linear-gradient(180deg, rgba(255,255,255,0.97), rgba(246,246,246,0.95))",
    },
    "Romance": {
        "accent": "#ff4d6d",
        "panel_bg": "linear-gradient(180deg, rgba(255,255,255,0.97), rgba(246,246,246,0.95))",
    },
    "Science-fiction": {
        "accent": "#00d4ff",
        "panel_bg": "linear-gradient(180deg, rgba(255,255,255,0.97), rgba(246,246,246,0.95))",
    },
    "Horreur": {
        "accent": "#ff0033",
        "panel_bg": "linear-gradient(180deg, rgba(255,255,255,0.97), rgba(246,246,246,0.95))",
    },
    "Été": {
        "accent": "#ffb703",
        "panel_bg": "linear-gradient(180deg, rgba(255,255,255,0.97), rgba(246,246,246,0.95))",
    },
    "Halloween": {
        "accent": "#ff7a00",
        "panel_bg": "linear-gradient(180deg, rgba(255,255,255,0.97), rgba(246,246,246,0.95))",
    },
    "Armistice": {
        "accent": "#3a86ff",
        "panel_bg": "linear-gradient(180deg, rgba(255,255,255,0.97), rgba(246,246,246,0.95))",
    },
    "Fête des mères": {
        "accent": "#ff7aa2",
        "panel_bg": "linear-gradient(180deg, rgba(255,255,255,0.97), rgba(246,246,246,0.95))",
    },
    "Printemps": {
        "accent": "#4caf50",
        "panel_bg": "linear-gradient(180deg, rgba(255,255,255,0.97), rgba(246,246,246,0.95))",
    },
}

THEME_SEED_TITLES = {
    "Cinéma vintage": ["Casablanca", "Vertigo", "The Godfather"],
    "Romance": ["Titanic", "The Notebook", "La La Land"],
    "Science-fiction": ["Interstellar", "The Matrix", "Blade Runner 2049"],
    "Horreur": ["Halloween", "It", "The Shining"],
    "Été": ["Mamma Mia!", "Jaws", "The Beach"],
    "Halloween": ["Halloween", "Scream", "Beetlejuice"],
    "Armistice": ["1917", "Dunkirk", "Saving Private Ryan"],
    "Fête des mères": ["Little Women", "Mamma Mia!", "The Blind Side"],
    "Printemps": ["Amélie", "Big Fish", "The Secret Garden"],
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


def apply_global_css(theme_name: str, poster_url: str):
    accent = THEMES[theme_name]["accent"]
    panel_bg = THEMES[theme_name]["panel_bg"]
    safe_url = safe_css_url(poster_url)

    css = f"""
    <style>
    :root {{
        color-scheme: light !important;
    }}

    html, body, .stApp, [data-testid="stAppViewContainer"] {{
        background-image:
            linear-gradient(180deg, rgba(0,0,0,0.18), rgba(0,0,0,0.56)),
            url("{safe_url}") !important;
        background-size: cover !important;
        background-position: center center !important;
        background-attachment: fixed !important;
        color: #111111 !important;
    }}

    [data-testid="stAppViewContainer"]::before {{
        content:"";
        position: fixed;
        inset: 0;
        pointer-events:none;
        background:
            repeating-linear-gradient(
                0deg,
                rgba(255,255,255,0.015),
                rgba(255,255,255,0.015) 1px,
                rgba(0,0,0,0.015) 2px,
                rgba(0,0,0,0.015) 3px
            );
        opacity: 0.10;
        z-index: 0;
    }}

    .main .block-container {{
        position: relative;
        z-index: 1;
        max-width: 1360px !important;
        margin: 12px auto !important;
        background: transparent !important;
        border: 0 !important;
        box-shadow: none !important;
        padding: 10px 12px 24px 12px !important;
    }}

    [data-testid="stSidebar"] > div:first-child {{
        background: rgba(255,255,255,0.90) !important;
        border-right: 1px solid rgba(0,0,0,0.08) !important;
    }}

    .ff-panel {{
        background: {panel_bg};
        border: 1px solid rgba(220,220,220,0.95);
        border-radius: 16px;
        padding: 12px;
        box-shadow: 0 8px 20px rgba(0,0,0,0.12);
        color: #111111 !important;
    }}

    .ff-muted {{
        color: rgba(0,0,0,0.72) !important;
        font-size: 13px;
    }}

    .ff-pilllabel {{
        display: inline-block;
        padding: 5px 10px;
        border-radius: 10px;
        background: linear-gradient(180deg, rgba(255,255,255,0.98), rgba(244,244,244,0.96));
        color: #111111 !important;
        border: 1px solid rgba(220,220,220,0.95);
        margin-bottom: 6px;
        box-shadow: 0 3px 8px rgba(0,0,0,0.10);
        font-size: 13px;
        font-weight: 600;
    }}

    .stButton > button,
    .stFormSubmitButton > button {{
        background: linear-gradient(180deg, rgba(255,255,255,0.99), rgba(242,242,242,0.96)) !important;
        color: #111111 !important;
        border: 1px solid #d9d9d9 !important;
        border-radius: 12px !important;
        box-shadow: 0 3px 10px rgba(0,0,0,0.10);
        font-weight: 600 !important;
    }}

    .stButton > button:hover,
    .stFormSubmitButton > button:hover {{
        border-color: {accent} !important;
    }}

    .ff-card {{
        border: 1px solid rgba(220,220,220,0.95);
        background: linear-gradient(180deg, rgba(255,255,255,0.97), rgba(248,248,248,0.95));
        border-radius: 16px;
        padding: 12px;
        margin-top: 10px;
        box-shadow: 0 10px 22px rgba(0,0,0,0.12);
    }}

    .ff-linkbox {{
        display: inline-block;
        padding: 4px 8px;
        margin: 3px 4px 3px 0;
        background: rgba(255,255,255,0.98);
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
        color: {accent};
        position: absolute;
        left: 0;
        top: 0;
        overflow: hidden;
        white-space: nowrap;
        display: block;
    }}
    </style>
    """
    st.markdown(css, unsafe_allow_html=True)


ACTIVE_THEME_NAME = choose_auto_theme_name()
ACTIVE_THEME_POSTER = get_theme_background_poster(
    ACTIVE_THEME_NAME,
    profile.get("country", "fr"),
    profile.get("lang", "fr"),
)
apply_global_css(ACTIVE_THEME_NAME, ACTIVE_THEME_POSTER)

# =========================================================
# BANDE-ANNONCE DIRECTE
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

    alias_titles = exact_alias_titles(query)
    alias_norms = [norm_loose(x) for x in alias_titles]

    if t == q:
        return 6
    if t in alias_norms:
        return 6
    if q in t or t in q:
        return 2

    for alias in alias_norms:
        if alias in t or t in alias:
            return 2

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

    if story:
        for title_candidate in exact_alias_titles(story):
            for stype in show_types:
                exact = search_by_title(country, stype, lang, title_candidate)
                if not exact:
                    exact = search_by_title("us", stype, lang, title_candidate)
                if exact:
                    found += add_chunk(country, exact)

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
        discovered_in = source_country.get(stable_id(show), country)

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


def apply_filters_and_sort(items, sort_mode, only_my_apps, platform_filter):
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
st.session_state.setdefault("scroll_to_results", False)

# Hidden bridge fields
st.session_state.setdefault("ff_story", "")
st.session_state.setdefault("ff_actor", "")
st.session_state.setdefault("ff_type", "Films")
st.session_state.setdefault("ff_mode", "Normal")
st.session_state.setdefault("ff_sort", "Pertinence")
st.session_state.setdefault("ff_platform", "Toutes")
st.session_state.setdefault("ff_only_apps", "0")

qp = get_query_params()
if "actor" in qp:
    val = qp.get("actor")
    actor_param = val[0] if isinstance(val, list) and val else (val if isinstance(val, str) else "")
    clear_query_params()
    st.session_state["ff_actor"] = actor_param
    st.session_state["ff_story"] = ""
    st.session_state["ff_type"] = "Films"
    st.session_state["did_enter"] = True
    st.session_state["page"] = "Recherche"

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

    hero = f"""
    <div class="ff-panel" style="padding:0;overflow:hidden;background:transparent;border:none;box-shadow:none;">
      <div style="
        position:relative; min-height:220px; border-radius:18px; overflow:hidden;
        box-shadow:0 12px 26px rgba(0,0,0,0.18);
        border:1px solid rgba(255,255,255,0.55);
      ">
        <div style="
          position:absolute; inset:0;
          background-image:url('{safe_css_url(ACTIVE_THEME_POSTER)}');
          background-size:cover;
          background-position:center;
          transform:scale(1.03);
        "></div>
        <div style="position:absolute; inset:0; background:linear-gradient(180deg, rgba(0,0,0,0.10), rgba(0,0,0,0.66));"></div>
        <div style="position:relative; z-index:2; padding:18px; min-height:220px; display:flex; align-items:flex-end;">
          <div style="
            background:linear-gradient(180deg, rgba(255,255,255,0.97), rgba(246,246,246,0.95));
            color:#111; padding:12px 14px; border-radius:16px; max-width:720px;
            border:1px solid rgba(220,220,220,0.95);
            box-shadow:0 6px 18px rgba(0,0,0,0.14);
          ">
            <div style="font-size:28px; font-weight:800; margin-bottom:4px;">
              🎬 FilmFinder IA
            </div>
            <div style="font-size:14px;">
              Choisis tes plateformes une fois, puis entre.
            </div>
          </div>
        </div>
      </div>
    </div>
    """
    st.markdown(hero, unsafe_allow_html=True)

    if not RAPIDAPI_KEY:
        st.error("RAPIDAPI_KEY manquante dans .env")
        st.stop()

    with st.form("welcome_profile"):
        left, right = st.columns(2)
        with left:
            st.markdown('<div class="ff-pilllabel">Pays</div>', unsafe_allow_html=True)
            country = st.selectbox(
                "Pays",
                ["fr", "be", "ch", "gb", "us"],
                index=["fr", "be", "ch", "gb", "us"].index(profile.get("country", "fr")),
                label_visibility="collapsed",
            )
        with right:
            st.markdown('<div class="ff-pilllabel">Langue</div>', unsafe_allow_html=True)
            lang = st.selectbox(
                "Langue",
                ["fr", "en"],
                index=["fr", "en"].index(profile.get("lang", "fr")),
                label_visibility="collapsed",
            )

        st.markdown('<div class="ff-pilllabel">Tes plateformes</div>', unsafe_allow_html=True)
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
            label_visibility="collapsed",
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

    with st.form("profile_form"):
        left, right = st.columns(2)
        with left:
            st.markdown('<div class="ff-pilllabel">Pays</div>', unsafe_allow_html=True)
            country = st.selectbox(
                "Pays",
                ["fr", "be", "ch", "gb", "us"],
                index=["fr", "be", "ch", "gb", "us"].index(profile.get("country", "fr")),
                label_visibility="collapsed",
            )
        with right:
            st.markdown('<div class="ff-pilllabel">Langue</div>', unsafe_allow_html=True)
            lang = st.selectbox(
                "Langue",
                ["fr", "en"],
                index=["fr", "en"].index(profile.get("lang", "fr")),
                label_visibility="collapsed",
            )

        st.markdown('<div class="ff-pilllabel">Tes plateformes</div>', unsafe_allow_html=True)
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
            label_visibility="collapsed",
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
# RECHERCHE - HIDDEN BRIDGE WIDGETS
# =========================================================
if not profile.get("platform_ids"):
    st.warning("Choisis au moins 1 plateforme dans Accueil/Profil.")
    st.session_state["did_enter"] = False
    st.session_state["page"] = "Accueil"
    st.rerun()

_ = st.text_input("__ff_story__", key="ff_story")
_ = st.text_input("__ff_actor__", key="ff_actor")
_ = st.text_input("__ff_type__", key="ff_type")
_ = st.text_input("__ff_mode__", key="ff_mode")
_ = st.text_input("__ff_sort__", key="ff_sort")
_ = st.text_input("__ff_platform__", key="ff_platform")
_ = st.text_input("__ff_only_apps__", key="ff_only_apps")
search_clicked = st.button("__ff_search__", key="ff_search_btn")

if search_clicked:
    st.session_state["scroll_to_results"] = True

# =========================================================
# RECHERCHE - UI CUSTOM
# =========================================================
services = get_services(profile["country"], profile["lang"])
id_to_name = {s.get("id"): (s.get("name") or s.get("id")) for s in services}
platform_choices = ["Toutes"] + sorted(
    [id_to_name.get(i, i) for i in profile.get("platform_ids", [])]
)

def search_component_html():
    theme_bg = safe_css_url(ACTIVE_THEME_POSTER)
    current_story = esc(st.session_state.get("ff_story", ""))
    current_actor = esc(st.session_state.get("ff_actor", ""))
    current_type = esc(st.session_state.get("ff_type", "Films"))
    current_mode = esc(st.session_state.get("ff_mode", "Normal"))
    current_sort = esc(st.session_state.get("ff_sort", "Pertinence"))
    current_platform = esc(st.session_state.get("ff_platform", "Toutes"))
    current_only = "checked" if st.session_state.get("ff_only_apps", "0") == "1" else ""

    type_options = ["Films", "Séries", "Films et séries"]
    mode_options = ["Rapide", "Normal", "Profond"]
    sort_options = ["Pertinence", "Année (récent)", "Année (ancien)", "Note (haute)"]

    type_opts_html = "".join(
        f'<option value="{esc(x)}" {"selected" if x == st.session_state.get("ff_type","Films") else ""}>{esc(x)}</option>'
        for x in type_options
    )
    sort_opts_html = "".join(
        f'<option value="{esc(x)}" {"selected" if x == st.session_state.get("ff_sort","Pertinence") else ""}>{esc(x)}</option>'
        for x in sort_options
    )
    platform_opts_html = "".join(
        f'<option value="{esc(x)}" {"selected" if x == st.session_state.get("ff_platform","Toutes") else ""}>{esc(x)}</option>'
        for x in platform_choices
    )

    radio_html = "".join(
        f"""
        <label class="ff-radio">
            <input type="radio" name="ff_mode_local" value="{esc(x)}" {"checked" if x == st.session_state.get("ff_mode","Normal") else ""}>
            <span>{esc(x)}</span>
        </label>
        """
        for x in mode_options
    )

    return f"""
    <!doctype html>
    <html>
    <head>
      <meta charset="utf-8" />
      <style>
        html, body {{
          margin: 0;
          padding: 0;
          background: transparent;
          font-family: Arial, Helvetica, sans-serif;
        }}

        .wrap {{
          padding: 4px 2px 8px 2px;
        }}

        .title {{
          display: inline-block;
          background: linear-gradient(180deg, rgba(255,255,255,0.98), rgba(244,244,244,0.96));
          color: #111;
          padding: 10px 14px;
          border-radius: 14px;
          font-size: 22px;
          font-weight: 800;
          border: 1px solid rgba(220,220,220,0.95);
          box-shadow: 0 4px 10px rgba(0,0,0,0.12);
          margin-bottom: 12px;
        }}

        .panel {{
          position: relative;
          border-radius: 22px;
          overflow: hidden;
          min-height: 260px;
          box-shadow: 0 14px 30px rgba(0,0,0,0.22);
          border: 1px solid rgba(255,255,255,0.35);
          background-image:
            linear-gradient(180deg, rgba(0,0,0,0.18), rgba(0,0,0,0.55)),
            url("{theme_bg}");
          background-size: cover;
          background-position: center;
        }}

        .overlay {{
          padding: 20px;
          display: grid;
          gap: 12px;
        }}

        .row2 {{
          display: grid;
          grid-template-columns: 1fr 1fr;
          gap: 14px;
        }}

        .row3 {{
          display: grid;
          grid-template-columns: 1.2fr 1.2fr 0.8fr;
          gap: 14px;
        }}

        .pill {{
          display: inline-block;
          padding: 5px 10px;
          border-radius: 10px;
          background: linear-gradient(180deg, rgba(255,255,255,0.98), rgba(244,244,244,0.96));
          color: #111;
          border: 1px solid rgba(220,220,220,0.95);
          margin-bottom: 6px;
          box-shadow: 0 3px 8px rgba(0,0,0,0.10);
          font-size: 13px;
          font-weight: 600;
        }}

        .fieldbox {{
          background: linear-gradient(180deg, rgba(255,255,255,0.98), rgba(246,246,246,0.96));
          border: 1px solid rgba(220,220,220,0.95);
          border-radius: 16px;
          box-shadow: 0 8px 20px rgba(0,0,0,0.12);
          padding: 10px;
        }}

        .select-clean {{
          width: 100%;
          border: none;
          outline: none;
          background: #fff;
          border-radius: 12px;
          padding: 12px 14px;
          font-size: 15px;
          color: #111;
          box-sizing: border-box;
          border: 1px solid rgba(220,220,220,0.95);
        }}

        .hintbox {{
          background: linear-gradient(180deg, rgba(255,255,255,0.98), rgba(246,246,246,0.96));
          border: 1px solid rgba(220,220,220,0.95);
          border-radius: 14px;
          padding: 10px 12px;
          color: rgba(0,0,0,0.70);
          font-size: 13px;
          box-shadow: 0 8px 20px rgba(0,0,0,0.10);
        }}

        .inputwrap {{
          position: relative;
        }}

        .input-clean {{
          width: 100%;
          border: 1px solid rgba(220,220,220,0.95);
          outline: none;
          background: #fff;
          border-radius: 14px;
          padding: 13px 44px 13px 14px;
          font-size: 15px;
          color: #111;
          box-sizing: border-box;
          box-shadow: 0 8px 20px rgba(0,0,0,0.10);
        }}

        .clear-btn {{
          position: absolute;
          right: 10px;
          top: 50%;
          transform: translateY(-50%);
          width: 28px;
          height: 28px;
          border-radius: 9px;
          border: 1px solid rgba(220,220,220,0.95);
          background: linear-gradient(180deg, rgba(255,255,255,0.98), rgba(244,244,244,0.96));
          color: #555;
          font-size: 16px;
          cursor: pointer;
          display: flex;
          align-items: center;
          justify-content: center;
        }}

        .modes {{
          display: flex;
          gap: 18px;
          align-items: center;
          flex-wrap: wrap;
          padding: 10px 12px;
          background: linear-gradient(180deg, rgba(255,255,255,0.98), rgba(246,246,246,0.96));
          border: 1px solid rgba(220,220,220,0.95);
          border-radius: 14px;
          box-shadow: 0 8px 20px rgba(0,0,0,0.10);
        }}

        .ff-radio {{
          display: inline-flex;
          align-items: center;
          gap: 7px;
          font-size: 15px;
          color: #111;
          cursor: pointer;
        }}

        .actionbar {{
          display: flex;
          gap: 10px;
          align-items: center;
          flex-wrap: wrap;
        }}

        .search-btn {{
          border: 1px solid rgba(220,220,220,0.95);
          background: linear-gradient(180deg, rgba(255,255,255,0.99), rgba(242,242,242,0.96));
          color: #111;
          border-radius: 14px;
          padding: 12px 18px;
          font-size: 16px;
          font-weight: 700;
          cursor: pointer;
          box-shadow: 0 6px 16px rgba(0,0,0,0.12);
        }}

        .only-apps {{
          display: inline-flex;
          align-items: center;
          gap: 8px;
          background: linear-gradient(180deg, rgba(255,255,255,0.98), rgba(246,246,246,0.96));
          border: 1px solid rgba(220,220,220,0.95);
          border-radius: 14px;
          padding: 12px 14px;
          box-shadow: 0 8px 20px rgba(0,0,0,0.10);
          color: #111;
          font-size: 14px;
        }}

        @media (max-width: 900px) {{
          .row2, .row3 {{
            grid-template-columns: 1fr;
          }}
        }}
      </style>
    </head>
    <body>
      <div class="wrap">
        <div class="title">Recherche</div>

        <div class="panel">
          <div class="overlay">

            <div class="row2">
              <div>
                <div class="pill">Je cherche</div>
                <div class="fieldbox">
                  <select id="ff_type_local" class="select-clean">{type_opts_html}</select>
                </div>
              </div>

              <div>
                <div class="pill">Mode</div>
                <div class="modes">{radio_html}</div>
              </div>
            </div>

            <div class="hintbox">Astuce • Acteur seul = OK • Clique acteur = films</div>

            <div>
              <div class="pill">Histoire / souvenir / titre exact</div>
              <div class="inputwrap">
                <input id="ff_story_local" class="input-clean" type="text"
                  value="{current_story}"
                  placeholder="Ex: Seul au monde ou un homme rescapé d'un crash avion sur une île déserte">
                <button id="ff_story_clear" class="clear-btn" type="button">×</button>
              </div>
            </div>

            <div>
              <div class="pill">Acteur/actrice (optionnel)</div>
              <div class="inputwrap">
                <input id="ff_actor_local" class="input-clean" type="text"
                  value="{current_actor}"
                  placeholder="Ex: Tom Hanks">
                <button id="ff_actor_clear" class="clear-btn" type="button">×</button>
              </div>
            </div>

            <div class="actionbar">
              <button id="ff_submit" class="search-btn" type="button">Chercher</button>
            </div>

            <div class="row3">
              <div>
                <div class="pill">Trier par</div>
                <div class="fieldbox">
                  <select id="ff_sort_local" class="select-clean">{sort_opts_html}</select>
                </div>
              </div>

              <div>
                <div class="pill">Plateforme</div>
                <div class="fieldbox">
                  <select id="ff_platform_local" class="select-clean">{platform_opts_html}</select>
                </div>
              </div>

              <div>
                <div class="pill">Filtre</div>
                <label class="only-apps">
                  <input id="ff_only_local" type="checkbox" {current_only}>
                  <span>Seulement mes applis</span>
                </label>
              </div>
            </div>
          </div>
        </div>
      </div>

      <script>
        function setFrameHeight() {{
          const h = Math.max(document.body.scrollHeight, 420);
          parent.postMessage({{
            isStreamlitMessage: true,
            type: "streamlit:setFrameHeight",
            height: h
          }}, "*");
        }}

        function qParentInput(label) {{
          return parent.document.querySelector('input[aria-label="' + label + '"]');
        }}

        function qParentButton(label) {{
          const btns = Array.from(parent.document.querySelectorAll("button"));
          return btns.find(b => (b.innerText || "").trim() === label);
        }}

        function reactSetValue(el, value) {{
          if (!el) return;
          const setter = Object.getOwnPropertyDescriptor(window.HTMLInputElement.prototype, "value").set;
          setter.call(el, value);
          el.dispatchEvent(new Event("input", {{ bubbles: true }}));
          el.dispatchEvent(new Event("change", {{ bubbles: true }}));
        }}

        function hideBridge() {{
          const labels = [
            "__ff_story__",
            "__ff_actor__",
            "__ff_type__",
            "__ff_mode__",
            "__ff_sort__",
            "__ff_platform__",
            "__ff_only_apps__"
          ];

          labels.forEach(label => {{
            const input = qParentInput(label);
            if (input) {{
              const widget = input.closest('[data-testid="stTextInput"]') || input.closest('[data-testid="stWidget"]');
              if (widget) widget.style.display = "none";
            }}
          }});

          const btn = qParentButton("__ff_search__");
          if (btn) {{
            const wrap = btn.closest('[data-testid="stButton"]') || btn.parentElement;
            if (wrap) wrap.style.display = "none";
          }}
        }}

        function blurAll() {{
          try {{
            document.activeElement && document.activeElement.blur && document.activeElement.blur();
            parent.document.activeElement && parent.document.activeElement.blur && parent.document.activeElement.blur();
            parent.document.body && parent.document.body.focus && parent.document.body.focus();
          }} catch(e) {{}}
        }}

        function submitSearch() {{
          const story = document.getElementById("ff_story_local").value || "";
          const actor = document.getElementById("ff_actor_local").value || "";
          const type = document.getElementById("ff_type_local").value || "Films";
          const mode = (document.querySelector('input[name="ff_mode_local"]:checked') || {{value:"Normal"}}).value;
          const sort = document.getElementById("ff_sort_local").value || "Pertinence";
          const platform = document.getElementById("ff_platform_local").value || "Toutes";
          const onlyApps = document.getElementById("ff_only_local").checked ? "1" : "0";

          reactSetValue(qParentInput("__ff_story__"), story);
          reactSetValue(qParentInput("__ff_actor__"), actor);
          reactSetValue(qParentInput("__ff_type__"), type);
          reactSetValue(qParentInput("__ff_mode__"), mode);
          reactSetValue(qParentInput("__ff_sort__"), sort);
          reactSetValue(qParentInput("__ff_platform__"), platform);
          reactSetValue(qParentInput("__ff_only_apps__"), onlyApps);

          blurAll();

          const btn = qParentButton("__ff_search__");
          if (btn) btn.click();
        }}

        document.getElementById("ff_submit").addEventListener("click", submitSearch);

        document.getElementById("ff_story_local").addEventListener("keydown", function(e) {{
          if (e.key === "Enter") {{
            e.preventDefault();
            submitSearch();
          }}
        }});

        document.getElementById("ff_actor_local").addEventListener("keydown", function(e) {{
          if (e.key === "Enter") {{
            e.preventDefault();
            submitSearch();
          }}
        }});

        document.getElementById("ff_story_clear").addEventListener("click", function() {{
          document.getElementById("ff_story_local").value = "";
          document.getElementById("ff_story_local").focus();
        }});

        document.getElementById("ff_actor_clear").addEventListener("click", function() {{
          document.getElementById("ff_actor_local").value = "";
          document.getElementById("ff_actor_local").focus();
        }});

        document.getElementById("ff_sort_local").addEventListener("change", submitSearch);
        document.getElementById("ff_platform_local").addEventListener("change", submitSearch);
        document.getElementById("ff_only_local").addEventListener("change", submitSearch);

        setTimeout(() => {{
          hideBridge();
          setFrameHeight();
        }}, 80);

        setTimeout(() => {{
          hideBridge();
          setFrameHeight();
        }}, 400);
      </script>
    </body>
    </html>
    """

components.html(search_component_html(), height=460, scrolling=False)

# =========================================================
# SEARCH EXECUTION
# =========================================================
if search_clicked:
    st.session_state["raw_items"] = build_raw_items(
        st.session_state.get("ff_story", "").strip(),
        st.session_state.get("ff_actor", "").strip(),
        st.session_state.get("ff_mode", "Normal"),
        profile,
        showtype_to_list(st.session_state.get("ff_type", "Films")),
    )

raw_items = st.session_state.get("raw_items", [])

if not raw_items:
    st.markdown(
        '<div class="ff-panel ff-muted">Tape une histoire, un titre exact ou un acteur puis valide avec Entrée ou Chercher.</div>',
        unsafe_allow_html=True,
    )
    st.stop()

view = apply_filters_and_sort(
    raw_items,
    st.session_state.get("ff_sort", "Pertinence"),
    st.session_state.get("ff_only_apps", "0") == "1",
    st.session_state.get("ff_platform", "Toutes"),
)

st.markdown('<div id="ff-first-film-anchor"></div>', unsafe_allow_html=True)

if st.session_state.pop("scroll_to_results", False):
    components.html(
        """
        <script>
        setTimeout(function(){
          try {
            if (parent.document.activeElement && parent.document.activeElement.blur) {
              parent.document.activeElement.blur();
            }
            if (parent.document.body && parent.document.body.focus) {
              parent.document.body.focus();
            }
          } catch(e) {}

          const el = parent.document.getElementById("ff-first-film-anchor");
          if (el) {
            el.scrollIntoView({behavior:"smooth", block:"start"});
          }
        }, 120);
        </script>
        """,
        height=0,
        scrolling=False,
    )

# =========================================================
# RESULTS HTML CUSTOM
# =========================================================
allowed_ids = set(profile.get("platform_ids", []))


def details_fr_links(show_id: str):
    data = get_show_details(show_id, profile["country"], "movie", profile["lang"])
    if not data:
        data = get_show_details(show_id, profile["country"], "series", profile["lang"])
    opts = ((data.get("streamingOptions") or {}).get(profile["country"]) or []) if data else []
    return dedupe_streaming_options(opts)


def result_card_html(item):
    show_id = str(item.get("api_id") or "")
    title = esc(item["title"])
    year = esc(item["year"] if item["year"] else "")
    poster = esc(item.get("poster") or "")
    overview = esc(item.get("overview") or "")
    trailer_url = esc(trailer_direct_url(item["title"], item.get("year")))

    stars = ""
    if item.get("score100") is not None:
        score5 = round(float(item["score100"]) / 20.0, 1)
        stars = f"""
        <div class="r-stars-line">
          {stars_html(item["score100"])}
          <span class="r-score">({esc(score5)}/5)</span>
        </div>
        """

    opts_all = item.get("opts_all") or []
    if not opts_all and show_id:
        opts_all = details_fr_links(show_id)

    groups = group_options_by_service(opts_all)
    mine = [g for g in groups if g["id"] in allowed_ids]
    others = [g for g in groups if g["id"] not in allowed_ids]

    mine_html = ""
    if mine:
        mine_html += '<div class="r-small ok">✅ Dispo sur tes applis</div>'
        mine_html += '<div class="r-block-title">Tes plateformes :</div>'
        for g in mine:
            primary, rest = pick_primary_option(g["opts"])
            label = esc(g["name"])
            typ = esc(primary["type"] if primary else "")
            link = esc(primary["link"] if primary and primary.get("link") else "")
            if link:
                mine_html += f'<div class="r-link-line"><b>{label}</b> ({typ}) → <a href="{link}" target="_blank">{link}</a></div>'
            else:
                mine_html += f'<div class="r-link-line"><b>{label}</b> ({typ})</div>'

            if rest:
                mine_html += '<div class="r-sublist">'
                for opt in rest:
                    typ2 = esc(opt["type"])
                    link2 = esc(opt["link"] or "")
                    if link2:
                        mine_html += f'<div>• ({typ2}) → <a href="{link2}" target="_blank">{link2}</a></div>'
                    else:
                        mine_html += f'<div>• ({typ2})</div>'
                mine_html += '</div>'
    else:
        mine_html += '<div class="r-small no">❌ Pas dispo sur tes applis</div>'

    others_html = ""
    if others:
        others_html += '<div class="r-block-title">Autres plateformes :</div>'
        for g in others:
            primary, rest = pick_primary_option(g["opts"])
            label = esc(g["name"])
            typ = esc(primary["type"] if primary else "")
            link = esc(primary["link"] if primary and primary.get("link") else "")
            if link:
                others_html += f'<div class="r-link-line"><b>{label}</b> ({typ}) → <a href="{link}" target="_blank">{link}</a></div>'
            else:
                others_html += f'<div class="r-link-line"><b>{label}</b> ({typ})</div>'
            if rest:
                others_html += '<div class="r-sublist">'
                for opt in rest:
                    typ2 = esc(opt["type"])
                    link2 = esc(opt["link"] or "")
                    if link2:
                        others_html += f'<div>• ({typ2}) → <a href="{link2}" target="_blank">{link2}</a></div>'
                    else:
                        others_html += f'<div>• ({typ2})</div>'
                others_html += '</div>'

    cast = item.get("cast") or []
    actors_html = ""
    if cast:
        actor_links = []
        for actor in cast[:12]:
            actor_safe = esc(actor)
            actor_js = actor.replace("\\", "\\\\").replace("'", "\\'")
            actor_links.append(
                f'<a href="javascript:void(0)" class="r-actor" onclick="searchActor(\'{actor_js}\')">{actor_safe}</a>'
            )
        actors_html = '<div class="r-actors"><b>Acteurs :</b> ' + " ".join(actor_links) + "</div>"

    trailer_html = ""
    if trailer_url:
        trailer_html = f'<a class="r-pilllink" href="{trailer_url}" target="_blank">Bande-annonce</a>'

    card_id = esc(stable_id(item["show"]))
    return f"""
    <div class="result-card" id="card-{card_id}">
      <div class="result-grid">
        <div class="result-left">
          {'<img class="poster" src="' + poster + '" alt="poster">' if poster else ''}
          {trailer_html}
        </div>

        <div class="result-right">
          <div class="result-title">{title} {f'({year})' if year else ''}</div>
          {stars}
          {mine_html}

          <button class="detail-btn" type="button" onclick="toggleDetails('{card_id}')">Détails</button>

          <div class="detail-box" id="detail-{card_id}">
            {'<div class="r-overview">' + overview + '</div>' if overview else ''}
            {actors_html}
            {others_html}
          </div>
        </div>
      </div>
    </div>
    """


cards_html = "".join(result_card_html(x) for x in view[:20])

results_html = f"""
<!doctype html>
<html>
<head>
  <meta charset="utf-8"/>
  <style>
    html, body {{
      margin:0;
      padding:0;
      background: transparent;
      font-family: Arial, Helvetica, sans-serif;
      color:#111;
    }}

    .results-wrap {{
      padding: 6px 2px 20px 2px;
    }}

    .count-box {{
      display:inline-block;
      margin-bottom:10px;
      padding:10px 14px;
      border-radius:14px;
      background: linear-gradient(180deg, rgba(255,255,255,0.97), rgba(246,246,246,0.95));
      border:1px solid rgba(220,220,220,0.95);
      box-shadow:0 6px 18px rgba(0,0,0,0.12);
      font-weight:700;
    }}

    .result-card {{
      border:1px solid rgba(220,220,220,0.95);
      background: linear-gradient(180deg, rgba(255,255,255,0.97), rgba(248,248,248,0.95));
      border-radius:18px;
      padding:14px;
      margin: 10px 0;
      box-shadow:0 12px 22px rgba(0,0,0,0.14);
    }}

    .result-grid {{
      display:grid;
      grid-template-columns: 180px 1fr;
      gap:18px;
    }}

    .poster {{
      width:160px;
      max-width:100%;
      border-radius:14px;
      display:block;
      box-shadow:0 6px 16px rgba(0,0,0,0.20);
    }}

    .result-title {{
      font-size: 34px;
      line-height: 1.08;
      font-weight: 800;
      margin-bottom: 10px;
      color:#111;
    }}

    .r-stars-line {{
      display:flex;
      align-items:center;
      gap:8px;
      margin-bottom: 10px;
      font-size: 16px;
    }}

    .r-score {{
      color: rgba(0,0,0,0.72);
      font-size: 14px;
    }}

    .r-small {{
      margin-bottom: 8px;
      font-size: 14px;
    }}

    .r-block-title {{
      font-weight: 700;
      margin: 8px 0 6px 0;
    }}

    .r-link-line {{
      margin: 4px 0;
      word-break: break-word;
    }}

    .r-link-line a {{
      color:#0b57d0;
      text-decoration:none;
    }}

    .r-sublist {{
      margin:4px 0 8px 14px;
      color:#333;
      font-size:13px;
    }}

    .r-pilllink {{
      display:inline-block;
      margin-top:10px;
      padding:8px 10px;
      border-radius:12px;
      background: linear-gradient(180deg, rgba(255,255,255,0.98), rgba(244,244,244,0.96));
      border:1px solid rgba(220,220,220,0.95);
      color:#111;
      text-decoration:none;
      font-weight:600;
      box-shadow:0 4px 10px rgba(0,0,0,0.10);
    }}

    .detail-btn {{
      margin-top:12px;
      padding:11px 14px;
      border-radius:12px;
      border:1px solid rgba(220,220,220,0.95);
      background: linear-gradient(180deg, rgba(255,255,255,0.99), rgba(242,242,242,0.96));
      color:#111;
      cursor:pointer;
      font-weight:700;
      box-shadow:0 4px 10px rgba(0,0,0,0.10);
    }}

    .detail-box {{
      display:none;
      margin-top:12px;
      padding:12px;
      border-radius:14px;
      border:1px solid rgba(220,220,220,0.95);
      background: linear-gradient(180deg, rgba(255,255,255,0.99), rgba(246,246,246,0.96));
    }}

    .detail-box.open {{
      display:block;
    }}

    .r-overview {{
      margin-bottom: 10px;
      line-height: 1.5;
    }}

    .r-actors {{
      line-height:1.7;
      margin-bottom:10px;
    }}

    .r-actor {{
      display:inline-block;
      padding: 3px 7px;
      border-radius: 9px;
      background: rgba(255,255,255,0.98);
      border:1px solid rgba(220,220,220,0.95);
      color:#0b57d0;
      text-decoration:none;
      margin:2px 4px 2px 0;
    }}

    @media (max-width: 860px) {{
      .result-grid {{
        grid-template-columns: 1fr;
      }}
      .result-left {{
        text-align:left;
      }}
      .result-title {{
        font-size: 24px;
      }}
    }}
  </style>
</head>
<body>
  <div class="results-wrap">
    <div class="count-box">✅ Résultats : {min(len(view), 20)} / {len(view)}</div>
    {cards_html}
  </div>

  <script>
    function setFrameHeight() {{
      const h = Math.max(document.body.scrollHeight, 500);
      parent.postMessage({{
        isStreamlitMessage: true,
        type: "streamlit:setFrameHeight",
        height: h
      }}, "*");
    }}

    function qParentInput(label) {{
      return parent.document.querySelector('input[aria-label="' + label + '"]');
    }}

    function qParentButton(label) {{
      const btns = Array.from(parent.document.querySelectorAll("button"));
      return btns.find(b => (b.innerText || "").trim() === label);
    }}

    function reactSetValue(el, value) {{
      if (!el) return;
      const setter = Object.getOwnPropertyDescriptor(window.HTMLInputElement.prototype, "value").set;
      setter.call(el, value);
      el.dispatchEvent(new Event("input", {{ bubbles: true }}));
      el.dispatchEvent(new Event("change", {{ bubbles: true }}));
    }}

    function searchActor(actorName) {{
      reactSetValue(qParentInput("__ff_actor__"), actorName);
      reactSetValue(qParentInput("__ff_story__"), "");
      reactSetValue(qParentInput("__ff_type__"), "Films");
      reactSetValue(qParentInput("__ff_mode__"), "Normal");
      const btn = qParentButton("__ff_search__");
      if (btn) btn.click();
    }}

    function toggleDetails(id) {{
      const all = Array.from(document.querySelectorAll(".detail-box"));
      all.forEach(el => {{
        if (el.id !== "detail-" + id) {{
          el.classList.remove("open");
        }}
      }});

      const target = document.getElementById("detail-" + id);
      if (target) {{
        target.classList.toggle("open");
      }}

      setTimeout(setFrameHeight, 80);
    }}

    setTimeout(setFrameHeight, 80);
    setTimeout(setFrameHeight, 400);
  </script>
</body>
</html>
"""

components.html(results_html, height=800, scrolling=False)