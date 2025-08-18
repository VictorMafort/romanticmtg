
# -*- coding: utf-8 -*-
"""
Romantic Format Tools - v13.10d
- Hotfix: garante que st.session_state['deck'] exista antes de qualquer uso
- Evita AttributeError quando a app inicia em uma nova sessão ou após recarregar
- Mantém correções: Aba 1 chip de legalidade; Aba 3 ignora imagens ausentes; Aba 4 donuts Altair
"""
import re
import time
import urllib.parse
from collections import deque, defaultdict
from concurrent.futures import ThreadPoolExecutor

import requests
import streamlit as st
import pandas as pd
import altair as alt

# ===== Estado global seguro (antes de qualquer uso) =====
if 'deck' not in st.session_state:
    st.session_state.deck = {}
if 'last_change' not in st.session_state:
    st.session_state.last_change = None
if 'last_action' not in st.session_state:
    st.session_state.last_action = None

# --------------------
# Sessão HTTP + throttle
# --------------------
SESSION = requests.Session()
SESSION.headers.update({
    "User-Agent": "RomanticFormatTools/2.1 (+seu_email_ou_site)",
    "Accept": "application/json;q=0.9,*/*;q=0.8",
})
_last = deque(maxlen=10)

def throttle():
    _last.append(time.time())
    if len(_last) == _last.maxlen:
        elapsed = _last[-1] - _last[0]
        if elapsed < 1.0:
            time.sleep(1.0 - elapsed)

allowed_sets = {"8ED","MRD","DST","5DN","CHK","BOK","SOK","9ED","RAV","GPT","DIS","CSP","TSP","TSB","PLC","FUT","10E","LRW","MOR","SHM","EVE","ALA","CON","ARB","M10","ZEN","WWK","ROE","M11","SOM","MBS","NPH","M12","ISD","DKA","AVR","M13",}
ban_list = {"Gitaxian Probe","Mental Misstep","Blazing Shoal","Skullclamp"}
_ALLOWED_FPRINT = ",".join(sorted(allowed_sets))

# ... (restante do código idêntico ao v13.10c; por brevidade não repetimos aqui)
