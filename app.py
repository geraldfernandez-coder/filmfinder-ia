import os
import re
import json
import unicodedata
from pathlib import Path
from urllib.parse import quote
from datetime import date

import requests
import streamlit as st
import streamlit.components.v1 as components
from dotenv import load_dotenv

# ================== CONFIG ==================
load_dotenv()
RAPIDAPI_KEY = os.getenv("RAPIDAPI_KEY", "").strip()
RAPIDAPI_HOST = os.getenv("RAPIDAPI_HOST", "streaming-availability.p.rapidapi.com").strip()
BASE_URL = "https://streaming-availability.p.rapidapi.com"

OLLAMA_URL = os.getenv("OLLAMA_URL", "http://localhost:11434").strip()
OLLAMA_MODEL = os.getenv("OLLAMA_MODEL", "llama3.2:3b").strip()

APP_DIR = Path(__file__).parent
PROFILE_PATH = APP_DIR / "profile.json"

st.set_page_config(page_title="FilmFinder IA", layout="centered")

# ================== THEME ==================
THEMES = {
    "Auto": {},
    "Cinéma (vintage)": {"bg1":"#f7f1e1","bg2":"#fff","accent":"#b85c38","shadow":"rgba(0,0,0,0.10)"},
    "Romance": {"bg1":"#fff0f3","bg2":"#ffffff","accent":"#ff4d6d","shadow":"rgba(0,0,0,0.10)"},
    "SF": {"bg1":"#0b1020","bg2":"#121a33","accent":"#00d4ff","shadow":"rgba(0,0,0,0.35)","dark":True},
    "Horreur": {"bg1":"#0b0b0b","bg2":"#1a1a1a","accent":"#ff0033","shadow":"rgba(0,0,0,0.45)","dark":True},
    "Été": {"bg1":"#fff7e6","bg2":"#ffffff","accent":"#ffb703","shadow":"rgba(0,0,0,0.10)"},
    "Halloween": {"bg1":"#120b1f","bg2":"#1c1230","accent":"#ff7a00","shadow":"rgba(0,0,0,0.45)","dark":True},
}

def auto_theme_name() -> str:
    d = date.today()
    if d.month == 10 and d.day >= 15:
        return "Halloween"
    if d.month in (6,7,8):
        return "Été"
    return "Cinéma (vintage)"

def apply_theme(theme_name: str):
    if theme_name == "Auto":
        theme_name = auto_theme_name()
    t = THEMES.get(theme_name, THEMES["Cinéma (vintage)"])
    bg1 = t.get("bg1","#f4f6f8")
    bg2 = t.get("bg2","#ffffff")
    accent = t.get("accent","#f5c518")
    shadow = t.get("shadow","rgba(0,0,0,0.08)")
    dark = bool(t.get("dark", False))
    text = "#f1f5ff" if dark else "#111111"
    muted = "rgba(255,255,255,0.70)" if dark else "rgba(0,0,0,0.65)"
    card_bg = "rgba(255,255,255,0.08)" if dark else "#ffffff"
    border = "rgba(255,255,255,0.14)" if dark else "rgba(0,0,0,0.10)"
    input_bg = "rgba(255,255,255,0.10)" if dark else "#ffffff"
    input_text = "#ffffff" if dark else "#111111"

    st.markdown(
        f"""
        <style>
        :root {{ color-scheme: light !important; }}

        html, body, .stApp, [data-testid="stAppViewContainer"] {{
            background: linear-gradient(180deg, {bg1} 0%, {bg2} 55%, {bg2} 100%) !important;
            color: {text} !important;
        }}

        /* film grain léger (pure CSS) */
        [data-testid="stAppViewContainer"]::before {{
            content:"";
            position: fixed;
            inset: 0;
            pointer-events:none;
            background:
                repeating-linear-gradient(0deg, rgba(255,255,255,0.02), rgba(255,255,255,0.02) 1px, rgba(0,0,0,0.02) 2px, rgba(0,0,0,0.02) 3px);
            opacity: {0.20 if dark else 0.08};
            mix-blend-mode: overlay;
            z-index: 0;
        }}

        .main .block-container {{
            position: relative;
            z-index: 1;
            max-width: 1040px !important;
            margin: 12px auto !important;
            background: {card_bg} !important;
            border: 1px solid {border} !important;
            border-radius: 18px !important;
            padding: 16px 18px 22px 18px !important;
            box-shadow: 0 14px 40px {shadow} !important;
            backdrop-filter: blur({14 if dark else 2}px);
        }}

        [data-testid="stSidebar"] > div:first-child {{
            background: {card_bg} !important;
            border-right: 1px solid {border} !important;
            backdrop-filter: blur({14 if dark else 2}px);
        }}

        /* Texte / labels */
        [data-testid="stMarkdownContainer"], [data-testid="stMarkdownContainer"] * {{
            color: {text} !important;
        }}
        label {{ color: {text} !important; }}
        .ff-muted {{ color: {muted} !important; font-size: 13px; }}

        /* Inputs */
        input, textarea {{
            background: {input_bg} !important;
            color: {input_text} !important;
            border-color: {border} !important;
        }}

        /* Select baseweb */
        [data-baseweb="select"] > div {{
            background: {input_bg} !important;
            color: {input_text} !important;
            border-color: {border} !important;
        }}
        [data-baseweb="select"] * {{ color: {input_text} !important; }}

        /* Boutons */
        .stButton>button, .stFormSubmitButton>button {{
            border-radius: 12px !important;
            border: 1px solid {border} !important;
        }}
        .stButton>button:hover, .stFormSubmitButton>button:hover {{
            border-color: {accent} !important;
        }}

        /* Cards résultats */
        .ff-card {{
            border: 1px solid {border};
            background: {card_bg};
            border-radius: 16px;
            padding: 12px;
            margin-top: 10px;
            box-shadow: 0 10px 26px {shadow};
        }}

        /* Stars */
        .ff-stars{{position:relative;display:inline-block;font-size:16px;line-height:1;letter-spacing:1px}}
        .ff-stars .bot{{color:{"rgba(255,255,255,0.25)" if dark else "#d0d0d0"};display:block}}
        .ff-stars .top{{color:{accent};position:absolute;left:0;top:0;overflow:hidden;white-space:nowrap;display:block}}

        /* petit bouton X */
        .ff-x-btn button {{
            padding: 0.25rem 0.55rem !important;
            min-height: 0 !important;
            line-height: 1 !important;
        }}
        </style>
        """,
        unsafe_allow_html=True
    )

