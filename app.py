import os
import re
import json
import random
from pathlib import Path

import requests
import streamlit as st
from dotenv import load_dotenv

# ================== CONFIG ==================
load_dotenv()

# Streaming Availability (RapidAPI)
RAPIDAPI_KEY = os.getenv("RAPIDAPI_KEY", "").strip()
RAPIDAPI_HOST = os.getenv("RAPIDAPI_HOST", "streaming-availability.p.rapidapi.com").strip()
BASE_URL = "https://streaming-availability.p.rapidapi.com"

# IA locale (Ollama) - ON si dispo
OLLAMA_URL = os.getenv("OLLAMA_URL", "http://localhost:11434").strip()
OLLAMA_MODEL = os.getenv("OLLAMA_MODEL", "llama3.2:3b").strip()

# Notes “sites critiques” (optionnel)
# -> si tu veux Rotten Tomatoes / Metacritic / IMDb: mets une clé OMDb dans .env :
# OMDB_API_KEY=xxxxxxxx
OMDB_API_KEY = os.getenv("OMDB_API_KEY", "").strip()

APP_DIR = Path(__file__).parent
PROFILE_PATH = APP_DIR / "profile.json"

st.set_page_config(page_title="FilmFinder IA", layout="centered")

# ================== THEME ==================
def apply_theme():
    css = """
    <style>
    html, body, .stApp, [data-testid="stAppViewContainer"] { background: #f4f6f8 !important; }

    .main .block-container{
        max-width: 1020px !important;
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
    .ff-badge{
        display:inline-block;
        padding: 4px 10px;
        border-radius: 999px;
        background: rgba(0,0,0,0.06);
        font-size: 13px;
        margin-right: 8px;
        margin-bottom: 6px;
    }
    </style>
    """
    st.markdown(css, unsafe_allow_html=True)

apply_theme()

# ================== PROFILE ==================
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

def parse_critic_scores(show: dict):
    """
    Retour:
    (display_str, score_0_100 or None)
    Priorité score: RT% > Metascore > IMDb*10 > rating API si présent
    """
    # 1) rating "API" (souvent /100) si dispo
    api_rating = show.get("rating", None)
    api_score = None
    if isinstance(api_rating, (int, float)):
        api_score = float(api_rating)

    imdb_id = show.get("imdbId") or show.get("imdbID") or None
    data = omdb_fetch(imdb_id) if imdb_id else None

    rt = None
    meta = None
    imdb = None

    if data:
        # IMDb
        try:
            if data.get("imdbRating") and data.get("imdbRating") != "N/A":
                imdb = float(data["imdbRating"])
        except Exception:
            pass
        # Metascore
        try:
            if data.get("Metascore") and data.get("Metascore") != "N/A":
                meta = int(data["Metascore"])
        except Exception:
            pass
        # Rotten Tomatoes dans Ratings[]
        try:
            for r in data.get("Ratings", []) or []:
                if r.get("Source") == "Rotten Tomatoes":
                    v = r.get("Value", "")
                    if v.endswith("%"):
                        rt = int(v.replace("%", "").strip())
        except Exception:
            pass

    parts = []
    if rt is not None:
        parts.append(f"🍅 {rt}%")
    if meta is not None:
        parts.append(f"📰 {meta}/100")
    if imdb is not None:
        parts.append(f"⭐ {imdb:.1f}/10")

    # Score utilisé pour trier
    if rt is not None:
        score = float(rt)
    elif meta is not None:
        score = float(meta)
    elif imdb is not None:
        score = float(imdb * 10.0)
    elif api_score is not None:
        score = float(api_score)
        parts.append(f"📊 {int(score)}/100")
    else:
        score = None
        if api_score is not None:
            parts.append(f"📊 {int(api_score)}/100")

    display = " · ".join(parts) if parts else ""
    return display, score

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

# ================== ACCUEIL: affiche ==================
@st.cache_data(show_spinner=False, ttl=3600)
def get_home_poster(country: str, lang: str):
    titles = [
        "Inception", "The Matrix", "Interstellar", "Titanic", "Gladiator",
        "Avatar", "The Godfather", "Pulp Fiction", "The Dark Knight",
        "Forrest Gump", "Jurassic Park"
    ]
    random.shuffle(titles)
    for t in titles:
        try:
            res = search_by_title(t, country=country, show_type="movie", lang=lang)
            if res:
                url = get_poster_url(res[0])
                if url:
                    return url, res[0].get("title", t)
        except Exception:
            pass
    return None, None

# ================== MENU / STATE ==================
st.session_state.setdefault("entered", False)
st.session_state.setdefault("page", "Accueil")
st.session_state.setdefault("do_search", False)
st.session_state.setdefault("last_results", None)  # liste de shows
st.session_state.setdefault("last_query", "")

with st.sidebar:
    ok, msg = api_healthcheck()
    st.markdown("## FilmFinder IA")
    st.caption("✅ " + msg if ok else "❌ " + msg)
    st.caption("🤖 IA locale : " + ("ON" if ollama_is_up() else "OFF"))
    st.caption("📝 Notes critiques : " + ("ON (OMDb)" if OMDB_API_KEY else "OFF (optionnel)"))

    if st.session_state["entered"]:
        st.radio("Menu", ["Recherche", "Profil"], key="page")
    else:
        st.caption("Accueil (début uniquement)")

