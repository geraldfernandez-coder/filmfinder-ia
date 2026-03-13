import os
import re
import json
import base64
import random
from pathlib import Path

import requests
import streamlit as st
from dotenv import load_dotenv

# ================== CONFIG ==================
load_dotenv()

RAPIDAPI_KEY = os.getenv("RAPIDAPI_KEY", "").strip()
RAPIDAPI_HOST = os.getenv("RAPIDAPI_HOST", "streaming-availability.p.rapidapi.com").strip()
BASE_URL = "https://streaming-availability.p.rapidapi.com"

# IA locale (Ollama)
OLLAMA_URL = os.getenv("OLLAMA_URL", "http://localhost:11434").strip()
OLLAMA_MODEL = os.getenv("OLLAMA_MODEL", "llama3.2:3b").strip()

APP_DIR = Path(__file__).parent
PROFILE_PATH = APP_DIR / "profile.json"
BG_DIR = APP_DIR / "bg"  # mets des images ici si tu veux un mode "affiche" plus tard

st.set_page_config(page_title="FilmFinder IA", layout="centered")


# ================== PROFILE STORAGE ==================
def load_profile():
    if PROFILE_PATH.exists():
        try:
            return json.loads(PROFILE_PATH.read_text(encoding="utf-8"))
        except Exception:
            pass
    return {
        "pseudo": "",
        "country": "fr",
        "lang": "fr",
        "show_type": "all",
        "platform_ids": [],
        "show_elsewhere": False,
        "use_local_ai": False,
        "enable_posters": False,  # affiches en fond (désactivé par défaut)
    }


def save_profile(p):
    PROFILE_PATH.write_text(json.dumps(p, ensure_ascii=False, indent=2), encoding="utf-8")


profile = load_profile()


# ================== THEMES (SANS IMAGE / AVEC AFFICHE) ==================
def apply_plain_theme():
    """Thème propre, sans image."""
    css = """
    <style>
    html, body, .stApp, [data-testid="stAppViewContainer"] {
        background: #f4f6f8 !important;
    }
    [data-testid="stSidebar"] > div:first-child {
        background: #ffffff !important;
        border-right: 1px solid rgba(0,0,0,0.06);
    }
    .main .block-container {
        max-width: 980px !important;
        margin: 18px auto !important;
        background: #ffffff !important;
        border-radius: 18px !important;
        padding: 22px 26px 30px 26px !important;
        box-shadow: 0 10px 35px rgba(0,0,0,0.08) !important;
    }
    .main h1, .main h2, .main h3, .main p, .main label, .main span, .main div, .main li {
        color: #111 !important;
    }
    .main a { color: #0b57d0 !important; font-weight: 600; }
    </style>
    """
    st.markdown(css, unsafe_allow_html=True)


def list_bg_files():
    if not BG_DIR.exists():
        return []
    files = []
    for ext in ("*.jpg", "*.jpeg", "*.png", "*.webp"):
        files += list(BG_DIR.glob(ext))
    return files


def pick_background_image():
    if "bg_file" in st.session_state:
        return st.session_state["bg_file"]
    files = list_bg_files()
    chosen = random.choice(files) if files else None
    st.session_state["bg_file"] = str(chosen) if chosen else ""
    return st.session_state["bg_file"]


def apply_poster_theme(bg_opacity: float = 0.55, blur_px: int = 6, card_opacity: float = 0.97):
    """Thème avec affiche + voile sombre + carte blanche."""
    bg_file = pick_background_image()

    base_css = f"""
    <style>
    [data-testid="stSidebar"] > div:first-child {{
        background: rgba(255,255,255,0.96) !important;
    }}
    .main .block-container {{
        background: rgba(255,255,255,{card_opacity}) !important;
        border-radius: 18px !important;
        padding: 22px 26px 30px 26px !important;
        box-shadow: 0 12px 45px rgba(0,0,0,0.35) !important;
        max-width: 980px !important;
        margin: 18px auto !important;
    }}
    .main h1, .main h2, .main h3,
    .main p, .main label, .main span,
    .main li, .main div {{
        color: #0b0b0b !important;
    }}
    .main a {{ color: #0b57d0 !important; font-weight: 600; }}

    [data-testid="stSidebar"], .main {{
        position: relative;
        z-index: 1;
    }}
    </style>
    """

    if bg_file:
        p = Path(bg_file)
        data = p.read_bytes()
        b64 = base64.b64encode(data).decode("utf-8")
        ext = p.suffix.lower().replace(".", "")
        if ext == "jpg":
            ext = "jpeg"

        bg_css = f"""
        <style>
        html, body, .stApp, [data-testid="stAppViewContainer"] {{
            background: url("data:image/{ext};base64,{b64}") no-repeat center center fixed !important;
            background-size: cover !important;
        }}
        .stApp::before,
        [data-testid="stAppViewContainer"]::before {{
            content: "";
            position: fixed;
            inset: 0;
            background: rgba(0,0,0,{bg_opacity});
            backdrop-filter: blur({blur_px}px);
            z-index: 0;
        }}
        </style>
        """
    else:
        bg_css = """
        <style>
        html, body, .stApp, [data-testid="stAppViewContainer"] {
            background: #0b1220 !important;
        }
        </style>
        """

    st.markdown(bg_css + base_css, unsafe_allow_html=True)


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
    r.raise_for_status()
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
        key = (sid, typ)
        if key in seen:
            continue
        seen.add(key)
        out.append(o)
    return out


