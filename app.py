import os
import re
import json
import unicodedata
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

APP_DIR = Path(__file__).parent
PROFILE_PATH = APP_DIR / "profile.json"

st.set_page_config(page_title="FilmFinder IA", layout="centered")

# ================== STYLE (fix dark mode) ==================
def apply_theme():
    st.markdown(
        """
        <style>
        :root { color-scheme: light !important; }

        /* Streamlit variables override (important for dark-mode browsers) */
        [data-testid="stAppViewContainer"]{
            --text-color: #111111 !important;
            --background-color: #f4f6f8 !important;
            --secondary-background-color: #ffffff !important;
            --primary-color: #f5c518 !important;
        }

        html, body, .stApp, [data-testid="stAppViewContainer"] {
            background: #f4f6f8 !important;
            color: #111111 !important;
        }

        .main .block-container{
            max-width: 1040px !important;
            margin: 12px auto !important;
            background: #ffffff !important;
            border-radius: 18px !important;
            padding: 16px 20px 22px 20px !important;
            box-shadow: 0 10px 35px rgba(0,0,0,0.08) !important;
        }

        [data-testid="stSidebar"] > div:first-child{
            background: #ffffff !important;
            border-right: 1px solid rgba(0,0,0,0.08) !important;
        }

        /* Markdown and labels */
        [data-testid="stMarkdownContainer"], 
        [data-testid="stMarkdownContainer"] * {
            color: #111111 !important;
        }
        label { color: #111111 !important; }

        /* Inputs */
        input, textarea {
            background: #ffffff !important;
            color: #111111 !important;
            border-color: rgba(0,0,0,0.18) !important;
        }

        /* Select (BaseWeb) */
        [data-baseweb="select"] > div {
            background: #ffffff !important;
            color: #111111 !important;
            border-color: rgba(0,0,0,0.18) !important;
        }
        [data-baseweb="select"] * { color: #111111 !important; }

        /* Dropdown menu portal */
        [role="listbox"]{
            background: #ffffff !important;
            color: #111111 !important;
            border: 1px solid rgba(0,0,0,0.18) !important;
        }
        [role="option"]{ color:#111111 !important; }
        [role="option"][aria-selected="true"]{ background: rgba(0,0,0,0.06) !important; }

        /* Expander */
        [data-testid="stExpander"]{
            background:#ffffff !important;
            border-color: rgba(0,0,0,0.10) !important;
        }

        .ff-muted{ color: rgba(0,0,0,0.65) !important; font-size: 13px; }

        /* étoiles */
        .ff-stars{position:relative;display:inline-block;font-size:16px;line-height:1;letter-spacing:1px}
        .ff-stars .bot{color:#d0d0d0 !important;display:block}
        .ff-stars .top{color:#f5c518 !important;position:absolute;left:0;top:0;overflow:hidden;white-space:nowrap;display:block}
        </style>
        """,
        unsafe_allow_html=True,
    )

apply_theme()

# ================== UTILS ==================
STOPWORDS = {
    "le","la","les","un","une","des","de","du","dans","sur","avec","sans","et","ou",
    "qui","que","quoi","dont","au","aux","en","a","à","pour","par","se","sa","son","ses",
    "je","tu","il","elle","on","nous","vous","ils","elles","toujours",
    "the","a","an","and","or","in","on","with","without","to","of","for","by","from"
}

TYPE_PRIORITY = {"subscription": 0, "free": 1, "addon": 2, "rent": 3, "buy": 4}

FR_NUM = {
    "0":"zéro","1":"un","2":"deux","3":"trois","4":"quatre","5":"cinq","6":"six","7":"sept","8":"huit","9":"neuf",
    "10":"dix","11":"onze","12":"douze","13":"treize","14":"quatorze","15":"quinze","16":"seize","17":"dix-sept",
    "18":"dix-huit","19":"dix-neuf","20":"vingt"
}

