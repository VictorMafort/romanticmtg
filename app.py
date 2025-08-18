import streamlit as st
import requests
import urllib.parse
from concurrent.futures import ThreadPoolExecutor
import re

# --- Sessão HTTP compartilhada + headers + throttle da Scryfall ---
import time
from collections import deque

SESSION = requests.Session()
SESSION.headers.update({
    # identifique seu app (pode trocar por seu email/site)
    "User-Agent": "RomanticFormatTools/0.1 (+seu_email_ou_site)",
    "Accept": "application/json;q=0.9,*/*;q=0.8",
})

# throttling simples para respeitar ~10 req/s
_last = deque(maxlen=10)
def throttle():
    _last.append(time.time())
    if len(_last) == _last.maxlen:
        elapsed = _last[-1] - _last[0]
        if elapsed < 1.0:
            time.sleep(1.0 - elapsed)

# =========================
# Config & listas
# =========================
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

# =========================
# Utilidades
# =========================

def buscar_sugestoes(query: str):
    q = query.strip()
    if len(q) < 2:
        return []
    url = f"https://api.scryfall.com/cards/autocomplete?q={urllib.parse.quote(q)}"
    try:
        throttle()
        r = SESSION.get(url, timeout=8)
        if r.ok:
            # por padrão include_extras=false (tokens e afins não entram)
            return r.json().get("data", [])
    except Exception:
        pass
    return []

@st.cache_data(show_spinner=False)
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
                "oracle": data.get("oracle_text", "")
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
        "oracle": data.get("oracle_text", "")
    }


def check_legality(name, sets):
    if name in ban_list:
        return "❌ Banned", "danger"
    if sets & allowed_sets:
        return "✅ Legal", "success"
    return "⚠️ Not Legal", "warning"

# =========================
# App
# =========================
st.set_page_config(page_title="Romantic Format Tools", page_icon="🧙", layout="centered")

st.markdown("""
<style>
.rf-card {
  position: relative;
  border-radius: 10px;
  overflow: hidden;
  box-shadow: 0 2px 10px rgba(0,0,0,.12);
}
.rf-img {
  display: block;
  width: 100%;
  height: auto;
}

/* Gradiente para dar contraste em topo/rodapé */
.rf-gradient {
  position: absolute;
  inset: 0;
  background: linear-gradient(
    to bottom,
    rgba(0,0,0,0.40) 0%,
    rgba(0,0,0,0.00) 38%,
    rgba(0,0,0,0.00) 62%,
    rgba(0,0,0,0.50) 100%
  );
  opacity: 0;
  transition: opacity .18s ease;
  pointer-events: none;
}

/* Containers de topo e rodapé (ocultos por padrão) */
.rf-top, .rf-bottom {
  position: absolute;
  left: 8px; right: 8px;
  display: flex;
  align-items: center;
  opacity: 0;
  transform: translateY(-6px);
  transition: opacity .18s ease, transform .18s ease;
  pointer-events: none;
}
.rf-top { top: 8px; justify-content: flex-start; }
.rf-bottom {
  bottom: 8px;
  justify-content: space-between;
  transform: translateY(6px);
}

/* Mostra no hover */
.rf-card:hover .rf-gradient { opacity: 1; }
.rf-card:hover .rf-top,
.rf-card:hover .rf-bottom {
  opacity: 1;
  transform: translateY(0);
  pointer-events: auto;
}

/* Badge de legalidade */
.rf-badge {
  display: inline-block;
  padding: 4px 10px;
  border-radius: 999px;
  font-weight: 700;
  font-size: .82rem;
  background: rgba(255,255,255,.92);
  color: #0f172a;
  box-shadow: 0 1px 4px rgba(0,0,0,.15);
  border: 1px solid rgba(0,0,0,.08);
}
.rf-success { color:#166534; background:#dcfce7; border-color:#bbf7d0; }
.rf-warning { color:#92400e; background:#fef3c7; border-color:#fde68a; }
.rf-danger  { color:#991b1b; background:#fee2e2; border-color:#fecaca; }

/* Pílulas de botões */
.rf-pill {
  display: inline-flex;
  gap: 6px;
  background: rgba(255,255,255, .92);
  border: 1px solid rgba(0,0,0,.12);
  border-radius: 999px;
  padding: 4px 6px;
  box-shadow: 0 1px 4px rgba(0,0,0,.15);
}
.rf-btn {
  display:inline-block;
  min-width: 34px;
  text-align:center;
  padding: 2px 8px;
  border-radius: 999px;
  font-weight: 800;
  color: #0f172a;
  text-decoration: none;
  background: white;
  border: 1px solid rgba(0,0,0,.08);
}
.rf-btn:hover { background: #f1f5f9; }

/* Acessibilidade: em dispositivos touch (sem hover), manter visível */
@media (hover: none) and (pointer: coarse) {
  .rf-gradient { opacity: 1; }
  .rf-top, .rf-bottom {
    opacity: 1;
    transform: none;
    pointer-events: auto;
  }
}
</style>
""", unsafe_allow_html=True)



