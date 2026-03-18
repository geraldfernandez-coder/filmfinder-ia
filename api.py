import os
from typing import Any, Dict, Optional

import requests
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

TMDB_API_KEY = os.getenv("TMDB_API_KEY", "").strip()
TMDB_BEARER_TOKEN = os.getenv("TMDB_BEARER_TOKEN", "").strip()
TMDB_BASE = "https://api.themoviedb.org/3"
TMDB_IMAGE_BASE = "https://image.tmdb.org/t/p"

app = FastAPI(title="FilmFinder IA API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


class SearchPayload(BaseModel):
    title: Optional[str] = None
    titre: Optional[str] = None
    year: Optional[str] = None
    releaseYear: Optional[str] = None
    relevance: Optional[int] = None
    souvenir: Optional[str] = None
    replique: Optional[str] = None
    acteur: Optional[str] = None
    musique: Optional[str] = None


class MovieResponse(BaseModel):
    title: Optional[str] = None
    year: Optional[str] = None
    posterUrl: Optional[str] = None
    backdropUrl: Optional[str] = None
    tmdbId: Optional[int] = None
    tmdbTitle: Optional[str] = None
    tmdbOriginalTitle: Optional[str] = None
    tmdbYear: Optional[str] = None
    overview: Optional[str] = None
    relevance: Optional[int] = None


def tmdb_headers() -> Dict[str, str]:
    headers = {"accept": "application/json"}
    if TMDB_BEARER_TOKEN:
        headers["Authorization"] = f"Bearer {TMDB_BEARER_TOKEN}"
    return headers


def tmdb_get(path: str, params: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    if not TMDB_API_KEY and not TMDB_BEARER_TOKEN:
        raise RuntimeError("TMDB non configuré")

    params = dict(params or {})
    if TMDB_API_KEY and not TMDB_BEARER_TOKEN:
        params["api_key"] = TMDB_API_KEY

    response = requests.get(
        f"{TMDB_BASE}{path}",
        headers=tmdb_headers(),
        params=params,
        timeout=20,
    )
    if response.status_code >= 400:
        raise RuntimeError(f"TMDB {response.status_code}: {response.text[:250]}")
    return response.json()


def build_image_url(size: str, file_path: Optional[str]) -> Optional[str]:
    return f"{TMDB_IMAGE_BASE}/{size}{file_path}" if file_path else None


def search_tmdb_movie(title: str, year: Optional[str] = None) -> Dict[str, Any]:
    title = (title or "").strip()
    if not title:
        raise ValueError("Titre manquant")

    params: Dict[str, Any] = {
        "query": title,
        "include_adult": False,
        "language": "fr-FR",
    }
    if year:
        params["year"] = str(year)[:4]

    data = tmdb_get("/search/movie", params)
    results = data.get("results", [])
    if not results:
        raise LookupError("Aucun résultat TMDB")

    best = results[0]
    return {
        "tmdbId": best.get("id"),
        "tmdbTitle": best.get("title"),
        "tmdbOriginalTitle": best.get("original_title"),
        "tmdbYear": (best.get("release_date") or "")[:4] or None,
        "posterUrl": build_image_url("w500", best.get("poster_path")),
        "backdropUrl": build_image_url("w780", best.get("backdrop_path")),
        "overview": best.get("overview"),
    }


@app.get("/health")
def health() -> Dict[str, bool]:
    return {"ok": True}


@app.get("/tmdb-test", response_model=MovieResponse)
def tmdb_test(title: str, year: Optional[str] = None):
    try:
        result = search_tmdb_movie(title, year)
        return {
            "title": result.get("tmdbTitle") or title,
            "year": result.get("tmdbYear") or year,
            **result,
        }
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.post("/search", response_model=MovieResponse)
def search(payload: SearchPayload):
    title = (payload.title or payload.titre or "").strip()
    year = (payload.year or payload.releaseYear or "").strip() or None

    if not title:
        raise HTTPException(
            status_code=400,
            detail="Envoie au minimum 'title' ou 'titre' dans le JSON.",
        )

    try:
        result = search_tmdb_movie(title, year)
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc

    return {
        "title": payload.title or payload.titre or result.get("tmdbTitle"),
        "year": payload.year or payload.releaseYear or result.get("tmdbYear"),
        "relevance": payload.relevance,
        **result,
    }
