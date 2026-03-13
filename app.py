import os
import re
import json
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

RAPIDAPI_KEY = os.getenv("RAPIDAPI_KEY", "").strip()
RAPIDAPI_HOST = os.getenv("RAPIDAPI_HOST", "streaming-availability.p.rapidapi.com").strip()
BASE_URL = "https://streaming-availability.p.rapidapi.com"

OLLAMA_URL = os.getenv("OLLAMA_URL", "http://localhost:11434").strip()
OLLAMA_MODEL = os.getenv("OLLAMA_MODEL", "llama3.2:3b").strip()

OMDB_API_KEY = os.getenv("OMDB_API_KEY", "").strip()

XMLTV_TNT_URL = os.getenv("XMLTV_TNT_URL", "").strip()
TNT_LOOKAHEAD_DAYS = int(os.getenv("TNT_LOOKAHEAD_DAYS", "5"))

APP_DIR = Path(__file__).parent
PROFILE_PATH = APP_DIR / "profile.json"

st.set_page_config(page_title="FilmFinder IA", layout="centered")


# ================== THEME ==================
def apply_theme():
    css = """
    <style>
    html, body, .stApp, [data-testid="stAppViewContainer"] {
        background: #eef1f5 !important;
    }

    .main .block-container{
        max-width: 1100px !important;
        margin: 14px auto !important;
        background: rgba(255,255,255,0.94) !important;
        border-radius: 18px !important;
        padding: 18px 22px 28px 22px !important;
        box-shadow: 0 10px 35px rgba(0,0,0,0.08) !important;
        backdrop-filter: blur(3px);
    }

    [data-testid="stSidebar"] > div:first-child{
        background: rgba(255,255,255,0.96) !important;
        border-right: 1px solid rgba(0,0,0,0.06);
    }

    .main a{ color:#0b57d0 !important; font-weight:600; }
    .ff-muted{ color: rgba(0,0,0,0.68) !important; font-size: 13px; }

    .ff-panel{
        background: rgba(255,255,255,0.90);
        border: 1px solid rgba(0,0,0,0.08);
        border-radius: 16px;
        padding: 14px 16px;
        margin: 10px 0 16px 0;
        box-shadow: 0 6px 18px rgba(0,0,0,0.05);
    }

    .ff-result{
        background: rgba(255,255,255,0.94);
        border: 1px solid rgba(0,0,0,0.09);
        border-radius: 18px;
        padding: 14px 14px 10px 14px;
        margin: 14px 0 18px 0;
        box-shadow: 0 8px 20px rgba(0,0,0,0.06);
    }

    .ff-links{
        background: rgba(255,255,255,0.88);
        border: 1px solid rgba(0,0,0,0.08);
        border-radius: 12px;
        padding: 10px 12px;
        margin: 8px 0 10px 0;
    }

    .ff-meta{
        background: rgba(255,255,255,0.82);
        border: 1px solid rgba(0,0,0,0.07);
        border-radius: 12px;
        padding: 8px 10px;
        margin: 8px 0;
    }

    .ff-stars{position:relative;display:inline-block;font-size:16px;line-height:1;letter-spacing:1px}
    .ff-stars .bot{color:#d0d0d0;display:block}
    .ff-stars .top{color:#f5c518;position:absolute;left:0;top:0;overflow:hidden;white-space:nowrap;display:block}

    div[data-testid="stExpander"]{
        border-radius: 12px !important;
        border: 1px solid rgba(0,0,0,0.08) !important;
        background: rgba(255,255,255,0.88) !important;
    }
    </style>
    """
    st.markdown(css, unsafe_allow_html=True)

apply_theme()


# ================== UTILS ==================
STOPWORDS = {
    "le","la","les","un","une","des","de","du","dans","sur","avec","sans","et","ou",
    "qui","que","quoi","dont","au","aux","en","a","à","pour","par","se","sa","son","ses",
    "je","tu","il","elle","on","nous","vous","ils","elles","toujours",
    "the","a","an","and","or","in","on","with","without","to","of","for","by","from"
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

def flag_from_iso2(code2: str) -> str:
    if not code2 or len(code2) != 2:
        return ""
    code2 = code2.upper()
    if not ("A" <= code2[0] <= "Z" and "A" <= code2[1] <= "Z"):
        return ""
    return chr(0x1F1E6 + ord(code2[0]) - ord("A")) + chr(0x1F1E6 + ord(code2[1]) - ord("A"))

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


# ================== PROFILE ==================
def load_profile():
    if PROFILE_PATH.exists():
        try:
            p = json.loads(PROFILE_PATH.read_text(encoding="utf-8"))
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
        "show_type": "movie",
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
    prompt = f"""
Réponds UNIQUEMENT avec un JSON valide:
{{"titles":[...], "queries":[...]}}

Règles:
- Si tu reconnais le titre exact, mets-le en PREMIER dans "titles".
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
        timeout=70,
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


# ================== OMDb ==================
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

def country_from_omdb(show: dict) -> str:
    imdb_id = show.get("imdbId") or show.get("imdbID") or None
    data = omdb_fetch(imdb_id) if imdb_id else None
    if not data:
        return ""
    c = data.get("Country")
    if isinstance(c, str) and c.strip() and c.strip().upper() != "N/A":
        return c.strip()
    return ""


# ================== TNT ==================
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
    content = None
    used_url = None
    last_err = None

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
                matches += idx.get(ck