# Estado do deck
if "deck" not in st.session_state:
    st.session_state.deck = {}

def add_card(card_name, qty=1):
    st.session_state.deck[card_name] = st.session_state.deck.get(card_name, 0) + qty

def remove_card(card_name, qty=1):
    if card_name in st.session_state.deck:
        st.session_state.deck[card_name] -= qty
        if st.session_state.deck[card_name] <= 0:
            del st.session_state.deck[card_name]

st.title("🧙 Romantic Format Tools")
tab1, tab2, tab3 = st.tabs(["🔍 Single Card Checker", "📦 Decklist Checker", "🧙 Deckbuilder"])

# Captura de clique via query param (?pick=Nome&delta=±1/±4)
picked = None
try:
    params = st.query_params
    pick  = params.get("pick")
    delta = params.get("delta")

    if pick and delta:
        try:
            d = int(delta)
        except Exception:
            d = 0

        if d > 0:
            add_card(pick, d)
            st.session_state.last_change = pick
            st.session_state.last_action = "add"
        elif d < 0:
            remove_card(pick, -d)
            st.session_state.last_change = pick
            st.session_state.last_action = "remove"

        # limpa a URL para evitar repetição ao recarregar
        st.query_params.clear()

    elif pick:
        picked = pick
        st.query_params.clear()

except Exception:
    pass

	
# =========================
# Tab 1 - Single Card Checker
# =========================
with tab1:
    query = st.text_input(
        "Digite o começo do nome da carta:",
        value=picked or ""
    )
    card_input = picked or None

    # Sempre inicialize
    thumbs = []

    if query.strip():
        sugestoes = buscar_sugestoes(query.strip())  # busca na API Scryfall

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

    from urllib.parse import quote

    def _badge_class(status_type: str) -> str:
        return {
            "success": "rf-success",
            "warning": "rf-warning",
            "danger":  "rf-danger",
        }.get(status_type, "rf-warning")

    for i in range(0, len(thumbs), cols_per_row):
        cols = st.columns(cols_per_row)

        for j, (nome, img, status_text, status_type) in enumerate(thumbs[i:i+cols_per_row]):
            with cols[j]:
                pickq = quote(nome)

                html = f"""
                <div class="rf-card">
                  <img src="{img}" class="rf-img" alt="{nome}"/>
                  <div class="rf-gradient"></div>

                  <!-- Topo: legalidade (aparece no hover) -->
                  <div class="rf-top">
                    <span class="rf-badge {_badge_class(status_type)}">{status_text}</span>
                  </div>

                  <!-- Rodapé: duas pílulas (-1/+1) e (-4/+4), aparecem no hover -->
                  <div class="rf-bottom">
                    <div class="rf-pill">
                      <a class="rf-btn" href="?pick={pickq}&delta=-1">-1</a>
                      <a class="rf-btn" href="?pick={pickq}&delta=+1">+1</a>
                    </div>
                    <div class="rf-pill">
                      <a class="rf-btn" href="?pick={pickq}&delta=-4">-4</a>
                      <a class="rf-btn" href="?pick={pickq}&delta=+4">+4</a>
                    </div>
                  </div>
                </div>
                """
                st.markdown(html, unsafe_allow_html=True)


# =========================
# Tab 2 – Decklist Checker
# =========================
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
            from concurrent.futures import ThreadPoolExecutor
            with ThreadPoolExecutor(max_workers=8) as executor:
                results = list(executor.map(process_line, lines))

        # remove linhas None (comentários/vazias)
        results = [r for r in results if r]

        st.subheader("📋 Resultados:")
        for name, qty, status_text, status_type, _ in results:
            color = {
                "success": "green",
                "warning": "orange",
                "danger": "red"
            }[status_type]
            st.markdown(
                f"{qty}x {name}: "
                f"<span style='color:{color}'>{status_text}</span>",
                unsafe_allow_html=True
            )

        # Botão para adicionar toda a decklist ao deckbuilder
        if st.button("📥 Adicionar lista ao Deckbuilder"):
            for name, qty, status_text, status_type, _ in results:
                if status_type != "danger":  # só adiciona se não for erro
                    st.session_state.deck[name] = st.session_state.deck.get(name, 0) + qty
            st.success("Decklist adicionada ao Deckbuilder!")



# =========================
# Tab 3 - Deckbuilder
# =========================
# =========================
# Tab 3 – Deckbuilder
# =========================
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
                        unsafe_allow_html=True
                    )
                elif st.session_state.last_action == "remove":
                    col2.markdown(
                        f"<span style='color:red;font-weight:bold;'>x{qty}</span>",
                        unsafe_allow_html=True
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
            f"{qty}x {name}"
            for name, qty in sorted(st.session_state.deck.items(), key=lambda x: x[0].lower())
        ]
        export_text = "\n".join(export_lines)
        st.download_button(
            "⬇️ Baixar deck (.txt)",
            data=export_text,
            file_name="deck.txt",
            mime="text/plain"
        )

        st.caption("Dica: use a Aba 1 para pesquisar cartas e ajustá-las rapidamente no deck.")


















