# -*- coding: utf-8 -*-
"""
Romantic Format Tools - v5 (overlay + contador + flash sem deslocar layout)
- Badge de legalidade sobre a arte (offset para não cobrir o nome)
- Contador de quantidade do deck como chip no canto inferior direito da arte
- Efeito de feedback visual nos botões (verde ao adicionar, vermelho ao remover)
  sem deslocar layout (marcador zero-dimensões + animação no próprio botão)
"""
import re
import time
import urllib.parse
from collections import deque
from concurrent.futures import ThreadPoolExecutor
import requests
import streamlit as st

# -------------------------
# Sessão HTTP + throttle
# -------------------------
SESSION = requests.Session()
SESSION.headers.update(
    {
        "User-Agent": "RomanticFormatTools/1.0 (+seu_email_ou_site)",
        "Accept": "application/json;q=0.9,*/*;q=0.8",
    }
)
_last = deque(maxlen=10)

def throttle():
    _last.append(time.time())
    if len(_last) == _last.maxlen:
        elapsed = _last[-1] - _last[0]
        if elapsed < 1.0:
            time.sleep(1.0 - elapsed)

# -------------------------
# Config & listas
# -------------------------
allowed_sets = {
    "8ED","MRD","DST","5DN",
    "CHK","BOK","SOK",
    "9ED",
    "RAV","GPT","DIS",
    "CSP","TSP","TSB","PLC","FUT",
    "10E",
    "LRW","MOR","SHM","EVE",
    "ALA","CON","ARB",
    "M10",
    "ZEN","WWK","ROE",
    "M11",
    "SOM","MBS","NPH",
    "M12",
    "ISD","DKA","AVR",
    "M13",
}
ban_list = {"Gitaxian Probe","Mental Misstep","Blazing Shoal","Skullclamp"}

# -------------------------
# Utilidades
# -------------------------

def buscar_sugestoes(query: str):
    q = query.strip()
    if len(q) < 2:
        return []
    url = f"https://api.scryfall.com/cards/autocomplete?q={urllib.parse.quote(q)}"
    try:
        throttle()
        r = SESSION.get(url, timeout=8)
        if r.ok:
            return r.json().get("data", [])
    except Exception:
        pass
    return []

@st.cache_data(show_spinner=False)
def fetch_card_data(card_name):
    safe_name = urllib.parse.quote(card_name)
    url = f"https://api.scryfall.com/cards/named?fuzzy={safe_name}"
    try:
        throttle()
        resp = SESSION.get(url, timeout=8)
    except Exception:
        return None
    if resp.status_code != 200:
        return None
    data = resp.json()
    if "prints_search_uri" not in data:
        return None

    all_sets = set()

    # Busca rápida limitada aos sets permitidos
    set_query = " OR ".join(s.lower() for s in allowed_sets)
    quick_url = f"https://api.scryfall.com/cards/search?q=!%22{safe_name}%22+e:({set_query})"
    try:
        throttle()
        quick_resp = SESSION.get(quick_url, timeout=8)
        if quick_resp.status_code == 200 and quick_resp.json().get("total_cards", 0) > 0:
            for c in quick_resp.json().get("data", []):
                if "Token" not in c.get("type_line", ""):
                    all_sets.add(c["set"].upper())
            return {
                "name": data.get("name", ""),
                "sets": all_sets,
                "image": data.get("image_uris", {}).get("normal") or data.get("image_uris", {}).get("small"),
                "type": data.get("type_line", ""),
                "mana": data.get("mana_cost", ""),
                "oracle": data.get("oracle_text", ""),
            }
    except Exception:
        pass

    # Busca completa por prints (early stop se achar set permitido)
    next_page = data["prints_search_uri"]
    while next_page:
        try:
            throttle()
            p = SESSION.get(next_page, timeout=8)
            if p.status_code != 200:
                break
            j = p.json()
            for c in j["data"]:
                if "Token" not in c.get("type_line", ""):
                    set_code = c["set"].upper()
                    all_sets.add(set_code)
                    if set_code in allowed_sets:
                        next_page = None
                        break
            else:
                next_page = j.get("next_page")
        except Exception:
            break
    return {
        "name": data.get("name", ""),
        "sets": all_sets,
        "image": data.get("image_uris", {}).get("normal"),
        "type": data.get("type_line", ""),
        "mana": data.get("mana_cost", ""),
        "oracle": data.get("oracle_text", ""),
    }

