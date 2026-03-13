import os
import re
import json
import random
import gzip
import io
import difflib
from datetime import datetime, timedelta, timezone
from pathlib import Path
import xml.etree.ElementTree as ET

import requests
import streamlit as st
from dotenv import load_dotenv

# ================== CONFIG ==================
load_dotenv()

# RapidAPI - Streaming Availability
RAPIDAPI_KEY = os.getenv("RAPIDAPI_KEY", "").strip()
RAPIDAPI_HOST = os.getenv("RAPIDAPI_HOST", "streaming-availability.p.rapidapi.com").strip()
BASE_URL = "https://streaming-availability.p.rapidapi.com"

# IA locale (Ollama)
OLLAMA_URL = os.getenv("OLLAMA_URL", "http://localhost:11434").strip()
OLLAMA_MODEL = os.getenv("OLLAMA_MODEL", "llama3.2:3b").strip()

# Notes/acteurs/genres via OMDb (optionnel)
OMDB_API_KEY = os.getenv("OMDB_API_KEY", "").strip()

# TNT (XMLTVFr) - optionnel
XMLTV_TNT_URL = os.getenv("XMLTV_TNT_URL", "").strip()
TNT_LOOKAHEAD_DAYS = int(os.getenv("TNT_LOOKAHEAD_DAYS", "5"))

APP_DIR = Path(__file__).parent
PROFILE_PATH = APP_DIR / "profile.json"

st.set_page_config(page_title="FilmFinder IA", layout="centered")


# ================== THEME ==================
def apply_theme():
    css = """
    <style>
    html, body, .stApp, [data-testid="stAppViewContainer"] { background: #f4f6f8 !important; }

    .main .block-container{
        max-width: 1040px !important;
        margin: 18px auto !important;
        background: #ffffff !important;
        border-radius: 18px !important;
        padding: 22px 26px 30px 26px !important;
        box-shadow: 0 10px 35px rgba(0,0,0,0.08) !important;
    }

    [data-testid="stSidebar"] > div:first-child{
        background: #ffffff !important;
        border-right: 1px solid rgba(0,0,0,0.06);
    }

    .main h1,.main h2,.main h3,.main p,.main label,.main span,.main div,.main li{ color:#111 !important; }
    .main a{ color:#0b57d0 !important; font-weight:600; }

    .ff-card{
        border: 1px solid rgba(0,0,0,0.08);
        border-radius: 16px;
        padding: 16px 16px 10px 16px;
        background: #ffffff;
        box-shadow: 0 8px 24px rgba(0,0,0,0.06);
        margin: 12px 0 18px 0;
    }

    .ff-muted{ color: rgba(0,0,0,0.65) !important; font-size: 13px; }

    /* étoiles robustes (pas de dégradé) */
    .ff-stars{position:relative;display:inline-block;font-size:16px;line-height:1;letter-spacing:1px}
    .ff-stars .bot{color:#d0d0d0;display:block}
    .ff-stars .top{color:#f5c518;position:absolute;left:0;top:0;overflow:hidden;white-space:nowrap;display:block}
    </style>
    """
    st.markdown(css, unsafe_allow_html=True)

apply_theme()


# ================== UTILS ==================
def norm_text(s: str) -> str:
    if not s:
        return ""
    s = s.lower().strip()
    s = re.sub(r"[’']", "'", s)
    s = re.sub(r"[^a-z0-9àâçéèêëîïôùûüÿñæœ'\s-]", " ", s, flags=re.I)
    s = re.sub(r"\s+", " ", s).strip()
    return s

def stars_html(score_0_100):
    """5 étoiles jaunes proportionnelles (0..100) - version robuste."""
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