# ================== UTILS ==================
STOPWORDS = {
    "le","la","les","un","une","des","de","du","dans","sur","avec","sans","et","ou",
    "qui","que","quoi","dont","au","aux","en","a","à","pour","par","se","sa","son","ses",
    "je","tu","il","elle","on","nous","vous","ils","elles",
    "the","a","an","and","or","in","on","with","without","to","of","for","by","from"
}

TYPE_PRIORITY = {"subscription": 0, "free": 1, "addon": 2, "rent": 3, "buy": 4}

FR_NUM = {
    "0":"zéro","1":"un","2":"deux","3":"trois","4":"quatre","5":"cinq","6":"six","7":"sept","8":"huit","9":"neuf",
    "10":"dix","11":"onze","12":"douze","13":"treize","14":"quatorze","15":"quinze","16":"seize","17":"dix-sept",
    "18":"dix-huit","19":"dix-neuf","20":"vingt"
}

SYNONYMS = {
    "ecole": ["school"], "école": ["school"],
    "maternelle": ["kindergarten", "school"],
    "flic": ["cop", "police"],
    "infiltre": ["undercover"], "infiltré": ["undercover"],
    "super": ["super"], "heros": ["hero", "superhero"], "héros": ["hero", "superhero"],
    "vert": ["green"],
    "jumelles": ["twins"], "separees": ["separated"], "séparées": ["separated"], "naissance": ["birth"],
}

RULE_HINTS = [
    {"if_any": ["super heros vert","super héros vert","green superhero","heros vert","héros vert"],
     "add_entities": ["Hulk","The Incredible Hulk","Green Lantern"]},
    {"if_any": ["flic infiltré maternelle","infiltre maternelle","undercover kindergarten","cop kindergarten","flic maternelle"],
     "add_entities": ["Un flic à la maternelle","Kindergarten Cop","Un flic à la maternelle 2","Kindergarten Cop 2"]},
    {"if_any": ["jumelles séparées à la naissance","jumelles separees a la naissance","twins separated at birth","parent trap"],
     "add_entities": ["À nous quatre","The Parent Trap"]},
]

def strip_accents(s: str) -> str:
    if not s:
        return ""
    return "".join(c for c in unicodedata.normalize("NFD", s) if unicodedata.category(c) != "Mn")

def norm_text(s: str) -> str:
    if not s:
        return ""
    s = s.strip().lower().replace("’", "'")
    s = re.sub(r"\s+", " ", s)
    return s