def check_legality(name, sets):
    if name in ban_list:
        return "❌ Banned", "danger"
    if sets & allowed_sets:
        return "✅ Legal", "success"
    return "⚠️ Not Legal", "warning"

# -------------------------
# Estado do deck
# -------------------------
if "deck" not in st.session_state:
    st.session_state.deck = {}
if "last_change" not in st.session_state:
    st.session_state.last_change = None
if "last_action" not in st.session_state:
    st.session_state.last_action = None

def add_card(card_name, qty=1):
    st.session_state.deck[card_name] = st.session_state.deck.get(card_name, 0) + qty
    st.session_state.last_change = card_name
    st.session_state.last_action = "add"

def remove_card(card_name, qty=1):
    if card_name in st.session_state.deck:
        st.session_state.deck[card_name] -= qty
        if st.session_state.deck[card_name] <= 0:
            del st.session_state.deck[card_name]
    st.session_state.last_change = card_name
    st.session_state.last_action = "remove"

# -------------------------
# App
# -------------------------
st.set_page_config(page_title="Romantic Format Tools", page_icon="\U0001F9D9", layout="centered")

# CSS (overlay + contador + flash sem deslocar)
st.markdown(
    """
    <style>
    /* Card com overlay e contador */
    .rf-card{ position:relative; border-radius:12px; overflow:hidden; box-shadow:0 2px 10px rgba(0,0,0,.12); }
    .rf-card img.rf-img{ display:block; width:100%; height:auto; }

    /* Badge de legalidade sobre a arte */
    .rf-badge-overlay{
        position:absolute; left:50%; transform:translateX(-50%);
        top: 40px;
        padding: 4px 10px; border-radius:999px; font-weight:700; font-size:12px;
        background: rgba(255,255,255,.96); color:#0f172a;
        box-shadow: 0 1px 4px rgba(0,0,0,.18); border:1px solid rgba(0,0,0,.08);
        pointer-events:none; white-space:nowrap;
    }
    .rf-success{color:#166534;background:#dcfce7;border-color:#bbf7d0}
    .rf-warning{color:#92400e;background:#fef3c7;border-color:#fde68a}
    .rf-danger{color:#991b1b;background:#fee2e2;border-color:#fecaca}

    /* Contador no canto inferior direito da arte */
    .rf-qty-badge{
        position:absolute; right:8px; bottom:8px;
        background: rgba(0,0,0,.65); color:#fff;
        padding:2px 8px; border-radius:999px; font-weight:800; font-size:12px;
        border:1px solid rgba(255,255,255,.25); backdrop-filter:saturate(120%) blur(1px);
    }

    /* Botões-pílula */
    div.stButton>button{
        width:100%; min-width:0; padding:6px 10px; border-radius:999px;
        border:1px solid rgba(0,0,0,.10); background:#fff; color:#0f172a;
        font-weight:700; font-size:13px; line-height:1.2; box-shadow:0 1px 3px rgba(0,0,0,.08);
        transition: background .15s ease, box-shadow .15s ease, filter .15s ease;
    }
    div.stButton>button:hover{ background:#f1f5f9 }

    /* Marcadores de flash que não ocupam espaço (evita deslocar layout) */
    .rf-flash-marker{ position:absolute; width:0; height:0; overflow:hidden; }

    /* Animações aplicadas no botão seguinte ao marcador */
    @keyframes rfFlashGreen{ 0%{filter:drop-shadow(0 0 0 #86efac)} 30%{filter:drop-shadow(0 0 6px #86efac)} 100%{filter:none} }
    @keyframes rfFlashRed{ 0%{filter:drop-shadow(0 0 0 #fca5a5)} 30%{filter:drop-shadow(0 0 6px #fca5a5)} 100%{filter:none} }
    .rf-flash-add + div button{ animation: rfFlashGreen .6s ease-out 1 }
    .rf-flash-rem + div button{ animation: rfFlashRed .6s ease-out 1 }

    /* Acessibilidade: desativa animação se usuário preferir menos movimento */
    @media (prefers-reduced-motion: reduce){
      .rf-flash-add + div button, .rf-flash-rem + div button{ animation: none }
    }

    .rf-spacer{height:8px}

    /* Responsivo */
    @media (max-width:1100px){
        .rf-badge-overlay{ top:36px; font-size:11.5px; padding:3px 9px }
        .rf-qty-badge{ font-size:11.5px; padding:2px 7px }
        div.stButton>button{ font-size:12px; padding:5px 10px }
    }
    @media (max-width:820px){
        .rf-badge-overlay{ top:34px; font-size:11px; padding:3px 8px }
        .rf-qty-badge{ font-size:11px; padding:2px 7px }
        div.stButton>button{ font-size:11.5px; padding:4px 9px }
        [data-testid="column"]{ padding-left:.25rem; padding-right:.25rem }
    }
    @media (max-width:640px){
        .rf-badge-overlay{ top:30px; font-size:10.5px; padding:2px 7px }
        .rf-qty-badge{ font-size:10.5px; padding:2px 6px }
        div.stButton>button{ font-size:11px; padding:3px 8px }
    }
    @media (max-width:480px){
        .rf-badge-overlay{ top:28px; font-size:10px; padding:2px 6px }
        .rf-qty-badge{ font-size:10px; padding:2px 6px }
        div.stButton>button{ font-size:10.5px; padding:3px 7px }
    }
    </style>
    """,
    unsafe_allow_html=True,
)

