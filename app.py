import os
import re
import json
import gzip
import io
import difflib
from datetime import datetime, timedelta, timezone
from pathlib import Path
from urllib.parse import quote
import html
import base64
import random
import streamlit.components.v1 as components
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
BG_DIR = APP_DIR / "bg"

def list_bg_files():
    if not BG_DIR.exists():
        return []
    return [p for p in BG_DIR.iterdir() if p.is_file() and p.suffix.lower() in {".jpg", ".jpeg", ".png", ".webp"}]

def pick_bg_file():
    files = list_bg_files()
    if not files:
        return None
    current = st.session_state.get("_bg_file")
    if current:
        p = Path(current)
        if p.exists():
            return p
    chosen = random.choice(files)
    st.session_state["_bg_file"] = str(chosen)
    return chosen

def bg_data_uri():
    p = pick_bg_file()
    if not p:
        return ""
    try:
        mime = "image/jpeg"
        if p.suffix.lower() == ".png":
            mime = "image/png"
        elif p.suffix.lower() == ".webp":
            mime = "image/webp"
        data = base64.b64encode(p.read_bytes()).decode("ascii")
        return f"data:{mime};base64,{data}"
    except Exception:
        return ""

def apply_theme():
    bg_uri = bg_data_uri()
    bg_css = f"background-image: linear-gradient(rgba(238,241,245,0.72), rgba(238,241,245,0.72)), url('{bg_uri}');" if bg_uri else "background:#eef1f5;"
    css = f"""
    <style>
    html, body, .stApp, [data-testid="stAppViewContainer"] {{
        {bg_css}
        background-size: cover !important;
        background-position: center center !important;
        background-attachment: fixed !important;
    }}

    .main .block-container {{
        max-width: 1120px !important;
        margin: 8px auto !important;
        background: transparent !important;
        padding: 10px 12px 24px 12px !important;
        box-shadow: none !important;
    }}

    [data-testid="stSidebar"] > div:first-child {{
        background: rgba(255,255,255,0.90) !important;
        border-right: 1px solid rgba(0,0,0,0.06);
        backdrop-filter: blur(8px);
    }}

    .ff-shell-title {{
        background: rgba(255,255,255,0.90);
        border: 1px solid rgba(0,0,0,0.08);
        border-radius: 24px;
        padding: 18px 22px;
        margin: 0 0 12px 0;
        box-shadow: 0 8px 24px rgba(0,0,0,0.06);
        backdrop-filter: blur(7px);
    }}

    .ff-bubble {{
        background: rgba(255,255,255,0.92);
        border: 1px solid rgba(0,0,0,0.08);
        border-radius: 24px;
        padding: 14px 16px;
        margin: 0 0 12px 0;
        box-shadow: 0 8px 24px rgba(0,0,0,0.06);
        backdrop-filter: blur(7px);
    }}

    .ff-search-shell {{
        padding: 14px 14px 10px 14px;
    }}

    .ff-subtle {{
        background: rgba(255,255,255,0.82);
    }}

    .ff-field-label {{
        font-size: 0.98rem;
        font-weight: 600;
        margin: 0 0 4px 2px;
        color: #1f2a44;
    }}

    .ff-muted {{
        color: rgba(0,0,0,0.68) !important;
        font-size: 13px;
    }}

    .ff-meta {{
        background: rgba(255,255,255,0.86);
        border: 1px solid rgba(0,0,0,0.07);
        border-radius: 16px;
        padding: 9px 12px;
        margin: 8px 0;
    }}

    .ff-links {{
        background: rgba(255,255,255,0.86);
        border: 1px solid rgba(0,0,0,0.07);
        border-radius: 16px;
        padding: 9px 12px;
        margin: 8px 0;
    }}

    .ff-linkline {{
        margin: 2px 0;
        font-size: 0.96rem;
    }}

    .ff-inline-actors a {{
        color:#0b57d0 !important;
        text-decoration:none;
        font-weight:600;
    }}
    .ff-inline-actors a:hover {{
        text-decoration:underline;
    }}

    .ff-stars{{position:relative;display:inline-block;font-size:16px;line-height:1;letter-spacing:1px}}
    .ff-stars .bot{{color:#d0d0d0;display:block}}
    .ff-stars .top{{color:#f5c518;position:absolute;left:0;top:0;overflow:hidden;white-space:nowrap;display:block}}

    div[data-testid="stExpander"] {{
        border-radius: 18px !important;
        border: 1px solid rgba(0,0,0,0.08) !important;
        background: rgba(255,255,255,0.82) !important;
        margin-top: 6px !important;
    }}

    .stTextInput > div > div,
    .stSelectbox > div > div,
    .stMultiSelect > div > div {{
        background: rgba(255,255,255,0.98) !important;
        border-radius: 18px !important;
        border: 1px solid rgba(0,0,0,0.08) !important;
        min-height: 3rem !important;
    }}

    .stTextArea textarea {{
        background: rgba(255,255,255,0.98) !important;
        border-radius: 18px !important;
        border: 1px solid rgba(0,0,0,0.08) !important;
        min-height: 92px !important;
    }}

    .stButton > button {{
        border-radius: 18px !important;
        border: 1px solid rgba(0,0,0,0.10) !important;
        background: rgba(255,255,255,0.98) !important;
        box-shadow: none !important;
    }}

    .ff-clear-col .stButton > button {{
        min-height: 46px !important;
        width: 46px !important;
        padding: 0 !important;
        font-size: 1.25rem !important;
    }}

    .ff-find-col .stButton > button {{
        min-height: 46px !important;
        font-weight: 700 !important;
    }}

    .ff-result-wrap {{
        margin-bottom: 16px;
    }}

    .ff-poster {{
        margin-top: 6px;
    }}

    .ff-result-bubble {{
        background: rgba(255,255,255,0.94);
        border: 1px solid rgba(0,0,0,0.08);
        border-radius: 26px;
        padding: 14px 16px 12px 16px;
        box-shadow: 0 10px 28px rgba(0,0,0,0.07);
        backdrop-filter: blur(8px);
    }}

    .ff-pill-ok {{
        color: #0d652d;
        font-weight: 700;
    }}

    .ff-pill-no {{
        color: #a61b34;
        font-weight: 700;
    }}

    .stMarkdown p {{
        margin-bottom: 0.35rem !important;
    }}

    .stRadio > div {{
        gap: 0.75rem !important;
    }}

    
    .ff-bubble, .ff-result-bubble, .ff-shell-title {{
        border-radius: 30px;
        box-shadow: 0 14px 34px rgba(0,0,0,0.08);
    }}
    .ff-result-bubble {{
        padding: 16px 18px 14px 18px;
    }}
    .stButton > button {{
        border-radius: 999px !important;
    }}
    

    @media (max-width: 768px) {{
        .main .block-container {{
            padding: 8px 8px 20px 8px !important;
        }}
        .ff-shell-title {{
            border-radius: 20px;
            padding: 14px 16px;
        }}
        .ff-bubble {{
            border-radius: 20px;
            padding: 12px 12px;
        }}
        .ff-result-bubble {{
            border-radius: 22px;
            padding: 12px 12px 10px 12px;
        }}
        .ff-clear-col .stButton > button {{
            min-height: 42px !important;
            width: 42px !important;
        }}
    }}
    </style>
    """
    st.markdown(css, unsafe_allow_html=True)