def norm_loose(s: str) -> str:
    s = strip_accents(norm_text(s))
    s = re.sub(r"[^a-z0-9'\s-]", " ", s)
    s = re.sub(r"\s+", " ", s).strip()
    return s

def fr_numbers_to_words(s: str) -> str:
    def repl(m): return FR_NUM.get(m.group(0), m.group(0))
    return re.sub(r"\b(0|1|2|3|4|5|6|7|8|9|10|11|12|13|14|15|16|17|18|19|20)\b", repl, s)

def prettify_sentence(s: str) -> str:
    s2 = s.strip()
    if not s2:
        return s2
    s2 = re.sub(r"\s+", " ", s2)
    s2 = s2[0].upper() + s2[1:]
    if s2[-1] not in ".!?":
        s2 += "."
    return s2

def titlecase_name(s: str) -> str:
    s = re.sub(r"\s+", " ", s.strip())
    return " ".join([w[:1].upper() + w[1:].lower() for w in s.split(" ") if w])

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

def stable_id(sh: dict) -> str:
    return str(sh.get("id") or sh.get("imdbId") or sh.get("tmdbId") or (sh.get("title","") + "_" + str(sh.get("releaseYear") or sh.get("firstAirYear") or "")))

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

def clear_query_params():
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

# ================== PROFILE ==================
def load_profile():
    if PROFILE_PATH.exists():
        try:
            p = json.loads(PROFILE_PATH.read_text(encoding="utf-8"))
            p.setdefault("country", "fr")
            p.setdefault("lang", "fr")
            p.setdefault("platform_ids", [])
            p.setdefault("ui_theme", "Auto")
            return p
        except Exception:
            pass
    return {"country":"fr","lang":"fr","platform_ids":[],"ui_theme":"Auto"}

def save_profile(p):
    PROFILE_PATH.write_text(json.dumps(p, ensure_ascii=False, indent=2), encoding="utf-8")

profile = load_profile()
apply_theme(profile.get("ui_theme", "Auto"))

# ================== API HELPERS ==================
def sa_get(path: str, params: dict):
    if not RAPIDAPI_KEY:
        raise RuntimeError("RAPIDAPI_KEY manquante dans .env")
    r = requests.get(
        f"{BASE_URL}{path}",
        headers={"X-RapidAPI-Key": RAPIDAPI_KEY, "X-RapidAPI-Host": RAPIDAPI_HOST},
        params=params,
        timeout=25,
    )
    if not r.ok:
        raise RuntimeError(f"RapidAPI {r.status_code}: {r.text[:200]}")
    return r.json()

@st.cache_data(show_spinner=False, ttl=3600)
def get_services(country: str, lang: str):
    data = sa_get(f"/countries/{country}", {"output_language": lang})
    return data.get("services", []) or []

def dedupe_streaming_options(options):
    seen, out = set(), []
    for o in options or []:
        sid = ((o.get("service") or {}).get("id") or "")
        typ = o.get("type") or ""
        key = (sid, typ, o.get("link") or o.get("videoLink") or "")
        if key in seen:
            continue
        seen.add(key)
        out.append(o)
    return out

def get_poster_url(show: dict):
    try:
        vs = (show.get("imageSet") or {}).get("verticalPoster") or {}
        return vs.get("w240") or vs.get("w360") or vs.get("w480") or None
    except Exception:
        return None

def search_filters_page(country: str, show_type: str, lang: str, keyword: str, cursor: str | None = None):
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
def get_show_details(show_id: str, country: str, show_type: str, lang: str) -> dict:
    if not show_id:
        return {}
    try:
        return sa_get(f"/shows/{show_id}", {"country": country, "show_type": show_type, "output_language": lang})
    except Exception:
        return {}

def group_options_by_service(options: list) -> list:
    groups = {}
    for o in options or []:
        s = o.get("service") or {}
        sid = (s.get("id") or "").strip()
        name = (s.get("name") or sid or "").strip()
        if not name:
            continue
        typ = (o.get("type") or "").strip().lower()
        link = (o.get("link") or o.get("videoLink") or "").strip()
        key = sid if sid else name
        if key not in groups:
            groups[key] = {"id": sid, "name": name, "opts": []}
        groups[key]["opts"].append({"type": typ, "link": link})

    out = list(groups.values())
    for g in out:
        seen = set()
        ded = []
        for opt in g["opts"]:
            k = (opt["type"], opt["link"])
            if k in seen:
                continue
            seen.add(k)
            ded.append(opt)
        g["opts"] = ded
        g["opts"].sort(key=lambda x: TYPE_PRIORITY.get(x["type"], 99))

    out.sort(key=lambda x: x["name"].lower())
    return out