def stable_id(sh: dict) -> str:
    return str(
        sh.get("id")
        or sh.get("imdbId")
        or sh.get("tmdbId")
        or (sh.get("title", "") + "_" + str(sh.get("releaseYear") or sh.get("firstAirYear") or ""))
    )


# ================== SEARCH HELPERS ==================
def score(sh, qtext):
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
    data = sa_get(
        "/shows/search/title",
        {
            "title": title,
            "country": country,
            "show_type": type_param,
            "series_granularity": "show",
            "output_language": lang,
        },
    )
    return data if isinstance(data, list) else []


def search_by_keyword(keyword: str, country: str, show_type: str, lang: str):
    type_param = None if show_type == "all" else show_type
    res = sa_get(
        "/shows/search/filters",
        {
            "country": country,
            "show_type": type_param,
            "keyword": keyword,
            "series_granularity": "show",
            "output_language": lang,
        },
    )
    return res.get("shows", []) if isinstance(res, dict) else []


def extract_keywords(text: str, max_words: int = 10) -> str:
    stop = {
        "le", "la", "les", "un", "une", "des", "de", "du", "dans", "sur", "avec", "sans", "et", "ou",
        "qui", "que", "quoi", "dont", "au", "aux", "en", "a", "à", "pour", "par", "se", "sa", "son", "ses",
        "je", "tu", "il", "elle", "on", "nous", "vous", "ils", "elles", "toujours",
        "the", "a", "an", "and", "or", "in", "on", "with", "without", "to", "of", "for", "by", "from",
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


# ================== IA LOCALE (Ollama) ==================
def ollama_is_up():
    try:
        r = requests.get(f"{OLLAMA_URL}/api/tags", timeout=2)
        return r.ok
    except Exception:
        return False


def ollama_pack(description: str):
    """
    Retour attendu (JSON):
    {
      "titles": ["Un jour sans fin", "Groundhog Day", ...],
      "queries": ["time loop repeats the same day", "..."]
    }
    """
    prompt = f"""
Tu aides à retrouver un film/série depuis un souvenir flou.
Retourne UNIQUEMENT un JSON valide avec:
- "titles": liste de 5 à 10 titres probables (FR + original si possible)
- "queries": liste de 6 à 12 requêtes (FR/EN) pour chercher dans une base de films

Souvenir: {description}
""".strip()

    r = requests.post(
        f"{OLLAMA_URL}/api/generate",
        json={"model": OLLAMA_MODEL, "prompt": prompt, "stream": False},
        timeout=60,
    )
    r.raise_for_status()
    txt = r.json().get("response", "")

    start = txt.find("{")
    end = txt.rfind("}")
    if start == -1 or end == -1 or end <= start:
        return {"titles": [], "queries": []}
    try:
        return json.loads(txt[start:end + 1])
    except Exception:
        return {"titles": [], "queries": []}


# ================== ROUTING ==================
if "page" not in st.session_state:
    st.session_state["page"] = "Accueil"
if "no_poster_mode" not in st.session_state:
    st.session_state["no_poster_mode"] = True  # on démarre sans affiche (ton souhait)

# Appliquer le thème selon le mode
if st.session_state["no_poster_mode"]:
    apply_plain_theme()
else:
    apply_poster_theme()

# Sidebar navigation
with st.sidebar:
    st.markdown("## Navigation")
    st.session_state["page"] = st.radio("Page", ["Accueil", "Profil", "Recherche"], index=["Accueil","Profil","Recherche"].index(st.session_state["page"]))

    if not st.session_state["no_poster_mode"]:
        if st.button("🎲 Changer le fond (session)"):
            st.session_state.pop("bg_file", None)
            st.rerun()

        st.caption(f"Affiches trouvées: {len(list_bg_files())} (dossier: bg)")


# ================== PAGE: ACCUEIL ==================
if st.session_state["page"] == "Accueil":
    st.markdown("# FilmFinder IA")
    st.markdown("### 🍿 Entre avec une boîte de popcorn")
    st.caption("Clique pour entrer dans la version **sans affiche** (lisibilité max).")

    colA, colB, colC = st.columns([1,2,1])
    with colB:
        st.markdown(
            """
            <div style="text-align:center; font-size:80px; line-height:1; margin-top:10px; margin-bottom:10px;">
                🍿
            </div>
            """,
            unsafe_allow_html=True
        )
        if st.button("🍿 Entrer (version sans affiche)", use_container_width=True):
            st.session_state["no_poster_mode"] = True
            # si profil déjà ok -> recherche, sinon profil
            st.session_state["page"] = "Recherche" if profile.get("platform_ids") else "Profil"
            st.rerun()

        # Optionnel (si un jour tu veux rentrer direct avec affiche)
        if st.button("🎬 Entrer (avec affiche)", use_container_width=True):
            st.session_state["no_poster_mode"] = False
            st.session_state["page"] = "Recherche" if profile.get("platform_ids") else "Profil"
            st.rerun()

    st.stop()


# ================== PAGE: PROFIL ==================
if st.session_state["page"] == "Profil":
    st.markdown("# Profil")
    st.caption("Pas de nom/prénom. Juste ce qui sert à filtrer la recherche.")

    if not RAPIDAPI_KEY:
        st.error("RAPIDAPI_KEY manquante dans .env (RapidAPI).")
        st.stop()

    with st.form("profile_form"):
        pseudo = st.text_input("Pseudo (optionnel)", value=profile.get("pseudo", ""))

        col1, col2, col3 = st.columns(3)
        with col1:
            country = st.selectbox("Pays", ["fr", "be", "ch", "gb", "us"], index=["fr","be","ch","gb","us"].index(profile.get("country", "fr")))
        with col2:
            lang = st.selectbox("Langue", ["fr", "en"], index=["fr","en"].index(profile.get("lang", "fr")))
        with col3:
            show_type = st.selectbox("Type", ["all", "movie", "series"], index=["all","movie","series"].index(profile.get("show_type", "all")))

        services = get_services(country, lang)
        name_to_id = {(s.get("name") or s.get("id")): s.get("id") for s in services if (s.get("name") or s.get("id")) and s.get("id")}
        id_to_name = {v: k for k, v in name_to_id.items()}

        default_names = [id_to_name[i] for i in profile.get("platform_ids", []) if i in id_to_name]
        if not default_names:
            for wanted in ["Netflix", "Prime Video", "Disney+", "Apple TV+", "Max", "HBO Max"]:
                if wanted in name_to_id:
                    default_names.append(wanted)

        chosen_names = st.multiselect("Tes plateformes", options=sorted(name_to_id.keys()), default=sorted(set(default_names)))
        platform_ids = [name_to_id[n] for n in chosen_names]

        show_elsewhere = st.checkbox("Si pas dispo sur mes applis, montrer où c’est dispo ailleurs", value=bool(profile.get("show_elsewhere", False)))

        st.subheader("IA locale (option)")
        up = ollama_is_up()
        use_local_ai = st.checkbox("Activer IA locale (Ollama)", value=bool(profile.get("use_local_ai", False)), disabled=not up)
        if not up:
            st.caption("Ollama non détecté (normal si pas installé).")

        ok = st.form_submit_button("✅ Enregistrer")

    if ok:
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
                "use_local_ai": bool(use_local_ai),
                "enable_posters": bool(profile.get("enable_posters", False)),
            }
            save_profile(profile)
            st.success("Profil enregistré. Va sur Recherche.")
    st.stop()