# mapping minimal FR/EN -> ISO2
_COUNTRY_MAP = {
    "france": "FR", "fr": "FR",
    "united states": "US", "usa": "US", "us": "US", "états-unis": "US", "etats-unis": "US",
    "united kingdom": "GB", "uk": "GB", "royaume-uni": "GB", "angleterre": "GB", "gb": "GB",
    "japan": "JP", "japon": "JP", "jp": "JP",
    "korea": "KR", "corée": "KR", "coree": "KR", "south korea": "KR", "kr": "KR",
    "spain": "ES", "espagne": "ES", "es": "ES",
    "italy": "IT", "italie": "IT", "it": "IT",
    "germany": "DE", "allemagne": "DE", "de": "DE",
    "canada": "CA", "ca": "CA",
    "australia": "AU", "au": "AU",
    "sweden": "SE", "suède": "SE", "suede": "SE", "se": "SE",
    "norway": "NO", "norvège": "NO", "norvege": "NO", "no": "NO",
    "denmark": "DK", "danemark": "DK", "dk": "DK",
    "belgium": "BE", "belgique": "BE", "be": "BE",
    "switzerland": "CH", "suisse": "CH", "ch": "CH",
}

def origin_iso2(show: dict) -> str:
    # champs possibles (souvent codes ISO2)
    for k in ["originCountry", "originalCountry", "countryOfOrigin"]:
        v = show.get(k)
        if isinstance(v, str) and v.strip():
            vv = norm_text(v.strip())
            if len(v.strip()) == 2:
                return v.strip().upper()
            return _COUNTRY_MAP.get(vv, "")
        if isinstance(v, list) and v:
            for it in v:
                if isinstance(it, str) and it.strip():
                    if len(it.strip()) == 2:
                        return it.strip().upper()
                    return _COUNTRY_MAP.get(norm_text(it.strip()), "")
    # fallback texte dans productionCountries
    for k in ["productionCountries", "countries"]:
        v = show.get(k)
        if isinstance(v, list) and v:
            for it in v:
                if isinstance(it, str) and it.strip():
                    if len(it.strip()) == 2:
                        return it.strip().upper()
                    iso = _COUNTRY_MAP.get(norm_text(it.strip()), "")
                    if iso:
                        return iso
                if isinstance(it, dict):
                    n = it.get("code") or it.get("name")
                    if isinstance(n, str) and n.strip():
                        if len(n.strip()) == 2:
                            return n.strip().upper()
                        iso = _COUNTRY_MAP.get(norm_text(n.strip()), "")
                        if iso:
                            return iso
    return ""

def get_origin_text(show: dict) -> str:
    candidates = []
    for k in ["originCountry", "originalCountry", "countryOfOrigin"]:
        v = show.get(k)
        if isinstance(v, str) and v.strip():
            candidates.append(v.strip())
        elif isinstance(v, list):
            candidates += [x for x in v if isinstance(x, str) and x.strip()]
    for k in ["productionCountries", "countries"]:
        v = show.get(k)
        if isinstance(v, list):
            for x in v:
                if isinstance(x, str) and x.strip():
                    candidates.append(x.strip())
                elif isinstance(x, dict):
                    n = x.get("name") or x.get("code")
                    if isinstance(n, str) and n.strip():
                        candidates.append(n.strip())
    out = []
    for c in candidates:
        if c not in out:
            out.append(c)
    return ", ".join(out[:3])

def get_genres_text(show: dict) -> str:
    g = show.get("genres")
    names = []
    if isinstance(g, list):
        for x in g:
            if isinstance(x, str) and x.strip():
                names.append(x.strip())
            elif isinstance(x, dict):
                n = x.get("name") or x.get("title")
                if isinstance(n, str) and n.strip():
                    names.append(n.strip())
    elif isinstance(g, str) and g.strip():
        names = [g.strip()]
    out = []
    for n in names:
        if n not in out:
            out.append(n)
    return ", ".join(out[:6])

def get_genres_list_lower(show: dict):
    txt = get_genres_text(show)
    if not txt:
        return []
    return [norm_text(x.strip()) for x in txt.split(",") if x.strip()]


# ================== PROFILE ==================
def load_profile():
    if PROFILE_PATH.exists():
        try:
            p = json.loads(PROFILE_PATH.read_text(encoding="utf-8"))
            # compat ancien "all"
            if p.get("show_type") == "all":
                p["show_type"] = "movie"
            if p.get("show_type") not in ("movie", "series"):
                p["show_type"] = "movie"
            return p
        except Exception:
            pass
    return {
        "pseudo": "",
        "country": "fr",
        "lang": "fr",
        "show_type": "movie",   # PAR DÉFAUT: FILM
        "platform_ids": [],
        "show_elsewhere": False,
    }

def save_profile(p):
    PROFILE_PATH.write_text(json.dumps(p, ensure_ascii=False, indent=2), encoding="utf-8")