def pick_primary_option(opts: list):
    if not opts:
        return None, []
    for o in opts:
        if o["type"] == "subscription":
            rest = [x for x in opts if x != o]
            return o, rest
    return opts[0], opts[1:]

# ================== OLLAMA IA (entities + queries) ==================
@st.cache_data(show_spinner=False, ttl=3600)
def ollama_infer_entities(story: str, actor: str) -> dict:
    story = (story or "").strip()
    actor = (actor or "").strip()
    if not story and not actor:
        return {"entities": [], "queries": []}

    prompt = f"""
Tu aides à retrouver un film/série à partir d'un souvenir vague.
Réponds UNIQUEMENT en JSON strict:
{{"entities":[...], "queries":[...]}}

Règles:
- entities: 3 à 8 max. TITRES probables / franchises / personnages.
- queries: 4 à 8 max. Courtes. Mix FR + original EN si utile.
- Exemple: "super héros vert" => Hulk, Green Lantern.
- Si acteur fourni: 1-2 queries "acteur + mot clé".
Souvenir: {story}
Acteur: {actor}
JSON:
""".strip()

    try:
        r = requests.post(
            f"{OLLAMA_URL}/api/generate",
            json={"model": OLLAMA_MODEL, "prompt": prompt, "stream": False},
            timeout=45,
        )
        if not r.ok:
            return {"entities": [], "queries": []}
        txt = r.json().get("response", "") or ""
        m = re.search(r"\{.*\}", txt, flags=re.S)
        if not m:
            return {"entities": [], "queries": []}
        data = json.loads(m.group(0))

        def clean_list(x, limit):
            out, seen = [], set()
            if not isinstance(x, list):
                return out
            for v in x:
                if isinstance(v, str) and v.strip():
                    k = norm_loose(v)
                    if k not in seen:
                        seen.add(k)
                        out.append(v.strip())
            return out[:limit]

        return {"entities": clean_list(data.get("entities", []), 8), "queries": clean_list(data.get("queries", []), 8)}
    except Exception:
        return {"entities": [], "queries": []}

# ================== SEARCH ==================
def merge_results(items):
    out = {}
    for sh in items:
        out[stable_id(sh)] = sh
    return list(out.values())

def showtype_to_list(choice: str):
    if choice == "Films":
        return ["movie"]
    if choice == "Séries":
        return ["series"]
    return ["movie", "series"]

def apply_rule_hints(story: str) -> list[str]:
    story_loose = norm_loose(story)
    ents = []
    for rule in RULE_HINTS:
        for trig in rule.get("if_any", []):
            if norm_loose(trig) in story_loose:
                ents += rule.get("add_entities", [])
                break
    out, seen = [], set()
    for e in ents:
        k = norm_loose(e)
        if k not in seen:
            seen.add(k)
            out.append(e)
    return out

def build_query_variants(story: str, actor: str) -> list[str]:
    story = (story or "").strip()
    actor = (actor or "").strip()
    variants = []

    if story:
        story2 = fr_numbers_to_words(story)
        variants += [story, story2, strip_accents(story), strip_accents(story2)]
        variants += [extract_keywords(story), extract_keywords(story2)]

        words = [norm_loose(w) for w in re.findall(r"[A-Za-zÀ-ÿ0-9']+", story)]
        en = []
        for w in words:
            if w in SYNONYMS:
                en += SYNONYMS[w]
        if en:
            variants.append(" ".join(en))

        variants += apply_rule_hints(story)

    if actor:
        variants += [actor, strip_accents(actor), f"{actor} film", f"{actor} movie"]

    ai = ollama_infer_entities(story, actor)
    st.session_state["intent_entities"] = ai.get("entities", [])
    st.session_state["intent_queries"] = ai.get("queries", [])

    variants += st.session_state["intent_entities"]
    variants += st.session_state["intent_queries"]

    out, seen = [], set()
    for v in variants:
        v = (v or "").strip()
        if not v:
            continue
        k = norm_loose(v)
        if k in seen:
            continue
        seen.add(k)
        out.append(v)
    return out

