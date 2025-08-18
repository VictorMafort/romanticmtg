# -*- coding: utf-8 -*-
"""
Romantic Format Tools – versão sem navegação por URL
Troca os links <a href> por st.button para adicionar/remover cartas
sem abrir nova aba/guia. Mantém as 3 abas: Single Card Checker,
Decklist Checker e Deckbuilder.
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
        # identifique seu app (pode trocar por seu email/site)
        "User-Agent": "RomanticFormatTools/0.2 (+seu_email_ou_site)",
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
    "M13"
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
                "image": data.get("image_uris", {}).get("small"),
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

def add_card(card_name, qty=1):
    st.session_state.deck[card_name] = st.session_state.deck.get(card_name, 0) + qty

def remove_card(card_name, qty=1):
    if card_name in st.session_state.deck:
        st.session_state.deck[card_name] -= qty
        if st.session_state.deck[card_name] <= 0:
            del st.session_state.deck[card_name]

# -------------------------
# App
# -------------------------
st.set_page_config(page_title="Romantic Format Tools", page_icon="🧙", layout="centered")

st.title("🧙 Romantic Format Tools")

tab1, tab2, tab3 = st.tabs(["🔍 Single Card Checker", "📦 Decklist Checker", "🧙 Deckbuilder"])

# -------------------------
# Tab 1 – Single Card Checker (sem navegação por URL)
# -------------------------
with tab1:
    query = st.text_input("Digite o começo do nome da carta:", value="")

    thumbs = []
    if query.strip():
        sugestoes = buscar_sugestoes(query.strip())
        for nome in sugestoes[:21]:  # mostra até 21 sugestões
            data = fetch_card_data(nome)
            if data and data.get("image"):
                status_text, status_type = check_legality(
                    data["name"], data.get("sets", [])
                )
                thumbs.append((nome, data["image"], status_text, status_type))

    if thumbs:
        st.caption("🔎 Sugestões:")
        cols_per_row = 3
        for i in range(0, len(thumbs), cols_per_row):
            cols = st.columns(cols_per_row)
            for j, (nome, img, status_text, status_type) in enumerate(thumbs[i : i + cols_per_row]):
                with cols[j]:
                    st.image(img, caption=nome, use_container_width=True)
                    # badge de legalidade
                    color = {
                        "success": "#166534",
                        "warning": "#92400e",
                        "danger": "#991b1b",
                    }.get(status_type, "#92400e")
                    st.markdown(
                        f"<span style='font-weight:700;color:{color}'>" + status_text + "</span>",
                        unsafe_allow_html=True,
                    )

                    # linha de botões
                    bcols = st.columns(4)
                    if bcols[0].button("−4", key=f"minus4_{i}_{j}_{nome}"):
                        remove_card(nome, 4)
                        st.session_state.last_change = nome
                        st.session_state.last_action = "remove"
                    if bcols[1].button("−1", key=f"minus1_{i}_{j}_{nome}"):
                        remove_card(nome, 1)
                        st.session_state.last_change = nome
                        st.session_state.last_action = "remove"
                    if bcols[2].button("+1", key=f"plus1_{i}_{j}_{nome}"):
                        add_card(nome, 1)
                        st.session_state.last_change = nome
                        st.session_state.last_action = "add"
                    if bcols[3].button("+4", key=f"plus4_{i}_{j}_{nome}"):
                        add_card(nome, 4)
                        st.session_state.last_change = nome
                        st.session_state.last_action = "add"

# -------------------------
# Tab 2 – Decklist Checker
# -------------------------
with tab2:
    st.write("Cole sua decklist abaixo (uma carta por linha):")
    deck_input = st.text_area("Decklist", height=300)

    def process_line(line: str):
        # remove comentários no fim da linha e espaços
        line = re.sub(r'#.*$', '', line).strip()
        if not line:
            return None  # ignora linhas vazias após limpeza
        # Formatos aceitos: "SB: 3x Nome", "4x Nome", "4 Nome", "Nome"
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
        # remove linhas None (comentários/vazias)
        results = [r for r in results if r]

        st.subheader("📋 Resultados:")
        for name, qty, status_text, status_type, _ in results:
            color = {"success": "green", "warning": "orange", "danger": "red"}[status_type]
            st.markdown(
                f"{qty}x {name}: " f"<span style='color:{color}'>" f"{status_text}</span>",
                unsafe_allow_html=True,
            )

        # Botão para adicionar toda a decklist ao deckbuilder
        if st.button("📥 Adicionar lista ao Deckbuilder"):
            for name, qty, status_text, status_type, _ in results:
                if status_type != "danger":  # só adiciona se não for erro
                    st.session_state.deck[name] = st.session_state.deck.get(name, 0) + qty
            st.success("Decklist adicionada ao Deckbuilder!")

# -------------------------
# Tab 3 – Deckbuilder
# -------------------------
with tab3:
    st.subheader("🧙‍♂️ Seu Deck Atual")

    # Total de cartas no deck
    total_cartas = sum(st.session_state.deck.values())
    st.markdown(f"**Total de cartas:** {total_cartas}")

    # Guardar a última carta alterada e a ação (add/remove)
    if "last_change" not in st.session_state:
        st.session_state.last_change = None
    if "last_action" not in st.session_state:
        st.session_state.last_action = None

    if not st.session_state.deck:
        st.info("Seu deck está vazio. Adicione cartas pela Aba 1 ou cole uma lista na Aba 2.")
    else:
        for card, qty in sorted(list(st.session_state.deck.items()), key=lambda x: x[0].lower()):
            col1, col2, col3, col4 = st.columns([4, 1, 1, 1])
            # Nome
            col1.markdown(f"**{card}**")
            # Quantidade com highlight se foi a última alterada
            if st.session_state.last_change == card:
                if st.session_state.last_action == "add":
                    col2.markdown(
                        f"<span style='color:green;font-weight:bold;'>x{qty}</span>",
                        unsafe_allow_html=True,
                    )
                elif st.session_state.last_action == "remove":
                    col2.markdown(
                        f"<span style='color:red;font-weight:bold;'>x{qty}</span>",
                        unsafe_allow_html=True,
                    )
                else:
                    col2.markdown(f"**x{qty}**")
            else:
                col2.markdown(f"**x{qty}**")
            # Botão de remover
            if col3.button("➖", key=f"minus_{card}"):
                remove_card(card, 1)
                st.session_state.last_change = card
                st.session_state.last_action = "remove"
            # Botão de adicionar
            if col4.button("➕", key=f"plus_{card}"):
                add_card(card, 1)
                st.session_state.last_change = card
                st.session_state.last_action = "add"
            st.markdown("---")

        # Botão para limpar deck
        if st.button("🗑️ Limpar Deck", key="clear_deck"):
            st.session_state.deck.clear()
            st.success("Deck limpo!")
            st.session_state.last_change = None
            st.session_state.last_action = None
        st.markdown("---")

        # --- Exportar deck como .txt ---
        export_lines = [
            f"{qty}x {name}" for name, qty in sorted(st.session_state.deck.items(), key=lambda x: x[0].lower())
        ]
        export_text = "\n".join(export_lines)
        st.download_button(
            "⬇️ Baixar deck (.txt)",
            data=export_text,
            file_name="deck.txt",
            mime="text/plain",
        )
        st.caption("Dica: use a Aba 1 para pesquisar cartas e ajustá-las rapidamente no deck.")