apply_theme()

def normalize_service_name(name: str) -> str:
    s = norm_text(name or "")
    s = s.replace("+", " plus ")
    s = re.sub(r"\s+", " ", s).strip()
    aliases = {
        "hbo max": "max",
        "max": "max",
        "prime video": "prime video",
        "amazon prime video": "prime video",
        "prime subscription": "prime video",
        "disney plus": "disney plus",
        "disney+": "disney plus",
        "apple tv plus": "apple tv plus",
        "appletv+": "apple tv plus",
        "canal+": "canal plus",
        "canal plus": "canal plus",
    }
    return aliases.get(s, s)

def profile_platform_name_norms(profile: dict):
    country = profile.get("country", "fr")
    lang = profile.get("lang", "fr")
    out = set()
    try:
        services = get_services(country, lang)
        id_to_name = {}
        for s in services:
            sid = s.get("id")
            sname = s.get("name") or sid
            if sid:
                id_to_name[sid] = sname
        for sid in profile.get("platform_ids", []):
            if sid in id_to_name:
                out.add(normalize_service_name(id_to_name[sid]))
    except Exception:
        pass
    return out

def service_option_matches(opt: dict, allowed_services: set, platform_name_norms: set) -> bool:
    service = opt.get("service") or {}
    sid = service.get("id")
    sname = service.get("name") or sid or ""
    if sid in allowed_services:
        return True
    return normalize_service_name(sname) in platform_name_norms

