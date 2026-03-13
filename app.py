import os
import re
import json
from pathlib import Path

import requests
import streamlit as st
from dotenv import load_dotenv

# ================== CONFIG ==================
load_dotenv()

RAPIDAPI_KEY = os.getenv("RAPIDAPI_KEY", "").strip()
RAPIDAPI_HOST = os.getenv("RAPIDAPI_HOST", "streaming-availability.p.rapidapi.com").strip()
BASE_URL = "https://streaming-availability.p.rapidapi.com"

# IA locale (Ollama) - optionnel
OLLAMA_URL = os.getenv("OLLAMA_URL", "http://localhost:11434").strip()
OLLAMA_MODEL = os.getenv("OLLAMA_MODEL", "llama3.2:3b").strip()

APP_DIR = Path(__file__).parent
PROFILE_PATH = APP_DIR / "profile.json"

st.set_page_config(page_title="FilmFinder IA", layout="centered")

# ================== THEME (propre & lisible) ==================
def apply_theme():
    css = """
    <style>
    html, body, .stApp, [data-testid="stAppViewContainer"] {
        background: #f4f6f8 !important;
    }

    /* bloc principal */
    .main .block-container {
        max-width: 980px !important;
        margin: 18px auto !important;
        background: #ffffff !important;
        border-radius: 18px !important;
        padding: 22px 26px 30px 26px !important;
        box-shadow: 0 10px 35px rgba(0,0,0,0.08) !important;
    }

    /* sidebar */
    [data-testid="stSidebar"] > div:first-child {
        background: #ffffff !important;
        border-right: 1px solid rgba(0,0,0,0.06);
    }

    /* texte */
    .main h1, .main h2, .main h3, .main p, .main label, .main span, .main div, .main li {
        color: #111 !important;
    }
    .main a { color: #0b57d0 !important; font-weight: 600; }

    /* cartes jolies */
    .ff-card {
        border: 1px solid rgba(0,0,0,0.08);
        border-radius: 16px;
        padding: 16px 16px 6px 16px;
        background: rgba(255,255,255,0.98);
        box-shadow: 0 8px 24px rgba(0,0,0,0.06);
        margin: 12px 0 18px 0;
    }
    .ff-card h3 { margin-top: 0; }
    </style>
    """
    st.markdown(css, unsafe_allow_html=True)

apply_theme()

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
    }

def save_profile(p):
    PROFILE_PATH.write_text(json.dumps(p, ensure_ascii=False, indent=2), encoding="utf-8")

profile = load_profile()

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

# ================== IA LOCALE (Ollama) ==================
def ollama_is_up():
    try:
        r = requests.get(f"{OLLAMA_URL}/api/tags", timeout=2)
        return r.ok
    except Exception:
        return False

def ollama_pack(description: str):
    """
    Retour attendu JSON:
    {"titles":[...], "queries":[...]}
    """
    prompt = f"""
Tu aides à retrouver un film/série depuis un souvenir flou.
Retourne UNIQUEMENT un JSON valide avec:
- "titles": 5 à 10 titres probables (FR + original si possible)
- "queries": 6 à 12 requêtes (FR/EN) pour chercher dans une base de films

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
st.session_state.setdefault("entered", False)
st.session_state.setdefault("page", "Accueil")

# Si l'utilisateur est déjà "entré", on ne doit plus jamais rester sur Accueil
if st.session_state["entered"] and st.session_state["page"] == "Accueil":
    st.session_state["page"] = "Recherche"

# Sidebar: après entrée -> seulement Profil / Recherche
with st.sidebar:
    st.markdown("## FilmFinder IA")
    if st.session_state["entered"]:
        st.radio("Menu", ["Recherche", "Profil"], key="page")
    else:
        st.caption("Accueil (1ère fois seulement)")

# ================== PAGE: ACCUEIL ==================
if st.session_state["page"] == "Accueil":
    st.markdown("# FilmFinder IA")
    st.caption("Retrouve un film/série depuis un souvenir flou, et obtiens le lien pour le regarder.")

    st.markdown('<div class="ff-card">', unsafe_allow_html=True)
    st.markdown("### 🍿 Inscription rapide")
    st.caption("Pas de nom/prénom. Juste ce qui sert à filtrer la recherche.")

    if not RAPIDAPI_KEY:
        st.error("RAPIDAPI_KEY manquante dans .env (RapidAPI).")
        st.stop()

    # Form inscription (jolie + simple)
    with st.form("signup_form", clear_on_submit=False):
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

        show_elsewhere = st.checkbox("Si pas dispo sur mes applis, montrer où c’est dispo ailleurs", value=bool(profile.get("show_elsewhere", False)))

        up = ollama_is_up()
        use_local_ai = st.checkbox("Activer IA locale (Ollama)", value=bool(profile.get("use_local_ai", False)), disabled=not up)
        if not up:
            st.caption("IA locale : Ollama non détecté (normal si pas installé).")

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
                "use_local_ai": bool(use_local_ai),
            }
            save_profile(profile)
            st.session_state["entered"] = True
            st.session_state["page"] = "Recherche"
            st.rerun()

    st.stop()

# ================== PAGE: PROFIL ==================
if st.session_state["page"] == "Profil":
    st.markdown("# Profil")
    st.caption("Tu peux modifier tes plateformes / pays / langue quand tu veux.")

    if not RAPIDAPI_KEY:
        st.error("RAPIDAPI_KEY manquante dans .env (RapidAPI).")
        st.stop()

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

        up = ollama_is_up()
        use_local_ai = st.checkbox("Activer IA locale (Ollama)", value=bool(profile.get("use_local_ai", False)), disabled=not up)

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
            }
            save_profile(profile)
            st.success("Profil enregistré.")
            st.rerun()

    st.stop()

# ================== PAGE: RECHERCHE ==================
st.markdown("# Recherche")

if not profile.get("platform_ids"):
    st.warning("Tu dois avoir un profil (plateformes) pour chercher.")
    st.stop()

# Form: Entrée = recherche automatique (text_input)
with st.form("search_form", clear_on_submit=False):
    q_main = st.text_input("Ton souvenir (appuie sur Entrée pour lancer)", value="", placeholder="Ex: un mec revit la même journée en boucle…")
    with st.expander("Ajouter des détails (optionnel)"):
        q_more = st.text_area("Détails", height=90, placeholder="Acteur, époque, scène, pays, etc.")
    go = st.form_submit_button("Trouver")

if go:
    q = (q_main.strip() + " " + q_more.strip()).strip()
    if not q:
        st.warning("Écris au moins une phrase 🙂")
        st.stop()

    country = profile["country"]
    lang = profile["lang"]
    show_type = profile["show_type"]
    allowed_services = set(profile["platform_ids"])
    show_elsewhere = bool(profile.get("show_elsewhere", False))

    found = []
    titles = []
    queries = []

    # IA locale si activée
    if profile.get("use_local_ai") and ollama_is_up():
        pack = ollama_pack(q)
        titles = pack.get("titles", []) or []
        queries = pack.get("queries", []) or []

    # fallback sans IA
    if not queries:
        queries = [extract_keywords(q), q]

    # 1) titres proposés par IA
    for t in titles[:10]:
        try:
            found += search_by_title(t, country, show_type, lang)
        except Exception:
            pass

    # 2) mots-clés FR + EN
    for kw in queries[:12]:
        try:
            found += search_by_keyword(kw, country, show_type, lang)
        except Exception:
            pass
        try:
            found += search_by_keyword(kw, country, show_type, "en")
        except Exception:
            pass

    # 3) titres entre guillemets "..."
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