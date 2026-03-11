import os
import re
import json
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

# ================== STYLE ==================
def apply_theme():
    st.markdown(
        """
        <style>
        html, body, .stApp, [data-testid="stAppViewContainer"] { background: #f4f6f8 !important; }
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
            border-right: 1px solid rgba(0,0,0,0.06);
        }
        .ff-muted{ color: rgba(0,0,0,0.65) !important; font-size: 13px; }
        .ff-stars{position:relative;display:inline-block;font-size:16px;line-height:1;letter-spacing:1px}
        .ff-stars .bot{color:#d0d0d0;display:block}
        .ff-stars .top{color:#f5c518;position:absolute;left:0;top:0;overflow:hidden;white-space:nowrap;display:block}
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

TYPE_PRIORITY = {
    "subscription": 0,
    "free": 1,
    "addon": 2,
    "rent": 3,
    "buy": 4,
}

def norm_text(s: str) -> str:
    if not s:
        return ""
    s = s.lower().strip()
    s = re.sub(r"[’']", "'", s)
    s = re.sub(r"[^a-z0-9àâçéèêëîïôùûüÿñæœ'\s-]", " ", s, flags=re.I)
    s = re.sub(r"\s+", " ", s).strip()
    return s

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
            p.setdefault("show_elsewhere", False)
            return p
        except Exception:
            pass
    return {"country":"fr","lang":"fr","platform_ids":[],"show_elsewhere":False}

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

def search_by_keyword(keyword: str, country: str, show_type: str, lang: str):
    res = sa_get("/shows/search/filters", {
        "country": country,
        "show_type": show_type,
        "keyword": keyword,
        "series_granularity": "show",
        "output_language": lang,
    })
    return res.get("shows", []) if isinstance(res, dict) else []

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

# ================== OMDb ==================
@st.cache_data(show_spinner=False, ttl=86400)
def omdb_fetch(imdb_id: str):
    if not OMDB_API_KEY or not imdb_id:
        return None
    try:
        r = requests.get("https://www.omdbapi.com/",
                         params={"i": imdb_id, "apikey": OMDB_API_KEY, "tomatoes":"true"},
                         timeout=20)
        if not r.ok:
            return None
        data = r.json()
        return data if data.get("Response") == "True" else None
    except Exception:
        return None

def omdb_pack(imdb_id: str):
    data = omdb_fetch(imdb_id)
    if not data:
        return (None, "", [])
    rt = None; meta = None; imdb = None
    try:
        imdb = float(data.get("imdbRating")) if data.get("imdbRating") not in (None,"N/A") else None
    except Exception:
        pass
    try:
        meta = int(data.get("Metascore")) if data.get("Metascore") not in (None,"N/A") else None
    except Exception:
        pass
    try:
        for rr in data.get("Ratings", []) or []:
            if rr.get("Source") == "Rotten Tomatoes":
                v = rr.get("Value","")
                if v.endswith("%"):
                    rt = int(v.replace("%","").strip())
    except Exception:
        pass

    if rt is not None: score = float(rt)
    elif meta is not None: score = float(meta)
    elif imdb is not None: score = float(imdb * 10.0)
    else: score = None

    country = data.get("Country") if isinstance(data.get("Country"), str) else ""
    actors = []
    a = data.get("Actors")
    if isinstance(a, str) and a.strip() and a.strip().upper() != "N/A":
        actors = [x.strip() for x in a.split(",") if x.strip()]
    return (score, country, actors)

def ensure_omdb_for(items, max_n: int):
    if not OMDB_API_KEY:
        return
    done = 0
    for it in items:
        if done >= max_n:
            break
        if it["imdb_id"] and it["score100"] is None:
            score, ctry, actors = omdb_pack(it["imdb_id"])
            it["score100"] = score
            it["country_text"] = ctry or ""
            it["actors"] = actors or []
            done += 1

# ================== SEARCH LOGIC ==================
def merge_results(items):
    out = {}
    for sh in items:
        out[stable_id(sh)] = sh
    return list(out.values())

def relevance_score(sh: dict, q: str) -> float:
    hay = norm_text((sh.get("title") or "") + " " + (sh.get("overview") or ""))
    qn = norm_text(q)
    words = [w for w in qn.split() if len(w) >= 4 and w not in STOPWORDS]
    score = 0.0
    for w in set(words):
        if w in hay:
            score += 1.0
    return score

def parse_genres(show: dict):
    g = show.get("genres")
    out = []
    if isinstance(g, list):
        for x in g:
            if isinstance(x, str) and x.strip():
                out.append(x.strip())
            elif isinstance(x, dict):
                n = x.get("name") or x.get("title")
                if isinstance(n, str) and n.strip():
                    out.append(n.strip())
    elif isinstance(g, str) and g.strip():
        out.append(g.strip())
    res = []
    for a in out:
        if a not in res:
            res.append(a)
    return res

# --- show_type selection in Recherche ---
def showtype_to_list(choice: str):
    if choice == "Film":
        return ["movie"]
    if choice == "Série":
        return ["series"]
    return ["movie", "series"]

def build_raw_items(query: str, mode: str, prof: dict, show_types: list):
    country = prof["country"]
    lang = prof["lang"]
    allowed = set(prof.get("platform_ids", []))

    presets = {
        "Rapide":  {"queries_max": 2, "pool": 60,  "en_if_under": 6},
        "Normal":  {"queries_max": 4, "pool": 90,  "en_if_under": 8},
        "Profond": {"queries_max": 7, "pool": 140, "en_if_under": 999},
    }
    pre = presets.get(mode, presets["Normal"])

    q = query.strip()
    if not q:
        return []

    queries = [extract_keywords(q), q]
    q_seen = []
    for x in queries:
        x = x.strip()
        if x and x not in q_seen:
            q_seen.append(x)
    queries = q_seen

    found = []
    for stype in show_types:
        for kw in queries[:pre["queries_max"]]:
            found += search_by_keyword(kw, country, stype, lang)
        if len(found) < pre["en_if_under"]:
            for kw in queries[:pre["queries_max"]]:
                found += search_by_keyword(kw, country, stype, "en")

    shows = merge_results(found)

    raw = []
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

        origin_fallback = ""
        oc = sh.get("originCountry") or sh.get("countryOfOrigin") or sh.get("originalCountry")
        if isinstance(oc, str) and oc.strip():
            origin_fallback = oc.strip()
        elif isinstance(oc, list) and oc:
            origin_fallback = oc[0] if isinstance(oc[0], str) else ""

        raw.append({
            "show": sh,
            "api_id": sh.get("id"),
            "id": stable_id(sh),
            "title": sh.get("title") or "Sans titre",
            "year": year,
            "poster": get_poster_url(sh),
            "overview": sh.get("overview") or "",
            "genres": parse_genres(sh),
            "imdb_id": imdb_id,
            "score100": None,
            "country_text": "",
            "actors": [],
            "origin_fallback": origin_fallback,
            "is_mine": 1 if opts_mine else 0,
            "opts_mine": opts_mine,
            "opts_all": opts_all,
            "rel": relevance_score(sh, q) + (0.25 * (1 if opts_mine else 0)),
        })

    raw.sort(key=lambda x: x["rel"], reverse=True)
    return raw[:pre["pool"]]

# ✅ MODIF: filtre année en slider (year_range) au lieu de min/max 0/0
def apply_filters_and_sort(raw_items, sort_mode, only_my_apps, platform_filter, year_range, genre_filter):
    items = list(raw_items)

    if only_my_apps:
        keep = [x for x in items if x["is_mine"] == 1]
        items = keep if keep else items

    if platform_filter != "Toutes":
        def okp(it):
            for o in it["opts_all"]:
                s = (o.get("service") or {})
                name = (s.get("name") or s.get("id") or "").strip()
                if name == platform_filter:
                    return True
            return False
        k = [x for x in items if okp(x)]
        items = k if k else items

    # année (slider)
    if year_range:
        y0, y1 = year_range
        items = [x for x in items if x["year"] is None or (x["year"] >= y0 and x["year"] <= y1)]

    if genre_filter != "Tous":
        ng = norm_text(genre_filter)
        def okg(it):
            return ng in [norm_text(g) for g in (it["genres"] or [])]
        k = [x for x in items if okg(x)]
        items = k if k else items

    ensure_omdb_for(items, max_n=120 if sort_mode == "Note (haute)" else 30)

    if sort_mode == "Pertinence":
        items.sort(key=lambda x: (x["rel"], x["is_mine"]), reverse=True)
    elif sort_mode == "Année (récent)":
        items.sort(key=lambda x: ((x["year"] is not None), x["year"] or -1, x["is_mine"]), reverse=True)
    else:
        items.sort(key=lambda x: ((x["score100"] is not None), x["score100"] or -1, x["is_mine"]), reverse=True)

    return items

# ================== NAV / SESSION ==================
st.session_state.setdefault("did_enter", False)
st.session_state.setdefault("page", "Accueil" if not st.session_state["did_enter"] else "Recherche")
st.session_state.setdefault("raw_items", [])
st.session_state.setdefault("raw_query", "")

# acteur via URL (inchangé)
qp = get_query_params()
actor_param = None
if "actor" in qp:
    v = qp.get("actor")
    actor_param = v[0] if isinstance(v, list) and v else (v if isinstance(v, str) else None)
if actor_param:
    clear_query_params()
    st.session_state["did_enter"] = True
    st.session_state["page"] = "Recherche"

# ================== SIDEBAR ==================
with st.sidebar:
    st.markdown("## FilmFinder IA")
    if st.session_state["did_enter"]:
        nav = st.radio("Menu", ["Recherche", "Profil"], index=0 if st.session_state["page"]=="Recherche" else 1, key="nav")
        st.session_state["page"] = nav
    else:
        st.caption("Démarrage (Accueil)")

# ================== PAGES ==================
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
            profile = {
                "country": country,
                "lang": lang,
                "platform_ids": platform_ids,
                "show_elsewhere": False,
            }
            save_profile(profile)
            st.session_state["did_enter"] = True
            st.session_state["page"] = "Recherche"
            st.rerun()

    st.stop()

# -------- PROFIL --------
if page == "Profil":
    st.markdown("# Profil")
    st.caption("Ici tu modifies pays/langue/plateformes. (Film/Série se choisit dans Recherche.)")

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
            profile = {
                "country": country,
                "lang": lang,
                "platform_ids": platform_ids,
                "show_elsewhere": bool(profile.get("show_elsewhere", False)),
            }
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

# ✅ Film/Série ici (pas dans profil)
show_choice = st.selectbox("Je cherche :", ["Film", "Série", "Les deux"], index=2)
show_types = showtype_to_list(show_choice)

mode = st.radio("Mode", ["Rapide","Normal","Profond"], horizontal=True, index=1)

def do_search(q: str):
    raw = build_raw_items(q, mode=mode, prof=profile, show_types=show_types)
    st.session_state["raw_items"] = raw
    st.session_state["raw_query"] = q
    st.session_state["last_show_types"] = show_types

with st.form("search_form", clear_on_submit=False):
    q_main = st.text_input("Ton souvenir (Entrée lance)", key="q_main")
    q_more = st.text_area("Détails (optionnel)", key="q_more", height=70,
                          placeholder="Acteur/actrice · année approx · scène marquante · SF…")
    submitted = st.form_submit_button("Trouver")

if submitted:
    q = (st.session_state.get("q_main","").strip() + " " + st.session_state.get("q_more","").strip()).strip()
    if q:
        do_search(q)

raw_items = st.session_state.get("raw_items", [])
genre_choices = ["Tous"] + get_genres(profile["country"], profile["lang"])

services = get_services(profile["country"], profile["lang"])
id_to_name = {s.get("id"): (s.get("name") or s.get("id")) for s in services}
platform_choices = ["Toutes"] + sorted([id_to_name.get(i, i) for i in profile.get("platform_ids", [])])

# filtres (année = slider seulement si résultats)
c1, c2, c3 = st.columns([2.2, 1.1, 1.6])
with c1:
    sort_mode = st.selectbox("Trier par", ["Pertinence","Année (récent)","Note (haute)"], index=0)
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
        year_range = st.slider("Année (min–max)", min_value=int(y_min), max_value=int(y_max), value=(int(y_min), int(y_max)))
    # si y_min == y_max, pas besoin de slider
# sinon: pas d’affichage année (ça évite tes 0/0 inutiles)

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
        # pour "Les deux", l'API veut un show_type: on tente dans l'ordre choisi
        for stype in show_types:
            d = get_show_details(api_id, profile["country"], stype, profile["lang"])
            if d:
                return d
        # fallback extra si les deux
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

        country_label = ""
        iso = ""
        if it.get("country_text"):
            country_label = it["country_text"].split(",")[0].strip()
            iso = iso2_from_country_text(it["country_text"])
        elif it.get("origin_fallback"):
            country_label = it["origin_fallback"]
            iso = iso2_from_country_text(it["origin_fallback"])

        flag_html = flag_img_html(iso)
        shown_country = country_label if country_label else (iso.upper() if iso else "")

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

            # plateformes
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

                if it.get("actors"):
                    links = [f"[{a}](?actor={quote(a)})" for a in it["actors"][:10]]
                    st.markdown("**Acteurs :** " + " · ".join(links))

        st.divider()
else:
    st.markdown("<div class='ff-muted'>Tape un souvenir puis Entrée (ou clique Trouver).</div>", unsafe_allow_html=True)