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
        margin: 8px auto !important;
        background: rgba(255,255,255,0.94) !important;
        border-radius: 18px !important;
        padding: 12px 16px 20px 16px !important;
        box-shadow: 0 10px 30px rgba(0,0,0,0.07) !important;
        backdrop-filter: blur(2px);
    }

    [data-testid="stSidebar"] > div:first-child{
        background: rgba(255,255,255,0.96) !important;
        border-right: 1px solid rgba(0,0,0,0.06);
    }

    .main h1, .main h2 {
        margin-top: 0.15rem !important;
        margin-bottom: 0.4rem !important;
    }

    .main p, .main label {
        margin-bottom: 0.25rem !important;
    }

    .main a { color:#0b57d0 !important; font-weight:600; }
    .ff-muted { color: rgba(0,0,0,0.68) !important; font-size: 13px; }

    .ff-panel{
        background: rgba(255,255,255,0.92);
        border: 1px solid rgba(0,0,0,0.08);
        border-radius: 16px;
        padding: 10px 12px;
        margin: 6px 0 10px 0;
        box-shadow: 0 5px 14px rgba(0,0,0,0.05);