profile = load_profile()


# ================== OLLAMA ==================
def ollama_is_up() -> bool:
    try:
        r = requests.get(f"{OLLAMA_URL}/api/tags", timeout=2)
        return r.ok
    except Exception:
        return False

def ollama_pack(description: str):
    """
    JSON STRICT + court => rapide
    {"titles":[...], "queries":[...]}
    """
    prompt = f"""
Réponds UNIQUEMENT avec un JSON valide:
{{"titles":[...], "queries":[...]}}

Règles:
- titles: 3 à 6 titres max (courts)
- queries: 4 à 6 requêtes max (3 à 7 mots), FR/EN
- PAS de phrases longues

Souvenir: {description}
""".strip()

    r = requests.post(
        f"{OLLAMA_URL}/api/generate",
        json={
            "model": OLLAMA_MODEL,
            "prompt": prompt,
            "stream": False,
            "options": {"temperature": 0.2, "num_predict": 220}
        },
        timeout=60,
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


# ================== RAPIDAPI ==================
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
        raise RuntimeError(f"API ERROR {r.status_code}: {r.text[:300]}")
    return r.json()

@st.cache_data(show_spinner=False, ttl=3600)
def get_services(country: str, lang: str):
    data = sa_get(f"/countries/{country}", {"output_language": lang})
    return data.get("services", []) or []

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
        sid = ((o.get("service") or {}).get("id") or "")
        typ = o.get("type") or ""
        key = (sid, typ)
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


# ================== OMDb (notes + acteurs) ==================
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
    """
    score_0_100 + sources string
    """
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

def actors_from_omdb(show: dict) -> str:
    imdb_id = show.get("imdbId") or show.get("imdbID") or None
    data = omdb_fetch(imdb_id) if imdb_id else None
    if not data:
        return ""
    a = data.get("Actors")
    if isinstance(a, str) and a.strip() and a.strip().upper() != "N/A":
        return a.strip()
    return ""


# ================== TNT (XMLTVFr) ==================
def _candidate_xmltv_urls():
    urls = []
    if XMLTV_TNT_URL:
        urls.append(XMLTV_TNT_URL)
    urls += [
        "https://xmltvfr.fr/xmltv/xmltv_tnt.xml.gz",
        "https://xmltvfr.fr/xmltv/xmltv_tnt.xml",
    ]
    return urls

@st.cache_data(show_spinner=False, ttl=3600)
def tnt_load_index():
    headers = {"User-Agent": "Mozilla/5.0 FilmFinderIA/1.0"}
    last_err = None

    content = None
    used_url = None
    for url in _candidate_xmltv_urls():
        try:
            r = requests.get(url, headers=headers, timeout=30)
            if r.ok and r.content:
                content = r.content
                used_url = url
                break
            last_err = f"{url} -> {r.status_code}"
        except Exception as e:
            last_err = f"{url} -> {e}"

    if content is None:
        raise RuntimeError(f"Impossible de récupérer le guide TNT. Dernière erreur: {last_err}")

    if used_url.endswith(".gz") or (len(content) > 2 and content[0] == 0x1F and content[1] == 0x8B):
        content = gzip.decompress(content)

    channel_names = {}
    title_index = {}

    now = datetime.now(timezone.utc)
    end = now + timedelta(days=max(1, TNT_LOOKAHEAD_DAYS))

    for event, elem in ET.iterparse(io.BytesIO(content), events=("end",)):
        if elem.tag == "channel":
            cid = elem.attrib.get("id", "")
            name = None
            for dn in elem.findall("display-name"):
                if dn.text:
                    name = dn.text.strip()
                    break
            if cid and name:
                channel_names[cid] = name
            elem.clear()

        elif elem.tag == "programme":
            ch = elem.attrib.get("channel", "")
            start_s = elem.attrib.get("start", "")
            stop_s = elem.attrib.get("stop", "")

            def parse_dt(s):
                try:
                    return datetime.strptime(s, "%Y%m%d%H%M%S %z")
                except Exception:
                    return None

            start_dt = parse_dt(start_s)
            stop_dt = parse_dt(stop_s)
            if not start_dt or not stop_dt:
                elem.clear()
                continue

            start_utc = start_dt.astimezone(timezone.utc)
            if start_utc < now or start_utc > end:
                elem.clear()
                continue

            title = None
            for t in elem.findall("title"):
                if t.text:
                    title = t.text.strip()
                    break
            if not title:
                elem.clear()
                continue

            key = norm_text(title)
            if key:
                title_index.setdefault(key, []).append((start_dt.isoformat(), stop_dt.isoformat(), ch))
            elem.clear()

    for k in list(title_index.keys()):
        title_index[k].sort(key=lambda x: x[0])
        title_index[k] = title_index[k][:10]

    return channel_names, title_index

def tnt_find_airings(title_variants, limit=2):
    try:
        channel_names, idx = tnt_load_index()
    except Exception:
        return []

    keys = [norm_text(t) for t in title_variants if t]
    keys = [k for k in keys if k]

    matches = []
    for k in keys:
        if k in idx:
            matches += idx[k]

    if not matches and idx and keys:
        all_keys = list(idx.keys())
        for k in keys:
            close = difflib.get_close_matches(k, all_keys, n=2, cutoff=0.92)
            for ck in close:
                matches += idx.get(ck, [])

    uniq = []
    seen = set()
    for s, e, ch in matches:
        key = (s, ch)
        if key in seen:
            continue
        seen.add(key)
        uniq.append((s, e, ch))
    uniq.sort(key=lambda x: x[0])

    out = []
    for s, e, ch in uniq[:limit]:
        try:
            sdt = datetime.fromisoformat(s)
            edt = datetime.fromisoformat(e)
            out.append({
                "channel": channel_names.get(ch, ch),
                "start": sdt.strftime("%d/%m %H:%M"),
                "stop": edt.strftime("%H:%M"),
            })
        except Exception:
            continue
    return out


# ================== SEARCH HELPERS ==================
def score_relevance(sh, qtext):
    t = ((sh.get("title") or "") + " " + (sh.get("overview") or "")).lower()
    words = [w for w in re.findall(r"[a-zA-ZÀ-ÿ0-9']+", qtext.lower()) if len(w) >= 4]
    return sum(1 for w in set(words) if w in t)

def merge_results(items):
    merged = {}
    for sh in items:
        merged[stable_id(sh)] = sh
    return list(merged.values())

def extract_keywords(text: str, max_words: int = 10) -> str:
    stop = {
        "le","la","les","un","une","des","de","du","dans","sur","avec","sans","et","ou",
        "qui","que","quoi","dont","au","aux","en","a","à","pour","par","se","sa","son","ses",
        "je","tu","il","elle","on","nous","vous","ils","elles","toujours",
        "the","a","an","and","or","in","on","with","without","to","of","for","by","from",
    }
    words = re.findall(r"[a-zA-ZÀ-ÿ0-9']+", text.lower())
    words = [w for w in words if len(w) >= 4 and w not in stop]
    out = []
    for w in words:
        if w not in out:
            out.append(w)
        if len(out) >= max_words:
            break
    return " ".join(out) if out else text.strip()

def apply_user_filters(shows, include_genres_fr, avoid_tags):
    """
    Filtrage "best effort" (genre fiable si dispo, tags sensibles = heuristique).
    avoid_tags: set[str] in {"gore","sex","adult"}
    """
    if not include_genres_fr and not avoid_tags:
        return shows

    # mapping FR -> tokens à matcher dans genres
    genre_map = {
        "Action": ["action"],
        "Aventure": ["adventure", "aventure"],
        "Animation": ["animation"],
        "Comédie": ["comedy", "comedie", "comédie"],
        "Crime": ["crime"],
        "Documentaire": ["documentary", "documentaire"],
        "Drame": ["drama", "drame"],
        "Famille": ["family", "famille"],
        "Fantasy": ["fantasy"],
        "Horreur": ["horror", "horreur"],
        "Mystère": ["mystery", "mystere", "mystère"],
        "Romance": ["romance"],
        "Science-fiction": ["science fiction", "sci-fi", "scifi", "science-fiction"],
        "Thriller": ["thriller"],
        "Guerre": ["war", "guerre"],
        "Western": ["western"],
    }

    include_tokens = []
    for g in include_genres_fr:
        include_tokens += genre_map.get(g, [])

    def looks_sensitive(sh):
        hay = norm_text((sh.get("title") or "") + " " + (sh.get("overview") or ""))
        gl = get_genres_list_lower(sh)
        # gore
        if "gore" in avoid_tags:
            if "horror" in gl or "horreur" in gl or "thriller" in gl:
                if any(w in hay for w in ["gore", "sang", "massacre", "torture", "slasher", "ultra-violent", "ultra violent"]):
                    return True
        # sex explicit
        if "sex" in avoid_tags:
            if any(w in hay for w in ["sex", "sexe", "porn", "pornographie", "érotique", "erotique", "nudité", "nudite", "escort"]):
                return True
        # adult
        if "adult" in avoid_tags:
            if any(w in hay for w in ["porn", "pornographie", "xxx", "adulte", "hardcore"]):
                return True
        return False

    filtered = []
    for sh in shows:
        # genre include
        if include_tokens:
            gl = get_genres_list_lower(sh)
            if gl:
                ok = any(any(tok in g for tok in include_tokens) for g in gl)
                if not ok:
                    continue

        # sensitive avoid
        if avoid_tags and looks_sensitive(sh):
            continue

        filtered.append(sh)

    # si filtre trop agressif, on garde original
    return filtered if len(filtered) >= 6 else shows


# ================== UI STATE ==================
st.session_state.setdefault("entered", False)
st.session_state.setdefault("page", "Accueil")
st.session_state.setdefault("do_search", False)
st.session_state.setdefault("last_results", None)
st.session_state.setdefault("last_query", "")
st.session_state.setdefault("last_mode", "Normal")
st.session_state.setdefault("last_filters", {})


# ================== SIDEBAR MENU (sans “API OK / IA ON…”) ==================
with st.sidebar:
    st.markdown("## FilmFinder IA")
    if st.session_state["entered"]:
        st.radio("Menu", ["Recherche", "Profil"], key="page")
    else:
        st.caption("Accueil (début uniquement)")


# ================== ACCUEIL ==================
if st.session_state["page"] == "Accueil":
    st.markdown("# FilmFinder IA")
    st.caption("Souvenir flou → titres probables → où regarder.")

    st.markdown('<div class="ff-card">', unsafe_allow_html=True)
    st.markdown("### Inscription rapide")

    if not RAPIDAPI_KEY:
        st.error("RAPIDAPI_KEY manquante dans .env (RapidAPI).")
        st.stop()

    with st.form("signup_form"):
        pseudo = st.text_input("Pseudo (optionnel)", value=profile.get("pseudo", ""))

        col1, col2, col3, col4 = st.columns(4)
        with col1:
            country = st.selectbox("Pays", ["fr", "be", "ch", "gb", "us"], index=["fr","be","ch","gb","us"].index(profile.get("country","fr")))
        with col2:
            lang = st.selectbox("Langue", ["fr", "en"], index=["fr","en"].index(profile.get("lang","fr")))
        with col3:
            typ = st.selectbox("Type", ["Film", "Série"], index=0 if profile.get("show_type","movie")=="movie" else 1)
        with col4:
            show_elsewhere = st.checkbox("Montrer ailleurs", value=bool(profile.get("show_elsewhere", False)))

        services = get_services(country, lang)
        name_to_id = {(s.get("name") or s.get("id")): s.get("id") for s in services if (s.get("name") or s.get("id")) and s.get("id")}
        id_to_name = {v: k for k, v in name_to_id.items()}

        default_names = [id_to_name[i] for i in profile.get("platform_ids", []) if i in id_to_name]
        if not default_names:
            for wanted in ["Netflix","Prime Video","Disney+","Apple TV+","Max","HBO Max"]:
                if wanted in name_to_id:
                    default_names.append(wanted)

        chosen_names = st.multiselect("Tes plateformes", options=sorted(name_to_id.keys()), default=sorted(set(default_names)))
        platform_ids = [name_to_id[n] for n in chosen_names]

        enter_btn = st.form_submit_button("Entrer")

    st.markdown("</div>", unsafe_allow_html=True)

    if enter_btn:
        if not platform_ids:
            st.warning("Coche au moins 1 plateforme 🙂")
        else:
            profile = {
                "pseudo": pseudo.strip(),
                "country": country,
                "lang": lang,
                "show_type": "movie" if typ == "Film" else "series",
                "platform_ids": platform_ids,
                "show_elsewhere": bool(show_elsewhere),
            }
            save_profile(profile)
            st.session_state["entered"] = True
            st.session_state["page"] = "Recherche"
            st.rerun()

    st.stop()


# ================== PROFIL ==================
if st.session_state["page"] == "Profil":
    st.markdown("# Profil")

    with st.form("profile_form"):
        pseudo = st.text_input("Pseudo (optionnel)", value=profile.get("pseudo", ""))

        col1, col2, col3, col4 = st.columns(4)
        with col1:
            country = st.selectbox("Pays", ["fr", "be", "ch", "gb", "us"], index=["fr","be","ch","gb","us"].index(profile.get("country","fr")))
        with col2:
            lang = st.selectbox("Langue", ["fr", "en"], index=["fr","en"].index(profile.get("lang","fr")))
        with col3:
            typ = st.selectbox("Type", ["Film", "Série"], index=0 if profile.get("show_type","movie")=="movie" else 1)
        with col4:
            show_elsewhere = st.checkbox("Montrer ailleurs", value=bool(profile.get("show_elsewhere", False)))

        services = get_services(country, lang)
        name_to_id = {(s.get("name") or s.get("id")): s.get("id") for s in services if (s.get("name") or s.get("id")) and s.get("id")}
        id_to_name = {v: k for k, v in name_to_id.items()}

        default_names = [id_to_name[i] for i in profile.get("platform_ids", []) if i in id_to_name]
        chosen_names = st.multiselect("Tes plateformes", options=sorted(name_to_id.keys()), default=sorted(set(default_names)))
        platform_ids = [name_to_id[n] for n in chosen_names]

        ok_btn = st.form_submit_button("✅ Enregistrer")

    if ok_btn:
        if not platform_ids:
            st.warning("Coche au moins 1 plateforme 🙂")
        else:
            profile = {
                "pseudo": pseudo.strip(),
                "country": country,
                "lang": lang,
                "show_type": "movie" if typ == "Film" else "series",
                "platform_ids": platform_ids,
                "show_elsewhere": bool(show_elsewhere),
            }
            save_profile(profile)
            st.success("Profil enregistré.")
            st.rerun()

    st.stop()


# ================== RECHERCHE ==================
st.markdown("# Recherche")

if not profile.get("platform_ids"):
    st.warning("Crée ton profil (plateformes) avant de chercher.")
    st.stop()

MODE_PRESETS = {
    "Rapide":  {"titles_max": 2, "queries_max": 2, "en_if_under": 6,   "pool": 40,  "omdb_top": 10},
    "Normal":  {"titles_max": 4, "queries_max": 4, "en_if_under": 8,   "pool": 60,  "omdb_top": 18},
    "Profond": {"titles_max": 6, "queries_max": 6, "en_if_under": 999, "pool": 100, "omdb_top": 25},
}

mode = st.radio("Mode", ["Rapide", "Normal", "Profond"], horizontal=True, index=1)
preset = MODE_PRESETS[mode]

def trigger_search():
    st.session_state["do_search"] = True

q_main = st.text_input("Ton souvenir (Entrée lance)", key="q_main", on_change=trigger_search, placeholder="Ex: un homme se perd dans la forêt…")
q_more = st.text_area(
    "Détails (optionnel)",
    key="q_more",
    height=90,
    placeholder="Acteur/actrice · année approx · pays · plateforme · scène marquante · ambiance · SF/space · gore/violent · scène de sexe…"
)

with st.expander("Filtres (optionnel)", expanded=False):
    genre_choices = [
        "Action","Aventure","Animation","Comédie","Crime","Documentaire","Drame","Famille","Fantasy",
        "Horreur","Mystère","Romance","Science-fiction","Thriller","Guerre","Western"
    ]
    include_genres = st.multiselect("Genre (inclure)", genre_choices, default=[])

    avoid = st.multiselect(
        "Éviter (best effort)",
        ["Gore/violent", "Sexe explicite", "Adulte"],
        default=[]
    )
    avoid_tags = set()
    if "Gore/violent" in avoid:
        avoid_tags.add("gore")
    if "Sexe explicite" in avoid:
        avoid_tags.add("sex")
    if "Adulte" in avoid:
        avoid_tags.add("adult")

if st.button("Trouver"):
    st.session_state["do_search"] = True


# --- recherche ---
if st.session_state["do_search"]:
    st.session_state["do_search"] = False
    q = (q_main.strip() + " " + q_more.strip()).strip()
    if not q:
        st.warning("Écris au moins une phrase 🙂")
        st.stop()

    country = profile["country"]
    lang = profile["lang"]
    show_type = profile["show_type"]  # IMPORTANT: film ou série selon ton choix au début

    titles = []
    queries = []
    errors = []

    if ollama_is_up():
        try:
            pack = ollama_pack(q)
            titles = pack.get("titles", []) or []
            queries = pack.get("queries", []) or []
        except Exception as e:
            errors.append(f"IA locale: {e}")

    if not queries:
        queries = [extract_keywords(q), q]

    if mode == "Profond":
        qk = extract_keywords(q, max_words=14)
        if qk not in queries:
            queries.append(qk)
        if q not in queries:
            queries.append(q)

    # dedupe queries
    q_seen = []
    for x in queries:
        x = x.strip()
        if x and x not in q_seen:
            q_seen.append(x)
    queries = q_seen

    found = []

    # 1) titres
    for t in titles[:preset["titles_max"]]:
        try:
            found += search_by_title(t, country, show_type, lang)
        except Exception as e:
            errors.append(str(e))

    # 2) keywords FR
    for kw in queries[:preset["queries_max"]]:
        try:
            found += search_by_keyword(kw, country, show_type, lang)
        except Exception as e:
            errors.append(str(e))

    # 3) keywords EN si trop peu
    if len(found) < preset["en_if_under"]:
        for kw in queries[:preset["queries_max"]]:
            try:
                found += search_by_keyword(kw, country, show_type, "en")
            except Exception as e:
                errors.append(str(e))

    found = merge_results(found)
    found.sort(key=lambda sh: score_relevance(sh, q), reverse=True)

    # anti hors-sujet
    q_clean = norm_text(q)
    key_words = [w for w in q_clean.split() if len(w) >= 6]

    def is_relevant(sh):
        hay = norm_text((sh.get("title") or "") + " " + (sh.get("overview") or ""))
        if not key_words:
            return True
        for w in key_words[:2]:
            root = w[:7]
            if root and root in hay:
                return True
        return False

    filtered = [sh for sh in found if is_relevant(sh)]
    found = filtered if len(filtered) >= 6 else found

    # filtres utilisateur (genre/éviter)
    found = apply_user_filters(found, include_genres, avoid_tags)

    found = found[:preset["pool"]]

    st.session_state["last_results"] = found
    st.session_state["last_query"] = q
    st.session_state["last_mode"] = mode
    st.session_state["last_filters"] = {"include_genres": include_genres, "avoid": list(avoid_tags)}
    st.session_state["last_errors"] = errors


# --- affichage ---
results = st.session_state.get("last_results")
if results is not None:
    q = st.session_state.get("last_query", "")
    mode_used = st.session_state.get("last_mode", mode)

    st.caption(f"Requête: {q} — Mode: {mode_used}")

    sort_mode = st.selectbox("Trier par", ["Pertinence", "Année (récent)", "Note (haute)"], index=0)

    enriched = []
    for i, sh in enumerate(results):
        year = sh.get("releaseYear") or sh.get("firstAirYear") or 0
        try:
            year = int(year) if year else 0
        except Exception:
            year = 0

        # score (OMDb top N)
        score100 = None
        sources = ""
        if i < MODE_PRESETS[mode_used]["omdb_top"]:
            score100, sources = critic_score_and_sources(sh)
        else:
            if isinstance(sh.get("rating"), (int, float)):
                score100 = float(sh["rating"])
                sources = f"Score {int(score100)}/100"

        enriched.append((sh, year, score100, sources))

    if sort_mode == "Année (récent)":
        enriched.sort(key=lambda x: x[1], reverse=True)
    elif sort_mode == "Note (haute)":
        enriched.sort(key=lambda x: (x[2] is not None, x[2] or -1), reverse=True)

    st.write(f"✅ Résultats : {len(enriched)} (20 affichés)")

    country = profile["country"]
    allowed_services = set(profile.get("platform_ids", []))
    show_elsewhere = bool(profile.get("show_elsewhere", False))

    for idx, (sh, year, score100, sources) in enumerate(enriched[:20]):
        title = sh.get("title", "Sans titre")
        overview = sh.get("overview", "")
        poster = get_poster_url(sh)

        # streaming
        opts_all = ((sh.get("streamingOptions") or {}).get(country) or [])
        opts_all = dedupe_streaming_options(opts_all)

        opts_mine = [o for o in opts_all if ((o.get("service") or {}).get("id") in allowed_services)]
        opts_mine = dedupe_streaming_options(opts_mine)

        # drapeau origine
        iso = origin_iso2(sh)
        flag = flag_from_iso2(iso) if iso else ""

        # TNT auto (afficher seulement si trouvé)
        # on le fait pour les 10 premiers seulement (perf) ; si trouvé -> on affiche, sinon rien.
        airings = []
        if idx < 10:
            title_variants = [title]
            if sh.get("originalTitle"):
                title_variants.append(sh["originalTitle"])
            airings = tnt_find_airings(title_variants, limit=2)

        c_img, c_txt = st.columns([1, 3])
        with c_img:
            if poster:
                st.image(poster, width=140)

        with c_txt:
            st.markdown(f"### {title} ({year if year else ''})")

            star = stars_html(score100)
            if star:
                score5 = None if score100 is None else round(float(score100) / 20.0, 1)
                label = "" if score5 is None else f"<span class='ff-muted' style='margin-left:8px'>({score5}/5)</span>"
                flag_html = f"<span style='margin-left:10px'>{flag}</span>" if flag else ""
                st.markdown(f"{star}{label}{flag_html}", unsafe_allow_html=True)

            # statut simple
            if opts_mine:
                st.markdown("<div class='ff-muted'>✅ Dispo sur tes applis</div>", unsafe_allow_html=True)
            else:
                st.markdown("<div class='ff-muted'>❌ Pas dispo sur tes applis</div>", unsafe_allow_html=True)

            # ---- DÉTAILS REPLIABLES ----
            with st.expander("Détails", expanded=False):
                # TNT (uniquement si trouvé)
                if airings:
                    txt = "TNT : " + " · ".join([f"{a['channel']} {a['start']}-{a['stop']}" for a in airings])
                    st.markdown(f"<div class='ff-muted'>{txt}</div>", unsafe_allow_html=True)

                # notes sources
                if sources:
                    st.markdown(f"<div class='ff-muted'>{sources}</div>", unsafe_allow_html=True)

                # origine + genres (texte seulement dans détails)
                origin_txt = get_origin_text(sh)
                genres_txt = get_genres_text(sh)
                meta = []
                if origin_txt:
                    meta.append(f"Origine: {origin_txt}")
                if genres_txt:
                    meta.append(f"Genres: {genres_txt}")
                if meta:
                    st.markdown(f"<div class='ff-muted'>{' · '.join(meta)}</div>", unsafe_allow_html=True)

                # synopsis
                if overview:
                    st.write(overview)

                # acteurs (très fin)
                actors = actors_from_omdb(sh)
                if actors:
                    st.markdown(f"<div class='ff-muted'>Acteurs: {actors}</div>", unsafe_allow_html=True)

                # liens streaming
                if opts_mine:
                    st.write("**Sur tes applis :**")
                    for o in opts_mine:
                        s = (o.get("service") or {})
                        name = s.get("name", s.get("id", "service"))
                        typ = o.get("type", "")
                        link = o.get("link") or o.get("videoLink")
                        if link:
                            st.markdown(f"- **{name}** ({typ}) → {link}")
                        else:
                            st.markdown(f"- **{name}** ({typ})")

                if (not opts_mine) and show_elsewhere and opts_all:
                    st.write("**Ailleurs :**")
                    for o in opts_all:
                        s = (o.get("service") or {})
                        name = s.get("name", s.get("id", "service"))
                        typ = o.get("type", "")
                        link = o.get("link") or o.get("videoLink")
                        if link:
                            st.markdown(f"- **{name}** ({typ}) → {link}")
                        else:
                            st.markdown(f"- **{name}** ({typ})")

        st.divider()