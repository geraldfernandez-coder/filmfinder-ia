import os
import re
import json
import random
import gzip
import io
import difflib
from datetime import datetime, timedelta, timezone
import xml.etree.ElementTree as ET

import requests
import streamlit as st
from dotenv import load_dotenv

# ================== CONFIG ==================
load_dotenv()

# Streaming Availability (RapidAPI)
RAPIDAPI_KEY = os.getenv("RAPIDAPI_KEY", "").strip()
RAPIDAPI_HOST = os.getenv("RAPIDAPI_HOST", "streaming-availability.p.rapidapi.com").strip()
BASE_URL = "https://streaming-availability.p.rapidapi.com"

# IA locale (Ollama)
OLLAMA_URL = os.getenv("OLLAMA_URL", "http://localhost:11434").strip()
OLLAMA_MODEL = os.getenv("OLLAMA_MODEL", "llama3.2:3b").strip()

# Notes critiques (optionnel)
OMDB_API_KEY = os.getenv("OMDB_API_KEY", "").strip()

# TNT (XMLTVFr) - optionnel
XMLTV_TNT_URL = os.getenv("XMLTV_TNT_URL", "").strip()
TNT_LOOKAHEAD_DAYS = int(os.getenv("TNT_LOOKAHEAD_DAYS", "5"))

APP_DIR = os.path.dirname(os.path.abspath(__file__))
PROFILE_PATH = os.path.join(APP_DIR, "profile.json")

st.set_page_config(page_title="FilmFinder IA", layout="centered")


# ================== THEME ==================
def apply_theme() -> None:
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
    .ff-muted{ color: rgba(0,0,0,0.65) !important; }
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
    """5 étoiles avec remplissage proportionnel."""
    if score_0_100 is None:
        return ""
    try:
        s = float(score_0_100)
    except Exception:
        return ""
    s = max(0.0, min(100.0, s))
    pct = s
    return f"""
    <span style="
        font-size:16px;
        font-weight:700;
        background: linear-gradient(90deg, #f5c518 {pct}%, #d0d0d0 {pct}%);
        -webkit-background-clip: text;
        color: transparent;
        letter-spacing: 1px;
        white-space: nowrap;
    ">★★★★★</span>
    """


