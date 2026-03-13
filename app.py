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

APP_DIR = Path(__file__).parent
PROFILE_PATH = APP_DIR / "profile.json"
BG_DIR = APP_DIR / "bg"

st.set_page_config(page_title="FilmFinder IA", layout="centered")

# ================== HELPERS: STORAGE ==================
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

# ================== HELPERS: BACKGROUND ==================
def pick_background_image():
    if "bg_file" in st.session_state:
        return st.session_state["bg_file"]

    files = []
    if BG_DIR.exists():
        for ext in ("*.jpg", "*.jpeg", "*.png", "*.webp"):
            files += list(BG_DIR.glob(ext))

    chosen = random.choice(files) if files else None
    st.session_state["bg_file"] = str(chosen) if chosen else ""
    return st.session_state["bg_file"]

def set_background():
    bg_file = pick_background_image()
    if bg_file:
        p = Path(bg_file)
        data = p.read_bytes()
        b64 = base64.b64encode(data).decode("utf-8")
        ext = p.suffix.lower().replace(".", "")
        if ext == "jpg":
            ext = "jpeg"
        bg_css = f"""
        <style>
        .stApp {{
            background: url("data:image/{ext};base64,{b64}") no-repeat center center fixed;
            background-size: cover;
        }}
        /* voile sombre pour lisibilité */
        .stApp::before {{
            content: "";
            position: fixed;
            inset: 0;
            background: rgba(0,0,0,0.55);
            z-index: -1;
        }}
        /* “carte” claire pour le contenu */
        section.main > div {{
            background: rgba(255,255,255,0.88);
            border-radius: 16px;
            padding: 16px 18px;
        }}
        </style>
        """
    else:
        # fallback dégradé
        bg_css = """
        <style>
        .stApp {
            background: radial-gradient(circle at 20% 0%, #3b82f6 0%, transparent 45%),
                        radial-gradient(circle at 80% 10%, #ef4444 0%, transparent 45%),
                        radial-gradient(circle at 50% 90%, #22c55e 0%, transparent 45%),
                        #0b1220;
        }
        section.main > div {
            background: rgba(255,255,255,0.90);
            border-radius: 16px;
            padding: 16px 18px;
        }
        </style>
        """
    st.markdown(bg_css, unsafe_allow_html=True)

set_background()

# ================== HELPERS: API ==================
def sa_get(path: str, params: dict):
    if not RAPIDAPI_KEY:
        raise RuntimeError("RAPIDAPI_KEY manquante dans .env")
    r = requests.get(
        f"{BASE_URL}{path}",
        headers={"X-RapidAPI-Key": RAPIDAPI_KEY, "X-RapidAPI-Host": RAPIDAPI_HOST},
        params=params,
        timeout=20,
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
        or (sh.get("title","") + "_" + str(sh.get("releaseYear") or sh.get("firstAirYear") or ""))
    )

# ================== HELPERS: SEARCH (simple et robuste) ==================
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

def extract_keywords(text: str, max_words: int = 8) -> str:
    stop = {"le","la","les","un","une","des","de","du","dans","sur","avec","sans","et","ou",
            "qui","que","quoi","dont","au","aux","en","a","à","pour","par","se","sa","son","ses",
            "je","tu","il","elle","on","nous","vous","ils","elles","toujours",
            "the","a","an","and","or","in","on","with","without","to","of","for","by","from"}
    words = re.findall(r"[a-zA-ZÀ-ÿ0-9']+", text.lower())
    words = [w for w in words if len(w) >= 4 and w not in stop]
    # garder l'ordre
    out = []
    for w in words:
        if w not in out:
            out.append(w)
        if len(out) >= max_words:
            break
    return " ".join(out) if out else text.strip()

# ================== ROUTING (setup vs search) ==================
if "page" not in st.session_state:
    # si pas de profil (aucune plateforme cochée), on force setup
    st.session_state["page"] = "setup" if not profile.get("platform_ids") else "search"

# barre latérale
with st.sidebar:
    st.markdown("## Navigation")
    st.session_state["page"] = st.radio(
        "Page",
        ["Profil", "Recherche"],
        index=0 if st.session_state["page"] == "setup" else 1
    )
    if st.button("🎲 Changer le fond (session)"):
        st.session_state.pop("bg_file", None)
        st.rerun()

