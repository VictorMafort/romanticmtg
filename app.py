import streamlit as st
import requests
import urllib.parse
from concurrent.futures import ThreadPoolExecutor

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
def buscar_sugestoes(query):
    try:
        # Prefixo primeiro
        url_prefix = f"https://api.scryfall.com/cards/autocomplete?q=name:{urllib.parse.quote(query)}"
        r = requests.get(url_prefix, timeout=8)
        if r.status_code == 200:
            data = [s for s in r.json().get("data", []) if "token" not in s.lower()]
            if data:
                return data
        # Fallback geral
        url_any = f"https://api.scryfall.com/cards/autocomplete?q={urllib.parse.quote(query)}"
        r2 = requests.get(url_any, timeout=8)
        if r2.status_code == 200:
            return [s for s in r2.json().get("data", []) if "token" not in s.lower()]
    except:
        pass
    return []

@st.cache_data(show_spinner=False)
def fetch_card_data(card_name):
    safe_name = urllib.parse.quote(card_name)
    url = f"https://api.scryfall.com/cards/named?fuzzy={safe_name}"
    try:
        resp = requests.get(url, timeout=8)
    except:
        return None
    if resp.status_code != 200:
        return None
    data = resp.json()
    if "prints_search_uri" not in data:
        return None

    all_sets = set()

    # Busca rápida limitada aos sets permitidos
    set_query = " OR ".join(s.lower() for s in allowed_sets)
    quick_url = f"https://api.scryfall.com/cards/search?q=!\"{safe_name}\"+e:({set_query})"
    try:
        quick_resp = requests.get(quick_url, timeout=8)
        if quick_resp.status_code == 200 and quick_resp.json().get("total_cards",0) > 0:
            for c in quick_resp.json().get("data", []):
                if "Token" not in c.get("type_line",""):
                    all_sets.add(c["set"].upper())
            return {
                "name": data.get("name",""),
                "sets": all_sets,
                "image": data.get("image_uris",{}).get("normal"),
                "type": data.get("type_line",""),
                "mana": data.get("mana_cost",""),
                "oracle": data.get("oracle_text","")
            }
    except:
        pass

    # Busca completa por prints (early stop se achar set permitido)
    next_page = data["prints_search_uri"]
    while next_page:
        try:
            p = requests.get(next_page, timeout=8)
            if p.status_code != 200:
                break
            j = p.json()
            for c in j["data"]:
                if "Token" not in c.get("type_line",""):
                    set_code = c["set"].upper()
                    all_sets.add(set_code)
                    if set_code in allowed_sets:
                        next_page = None
                        break
            else:
                next_page = j.get("next_page")
        except:
            break

    return {
        "name": data.get("name",""),
        "sets": all_sets,
        "image": data.get("image_uris",{}).get("normal"),
        "type": data.get("type_line",""),
        "mana": data.get("mana_cost",""),
        "oracle": data.get("oracle_text","")
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

# CSS apenas para o grid de sugestões
st.markdown("""
<style>
.sug-card {
    position: relative;
}
.overlay-btns {
    position: absolute;
    top: 20%;
    left: 50%;
    transform: translateX(-50%);
    display: flex;
    align-items: center;
    gap: 4px;
    z-index: 5;
    opacity: 0;
    transition: opacity 0.2s ease;
}
.sug-card:hover .overlay-btns {
    opacity: 1;
}
.btn-group {
    display: flex;
    border: 1px solid black;
    border-radius: 4px;
    overflow: hidden;
}
.btn {
    background-color: white;
    color: black;
    font-weight: bold;
    font-size: 0.8em;
    width: 38px;
    height: 26px;
    display: flex;
    align-items: center;
    justify-content: center;
    cursor: pointer;
    border: none;
}
.btn:hover {
    background-color: #e6e6e6;
}
</style>
""", unsafe_allow_html=True)

# Estado do deck
if "deck" not in st.session_state:
    st.session_state.deck = {}

# Função para carregar o catálogo inicial de cartas
@st.cache_data(show_spinner=False)
def carregar_catalogo_inicial():
    url = "https://api.scryfall.com/catalog/card-names"
    try:
        resp = requests.get(url, timeout=8)
        if resp.status_code == 200:
            # Retorna a lista de nomes (já filtrando se quiser)
            return [name for name in resp.json().get("data", []) if "token" not in name.lower()]
    except:
        pass
    return []

# Estado do catálogo
if "catalog" not in st.session_state:
    st.session_state.catalog = carregar_catalogo_inicial()

def add_card(card_name, qty=1):
    st.session_state.deck[card_name] = st.session_state.deck.get(card_name, 0) + qty

def remove_card(card_name, qty=1):
    if card_name in st.session_state.deck:
        st.session_state.deck[card_name] -= qty
        if st.session_state.deck[card_name] <= 0:
            del st.session_state.deck[card_name]

st.title("🧙 Romantic Format Tools")
tab1, tab2, tab3 = st.tabs(["🔍 Single Card Checker", "📦 Decklist Checker", "🧙 Deckbuilder"])

# Captura de clique via query param (?pick=Nome)
picked = None
try:
    params = st.query_params
    if "pick" in params and params["pick"]:
        picked = params["pick"][0]
        st.query_params.clear()
except Exception:
    pass
	
# =========================
# Tab 1 - Single Card Checker (com adicionar e remover)
# =========================
with tab1:
    st.subheader("🔍 Buscar e Adicionar Cartas")

    search_query = st.text_input("Digite o nome da carta")

    if search_query:
        # Filtra catálogo (case-insensitive)
        results = [
            c for c in st.session_state.catalog
            if search_query.lower() in c.lower()
        ]

        if results:
            for card in results:
                col1, col2 = st.columns([5, 1])
                col1.markdown(f"**{card}**")

                # Busca dados completos da carta
                card_data = fetch_card_data(card)

                # Exibe imagem se disponível
                if card_data:
                    if card_data.get("image"):
                        col1.image(card_data["image"], use_column_width=True)
                    elif card_data.get("card_faces"):
                        # Pega a imagem da primeira face no caso de dupla face
                        face_img = card_data["card_faces"][0].get("image_uris", {}).get("normal")
                        if face_img:
                            col1.image(face_img, use_column_width=True)

                # Botão de adicionar (key inclui quantidade atual)
                if col2.button(
                    "➕",
                    key=f"add_{card}_{st.session_state.deck.get(card, 0)}"
                ):
                    add_card(card, 1)
                    st.experimental_rerun()
        else:
            st.warning("Nenhuma carta encontrada.")
    else:
        st.info("Digite parte do nome de
# =========================
# Tab 2
# =========================
with tab2:
    st.write("Cole sua decklist abaixo (uma carta por linha):")
    deck_input = st.text_area("Decklist", height=300)

    if deck_input.strip():
        lines = [l.strip() for l in deck_input.splitlines() if l.strip()]

        def process_line(line):
            parts = line.split(" ", 1)
            name_guess = parts[1] if parts[0].isdigit() and len(parts) > 1 else line
            card = fetch_card_data(name_guess)
            if not card:
                return (line, "❌ Card not found or API error", "danger", None)
            status_text, status_type = check_legality(card["name"], card["sets"])
            return (card["name"], status_text, status_type, card["sets"])

        with st.spinner("Checando decklist..."):
            with ThreadPoolExecutor(max_workers=8) as executor:
                results = list(executor.map(process_line, lines))

        st.subheader("📋 Resultados:")
        for name, status_text, status_type, sets in results:
            color = {
                "success": "green",
                "warning": "orange",
                "danger": "red"
            }[status_type]
            st.markdown(f"{name}: <span style='color:{color}'>{status_text}</span>",
                        unsafe_allow_html=True)
            with st.expander(f"🗒️ Sets para {name} (debug)"):
                st.write(sorted(sets) if sets else "Nenhum set encontrado")
				
# =========================
# Tab 3 - Deckbuilder (botões invertidos)
# =========================
with tab3:
    st.subheader("🧙‍♂️ Seu Deck Atual")

    total_cartas = sum(st.session_state.deck.values())

    if not st.session_state.deck:
        st.info("Seu deck está vazio. Adicione cartas pela Aba 1 ou cole uma lista na Aba 2.")
    else:
        st.markdown(f"**Total de cartas no deck:** {total_cartas}")
        st.markdown("---")

        for card, qty in list(st.session_state.deck.items()):
            col1, col2, col3, col4 = st.columns([4, 1, 1, 1])
            col1.markdown(f"**{card}**")
            col2.markdown(f"**x{qty}**")

            if col3.button("➖", key=f"minus_{card}_{qty}"):
                remove_card(card, 1)
                st.experimental_rerun()
            if col4.button("➕", key=f"plus_{card}_{qty}"):
                add_card(card, 1)
                st.experimental_rerun()

        st.markdown("---")
        if st.button("🗑️ Limpar Deck"):
            st.session_state.deck.clear()
            st.experimental_rerun()