# ================== PROFILE ==================
def load_profile():
    if os.path.exists(PROFILE_PATH):
        try:
            with open(PROFILE_PATH, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            pass
    return {
        "pseudo": "",
        "country": "fr",
        "lang": "fr",
        "show_type": "all",
        "platform_ids": [],
        "show_elsewhere": False,
    }


def save_profile(p) -> None:
    with open(PROFILE_PATH, "w", encoding="utf-8") as f:
        json.dump(p, f, ensure_ascii=False, indent=2)


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
            "options": {"temperature": 0.2, "num_predict": 220},
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
        raise RuntimeError(f"API ERROR {r.status_code}: {r.text[:400]}")
    return r.json()


@st.cache_data(show_spinner=False, ttl=3600)
def get_services(country: str, lang: str):
    data = sa_get(f"/countries/{country}", {"output_language": lang})
    return data.get("services", []) or []


@st.cache_data(show_spinner=False, ttl=300)
def api_healthcheck():
    try:
        _ = sa_get("/countries/fr", {"output_language": "fr"})
        return True, "API OK"
    except Exception as e:
        return False, str(e)


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


# ================== OMDb (notes critiques) ==================
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
    Retour:
      score_0_100 (float or None),
      sources_str (ex: "IMDb 8.2/10 · Meta 74/100 · RT 93%")
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


# ================== SEARCH ==================
def score_relevance(sh, qtext):
    t = ((sh.get("title") or "") + " " + (sh.get("overview") or "")).lower()
    words = [w for w in re.findall(r"[a-zA-ZÀ-ÿ0-9']+", qtext.lower()) if len(w) >= 4]
    return sum(1 for w in set(words) if w in t)


def merge_results(items):
    merged = {}
    for sh in items:
        merged[stable_id(sh)] = sh
    return list(merged.values())


def search_by_title(title: str, country: str, show_type: str, lang: str):
    type_param = None if show_type == "all" else show_type
    data = sa_get("/shows/search/title", {
        "title": title,
        "country": country,
        "show_type": type_param,
        "series_granularity": "show",
        "output_language": lang,
    })
    return data if isinstance(data, list) else []


def search_by_keyword(keyword: str, country: str, show_type: str, lang: str):
    type_param = None if show_type == "all" else show_type
    res = sa_get("/shows/search/filters", {
        "country": country,
        "show_type": type_param,
        "keyword": keyword,
        "series_granularity": "show",
        "output_language": lang,
    })
    return res.get("shows", []) if isinstance(res, dict) else []


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


# ================== STATE / MENU ==================
st.session_state.setdefault("entered", False)
st.session_state.setdefault("page", "Accueil")
st.session_state.setdefault("do_search", False)
st.session_state.setdefault("last_results", None)
st.session_state.setdefault("last_query", "")
st.session_state.setdefault("last_errors", [])

with st.sidebar:
    ok, msg = api_healthcheck()
    st.markdown("## FilmFinder IA")
    st.caption("✅ " + msg if ok else "❌ " + msg)
    st.caption("IA locale: " + ("ON" if ollama_is_up() else "OFF"))
    st.caption("Notes critiques: " + ("ON" if OMDB_API_KEY else "OFF"))
    if st.session_state["entered"]:
        st.radio("Menu", ["Recherche", "Profil"], key="page")
    else:
        st.caption("Accueil (début uniquement)")

# ================== ACCUEIL ==================
if st.session_state["page"] == "Accueil":
    st.markdown("# FilmFinder IA")
    st.markdown('<div class="ff-card">', unsafe_allow_html=True)
    st.markdown("### Inscription rapide")

    if not RAPIDAPI_KEY:
        st.error("RAPIDAPI_KEY manquante dans .env (RapidAPI).")
        st.stop()

    with st.form("signup_form"):
        pseudo = st.text_input("Pseudo (optionnel)", value=profile.get("pseudo", ""))

        col1, col2, col3 = st.columns(3)
        with col1:
            country = st.selectbox("Pays", ["fr","be","ch","gb","us"], index=["fr","be","ch","gb","us"].index(profile.get("country","fr")))
        with col2:
            lang = st.selectbox("Langue", ["fr","en"], index=["fr","en"].index(profile.get("lang","fr")))
        with col3:
            show_type = st.selectbox("Type", ["all","movie","series"], index=["all","movie","series"].index(profile.get("show_type","all")))

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

        show_elsewhere = st.checkbox("Si pas dispo sur mes applis, montrer ailleurs", value=bool(profile.get("show_elsewhere", False)))

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
                "show_type": show_type,
                "platform_ids": platform_ids,
                "show_elsewhere": show_elsewhere,
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

        col1, col2, col3 = st.columns(3)
        with col1:
            country = st.selectbox("Pays", ["fr","be","ch","gb","us"], index=["fr","be","ch","gb","us"].index(profile.get("country","fr")))
        with col2:
            lang = st.selectbox("Langue", ["fr","en"], index=["fr","en"].index(profile.get("lang","fr")))
        with col3:
            show_type = st.selectbox("Type", ["all","movie","series"], index=["all","movie","series"].index(profile.get("show_type","all")))

        services = get_services(country, lang)
        name_to_id = {(s.get("name") or s.get("id")): s.get("id") for s in services if (s.get("name") or s.get("id")) and s.get("id")}
        id_to_name = {v: k for k, v in name_to_id.items()}

        default_names = [id_to_name[i] for i in profile.get("platform_ids", []) if i in id_to_name]
        chosen_names = st.multiselect("Tes plateformes", options=sorted(name_to_id.keys()), default=sorted(set(default_names)))
        platform_ids = [name_to_id[n] for n in chosen_names]

        show_elsewhere = st.checkbox("Si pas dispo sur mes applis, montrer ailleurs", value=bool(profile.get("show_elsewhere", False)))

        ok_btn = st.form_submit_button("✅ Enregistrer")

    if ok_btn:
        if not platform_ids:
            st.warning("Coche au moins 1 plateforme 🙂")
        else:
            profile = {
                "pseudo": pseudo.strip(),
                "country": country,
                "lang": lang,
                "show_type": show_type,
                "platform_ids": platform_ids,
                "show_elsewhere": show_elsewhere,
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

mode = st.radio("Mode", ["Rapide", "Normal", "Profond"], horizontal=True)
preset = MODE_PRESETS[mode]

def trigger_search():
    st.session_state["do_search"] = True

q_main = st.text_input("Ton souvenir (Entrée lance)", key="q_main", on_change=trigger_search)
q_more = st.text_area("Détails (optionnel)", key="q_more", height=80)
if st.button("Trouver"):
    st.session_state["do_search"] = True

if st.session_state["do_search"]:
    st.session_state["do_search"] = False
    q = (q_main.strip() + " " + q_more.strip()).strip()
    if not q:
        st.warning("Écris au moins une phrase 🙂")
        st.stop()

    country = profile["country"]
    lang = profile["lang"]
    show_type = profile["show_type"]

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

    q_seen = []
    for x in queries:
        x = x.strip()
        if x and x not in q_seen:
            q_seen.append(x)
    queries = q_seen

    found = []

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

    if len(found) < preset["en_if_under"]:
        for kw in queries[:preset["queries_max"]]:
            try:
                found += search_by_keyword(kw, country, show_type, "en")
            except Exception as e:
                errors.append(str(e))

    found = merge_results(found)
    found.sort(key=lambda sh: score_relevance(sh, q), reverse=True)
    found = found[:preset["pool"]]

    st.session_state["last_results"] = found
    st.session_state["last_query"] = q
    st.session_state["last_errors"] = errors
    st.session_state["last_mode"] = mode

results = st.session_state.get("last_results")
if results is not None:
    q = st.session_state.get("last_query", "")
    errors = st.session_state.get("last_errors", [])
    mode_used = st.session_state.get("last_mode", mode)

    if errors:
        st.warning("⚠️ Debug :\n- " + "\n- ".join(errors[:2]))

    st.caption(f"Requête: {q} — Mode: {mode_used}")

    sort_mode = st.selectbox("Trier par", ["Pertinence", "Année (récent)", "Note (haute)"], index=0)
    tnt_auto = st.checkbox("TNT automatique (affiche seulement si trouvé)", value=False)

    enriched = []
    for i, sh in enumerate(results):
        year = sh.get("releaseYear") or sh.get("firstAirYear") or 0
        try:
            year = int(year) if year else 0
        except Exception:
            year = 0

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

    for sh, year, score100, sources in enriched[:20]:
        title = sh.get("title", "Sans titre")
        overview = sh.get("overview", "")
        poster = get_poster_url(sh)

        title_variants = [title]
        if sh.get("originalTitle"):
            title_variants.append(sh["originalTitle"])

        c_img, c_txt = st.columns([1, 3])
        with c_img:
            if poster:
                st.image(poster, width=140)

        with c_txt:
            top_line = f"### {title} ({year if year else ''})"
            star = stars_html(score100)
            if star:
                top_line += f" — {star}"
            st.markdown(top_line, unsafe_allow_html=True)

            if sources:
                st.markdown(f"<div class='ff-muted'>{sources}</div>", unsafe_allow_html=True)

            if tnt_auto:
                airings = tnt_find_airings(title_variants, limit=2)
                if airings:
                    txt = "TNT : " + " · ".join([f"{a['channel']} {a['start']}-{a['stop']}" for a in airings])
                    st.markdown(f"<div class='ff-muted'>{txt}</div>", unsafe_allow_html=True)

            if overview:
                st.write(overview)

            opts_all = ((sh.get("streamingOptions") or {}).get(country) or [])
            opts_all = dedupe_streaming_options(opts_all)

            opts_mine = [o for o in opts_all if ((o.get("service") or {}).get("id") in allowed_services)]
            opts_mine = dedupe_streaming_options(opts_mine)

            if opts_mine:
                st.write("Dispo sur tes applis :")
                for o in opts_mine:
                    s = (o.get("service") or {})
                    name = s.get("name", s.get("id", "service"))
                    typ = o.get("type", "")
                    link = o.get("link") or o.get("videoLink")
                    if link:
                        st.markdown(f"- **{name}** ({typ}) → {link}")
                    else:
                        st.markdown(f"- **{name}** ({typ})")
            else:
                if show_elsewhere and opts_all:
                    st.write("Dispo ailleurs :")
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