st.title("\U0001F9D9 Romantic Format Tools")

tab1, tab2, tab3 = st.tabs(["\U0001F50D Single Card Checker", "\U0001F4E6 Decklist Checker", "\U0001F9D9 Deckbuilder"])

# -------------------------
# Tab 1 - Single Card Checker
# -------------------------
with tab1:
    query = st.text_input("Digite o começo do nome da carta:", value="")
    thumbs = []
    if query.strip():
        sugestoes = buscar_sugestoes(query.strip())
        for nome in sugestoes[:21]:
            data = fetch_card_data(nome)
            if data and data.get("image"):
                status_text, status_type = check_legality(data["name"], data.get("sets", []))
                thumbs.append((data["name"], data["image"], status_text, status_type))

    def _badge_class(status_type: str) -> str:
        return {"success":"rf-success","warning":"rf-warning","danger":"rf-danger"}.get(status_type, "rf-warning")

    if thumbs:
        st.caption("\U0001F50E Sugestões:")
        cols_per_row = 3
        for i in range(0, len(thumbs), cols_per_row):
            cols = st.columns(cols_per_row)
            for j, (nome, img, status_text, status_type) in enumerate(thumbs[i:i+cols_per_row]):
                safe_id = re.sub(r"[^a-z0-9_\-]", "-", nome.lower())
                qty = st.session_state.deck.get(nome, 0)
                with cols[j]:
                    # Card com overlays (legalidade + contador)
                    st.markdown(
                        f"""
                        <div class='rf-card'>
                          <img src='{img}' class='rf-img' alt='{nome}'/>
                          <div class='rf-badge-overlay {_badge_class(status_type)}'>{status_text}</div>
                          <div class='rf-qty-badge'>x{qty}</div>
                        </div>
                        """,
                        unsafe_allow_html=True,
                    )

                    st.markdown('<div class="rf-spacer"></div>', unsafe_allow_html=True)

                    left, mid, right = st.columns([2.2, 0.6, 2.2], gap="small")

                    with left:
                        c1, c2 = st.columns([1, 1], gap="small")
                        with c1:
                            if st.session_state.get("last_action") == "remove" and st.session_state.get("last_change") == nome:
                                st.markdown('<span class="rf-flash-marker rf-flash-rem"></span>', unsafe_allow_html=True)
                            if st.button("−1", key=f"m1_{i}_{j}_{safe_id}"):
                                remove_card(nome, 1)
                        with c2:
                            if st.session_state.get("last_action") == "add" and st.session_state.get("last_change") == nome:
                                st.markdown('<span class="rf-flash-marker rf-flash-add"></span>', unsafe_allow_html=True)
                            if st.button("+1", key=f"p1_{i}_{j}_{safe_id}"):
                                add_card(nome, 1)

                    with mid:
                        st.write("")

                    with right:
                        c3, c4 = st.columns([1, 1], gap="small")
                        with c3:
                            if st.session_state.get("last_action") == "remove" and st.session_state.get("last_change") == nome:
                                st.markdown('<span class="rf-flash-marker rf-flash-rem"></span>', unsafe_allow_html=True)
                            if st.button("−4", key=f"m4_{i}_{j}_{safe_id}"):
                                remove_card(nome, 4)
                        with c4:
                            if st.session_state.get("last_action") == "add" and st.session_state.get("last_change") == nome:
                                st.markdown('<span class="rf-flash-marker rf-flash-add"></span>', unsafe_allow_html=True)
                            if st.button("+4", key=f"p4_{i}_{j}_{safe_id}"):
                                add_card(nome, 4)

                    st.markdown('<div class="rf-spacer"></div>', unsafe_allow_html=True)