def actor_links_html(actors):
    parts = []
    for a in actors[:8]:
        url = f"?actor={quote(a)}"
        parts.append(f"<a href='{url}' target='_self'>{html.escape(a)}</a>")
    return ", ".join(parts)

def run_scroll_to_results():
    components.html(
        """
        <script>
        setTimeout(function() {
            try {
                const doc = window.parent.document;
                const el = doc.getElementById("ff-results-anchor");
                if (doc && doc.activeElement && typeof doc.activeElement.blur === "function") {
                    doc.activeElement.blur();
                }
                if (el) {
                    el.scrollIntoView({behavior: "smooth", block: "start"});
                }
            } catch (e) {}
        }, 220);
        </script>
        """,
        height=0,
    )


# ================== UTILS ==================
STOPWORDS = {
    "le","la","les","un","une","des","de","du","dans","sur","avec","sans","et","ou",
    "qui","que","quoi","dont","au","aux","en","a","à","pour","par","se","sa","son","ses",
    "je","tu","il","elle","on","nous","vous","ils","elles","toujours",
    "the","a","an","and","or","in","on","with","without","to","of","for","by","from"
}

GENRE_CHOICES = [
    "Action","Aventure","Animation","Comédie","Crime","Documentaire","Drame",
    "Famille","Fantasy","Horreur","Mystère","Romance","Science-fiction",
    "Thriller","Guerre","Western"
]