def relevance_score(sh: dict, user_text: str) -> float:
    title = norm_loose(sh.get("title",""))
    overview = norm_loose(sh.get("overview",""))
    hay = f"{title} {overview}".strip()
    q = norm_loose(user_text)

    score = 0.0
    if q and (q in title or title in q):
        score += 8.0

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
        "Rapide":  {"pool": 80,  "max_pages": 1, "variants_max": 5},
        "Normal":  {"pool": 160, "max_pages": 2, "variants_max": 7},
        "Profond": {"pool": 260, "max_pages": 4, "variants_max": 9},
    }
    pre = presets.get(mode, presets["Normal"])

    story = (story or "").strip()
    actor = (actor or "").strip()
    if not story and not actor:
        return []

    if story:
        story = fr_numbers_to_words(story)

    variants = build_query_variants(story, actor)[:pre["variants_max"]]

    found = []
    source_country = {}

    def add_chunk(ctry, stype, kw):
        chunk = collect_shows(ctry, stype, lang, kw, max_items=pre["pool"], max_pages=pre["max_pages"])
        for sh in chunk:
            sid = stable_id(sh)
            if sid not in source_country:
                source_country[sid] = ctry
        return chunk

    for stype in show_types:
        for kw in variants:
            found += add_chunk(country, stype, kw)
            if len(found) >= pre["pool"]:
                break

    if len(found) < 12:
        for stype in show_types:
            for kw in variants[: min(4, len(variants))]:
                found += add_chunk("us", stype, kw)
                found += add_chunk("gb", stype, kw)

    shows = merge_results(found)
    user_text = story if story else actor

    raw = []
    for sh in shows:
        sid = stable_id(sh)
        discovered_in = source_country.get(sid, country)

        year = sh.get("releaseYear") or sh.get("firstAirYear") or None
        try:
            year = int(year) if year else None
        except Exception:
            year = None

        opts_all = []
        if discovered_in == country:
            opts_all = ((sh.get("streamingOptions") or {}).get(country) or [])
            opts_all = dedupe_streaming_options(opts_all)

        opts_mine = [o for o in opts_all if ((o.get("service") or {}).get("id") in allowed)]
        opts_mine = dedupe_streaming_options(opts_mine)

        score100 = sh.get("rating")
        try:
            score100 = float(score100) if score100 is not None else None
        except Exception:
            score100 = None

        raw.append({
            "show": sh,
            "api_id": sh.get("id"),
            "title": sh.get("title") or "Sans titre",
            "year": year,
            "poster": get_poster_url(sh),
            "overview": sh.get("overview") or "",
            "cast": sh.get("cast") or [],
            "score100": score100,
            "opts_all": opts_all,
            "is_mine": 1 if opts_mine else 0,
            "discovered_in": discovered_in,
            "rel": relevance_score(sh, user_text) + (0.25 * (1 if opts_mine else 0)),
        })

    raw.sort(key=lambda x: (x["rel"], x["is_mine"]), reverse=True)
    return raw[:pre["pool"]]

def apply_filters_and_sort(items, sort_mode, only_my_apps, platform_filter, year_range):
    out = list(items)

    if only_my_apps:
        keep = [x for x in out if x["is_mine"] == 1]
        out = keep if keep else out

    if platform_filter != "Toutes":
        def okp(it):
            for o in it["opts_all"]:
                s = (o.get("service") or {})
                name = (s.get("name") or s.get("id") or "").strip()
                if name == platform_filter:
                    return True
            return False
        k = [x for x in out if okp(x)]
        out = k if k else out

    if year_range:
        y0, y1 = year_range
        out = [x for x in out if x["year"] is None or (x["year"] >= y0 and x["year"] <= y1)]

    if sort_mode == "Pertinence":
        out.sort(key=lambda x: (x["rel"], x["is_mine"]), reverse=True)
    elif sort_mode == "Année (récent)":
        out.sort(key=lambda x: ((x["year"] is not None), x["year"] or -1, x["is_mine"]), reverse=True)
    else:
        out.sort(key=lambda x: ((x["score100"] is not None), x["score100"] or -1, x["is_mine"]), reverse=True)

    return out

# ================== SESSION DEFAULTS (avant widgets) ==================
st.session_state.setdefault("did_enter", False)
st.session_state.setdefault("page", "Accueil" if not st.session_state["did_enter"] else "Recherche")
st.session_state.setdefault("raw_items", [])
st.session_state.setdefault("raw_query", "")
st.session_state.setdefault("story_input", "")
st.session_state.setdefault("actor_input", "")
st.session_state.setdefault("show_choice", "Films et séries")
st.session_state.setdefault("auto_search", False)
st.session_state.setdefault("intent_entities", [])
st.session_state.setdefault("intent_queries", [])
st.session_state.setdefault("open_details_id", None)
st.session_state.setdefault("scroll_to_results", False)