SYNONYMS = {
    # FR -> EN keywords (petit dico utile pour l'interprétation)
    "école": ["school"],
    "ecole": ["school"],
    "adulte": ["adult"],
    "jumelles": ["twins"],
    "jumeaux": ["twins"],
    "séparées": ["separated"],
    "separees": ["separated"],
    "naissance": ["birth"],
    "forêt": ["forest"],
    "foret": ["forest"],
}

_COUNTRY_MAP = {
    "france":"FR","fr":"FR",
    "united states":"US","usa":"US","us":"US","united states of america":"US","etats unis":"US","états unis":"US",
    "united kingdom":"GB","uk":"GB","gb":"GB","great britain":"GB","england":"GB","royaume uni":"GB",
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
    "russia":"RU","russie":"RU","ru":"RU",
    "netherlands":"NL","pays bas":"NL","nl":"NL",
    "ireland":"IE","irlande":"IE","ie":"IE",
    "belgium":"BE","belgique":"BE","be":"BE",
    "switzerland":"CH","suisse":"CH","ch":"CH",
}

def strip_accents(s: str) -> str:
    if not s:
        return ""
    return "".join(c for c in unicodedata.normalize("NFD", s) if unicodedata.category(c) != "Mn")

def norm_text(s: str) -> str:
    if not s:
        return ""
    s = s.strip().lower()
    s = s.replace("’", "'")
    s = re.sub(r"\s+", " ", s)
    return s

def norm_loose(s: str) -> str:
    # normalisation plus agressive (accents, ponctuation)
    s = strip_accents(norm_text(s))
    s = re.sub(r"[^a-z0-9'\s-]", " ", s)
    s = re.sub(r"\s+", " ", s).strip()
    return s