# ================== ACCUEIL ==================
if st.session_state["page"] == "Accueil":
    st.markdown("# FilmFinder IA")
    st.caption("Souvenir flou → titres probables → où regarder (liens).")

    if RAPIDAPI_KEY:
        poster_url, poster_title = get_home_poster(country=profile.get("country","fr"), lang=profile.get("lang","fr"))
        if poster_url:
            c1, c2 = st.columns([1, 2])
            with c1:
                st.image(poster_url, width=210)
            with c2:
                st.markdown("### 🍿 Bienvenue")
                st.caption(f"Affiche aléatoire : **{poster_title}**")
        else:
            st.markdown("### 🍿 Bienvenue")

    st.markdown('<div class="ff-card">', unsafe_allow_html=True)
    st.markdown("### Inscription rapide")
    st.caption("Pas de nom/prénom. Juste ce qui sert à filtrer la recherche.")

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

def trigger_search():
    st.session_state["do_search"] = True

q_main = st.text_input(
    "Ton souvenir (Entrée lance la recherche)",
    key="q_main",
    on_change=trigger_search,
    placeholder="Ex: un homme se perd dans la forêt…"
)

with st.expander("Ajouter des détails (optionnel)"):
    q_more = st.text_area("Détails", key="q_more", height=90)

if st.button("Trouver"):
    st.session_state["do_search"] = True

# --- lance une nouvelle recherche ---
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

    # IA locale -> pack de requêtes (rapide)
    if ollama_is_up():
        try:
            pack = ollama_pack(q)
            titles = pack.get("titles", []) or []
            queries = pack.get("queries", []) or []
        except Exception as e:
            errors.append(f"IA locale: {e}")

    # fallback sans IA
    if not queries:
        queries = [extract_keywords(q), q]

    # MODE RAPIDE: peu d'appels
    TITLES_MAX = 4
    QUERIES_MAX = 4

    found = []

    # 1) Titres
    for t in titles[:TITLES_MAX]:
        try:
            found += search_by_title(t, country, show_type, lang)
        except Exception as e:
            errors.append(str(e))

    # 2) Keywords FR
    for kw in queries[:QUERIES_MAX]:
        try:
            found += search_by_keyword(kw, country, show_type, lang)
        except Exception as e:
            errors.append(str(e))

    # 3) Keywords EN seulement si on a trop peu de résultats
    if len(found) < 8:
        for kw in queries[:QUERIES_MAX]:
            try:
                found += search_by_keyword(kw, country, show_type, "en")
            except Exception as e:
                errors.append(str(e))

    found = merge_results(found)
    found.sort(key=lambda sh: score_relevance(sh, q), reverse=True)

    # on garde un “pool” raisonnable pour tri/notes (évite 280 résultats et le PC qui rame)
    found = found[:60]

    st.session_state["last_results"] = found
    st.session_state["last_query"] = q
    st.session_state["last_errors"] = errors

# --- affichage (tri) ---
results = st.session_state.get("last_results")
if results is not None:
    q = st.session_state.get("last_query", "")
    errors = st.session_state.get("last_errors", [])

    if errors:
        st.warning("⚠️ Debug (utile si ça bug) :\n- " + "\n- ".join(errors[:2]))

    st.caption(f"Requête: {q}")

    sort_mode = st.selectbox(
        "Trier par",
        ["Pertinence", "Année (récent)", "Note (haute)"],
        index=0
    )

    # Pré-calcul des notes pour tri (limité pour éviter lenteur OMDb)
    enriched = []
    for i, sh in enumerate(results):
        year = sh.get("releaseYear") or sh.get("firstAirYear") or 0
        try:
            year = int(year) if year else 0
        except Exception:
            year = 0

        # Notes: OMDb peut être lent -> on calcule pour les 25 premiers seulement
        note_str = ""
        note_score = None
        if i < 25:
            note_str, note_score = parse_critic_scores(sh)
        else:
            # fallback “API rating” si dispo
            if isinstance(sh.get("rating"), (int, float)):
                note_score = float(sh["rating"])
                note_str = f"📊 {int(note_score)}/100"

        enriched.append((sh, year, note_score, note_str))

    if sort_mode == "Année (récent)":
        enriched.sort(key=lambda x: x[1], reverse=True)
    elif sort_mode == "Note (haute)":
        enriched.sort(key=lambda x: (x[2] is not None, x[2] or -1), reverse=True)
    else:
        # Pertinence = on garde l'ordre déjà trié
        pass

    st.write(f"✅ Résultats : {len(enriched)} (affichage des 20 premiers)")

    country = profile["country"]
    allowed_services = set(profile.get("platform_ids", []))
    show_elsewhere = bool(profile.get("show_elsewhere", False))

    for sh, year, note_score, note_str in enriched[:20]:
        title = sh.get("title", "Sans titre")
        overview = sh.get("overview", "")
        poster = get_poster_url(sh)

        c_img, c_txt = st.columns([1, 3])

        with c_img:
            if poster:
                st.image(poster, width=140)
            else:
                st.markdown("🎞️")

        with c_txt:
            line = f"### {title} ({year if year else ''})"
            if note_str:
                line += f" — {note_str}"
            st.markdown(line)

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