# ================== PAGE: PROFIL ==================
if st.session_state["page"] == "Profil":
    st.markdown("# Création / réglages profil")
    st.caption("Aucun nom/prénom. Juste ce qui sert à trouver et filtrer.")

    if not RAPIDAPI_KEY:
        st.error("RAPIDAPI_KEY manquante dans .env — l’app ne peut pas récupérer les plateformes.")
        st.stop()

    with st.form("profile_form"):
        pseudo = st.text_input("Pseudo (optionnel)", value=profile.get("pseudo",""))

        col1, col2, col3 = st.columns(3)
        with col1:
            country = st.selectbox("Pays", ["fr","be","ch","gb","us"], index=["fr","be","ch","gb","us"].index(profile.get("country","fr")))
        with col2:
            lang = st.selectbox("Langue", ["fr","en"], index=["fr","en"].index(profile.get("lang","fr")))
        with col3:
            show_type = st.selectbox("Type", ["all","movie","series"], index=["all","movie","series"].index(profile.get("show_type","all")))

        services = get_services(country, lang)
        name_to_id = { (s.get("name") or s.get("id")): s.get("id") for s in services if (s.get("name") or s.get("id")) and s.get("id") }
        id_to_name = { v:k for k,v in name_to_id.items() }

        default_names = [id_to_name[i] for i in profile.get("platform_ids", []) if i in id_to_name]
        if not default_names:
            # defaults “classiques” si présents
            for wanted in ["Netflix", "Prime Video", "Disney+", "Apple TV+", "Max"]:
                if wanted in name_to_id:
                    default_names.append(wanted)

        chosen_names = st.multiselect("Tes plateformes", options=sorted(name_to_id.keys()), default=sorted(set(default_names)))
        platform_ids = [name_to_id[n] for n in chosen_names]

        show_elsewhere = st.checkbox("Si pas dispo sur mes applis, montrer où c’est dispo ailleurs", value=bool(profile.get("show_elsewhere", False)))

        ok = st.form_submit_button("✅ Enregistrer")

    if ok:
        if not platform_ids:
            st.warning("Coche au moins 1 plateforme, sinon ça ne sert à rien 🙂")
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
            st.success("Profil enregistré. Va dans l’onglet Recherche.")
    st.stop()

# ================== PAGE: RECHERCHE ==================
st.markdown("# Recherche")
if not profile.get("platform_ids"):
    st.warning("Tu dois d’abord créer ton profil (plateformes).")
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

    # stratégie simple : 1) on tente par keywords FR 2) on tente par keywords EN (même texte) 3) on tente quelques titres si l'utilisateur a mis des guillemets
    found = []

    # A) keyword FR "nettoyé"
    kw1 = extract_keywords(q)
    found += search_by_keyword(kw1, country, show_type, lang)

    # B) keyword EN (ça aide car souvent l’index est EN)
    found += search_by_keyword(q.strip(), country, show_type, "en")

    # C) si l’utilisateur a mis un titre entre guillemets "..."
    quoted = re.findall(r'"([^"]+)"', q)
    for t in quoted[:5]:
        found += search_by_title(t, country, show_type, lang)

    found = merge_results(found)
    found.sort(key=lambda sh: score(sh, q), reverse=True)

    st.write(f"✅ Résultats : {len(found)} (20 max affichés)")

    for sh in found[:20]:
        title = sh.get("title","Sans titre")
        year = sh.get("releaseYear") or sh.get("firstAirYear") or ""
        overview = sh.get("overview","")

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
                typ = o.get("type","")
                link = o.get("link") or o.get("videoLink")
                if link:
                    st.markdown(f"- **{name}** ({typ}) → {link}")
                else:
                    st.markdown(f"- **{name}** ({typ})")
        else:
            st.info("❌ Pas dispo sur tes applis.")
            if profile.get("show_elsewhere") and opts_all:
                st.write("Dispo ailleurs :")
                for o in opts_all:
                    s = (o.get("service") or {})
                    name = s.get("name", s.get("id", "service"))
                    typ = o.get("type","")
                    link = o.get("link") or o.get("videoLink")
                    if link:
                        st.markdown(f"- **{name}** ({typ}) → {link}")
                    else:
                        st.markdown(f"- **{name}** ({typ})")

        st.divider()