def fr_numbers_to_words(s: str) -> str:
    # remplace chiffres isolés (ex: "à nous 4" -> "à nous quatre")
    def repl(m):
        d = m.group(0)
        return FR_NUM.get(d, d)
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
    return str(
        sh.get("id")
        or sh.get("imdbId")
        or sh.get("tmdbId")
        or (sh.get("title","") + "_" + str(sh.get("releaseYear") or sh.get("firstAirYear") or ""))
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
    return _COUNTRY_MAP.get(norm_loose(first), "")

def flag_img_html(iso2: str) -> str:
    if not iso2:
        return ""
    iso2 = iso2.strip().lower()
    if len(iso2) != 2 or not iso2.isalpha():
        return ""
    return f'<img src="https://flagcdn.com/24x18/{iso2}.png" style="vertical-align:-3px;margin-right:6px;border-radius:2px;" />'

# ================== STREAMLIT QUERY PARAMS (compat) ==================
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
            return p
        except Exception:
            pass
    return {"country":"fr","lang":"fr","platform_ids":[]}

def save_profile(p):
    PROFILE_PATH.write_text(json.dumps(p, ensure_ascii=False, indent=2), encoding="utf-8")

profile = load_profile()

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

@st.cache_data(show_spinner=False, ttl=86400)
def get_genres(country: str, lang: str):
    try:
        data = sa_get("/genres", {"country": country, "output_language": lang})
        items = []
        if isinstance(data, dict) and "genres" in data:
            items = data["genres"]
        elif isinstance(data, list):
            items = data
        names = []
        for it in items:
            if isinstance(it, str) and it.strip():
                names.append(it.strip())
            elif isinstance(it, dict):
                n = it.get("name") or it.get("title") or it.get("label")
                if isinstance(n, str) and n.strip():
                    names.append(n.strip())
        names = sorted(set(names))
        if names:
            return names
    except Exception:
        pass

    return [
        "Action","Aventure","Animation","Comédie","Crime","Documentaire","Drame",
        "Familial","Fantastique","Horreur","Mystère","Romance","Science-Fiction",
        "Thriller","Guerre","Western"
    ]

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

# Pagination (pour récupérer plus que 20)
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
    pages = 0
    while pages < max_pages and len(shows) < max_items:
        res = search_filters_page(country, show_type, lang, keyword, cursor)
        chunk = res.get("shows", []) if isinstance(res, dict) else []
        shows.extend(chunk)
        pages += 1
        if not res.get("hasMore"):
            break
        cursor = res.get("nextCursor")
        if not cursor:
            break
    return shows

@st.cache_data(show_spinner=False, ttl=3600)
def get_show_details(show_id: str, country: str, show_type: str, lang: str) -> dict:
    if not show_id:
        return {}
    try:
        return sa_get(f"/shows/{show_id}", {
            "country": country,
            "show_type": show_type,
            "output_language": lang,
        })
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

# ================== OMDb (optionnel, surtout pour pays) ==================
@st.cache_data(show_spinner=False, ttl=86400)
def omdb_fetch(imdb_id: str):
    if not OMDB_API_KEY or not imdb_id:
        return None
    try:
        r = requests.get("https://www.omdbapi.com/",
                         params={"i": imdb_id, "apikey": OMDB_API_KEY},
                         timeout=20)
        if not r.ok:
            return None
        data = r.json()
        return data if data.get("Response") == "True" else None
    except Exception:
        return None

def omdb_country(imdb_id: str) -> str:
    d = omdb_fetch(imdb_id)
    if not d:
        return ""
    c = d.get("Country")
    return c if isinstance(c, str) else ""

# ================== SEARCH / INTERPRETATION ==================
def merge_results(items):
    out = {}
    for sh in items:
        out[stable_id(sh)] = sh
    return list(out.values())

def relevance_score(sh: dict, q: str, actor: str | None):
    hay = norm_loose((sh.get("title") or "") + " " + (sh.get("overview") or ""))
    qn = norm_loose(q)
    words = [w for w in qn.split() if len(w) >= 4 and w not in STOPWORDS]
    score = 0.0
    for w in set(words):
        if w in hay:
            score += 1.0
    # bonus si acteur match dans cast
    if actor:
        a = norm_loose(actor)
        cast = [norm_loose(x) for x in (sh.get("cast") or [])]
        if any(a == c for c in cast) or any(a in c for c in cast):
            score += 3.0
    return score

def showtype_to_list(choice: str):
    if choice == "Films":
        return ["movie"]
    if choice == "Séries":
        return ["series"]
    return ["movie", "series"]

def build_query_variants(story: str, actor: str):
    variants = []

    base = story.strip()
    if base:
        variants.append(base)
        variants.append(fr_numbers_to_words(base))
        variants.append(strip_accents(base))
        variants.append(strip_accents(fr_numbers_to_words(base)))

        # Mots clés
        variants.append(extract_keywords(base))
        variants.append(extract_keywords(fr_numbers_to_words(base)))

        # Petit “pont” FR->EN par mots
        words = [norm_loose(w) for w in re.findall(r"[A-Za-zÀ-ÿ0-9']+", base)]
        en = []
        for w in words:
            if w in SYNONYMS:
                en += SYNONYMS[w]
        if en:
            variants.append(" ".join(en))

    # acteur en variante keyword (utile même si story vide)
    if actor.strip():
        a = actor.strip()
        variants.append(a)
        variants.append(strip_accents(a))

    # dédupe + enlève vides
    out = []
    seen = set()
    for v in variants:
        v = (v or "").strip()
        if not v:
            continue
        key = norm_loose(v)
        if key in seen:
            continue
        seen.add(key)
        out.append(v)
    return out

def build_raw_items(story: str, actor: str, mode: str, prof: dict, show_types: list):
    country = prof["country"]
    lang = prof["lang"]
    allowed = set(prof.get("platform_ids", []))

    presets = {
        "Rapide":  {"pool": 60,  "max_pages": 1, "variants_max": 4},
        "Normal":  {"pool": 120, "max_pages": 2, "variants_max": 6},
        "Profond": {"pool": 220, "max_pages": 4, "variants_max": 8},
    }
    pre = presets.get(mode, presets["Normal"])

    story = (story or "").strip()
    actor = (actor or "").strip()
    if not story and not actor:
        return []

    variants = build_query_variants(story, actor)[:pre["variants_max"]]

    found = []
    for stype in show_types:
        for kw in variants:
            found += collect_shows(country, stype, lang, kw, max_items=pre["pool"], max_pages=pre["max_pages"])
            # si on a déjà beaucoup, on évite d’exploser
            if len(found) >= pre["pool"] * 2:
                break

    shows = merge_results(found)

    # filtre “acteur” : garde surtout les shows où cast contient l’acteur
    actor_norm = norm_loose(actor) if actor else ""
    if actor_norm:
        filtered = []
        for sh in shows:
            cast = [norm_loose(x) for x in (sh.get("cast") or [])]
            if any(actor_norm == c for c in cast) or any(actor_norm in c for c in cast):
                filtered.append(sh)
        # si filtre trop violent et vide, on garde l’original
        if filtered:
            shows = filtered

    raw = []
    query_for_score = story if story else actor

    for sh in shows:
        year = sh.get("releaseYear") or sh.get("firstAirYear") or None
        try:
            year = int(year) if year else None
        except Exception:
            year = None

        opts_all = ((sh.get("streamingOptions") or {}).get(country) or [])
        opts_all = dedupe_streaming_options(opts_all)

        opts_mine = [o for o in opts_all if ((o.get("service") or {}).get("id") in allowed)]
        opts_mine = dedupe_streaming_options(opts_mine)

        imdb_id = sh.get("imdbId") or sh.get("imdbID") or None

        # rating API (0-100) -> on l’utilise directement
        score100 = sh.get("rating")
        try:
            score100 = float(score100) if score100 is not None else None
        except Exception:
            score100 = None

        # pays via OMDb si dispo
        country_text = omdb_country(imdb_id) if imdb_id else ""

        raw.append({
            "show": sh,
            "api_id": sh.get("id"),
            "show_type": sh.get("showType"),
            "title": sh.get("title") or "Sans titre",
            "year": year,
            "poster": get_poster_url(sh),
            "overview": sh.get("overview") or "",
            "genres": [g.get("name") if isinstance(g, dict) else str(g) for g in (sh.get("genres") or [])],
            "cast": sh.get("cast") or [],
            "imdb_id": imdb_id,
            "score100": score100,
            "country_text": country_text,
            "is_mine": 1 if opts_mine else 0,
            "opts_all": opts_all,
            "rel": relevance_score(sh, query_for_score, actor) + (0.25 * (1 if opts_mine else 0)),
        })

    raw.sort(key=lambda x: (x["rel"], x["is_mine"]), reverse=True)
    return raw[:pre["pool"]]

def apply_filters_and_sort(items, sort_mode, only_my_apps, platform_filter, year_range, genre_filter):
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

    if genre_filter != "Tous":
        ng = norm_loose(genre_filter)
        def okg(it):
            return ng in [norm_loose(g) for g in (it["genres"] or [])]
        k = [x for x in out if okg(x)]
        out = k if k else out

    if sort_mode == "Pertinence":
        out.sort(key=lambda x: (x["rel"], x["is_mine"]), reverse=True)
    elif sort_mode == "Année (récent)":
        out.sort(key=lambda x: ((x["year"] is not None), x["year"] or -1, x["is_mine"]), reverse=True)
    else:
        out.sort(key=lambda x: ((x["score100"] is not None), x["score100"] or -1, x["is_mine"]), reverse=True)

    return out

# ================== NAV / SESSION ==================
st.session_state.setdefault("did_enter", False)
st.session_state.setdefault("page", "Accueil" if not st.session_state["did_enter"] else "Recherche")
st.session_state.setdefault("raw_items", [])
st.session_state.setdefault("raw_query", "")

# Prépare les clés des widgets
st.session_state.setdefault("story_input", "")
st.session_state.setdefault("actor_input", "")
st.session_state.setdefault("show_choice", "Films et séries")
st.session_state.setdefault("auto_search", False)

# Actor click via URL
qp = get_query_params()
if "actor" in qp:
    v = qp.get("actor")
    actor_param = v[0] if isinstance(v, list) and v else (v if isinstance(v, str) else "")
    actor_param = actor_param or ""
    clear_query_params()

    # IMPORTANT: set AVANT widgets
    st.session_state["actor_input"] = actor_param
    st.session_state["story_input"] = ""
    st.session_state["show_choice"] = "Films"  # comme tu veux : acteur => films
    st.session_state["did_enter"] = True
    st.session_state["page"] = "Recherche"
    st.session_state["auto_search"] = True

with st.sidebar:
    st.markdown("## FilmFinder IA")
    if st.session_state["did_enter"]:
        nav = st.radio("Menu", ["Recherche", "Profil"], index=0 if st.session_state["page"]=="Recherche" else 1, key="nav")
        st.session_state["page"] = nav
    else:
        st.caption("Démarrage (Accueil)")

page = st.session_state["page"]

# -------- ACCUEIL --------
if page == "Accueil":
    st.markdown("# FilmFinder IA")
    st.caption("Avant de chercher, choisis tes plateformes (1 fois).")

    if not RAPIDAPI_KEY:
        st.error("RAPIDAPI_KEY manquante dans .env")
        st.stop()

    with st.form("welcome_profile"):
        c1, c2 = st.columns(2)
        with c1:
            country = st.selectbox("Pays", ["fr","be","ch","gb","us"],
                                   index=["fr","be","ch","gb","us"].index(profile.get("country","fr")))
        with c2:
            lang = st.selectbox("Langue", ["fr","en"],
                                index=["fr","en"].index(profile.get("lang","fr")))

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
            profile = {"country": country, "lang": lang, "platform_ids": platform_ids}
            save_profile(profile)
            st.session_state["did_enter"] = True
            st.session_state["page"] = "Recherche"
            st.rerun()

    st.stop()

# -------- PROFIL --------
if page == "Profil":
    st.markdown("# Profil")
    st.caption("Ici tu modifies pays/langue/plateformes.")

    with st.form("profile_form"):
        c1, c2 = st.columns(2)
        with c1:
            country = st.selectbox("Pays", ["fr","be","ch","gb","us"],
                                   index=["fr","be","ch","gb","us"].index(profile.get("country","fr")))
        with c2:
            lang = st.selectbox("Langue", ["fr","en"],
                                index=["fr","en"].index(profile.get("lang","fr")))

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
            profile = {"country": country, "lang": lang, "platform_ids": platform_ids}
            save_profile(profile)
            st.success("OK")
            st.rerun()

    if st.button("↩️ Revenir à l'accueil (session)"):
        st.session_state["did_enter"] = False
        st.session_state["page"] = "Accueil"
        st.rerun()

    st.stop()

# -------- RECHERCHE --------
st.markdown("# Recherche")

if not profile.get("platform_ids"):
    st.warning("Choisis au moins 1 plateforme dans Accueil/Profil.")
    st.session_state["did_enter"] = False
    st.session_state["page"] = "Accueil"
    st.rerun()

# ✅ libellés au pluriel (comme tu veux)
show_choice = st.selectbox("Je cherche :", ["Films", "Séries", "Films et séries"], key="show_choice")
show_types = showtype_to_list(show_choice)

mode = st.radio("Mode", ["Rapide", "Normal", "Profond"], horizontal=True, index=1)

# --- Suggestions de correction (avant de lancer) ---
story_raw = st.session_state.get("story_input", "")
actor_raw = st.session_state.get("actor_input", "")

story_suggest = prettify_sentence(fr_numbers_to_words(story_raw.strip())) if story_raw.strip() else ""
actor_suggest = titlecase_name(actor_raw) if actor_raw.strip() else ""

colA, colB = st.columns([6, 2])
with colA:
    with st.form("search_form", clear_on_submit=False):
        story = st.text_input("Histoire / souvenir (optionnel)", key="story_input", placeholder="Ex: un adulte qui retourne à l'école")
        actor = st.text_input("Acteur/actrice (optionnel)", key="actor_input", placeholder="Ex: Louis de Funès")
        submitted = st.form_submit_button("Chercher")
with colB:
    st.markdown("<div class='ff-muted'>Astuce</div>", unsafe_allow_html=True)
    st.markdown("<div class='ff-muted'>• Acteur seul = OK</div>", unsafe_allow_html=True)
    st.markdown("<div class='ff-muted'>• Clique acteur = films</div>", unsafe_allow_html=True)

# Affiche propositions + bouton “Utiliser”
if story_suggest and story_suggest.strip() != story_raw.strip():
    c1, c2 = st.columns([5, 1])
    with c1:
        st.markdown(f"<div class='ff-muted'>Suggestion histoire : <b>{story_suggest}</b></div>", unsafe_allow_html=True)
    with c2:
        if st.button("Utiliser", key="use_story_fix"):
            st.session_state["story_input"] = story_suggest
            st.rerun()

if actor_suggest and actor_suggest != actor_raw.strip():
    c1, c2 = st.columns([5, 1])
    with c1:
        st.markdown(f"<div class='ff-muted'>Suggestion acteur : <b>{actor_suggest}</b></div>", unsafe_allow_html=True)
    with c2:
        if st.button("Utiliser", key="use_actor_fix"):
            st.session_state["actor_input"] = actor_suggest
            st.rerun()

def do_search(story_text: str, actor_text: str):
    raw = build_raw_items(story_text, actor_text, mode=mode, prof=profile, show_types=show_types)
    st.session_state["raw_items"] = raw
    st.session_state["raw_query"] = (story_text.strip() if story_text.strip() else actor_text.strip())

# Auto-search (si clic acteur)
auto = st.session_state.pop("auto_search", False)
if submitted or auto:
    s = st.session_state.get("story_input", "").strip()
    a = st.session_state.get("actor_input", "").strip()
    if not s and not a:
        st.warning("Mets une histoire OU un acteur.")
    else:
        do_search(s, a)

raw_items = st.session_state.get("raw_items", [])
genre_choices = ["Tous"] + get_genres(profile["country"], profile["lang"])

services = get_services(profile["country"], profile["lang"])
id_to_name = {s.get("id"): (s.get("name") or s.get("id")) for s in services}
platform_choices = ["Toutes"] + sorted([id_to_name.get(i, i) for i in profile.get("platform_ids", [])])

# Filtres avancés
sort_default = 2 if (st.session_state.get("actor_input","").strip() and not st.session_state.get("story_input","").strip()) else 0
with st.expander("Filtres avancés…", expanded=False):
    c1, c2, c3 = st.columns([2.2, 1.1, 1.6])
    with c1:
        sort_mode = st.selectbox("Trier par", ["Pertinence", "Année (récent)", "Note (haute)"], index=sort_default)
    with c2:
        only_my_apps = st.checkbox("Mes applis", value=False)
    with c3:
        platform_filter = st.selectbox("Plateforme", platform_choices, index=0)

    genre_filter = st.selectbox("Genre", genre_choices, index=0)

    year_range = None
    years = sorted({x["year"] for x in raw_items if x.get("year")})
    if years:
        y_min, y_max = min(years), max(years)
        if y_min != y_max:
            year_range = st.slider("Année (min–max)", min_value=int(y_min), max_value=int(y_max),
                                   value=(int(y_min), int(y_max)))

if raw_items:
    view = apply_filters_and_sort(
        raw_items,
        sort_mode=sort_mode,
        only_my_apps=only_my_apps,
        platform_filter=platform_filter,
        year_range=year_range,
        genre_filter=genre_filter
    )

    st.markdown(f"<div class='ff-muted'>Requête: {st.session_state.get('raw_query','')}</div>", unsafe_allow_html=True)
    st.write(f"✅ Résultats : {min(len(view), 20)} / {len(view)}")

    allowed_ids = set(profile.get("platform_ids", []))

    def details_with_fallback(api_id: str):
        for stype in show_types:
            d = get_show_details(api_id, profile["country"], stype, profile["lang"])
            if d:
                return d
        if show_types == ["movie", "series"]:
            d = get_show_details(api_id, profile["country"], "series", profile["lang"])
            if d: return d
            d = get_show_details(api_id, profile["country"], "movie", profile["lang"])
            if d: return d
        return {}

    for it in view[:20]:
        title = it["title"]
        year = it["year"]
        poster = it["poster"]

        star = stars_html(it["score100"])
        score5 = None if it["score100"] is None else round(float(it["score100"]) / 20.0, 1)

        # drapeau/pays (via OMDb si dispo)
        iso = iso2_from_country_text(it.get("country_text",""))
        flag_html = flag_img_html(iso)
        shown_country = (it.get("country_text","").split(",")[0].strip() if it.get("country_text") else "")

        c_img, c_txt = st.columns([1, 3])
        with c_img:
            if poster:
                st.image(poster, width=140)

        with c_txt:
            st.markdown(f"### {title} ({year if year else ''})")

            line = ""
            if star:
                line += f'{star}<span class="ff-muted" style="margin-left:8px">({score5}/5)</span>'
            if shown_country:
                line += f'<span class="ff-muted" style="margin-left:12px">{flag_html}{shown_country}</span>'
            if line:
                st.markdown(line, unsafe_allow_html=True)

            # ===== STREAMING: toutes plateformes, tes applis d'abord =====
            opts_all = it.get("opts_all") or []
            opts_all = dedupe_streaming_options(opts_all)

            need_details = (not opts_all) or any(((o.get("link") or o.get("videoLink") or "").strip() == "") for o in opts_all)
            if need_details and it.get("api_id"):
                details = details_with_fallback(str(it["api_id"]))
                opts_all2 = ((details.get("streamingOptions") or {}).get(profile["country"]) or [])
                opts_all2 = dedupe_streaming_options(opts_all2)
                if opts_all2:
                    opts_all = opts_all2

            groups = group_options_by_service(opts_all)
            mine = [g for g in groups if (g["id"] in allowed_ids)]
            other = [g for g in groups if (g["id"] not in allowed_ids)]

            if mine:
                st.markdown("<div class='ff-muted'>✅ Dispo sur tes applis</div>", unsafe_allow_html=True)
            else:
                st.markdown("<div class='ff-muted'>❌ Pas dispo sur tes applis</div>", unsafe_allow_html=True)

            if mine:
                st.markdown("**Tes plateformes :**")
                for g in mine:
                    primary, rest = pick_primary_option(g["opts"])
                    if primary:
                        p_link = primary["link"]
                        p_type = primary["type"]
                        if p_link:
                            st.markdown(f"- **{g['name']}** ({p_type}) → {p_link}")
                        else:
                            st.markdown(f"- **{g['name']}** ({p_type}) → *(lien non fourni par l’API)*")
                    if rest:
                        with st.expander(f"… autres options sur {g['name']}"):
                            for o in rest:
                                link = o["link"]
                                typ = o["type"]
                                if link:
                                    st.markdown(f"- ({typ}) → {link}")
                                else:
                                    st.markdown(f"- ({typ}) → *(lien non fourni par l’API)*")

            if other:
                with st.expander(f"… Autres plateformes ({len(other)})"):
                    for g in other:
                        primary, rest = pick_primary_option(g["opts"])
                        if primary:
                            p_link = primary["link"]
                            p_type = primary["type"]
                            if p_link:
                                st.markdown(f"- **{g['name']}** ({p_type}) → {p_link}")
                            else:
                                st.markdown(f"- **{g['name']}** ({p_type}) → *(lien non fourni par l’API)*")
                        if rest:
                            with st.expander(f"… autres options sur {g['name']}"):
                                for o in rest:
                                    link = o["link"]
                                    typ = o["type"]
                                    if link:
                                        st.markdown(f"- ({typ}) → {link}")
                                    else:
                                        st.markdown(f"- ({typ}) → *(lien non fourni par l’API)*")

            with st.expander("Détails", expanded=False):
                if it.get("overview"):
                    st.write(it["overview"])

                # ✅ Cast: liens cliquables => relance recherche acteur
                cast = it.get("cast") or []
                if cast:
                    links = [f"[{a}](?actor={quote(a)})" for a in cast[:12]]
                    st.markdown("**Acteurs :** " + " · ".join(links))

        st.divider()
else:
    st.markdown("<div class='ff-muted'>Tape une histoire OU un acteur puis clique Chercher (Entrée marche aussi).</div>", unsafe_allow_html=True)