YEAR_FILTERS = {
    "2020-2025": (2020, 2025),
    "2010-2019": (2010, 2019),
    "2000-2009": (2000, 2009),
    "1990-1999": (1990, 1999),
    "1980-1989": (1980, 1989),
    "Avant 1980": (1900, 1979),
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
def merge_results(items):
    merged = {}
    for sh in items:
        merged[stable_id(sh)] = sh
    return list(merged.values())

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

def heuristic_titles_from_query(q: str):
    nq = norm_text(q)
    titles = []
    time_loop = any(x in nq for x in ["boucle", "revit", "revivre", "meme journee", "même journée", "rena", "ressusc", "time loop", "loop"])
    tom = "tom cruise" in nq
    alien = any(x in nq for x in ["extraterrestre", "alien"])
    if time_loop:
        titles += ["Edge of Tomorrow", "Un jour sans fin", "Happy Death Day", "Palm Springs"]
    if tom:
        titles.insert(0, "Edge of Tomorrow")
        titles += ["Live Die Repeat"]
    if alien and time_loop and "Edge of Tomorrow" not in titles:
        titles.insert(0, "Edge of Tomorrow")
    out = []
    for t in titles:
        if t not in out:
            out.append(t)
    return out

def relevance_score(sh: dict, q: str, actor_hint: str = "") -> float:
    hay = norm_text((sh.get("title") or "") + " " + (sh.get("overview") or ""))
    qn = norm_text(q)

    words = [w for w in qn.split() if len(w) >= 4 and w not in STOPWORDS]
    score = 0.0
    for w in set(words):
        if w in hay:
            score += 1.0

    if any(x in qn for x in ["boucle", "revit", "revivre", "meme journee", "même journée", "ressusc", "rena"]):
        if any(x in hay for x in ["loop", "time loop", "revit", "revivre", "ressusc", "rena", "day repeats", "repeat the day"]):
            score += 3.0

    if any(x in qn for x in ["extraterrestre", "alien"]):
        if any(x in hay for x in ["alien", "extraterrestre", "invasion", "space", "military operation against aliens"]):
            score += 2.2

    if actor_hint:
        actors = " ".join([norm_text(a) for a in actors_list_from_omdb(sh)])
        if actor_hint in actors:
            score += 4.0

    title_n = norm_text(sh.get("title", ""))
    if "edge of tomorrow" in title_n or "live die repeat" in title_n:
        if any(x in qn for x in ["tom cruise", "extraterrestre", "revit", "rena", "ressusc", "journee", "journée", "loop"]):
            score += 4.0

    return score

def genre_match(show, selected_genres):
    if not selected_genres:
        return True
    txt = norm_text(json.dumps(show.get("genres", ""), ensure_ascii=False))
    title_overview = norm_text((show.get("title") or "") + " " + (show.get("overview") or ""))
    hay = txt + " " + title_overview

    mapping = {
        "Science-fiction": ["science fiction", "science-fiction", "sci-fi", "scifi"],
        "Comédie": ["comedie", "comédie", "comedy"],
        "Drame": ["drame", "drama"],
        "Horreur": ["horreur", "horror"],
        "Aventure": ["aventure", "adventure"],
        "Mystère": ["mystere", "mystère", "mystery"],
    }

    for g in selected_genres:
        toks = mapping.get(g, [norm_text(g)])
        if any(tok in hay for tok in toks):
            return True
    return False

def year_match(year_value, selected_year_ranges):
    if not selected_year_ranges:
        return True
    try:
        y = int(year_value)
    except Exception:
        return False
    for start, end in selected_year_ranges:
        if start <= y <= end:
            return True
    return False

# ================== STATE ==================
st.session_state.setdefault("entered", False)
st.session_state.setdefault("page", "Accueil")
st.session_state.setdefault("do_search", False)
st.session_state.setdefault("last_results", None)
st.session_state.setdefault("last_query", "")
st.session_state.setdefault("last_mode", "Normal")
st.session_state.setdefault("actor_search", "")
st.session_state.setdefault("sort_mode", "Pertinence")
st.session_state.setdefault("scroll_to_results", False)
st.session_state.setdefault("_last_actor_qp", "")

incoming_actor_qp = st.query_params.get("actor", "")
if incoming_actor_qp:
    if incoming_actor_qp != st.session_state.get("_last_actor_qp", ""):
        st.session_state["_last_actor_qp"] = incoming_actor_qp
        st.session_state["actor_search"] = incoming_actor_qp
        st.session_state["do_search"] = True
else:
    st.session_state["_last_actor_qp"] = ""

# ================== SIDEBAR ==================
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

    if not RAPIDAPI_KEY:
        st.error("RAPIDAPI_KEY manquante dans .env (RapidAPI).")
        st.stop()

    with st.form("signup_form"):
        c1, c2, c3, c4 = st.columns(4)
        with c1:
            country = st.selectbox("Pays", ["fr", "be", "ch", "gb", "us"], index=["fr","be","ch","gb","us"].index(profile.get("country","fr")))
        with c2:
            lang = st.selectbox("Langue", ["fr", "en"], index=["fr","en"].index(profile.get("lang","fr")))
        with c3:
            typ = st.selectbox("Type", ["Film", "Série"], index=0 if profile.get("show_type","movie")=="movie" else 1)
        with c4:
            show_elsewhere = st.checkbox("Ailleurs", value=bool(profile.get("show_elsewhere", False)))

        services = get_services(country, lang)
        name_to_id = {(s.get("name") or s.get("id")): s.get("id") for s in services if (s.get("name") or s.get("id")) and s.get("id")}
        id_to_name = {v: k for k, v in name_to_id.items()}
        default_names = [id_to_name[i] for i in profile.get("platform_ids", []) if i in id_to_name]
        chosen_names = st.multiselect("Tes plateformes", options=sorted(name_to_id.keys()), default=sorted(set(default_names)))
        platform_ids = [name_to_id[n] for n in chosen_names]

        enter_btn = st.form_submit_button("Entrer")

    if enter_btn:
        if not platform_ids:
            st.warning("Coche au moins 1 plateforme 🙂")
        else:
            profile = {
                "pseudo": "",
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
    st.markdown("## Profil")

    with st.form("profile_form"):
        c1, c2, c3, c4 = st.columns(4)
        with c1:
            country = st.selectbox("Pays", ["fr", "be", "ch", "gb", "us"], index=["fr","be","ch","gb","us"].index(profile.get("country","fr")))
        with c2:
            lang = st.selectbox("Langue", ["fr", "en"], index=["fr","en"].index(profile.get("lang","fr")))
        with c3:
            typ = st.selectbox("Type", ["Film", "Série"], index=0 if profile.get("show_type","movie")=="movie" else 1)
        with c4:
            show_elsewhere = st.checkbox("Ailleurs", value=bool(profile.get("show_elsewhere", False)))

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
                "pseudo": "",
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
st.markdown("<div class='ff-shell-title'><h1>Recherche</h1><p>Souvenir flou → titres probables → où regarder.</p></div>", unsafe_allow_html=True)

if not profile.get("platform_ids"):
    st.warning("Crée ton profil avant de chercher.")
    st.stop()

MODE_PRESETS = {
    "Rapide":  {"titles_max": 2, "queries_max": 2, "en_if_under": 6,  "pool": 40,  "omdb_top": 12},
    "Normal":  {"titles_max": 4, "queries_max": 4, "en_if_under": 8,  "pool": 70,  "omdb_top": 18},
    "Profond": {"titles_max": 7, "queries_max": 7, "en_if_under": 999, "pool": 120, "omdb_top": 25},
}

st.markdown("<div class='ff-bubble ff-search-shell'>", unsafe_allow_html=True)

st.markdown("<div class='ff-field-label'>Mode</div>", unsafe_allow_html=True)
mode = st.radio("Mode", ["Rapide", "Normal", "Profond"], horizontal=True, index=1, label_visibility="collapsed")
preset = MODE_PRESETS[mode]

if st.session_state.get("actor_search"):
    actor = st.session_state["actor_search"]
    st.markdown(f"<div class='ff-meta ff-inline-actors'>Recherche acteur : <b>{html.escape(actor)}</b> — recherche automatique lancée.</div>", unsafe_allow_html=True)
    st.session_state["sort_mode"] = "Note (haute)"
    if st.button("⬅️ Retour recherche normale", key="back_normal_search"):
        st.session_state["actor_search"] = ""
        st.session_state["last_results"] = None
        st.query_params.clear()
        st.rerun()

def trigger_search():
    st.session_state["do_search"] = True

selected_genres = []
selected_year_ranges = []

st.markdown("<div class='ff-field-label'>Ton souvenir (Entrée lance)</div>", unsafe_allow_html=True)
r1c1, r1c2, r1c3 = st.columns([12, 1, 3], vertical_alignment="bottom")
with r1c1:
    q_main = st.text_input(
        "Ton souvenir (Entrée lance)",
        key="q_main",
        label_visibility="collapsed",
        on_change=trigger_search,
        placeholder="Ex: homme extraterrestre renaît"
    )
with r1c2:
    st.markdown("<div class='ff-clear-col'>", unsafe_allow_html=True)
    if st.button("✕", key="clear_q_main"):
        st.session_state["q_main"] = ""
        st.rerun()
    st.markdown("</div>", unsafe_allow_html=True)
with r1c3:
    st.markdown("<div class='ff-find-col'>", unsafe_allow_html=True)
    if st.button("Trouver", key="find_button_main", type="primary"):
        st.session_state["do_search"] = True
    st.markdown("</div>", unsafe_allow_html=True)

st.markdown("<div class='ff-field-label'>Détails (optionnel)</div>", unsafe_allow_html=True)
r2c1, r2c2 = st.columns([12, 1], vertical_alignment="bottom")
with r2c1:
    q_more = st.text_input(
        "Détails (optionnel)",
        key="q_more",
        label_visibility="collapsed",
        on_change=trigger_search,
        placeholder="Acteur/actrice · année approx · pays · plateforme · scène marquante · ambiance · SF/space…"
    )
with r2c2:
    st.markdown("<div class='ff-clear-col'>", unsafe_allow_html=True)
    if st.button("✕", key="clear_q_more"):
        st.session_state["q_more"] = ""
        st.rerun()
    st.markdown("</div>", unsafe_allow_html=True)

with st.expander("Filtres", expanded=False):
    col_left, col_right = st.columns(2)

    with col_left:
        st.markdown("**Genres**")
        for g in GENRE_CHOICES:
            if st.checkbox(g, key=f"genre_{g}"):
                selected_genres.append(g)

    with col_right:
        st.markdown("**Années**")
        for label, yr in YEAR_FILTERS.items():
            if st.checkbox(label, key=f"year_{label}"):
                selected_year_ranges.append(yr)

st.markdown("</div>", unsafe_allow_html=True)

st.markdown("<div class='ff-bubble ff-subtle'>", unsafe_allow_html=True)
sort_mode = st.selectbox(
    "Trier par",
    ["Pertinence", "Année (récent)", "Note (haute)"],
    index=["Pertinence", "Année (récent)", "Note (haute)"].index(st.session_state.get("sort_mode", "Pertinence"))
)
st.session_state["sort_mode"] = sort_mode

only_my_apps = st.checkbox("Uniquement sur mes applis", value=False)
st.markdown("</div>", unsafe_allow_html=True)

# recherche
if st.session_state["do_search"]:
    st.session_state["do_search"] = False

    country = profile["country"]
    lang = profile["lang"]
    show_type = profile["show_type"]

    if st.session_state.get("actor_search"):
        show_type = "movie"

    q = (st.session_state.get("q_main", "").strip() + " " + st.session_state.get("q_more", "").strip()).strip()
    if st.session_state.get("actor_search"):
        q = st.session_state["actor_search"].strip()

    if not q:
        st.warning("Écris au moins une phrase 🙂")
        st.stop()

    titles = heuristic_titles_from_query(q)
    queries = []

    if ollama_is_up() and not st.session_state.get("actor_search"):
        try:
            pack = ollama_pack(q)
            titles += pack.get("titles", []) or []
            queries = pack.get("queries", []) or []
        except Exception:
            pass

    if not queries:
        queries = [extract_keywords(q), q]

    qn = norm_text(q)
    actor_hint = ""
    if "tom cruise" in qn:
        actor_hint = "tom cruise"
    else:
        bigrams = re.findall(r"[a-z]+ [a-z]+", qn)
        if bigrams:
            actor_hint = bigrams[0]

    titles = [x for i, x in enumerate(titles) if x and x not in titles[:i]]
    queries = [x for i, x in enumerate(queries) if x and x not in queries[:i]]

    found = []

    for t in titles[:preset["titles_max"]]:
        try:
            found += search_by_title(t, country, show_type, lang)
        except Exception:
            pass

    for kw in queries[:preset["queries_max"]]:
        try:
            found += search_by_keyword(kw, country, show_type, lang)
        except Exception:
            pass

    if (not st.session_state.get("actor_search")) and len(found) < preset["en_if_under"]:
        for kw in queries[:preset["queries_max"]]:
            try:
                found += search_by_keyword(kw, country, show_type, "en")
            except Exception:
                pass

    found = merge_results(found)

    allowed_services = set(profile.get("platform_ids", []))
    platform_name_norms = profile_platform_name_norms(profile)
    enriched = []

    for i, sh in enumerate(found):
        opts_all = ((sh.get("streamingOptions") or {}).get(country) or [])
        opts_all = dedupe_streaming_options(opts_all)
        opts_mine = [o for o in opts_all if service_option_matches(o, allowed_services, platform_name_norms)]
        opts_mine = dedupe_streaming_options(opts_mine)
        is_mine = 1 if opts_mine else 0

        rel = relevance_score(sh, q, actor_hint=actor_hint)
        rel += 0.30 * is_mine

        year = sh.get("releaseYear") or sh.get("firstAirYear") or 0
        try:
            year = int(year) if year else 0
        except Exception:
            year = 0

        score100 = None
        sources = ""
        if i < preset["omdb_top"]:
            score100, sources = critic_score_and_sources(sh)
        else:
            if isinstance(sh.get("rating"), (int, float)):
                score100 = float(sh["rating"])
                sources = f"Score {int(score100)}/100"

        enriched.append({
            "show": sh,
            "rel": rel,
            "year": year,
            "score100": score100,
            "sources": sources,
            "is_mine": is_mine,
        })

    # filtres genres + années
    if selected_genres:
        keep = [x for x in enriched if genre_match(x["show"], selected_genres)]
        enriched = keep if keep else enriched

    if selected_year_ranges:
        keep = [x for x in enriched if year_match(x["year"], selected_year_ranges)]
        enriched = keep if keep else enriched

    if only_my_apps:
        keep = [x for x in enriched if x["is_mine"] == 1]
        enriched = keep if keep else enriched

    if sort_mode == "Pertinence":
        enriched.sort(key=lambda x: (x["rel"], x["is_mine"]), reverse=True)
    elif sort_mode == "Année (récent)":
        enriched.sort(key=lambda x: (x["year"], x["is_mine"]), reverse=True)
    else:
        enriched.sort(key=lambda x: ((x["score100"] is not None), (x["score100"] or -1), x["is_mine"]), reverse=True)

    st.session_state["last_results"] = enriched[:preset["pool"]]
    st.session_state["last_query"] = q
    st.session_state["last_mode"] = mode
    st.session_state["scroll_to_results"] = True

    st.markdown("""
    <script>
    setTimeout(() => {
        try {
            if (document.activeElement) { document.activeElement.blur(); }
            const el = document.getElementById('ff-results-anchor');
            if (el) { el.scrollIntoView({behavior:'smooth', block:'start'}); }
        } catch(e) {}
    }, 100);
    </script>
    """, unsafe_allow_html=True)


# affichage
results = st.session_state.get("last_results")
if results is not None:
    st.markdown("<div id='ff-results-anchor'></div>", unsafe_allow_html=True)
    if st.session_state.get("scroll_to_results"):
        run_scroll_to_results()
        st.session_state["scroll_to_results"] = False

    st.markdown(
        f"<div class='ff-bubble ff-subtle'><div class='ff-muted'>Requête : {html.escape(st.session_state.get('last_query',''))} — Mode : {html.escape(st.session_state.get('last_mode',''))}</div><div style='margin-top:4px;font-weight:700;'>✅ Résultats : {min(len(results),20)} / {len(results)}</div></div>",
        unsafe_allow_html=True
    )

    country = profile["country"]
    allowed_services = set(profile.get("platform_ids", []))
    platform_name_norms = profile_platform_name_norms(profile)
    show_elsewhere = bool(profile.get("show_elsewhere", False))

    for idx, item in enumerate(results[:20]):
        sh = item["show"]
        title = sh.get("title", "Sans titre")
        year = item["year"]
        score100 = item["score100"]
        sources = item["sources"]
        poster = get_poster_url(sh)
        overview = sh.get("overview", "")

        opts_all = ((sh.get("streamingOptions") or {}).get(country) or [])
        opts_all = dedupe_streaming_options(opts_all)
        opts_mine = [o for o in opts_all if service_option_matches(o, allowed_services, platform_name_norms)]
        opts_mine = dedupe_streaming_options(opts_mine)

        ctxt = country_from_omdb(sh) if OMDB_API_KEY else ""
        iso = iso2_from_country_text(ctxt) if ctxt else ""
        flag = flag_from_iso2(iso) if iso else ""
        country_label = ctxt.split(",")[0].strip() if ctxt else ""

        airings = []
        if idx < 10:
            title_variants = [title]
            if sh.get("originalTitle"):
                title_variants.append(sh["originalTitle"])
            airings = tnt_find_airings(title_variants, limit=2)

        st.markdown("<div class='ff-result-wrap'>", unsafe_allow_html=True)
        c_img, c_txt = st.columns([1, 4], vertical_alignment="top")
        with c_img:
            if poster:
                st.markdown("<div class='ff-poster'>", unsafe_allow_html=True)
                st.image(poster, use_container_width=True)
                st.markdown("</div>", unsafe_allow_html=True)

        with c_txt:
            st.markdown("<div class='ff-result-bubble'>", unsafe_allow_html=True)
            st.markdown(f"### {title} ({year if year else ''})")

            star = stars_html(score100)
            if star:
                score5 = None if score100 is None else round(float(score100) / 20.0, 1)
                label = "" if score5 is None else f"<span class='ff-muted' style='margin-left:8px'>({score5}/5)</span>"
                fl = f"<span class='ff-muted' style='margin-left:10px'>{flag} {country_label}</span>" if (flag or country_label) else ""
                st.markdown(f"{star}{label}{fl}", unsafe_allow_html=True)

            if opts_mine:
                st.markdown("<div class='ff-meta'><span class='ff-pill-ok'>✅ Dispo sur tes applis</span></div>", unsafe_allow_html=True)
            else:
                st.markdown("<div class='ff-meta'><span class='ff-pill-no'>❌ Pas dispo sur tes applis</span></div>", unsafe_allow_html=True)

            if opts_mine:
                st.markdown("<div class='ff-links'>", unsafe_allow_html=True)
                for o in opts_mine[:4]:
                    s = (o.get("service") or {})
                    name = s.get("name", s.get("id", "service"))
                    typ = o.get("type", "")
                    link = o.get("link") or o.get("videoLink")
                    if link:
                        st.markdown(f"<div class='ff-linkline'><b>{html.escape(name)}</b> ({html.escape(typ)}) → <a href='{link}' target='_blank'>{html.escape(link)}</a></div>", unsafe_allow_html=True)
                st.markdown("</div>", unsafe_allow_html=True)
            elif show_elsewhere and opts_all:
                st.markdown("<div class='ff-links'>", unsafe_allow_html=True)
                for o in opts_all[:4]:
                    s = (o.get("service") or {})
                    name = s.get("name", s.get("id", "service"))
                    typ = o.get("type", "")
                    link = o.get("link") or o.get("videoLink")
                    if link:
                        st.markdown(f"<div class='ff-linkline'><b>{html.escape(name)}</b> ({html.escape(typ)}) → <a href='{link}' target='_blank'>{html.escape(link)}</a></div>", unsafe_allow_html=True)
                st.markdown("</div>", unsafe_allow_html=True)

            with st.expander("Détails", expanded=False):
                if airings:
                    txt = "TNT : " + " · ".join([f"{a['channel']} {a['start']}-{a['stop']}" for a in airings])
                    st.markdown(f"<div class='ff-muted'>{txt}</div>", unsafe_allow_html=True)

                if sources:
                    st.markdown(f"<div class='ff-muted'>{sources}</div>", unsafe_allow_html=True)

                if overview:
                    st.write(overview)

                actors = actors_list_from_omdb(sh)
                if actors:
                    st.markdown(f"<div class='ff-inline-actors'><span class='ff-muted'>Acteurs :</span> {actor_links_html(actors)}</div>", unsafe_allow_html=True)

            st.markdown("</div>", unsafe_allow_html=True)
        st.markdown("</div>", unsafe_allow_html=True)
