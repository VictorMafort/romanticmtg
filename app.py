# -*- coding: utf-8 -*-
"""
Romantic Format Tools - v12 (Tab1 revertida + Deckbuilder com artes estilo Archidekt)
- Tab 1: imagem com badge de legalidade e contador xN; controles abaixo (duas colunas) — atualização imediata
- Tab 2: checker de lista básico
- Tab 3 (NOVO): Deckbuilder com artes em grade, agrupadas por TIPO (Criaturas, Instantâneas, Feitiços, Artefatos, Encantamentos, Planeswalkers, Terrenos, Outros),
  com controles compactos em cada tile e contador por seção, além do total do deck.
"""
import re
import time
import urllib.parse
from collections import deque, defaultdict
from concurrent.futures import ThreadPoolExecutor
import requests
import streamlit as st

# -------------------------
# Sessão HTTP + throttle
# -------------------------
SESSION = requests.Session()
SESSION.headers.update(
    {
        "User-Agent": "RomanticFormatTools/1.7 (+seu_email_ou_site)",
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
                "image": data.get("image_uris", {}).get("small") or data.get("image_uris", {}).get("normal"),
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
        "image": data.get("image_uris", {}).get("small") or data.get("image_uris", {}).get("normal"),
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
# App + CSS
# -------------------------
st.set_page_config(page_title="Romantic Format Tools", page_icon="\U0001F9D9", layout="wide")

st.markdown(
    """
    <style>
    /* Imagem da carta com sombra/cantos */
    [data-testid="stImage"] img, .rf-img{ display:block; width:100%; height:auto; border-radius:10px; box-shadow:0 2px 10px rgba(0,0,0,.12); }

    /* Overlays (Tab 1) */
    .rf-card{ position:relative; border-radius:12px; overflow:hidden; box-shadow:0 2px 10px rgba(0,0,0,.12); }
    .rf-card img.rf-img{ display:block; width:100%; height:auto; }
    .rf-badge-overlay{ position:absolute; left:50%; transform:translateX(-50%); top:40px; padding:4px 10px; border-radius:999px; font-weight:700; font-size:12px; background:rgba(255,255,255,.96); color:#0f172a; box-shadow:0 1px 4px rgba(0,0,0,.18); border:1px solid rgba(0,0,0,.08); pointer-events:none; white-space:nowrap; }
    .rf-success{color:#166534;background:#dcfce7;border-color:#bbf7d0}
    .rf-warning{color:#92400e;background:#fef3c7;border-color:#fde68a}
    .rf-danger{color:#991b1b;background:#fee2e2;border-color:#fecaca}
    .rf-qty-badge{ position:absolute; right:8px; bottom:8px; background:rgba(0,0,0,.65); color:#fff; padding:2px 8px; border-radius:999px; font-weight:800; font-size:12px; border:1px solid rgba(255,255,255,.25); backdrop-filter:saturate(120%) blur(1px); }

    /* Botões pílula */
    div.stButton>button{ width:100%; min-width:0; padding:6px 10px; border-radius:999px; border:1px solid rgba(0,0,0,.10); background:#fff; color:#0f172a; font-weight:700; font-size:13px; line-height:1.2; box-shadow:0 1px 3px rgba(0,0,0,.08); }
    div.stButton>button:hover{ background:#f1f5f9 }

    .row-qty div.stButton>button{ padding:4px 8px; border-radius:10px; font-size:12px }
    .rf-tile-name{ font-size:.86rem; font-weight:600; margin:.25rem 0 .15rem; white-space:nowrap; overflow:hidden; text-overflow:ellipsis }
    .rf-sec-title{ font-size:1.0rem; font-weight:800; margin-top:.75rem }
    .rf-spacer{ height:6px }

    /* Reduz padding lateral das columns para gridear melhor */
    [data-testid="column"]{ padding-left:.35rem; padding-right:.35rem }
    @media (max-width: 1100px){ [data-testid="column"]{ padding-left:.25rem; padding-right:.25rem } }
    @media (max-width: 820px){  [data-testid="column"]{ padding-left:.2rem;  padding-right:.2rem  } }
    </style>
    """,
    unsafe_allow_html=True,
)

st.title("\U0001F9D9 Romantic Format Tools")

tab1, tab2, tab3 = st.tabs(["\U0001F50D Single Card Checker", "\U0001F4E6 Decklist Checker", "\U0001F9D9 Deckbuilder (artes)"])

# Helper: render card HTML (Tab 1)

def render_card_html(img_url: str, nome: str, status_text: str, status_type: str, qty: int) -> str:
    cls = {"success":"rf-success","warning":"rf-warning","danger":"rf-danger"}.get(status_type, "rf-warning")
    return f"""
        <div class='rf-card'>
          <img src='{img_url}' class='rf-img' alt='{nome}'/>
          <div class='rf-badge-overlay {cls}'>{status_text}</div>
          <div class='rf-qty-badge'>x{qty}</div>
        </div>
    """

# -------------------------
# Tab 1 - Single Card Checker (revertido / estável)
# -------------------------
with tab1:
    query = st.text_input("Digite o começo do nome da carta:")
    thumbs = []
    if query.strip():
        sugestoes = buscar_sugestoes(query.strip())
        for nome in sugestoes[:21]:
            data = fetch_card_data(nome)
            if data and data.get("image"):
                status_text, status_type = check_legality(data["name"], data.get("sets", []))
                thumbs.append((data["name"], data["image"], status_text, status_type))

    if thumbs:
        st.caption("\U0001F50E Sugestões:")
        cols_per_row = 3
        for i in range(0, len(thumbs), cols_per_row):
            cols = st.columns(cols_per_row)
            for j, (nome, img, status_text, status_type) in enumerate(thumbs[i:i+cols_per_row]):
                safe_id = re.sub(r"[^a-z0-9_\-]", "-", nome.lower())
                with cols[j]:
                    card_ph = st.empty()
                    qty_before = st.session_state.deck.get(nome, 0)
                    card_ph.markdown(render_card_html(img, nome, status_text, status_type, qty_before), unsafe_allow_html=True)

                    st.markdown('<div class="rf-spacer"></div>', unsafe_allow_html=True)

                    left, right = st.columns([1, 1], gap="small")
                    clicked = False
                    with left:
                        c1, c2 = st.columns([1, 1], gap="small")
                        if c1.button("−1", key=f"m1_{i}_{j}_{safe_id}"):
                            remove_card(nome, 1); clicked=True
                        if c2.button("+1", key=f"p1_{i}_{j}_{safe_id}"):
                            add_card(nome, 1); clicked=True
                    with right:
                        c3, c4 = st.columns([1, 1], gap="small")
                        if c3.button("−4", key=f"m4_{i}_{j}_{safe_id}"):
                            remove_card(nome, 4); clicked=True
                        if c4.button("+4", key=f"p4_{i}_{j}_{safe_id}"):
                            add_card(nome, 4); clicked=True

                    if clicked:
                        qty_after = st.session_state.deck.get(nome, 0)
                        card_ph.markdown(render_card_html(img, nome, status_text, status_type, qty_after), unsafe_allow_html=True)

                    st.markdown('<div class="rf-spacer"></div>', unsafe_allow_html=True)

# -------------------------
# Tab 2 - Decklist Checker (mesmo de antes)
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
# Tab 3 - Deckbuilder (ARTES agrupadas por tipo, estilo Archidekt)
# -------------------------
with tab3:
    st.subheader("\U0001F9D9\u200d♂️ Seu Deck — artes agrupadas por tipo")

    # Parâmetros de visual
    cols_per_row = st.slider("Colunas por linha", 4, 8, 6, help="Quantidade de colunas na grade de artes")
    show_names = st.toggle("Mostrar nomes abaixo da arte", value=True)

    total_cartas = sum(st.session_state.deck.values())
    st.markdown(f"**Total de cartas:** {total_cartas}")

    if not st.session_state.deck:
        st.info("Seu deck está vazio. Adicione cartas pela Aba 1 ou cole uma lista na Aba 2.")
    else:
        # Carrega dados de todas as cartas do deck (paralelo)
        names_list = sorted(list(st.session_state.deck.keys()), key=lambda x: x.lower())

        def load_one(nm):
            data = fetch_card_data(nm)
            return (nm, st.session_state.deck.get(nm, 0), data.get("type", "") if data else "", data.get("image") if data else None)

        with st.spinner("Carregando artes..."):
            with ThreadPoolExecutor(max_workers=10) as ex:
                deck_items = list(ex.map(load_one, names_list))

        # Função de bucket por TIPO
        def bucket(type_line: str) -> str:
            tl = type_line or ""
            if "Land" in tl:
                return "Terrenos"
            if "Creature" in tl:
                return "Criaturas"
            if "Instant" in tl:
                return "Instantâneas"
            if "Sorcery" in tl:
                return "Feitiços"
            if "Planeswalker" in tl:
                return "Planeswalkers"
            if "Enchantment" in tl:
                return "Encantamentos"
            if "Artifact" in tl:
                return "Artefatos"
            return "Outros"

        buckets = defaultdict(list)
        for name, qty, type_line, img in deck_items:
            buckets[bucket(type_line)].append((name, qty, type_line, img))

        order = ["Criaturas","Instantâneas","Feitiços","Artefatos","Encantamentos","Planeswalkers","Terrenos","Outros"]

        for sec in order:
            if sec not in buckets:
                continue
            sec_list = buckets[sec]
            sec_qty_sum = sum(q for _, q, _, _ in sec_list)
            st.markdown(f"<div class='rf-sec-title'>{sec} — {sec_qty_sum}</div>", unsafe_allow_html=True)

            # Grade por linhas
            for i in range(0, len(sec_list), cols_per_row):
                row = sec_list[i:i+cols_per_row]
                cols = st.columns(len(row))
                for c, (name, qty, type_line, img) in zip(cols, row):
                    with c:
                        # Arte
                        if img:
                            st.image(img, use_container_width=True)
                        else:
                            st.empty()

                        # Nome (opcional)
                        if show_names:
                            st.markdown(f"<div class='rf-tile-name' title='{name}'>{name}</div>", unsafe_allow_html=True)

                        # Controles compactos + contador à direita
                        st.markdown('<div class="row-qty">', unsafe_allow_html=True)
                        g1, g2, g3, g4, label = st.columns([1,1,1,1,2])
                        if g1.button("−1", key=f"db_m1_{sec}_{i}_{name}"):
                            remove_card(name, 1)
                        if g2.button("+1", key=f"db_p1_{sec}_{i}_{name}"):
                            add_card(name, 1)
                        if g3.button("−4", key=f"db_m4_{sec}_{i}_{name}"):
                            remove_card(name, 4)
                        if g4.button("+4", key=f"db_p4_{sec}_{i}_{name}"):
                            add_card(name, 4)
                        label.markdown(f"**x{st.session_state.deck.get(name, 0)}**")
                        st.markdown('</div>', unsafe_allow_html=True)

            st.markdown("---")

        # Exportar deck
        export_lines = [f"{qty}x {name}" for name, qty in sorted(st.session_state.deck.items(), key=lambda x: x[0].lower())]
        export_text = "\n".join(export_lines)
        st.download_button("⬇️ Baixar deck (.txt)", data=export_text, file_name="deck.txt", mime="text/plain")