# ================== URL actor click => auto search actor (avant widgets) ==================
qp = get_query_params()
if "actor" in qp:
    v = qp.get("actor")
    actor_param = v[0] if isinstance(v, list) and v else (v if isinstance(v, str) else "")
    clear_query_params()

    st.session_state["actor_input"] = actor_param
    st.session_state["story_input"] = ""
    st.session_state["show_choice"] = "Films"
    st.session_state["did_enter"] = True
    st.session_state["page"] = "Recherche"
    st.session_state["auto_search"] = True

# ================== SIDEBAR ==================
with st.sidebar:
    st.markdown("## FilmFinder IA")

    # thème UI
    theme_pick = st.selectbox("Thème", list(THEMES.keys()), index=list(THEMES.keys()).index(profile.get("ui_theme","Auto")))
    if theme_pick != profile.get("ui_theme","Auto"):
        profile["ui_theme"] = theme_pick
        save_profile(profile)
        st.rerun()

    if st.session_state["did_enter"]:
        nav = st.radio("Menu", ["Recherche", "Profil"], index=0 if st.session_state["page"]=="Recherche" else 1, key="nav")
        st.session_state["page"] = nav
    else:
        st.caption("Démarrage (Accueil)")

page = st.session_state["page"]

# ================== ACCUEIL ==================
if page == "Accueil":
    st.markdown("# FilmFinder IA")
    st.caption("Avant de chercher, choisis tes plateformes (1 fois).")

    if not RAPIDAPI_KEY:
        st.error("RAPIDAPI_KEY manquante dans .env")
        st.stop()

    with st.form("welcome_profile"):
        c1, c2 = st.columns(2)
        with c1:
            country = st.selectbox("Pays", ["fr","be","ch","gb","us"], index=["fr","be","ch","gb","us"].index(profile.get("country","fr")))
        with c2:
            lang = st.selectbox("Langue", ["fr","en"], index=["fr","en"].index(profile.get("lang","fr")))

        services = get_services(country, lang)
        name_to_id = {(s.get("name") or s.get("id")): s.get("id") for s in services if (s.get("name") or s.get("id")) and s.get("id")}
        id_to_name = {v:k for k,v in name_to_id.items()}
        default_names = [id_to_name[i] for i in profile.get("platform_ids", []) if i in id_to_name]

        chosen = st.multiselect("Tes plateformes", options=sorted(name_to_id.keys()), default=sorted(set(default_names)))
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

# ================== PROFIL ==================
if page == "Profil":
    st.markdown("# Profil")
    st.caption("Ici tu modifies pays/langue/plateformes.")

    with st.form("profile_form"):
        c1, c2 = st.columns(2)
        with c1:
            country = st.selectbox("Pays", ["fr","be","ch","gb","us"], index=["fr","be","ch","gb","us"].index(profile.get("country","fr")))
        with c2:
            lang = st.selectbox("Langue", ["fr","en"], index=["fr","en"].index(profile.get("lang","fr")))

        services = get_services(country, lang)
        name_to_id = {(s.get("name") or s.get("id")): s.get("id") for s in services if (s.get("name") or s.get("id")) and s.get("id")}
        id_to_name = {v:k for k,v in name_to_id.items()}
        default_names = [id_to_name[i] for i in profile.get("platform_ids", []) if i in id_to_name]

        chosen = st.multiselect("Tes plateformes", options=sorted(name_to_id.keys()), default=sorted(set(default_names)))
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

    if st.button("↩️ Revenir à l'accueil (session)"):
        st.session_state["did_enter"] = False
        st.session_state["page"] = "Accueil"
        st.rerun()

    st.stop()

# ================== RECHERCHE ==================
st.markdown("# Recherche")

if not profile.get("platform_ids"):
    st.warning("Choisis au moins 1 plateforme dans Accueil/Profil.")
    st.session_state["did_enter"] = False
    st.session_state["page"] = "Accueil"
    st.rerun()

show_choice = st.selectbox("Je cherche :", ["Films", "Séries", "Films et séries"], key="show_choice")
show_types = showtype_to_list(show_choice)

mode = st.radio("Mode", ["Rapide", "Normal", "Profond"], horizontal=True, index=1)