# ================== PAGE: RECHERCHE ==================
st.markdown("# Recherche")
if not profile.get("platform_ids"):
    st.warning("Crée ton profil (plateformes) avant de chercher.")
    st.stop()

q = st.text_area("Ton souvenir (phrase libre) :", height=120)
go = st.button("🔎 Trouver")

if go:
    if not q.strip():
        st.warning("Écris quelque chose 🙂")
        st.stop()

    country = profile["country"]
    lang = profile["lang"]
    show_type = profile["show_type"]
    allowed_services = set(profile["platform_ids"])
    show_elsewhere = bool(profile.get("show_elsewhere", False))

    found = []
    titles = []
    queries = []

    if profile.get("use_local_ai") and ollama_is_up():
        pack = ollama_pack(q.strip())
        titles = pack.get("titles", []) or []
        queries = pack.get("queries", []) or []

    if not queries:
        queries = [extract_keywords(q), q.strip()]

    for t in titles[:10]:
        try:
            found += search_by_title(t, country, show_type, lang)
        except Exception:
            pass

    for kw in queries[:12]:
        try:
            found += search_by_keyword(kw, country, show_type, lang)
        except Exception:
            pass
        try:
            found += search_by_keyword(kw, country, show_type, "en")
        except Exception:
            pass

    quoted = re.findall(r'"([^"]+)"', q)
    for t in quoted[:5]:
        try:
            found += search_by_title(t, country, show_type, lang)
        except Exception:
            pass

    found = merge_results(found)
    found.sort(key=lambda sh: score(sh, q), reverse=True)

    st.write(f"✅ Résultats : {len(found)} (20 max affichés)")

    for sh in found[:20]:
        title = sh.get("title", "Sans titre")
        year = sh.get("releaseYear") or sh.get("firstAirYear") or ""
        overview = sh.get("overview", "")

        st.markdown(f"### {title} ({year})")
        if overview:
            st.write(overview)

        opts_all = ((sh.get("streamingOptions") or {}).get(country) or [])
        opts_all = dedupe_streaming_options(opts_all)

        opts_mine = [o for o in opts_all if ((o.get("service") or {}).get("id") in allowed_services)]
        opts_mine = dedupe_streaming_options(opts_mine)

        if opts_mine:
            st.write("✅ Dispo sur tes applis :")
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
            st.info("❌ Pas dispo sur tes applis.")
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