# -------------------------
# Tab 2 - Decklist Checker
# -------------------------
with tab2:
    st.write("Cole sua decklist abaixo (uma carta por linha):")
    deck_input = st.text_area("Decklist", height=300)

    def process_line(line: str):
        line = re.sub(r'#.*$', '', line).strip()
        if not line:
            return None
        m = re.match(r'^(SB:)?\s*(\d+)?\s*x?\s*(.+)$', line, re.IGNORECASE)
        if not m:
            return (line, 1, "❌ Card not found or API error", "danger", None)
        qty = int(m.group(2) or 1)
        name_guess = m.group(3).strip()
        card = fetch_card_data(name_guess)
        if not card:
            return (line, qty, "❌ Card not found or API error", "danger", None)
        status_text, status_type = check_legality(card["name"], card["sets"])
        return (card["name"], qty, status_text, status_type, card["sets"])

    if deck_input.strip():
        lines = [l for l in deck_input.splitlines()]
        with st.spinner("Checando decklist..."):
            with ThreadPoolExecutor(max_workers=8) as executor:
                results = list(executor.map(process_line, lines))
            results = [r for r in results if r]

        st.subheader("\U0001F4CB Resultados:")
        for name, qty, status_text, status_type, _ in results:
            color = {"success": "green", "warning": "orange", "danger": "red"}[status_type]
            st.markdown(f"{qty}x {name}: <span style='color:{color}'>{status_text}</span>", unsafe_allow_html=True)

        if st.button("\U0001F4E5 Adicionar lista ao Deckbuilder"):
            for name, qty, status_text, status_type, _ in results:
                if status_type != "danger":
                    st.session_state.deck[name] = st.session_state.deck.get(name, 0) + qty
            st.success("Decklist adicionada ao Deckbuilder!")

# -------------------------
# Tab 3 - Deckbuilder
# -------------------------
with tab3:
    st.subheader("\U0001F9D9\u200d♂️ Seu Deck Atual")
    total_cartas = sum(st.session_state.deck.values())
    st.markdown(f"**Total de cartas:** {total_cartas}")

    if not st.session_state.deck:
        st.info("Seu deck está vazio. Adicione cartas pela Aba 1 ou cole uma lista na Aba 2.")
    else:
        for card, qty in sorted(list(st.session_state.deck.items()), key=lambda x: x[0].lower()):
            col1, col2, col3, col4 = st.columns([4, 1, 1, 1])
            col1.markdown(f"**{card}**")
            col2.markdown(f"**x{qty}**")
            if col3.button("➖", key=f"minus_{card}"):
                remove_card(card, 1)
            if col4.button("➕", key=f"plus_{card}"):
                add_card(card, 1)
            st.markdown("---")

    if st.button("\U0001F5D1️ Limpar Deck", key="clear_deck"):
        st.session_state.deck.clear()
        st.success("Deck limpo!")
        st.session_state.last_change = None
        st.session_state.last_action = None

    st.markdown("---")
    export_lines = [f"{qty}x {name}" for name, qty in sorted(st.session_state.deck.items(), key=lambda x: x[0].lower())]
    export_text = "\n".join(export_lines)
    st.download_button("⬇️ Baixar deck (.txt)", data=export_text, file_name="deck.txt", mime="text/plain")