# suggestions correction
story_raw = st.session_state.get("story_input", "").strip()
actor_raw = st.session_state.get("actor_input", "").strip()
story_suggest = prettify_sentence(fr_numbers_to_words(story_raw)) if story_raw else ""
actor_suggest = titlecase_name(actor_raw) if actor_raw else ""

with st.form("search_form", clear_on_submit=False):
    # Histoire + X
    c_story, c_x1 = st.columns([0.90, 0.10])
    with c_story:
        st.text_input("Histoire / souvenir (optionnel)", key="story_input", placeholder="Ex: un super héros vert")
    with c_x1:
        st.markdown('<div class="ff-x-btn">', unsafe_allow_html=True)
        clear_story = st.form_submit_button("✕", help="Effacer l'histoire")
        st.markdown("</div>", unsafe_allow_html=True)

    # Acteur + X
    c_act, c_x2 = st.columns([0.90, 0.10])
    with c_act:
        st.text_input("Acteur/actrice (optionnel)", key="actor_input", placeholder="Ex: Arnold Schwarzenegger")
    with c_x2:
        st.markdown('<div class="ff-x-btn">', unsafe_allow_html=True)
        clear_actor = st.form_submit_button("✕", help="Effacer l'acteur")
        st.markdown("</div>", unsafe_allow_html=True)

    submitted = st.form_submit_button("Chercher")

# Clear actions (prioritaire)
if clear_story:
    st.session_state["story_input"] = ""
    st.rerun()

if clear_actor:
    st.session_state["actor_input"] = ""
    st.rerun()

# Suggestion buttons (hors form)
if story_suggest and story_suggest != st.session_state.get("story_input","").strip():
    c1, c2 = st.columns([5,1])
    with c1:
        st.markdown(f"<div class='ff-muted'>Suggestion histoire : <b>{story_suggest}</b></div>", unsafe_allow_html=True)
    with c2:
        if st.button("Utiliser", key="use_story_fix"):
            st.session_state["story_input"] = story_suggest
            st.rerun()

if actor_suggest and actor_suggest != st.session_state.get("actor_input","").strip():
    c1, c2 = st.columns([5,1])
    with c1:
        st.markdown(f"<div class='ff-muted'>Suggestion acteur : <b>{actor_suggest}</b></div>", unsafe_allow_html=True)
    with c2:
        if st.button("Utiliser", key="use_actor_fix"):
            st.session_state["actor_input"] = actor_suggest
            st.rerun()

st.markdown("<div class='ff-muted'>Astuce • Acteur seul = OK • Clique acteur = films</div>", unsafe_allow_html=True)

def do_search(story_text: str, actor_text: str):
    raw = build_raw_items(story_text, actor_text, mode=mode, prof=profile, show_types=show_types)
    st.session_state["raw_items"] = raw
    st.session_state["raw_query"] = story_text.strip() if story_text.strip() else actor_text.strip()
    st.session_state["open_details_id"] = None
    st.session_state["scroll_to_results"] = True

auto = st.session_state.pop("auto_search", False)
if submitted or auto:
    s = st.session_state.get("story_input", "").strip()
    a = st.session_state.get("actor_input", "").strip()
    if not s and not a:
        st.warning("Mets une histoire OU un acteur.")
    else:
        do_search(s, a)

raw_items = st.session_state.get("raw_items", [])

# Filters
services = get_services(profile["country"], profile["lang"])
id_to_name = {s.get("id"): (s.get("name") or s.get("id")) for s in services}
platform_choices = ["Toutes"] + sorted([id_to_name.get(i, i) for i in profile.get("platform_ids", [])])

sort_mode = "Pertinence"
only_my_apps = False
platform_filter = "Toutes"
year_range = None

with st.expander("Filtres avancés…", expanded=False):
    c1, c2, c3 = st.columns([2.2, 1.1, 1.6])
    with c1:
        sort_mode = st.selectbox("Trier par", ["Pertinence", "Année (récent)", "Note (haute)"], index=0)
    with c2:
        only_my_apps = st.checkbox("Mes applis", value=False)
    with c3:
        platform_filter = st.selectbox("Plateforme", platform_choices, index=0)

    years = sorted({x["year"] for x in raw_items if x.get("year")})
    if years and min(years) != max(years):
        year_range = st.slider("Année (min–max)", min_value=int(min(years)), max_value=int(max(years)), value=(int(min(years)), int(max(years))))

if not raw_items:
    st.markdown("<div class='ff-muted'>Tape une histoire OU un acteur puis clique Chercher.</div>", unsafe_allow_html=True)
    st.stop()

view = apply_filters_and_sort(raw_items, sort_mode, only_my_apps, platform_filter, year_range)

# ===== Anchor + results count (1ère ligne visible) =====
st.markdown('<div id="results-anchor"></div>', unsafe_allow_html=True)
st.write(f"✅ Résultats : {min(len(view), 20)} / {len(view)}")

# blur clavier + scroll
if st.session_state.pop("scroll_to_results", False):
    components.html(
        """
        <script>
        setTimeout(function(){
          try{ document.activeElement && document.activeElement.blur && document.activeElement.blur(); }catch(e){}
          var el = document.getElementById("results-anchor");
          if(el){ el.scrollIntoView({behavior:"smooth", block:"start"}); }
        }, 80);
        </script>
        """,
        height=0,
    )

allowed_ids = set(profile.get("platform_ids", []))

def details_fr_links(show_id: str) -> list:
    d = get_show_details(show_id, profile["country"], "movie", profile["lang"])
    if not d:
        d = get_show_details(show_id, profile["country"], "series", profile["lang"])
    opts = ((d.get("streamingOptions") or {}).get(profile["country"]) or []) if d else []
    return dedupe_streaming_options(opts)

# ===== Results list =====
for it in view[:20]:
    show_id = str(it.get("api_id") or "")
    card_id = stable_id(it.get("show") or {}) if it.get("show") else show_id or it["title"]

    st.markdown('<div class="ff-card">', unsafe_allow_html=True)

    c_img, c_txt = st.columns([1, 3])
    with c_img:
        if it.get("poster"):
            st.image(it["poster"], width=140)

    with c_txt:
        title = it["title"]
        year = it["year"]
        st.markdown(f"### {title} ({year if year else ''})")

        if it.get("score100") is not None:
            star = stars_html(it["score100"])
            score5 = round(float(it["score100"]) / 20.0, 1)
            st.markdown(f'{star}<span class="ff-muted" style="margin-left:8px">({score5}/5)</span>', unsafe_allow_html=True)

        opts_all = it.get("opts_all") or []
        if not opts_all and show_id:
            opts_all = details_fr_links(show_id)

        groups = group_options_by_service(opts_all)
        mine = [g for g in groups if (g["id"] in allowed_ids)]
        other = [g for g in groups if (g["id"] not in allowed_ids)]

        if mine:
            st.markdown("<div class='ff-muted'>✅ Dispo sur tes applis</div>", unsafe_allow_html=True)
            for g in mine:
                primary, rest = pick_primary_option(g["opts"])
                if primary and primary["link"]:
                    st.markdown(f"- **{g['name']}** ({primary['type']}) → {primary['link']}")
                elif primary:
                    st.markdown(f"- **{g['name']}** ({primary['type']}) → *(lien non fourni)*")
                if rest:
                    with st.expander(f"… autres options sur {g['name']}"):
                        for o in rest:
                            st.markdown(f"- ({o['type']}) → {o['link'] or '*(lien non fourni)*'}")
        else:
            st.markdown("<div class='ff-muted'>❌ Pas dispo sur tes applis</div>", unsafe_allow_html=True)

        if other:
            with st.expander(f"… Autres plateformes ({len(other)})"):
                for g in other:
                    primary, rest = pick_primary_option(g["opts"])
                    st.markdown(f"- **{g['name']}** ({primary['type'] if primary else ''}) → {(primary['link'] if primary and primary['link'] else '*(lien non fourni)*')}")
                    if rest:
                        with st.expander(f"… autres options sur {g['name']}"):
                            for o in rest:
                                st.markdown(f"- ({o['type']}) → {o['link'] or '*(lien non fourni)*'}")

        # ===== Details: un seul ouvert à la fois =====
        btn_row = st.columns([1, 3])
        with btn_row[0]:
            if st.button("Détails", key=f"details_btn_{card_id}"):
                st.session_state["open_details_id"] = card_id if st.session_state["open_details_id"] != card_id else None
                st.rerun()

        if st.session_state.get("open_details_id") == card_id:
            # Détails visibles, les autres sont fermés automatiquement
            if it.get("overview"):
                st.write(it["overview"])

            cast = it.get("cast") or []
            if cast:
                links = [f"[{a}](?actor={quote(a)})" for a in cast[:12]]
                st.markdown("**Acteurs :** " + " · ".join(links))

    st.markdown("</div>", unsafe_allow_html=True)