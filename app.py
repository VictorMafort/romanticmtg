import streamlit as st
import requests
import urllib.parse
from concurrent.futures import ThreadPoolExecutor

# =========================
# Config & listas
# =========================
allowed_sets = {
    # Seus códigos de set permitidos, em maiúsculas
    "SET1", "SET2"
}
ban_list = {
    # Nomes de cartas banidas
    "Black Lotus", "Ancestral Recall"
}

# =========================
# Utilidades
# =========================
def buscar_sugestoes(query):
    try:
        url_prefix = f"https://api.scryfall.com/cards/autocomplete?q=name:{urllib.parse.quote(query)}"
        r = requests.get(url_prefix, timeout=8)
        if r.status_code == 200:
            data = [s for s in r.json()["data"] if "token" not in s.lower()]
            if data:
                return data
        url_any = f"https://api.scryfall.com/cards/autocomplete?q={urllib.parse.quote(query)}"
        r2 = requests.get(url_any, timeout=8)
        if r2.status_code == 200:
            return [s for s in r2.json()["data"] if "token" not in s.lower()]
    except:
        pass
    return []

@st.cache_data(show_spinner=False)
def fetch_card_data(card_name):
    try:
        resp = requests.get(f"https://api.scryfall.com/cards/named?exact={urllib.parse.quote(card_name)}", timeout=8)
        if resp.status_code != 200:
            return {}
        data = resp.json()
        name = data.get("name", "")
        img_url = data.get("image_uris", {}).get("normal", None)
        set_codes = {data.get("set", "").upper()}
        return {"name": name, "image": img_url, "sets": set_codes}
    except:
        return {}

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
st.title("🧙 Romantic Format Tools")

tab1, tab2 = st.tabs(["🔍 Single Card Checker", "📦 Decklist Checker"])

if "card_input" not in st.session_state:
    st.session_state.card_input = None

# =========================
# Tab 1 - Single Card Checker
# =========================
with tab1:
    query = st.text_input("Digite o começo do nome da carta:",
                          value=st.session_state.card_input or "")
    if query.strip():
        sugestoes = buscar_sugestoes(query.strip())
        thumbs = []
        for nome in sugestoes[:6]:
            data = fetch_card_data(nome)
            if isinstance(data, dict) and data.get("image"):
                thumbs.append((nome, data["image"]))
        if thumbs:
            st.caption("🔍 Sugestões:")
            cols = st.columns(len(thumbs))
            for idx, (nome, img) in enumerate(thumbs):
                if cols[idx].button("", key=f"sug_{nome}"):
                    st.session_state.card_input = nome
                cols[idx].image(img, use_container_width=True)

    if st.session_state.card_input:
        with st.spinner("Consultando Scryfall..."):
            card = fetch_card_data(st.session_state.card_input)
        if not card:
            st.error("❌ Carta não encontrada ou falha na comunicação.")
        else:
            status_text, status_type = check_legality(card["name"], card["sets"])
            color = {"success":"green","warning":"orange","danger":"red"}[status_type]
            st.markdown(f"{card['name']}: "
                        f"<span style='color:{color}'>{status_text}</span>",
                        unsafe_allow_html=True)

# =========================
# Tab 2 - Decklist Checker
# =========================
with tab2:
    st.write("Cole a lista do deck abaixo (uma carta por linha):")
    deck_input = st.text_area("", height=300)

    if st.button("Verificar Deck") and deck_input.strip():
        linhas = [l.strip() for l in deck_input.splitlines() if l.strip()]
        resultados = []

        def processar_linha(linha):
            # Remove quantidade no começo (ex: "3 Lightning Bolt")
            partes = linha.split(" ", 1)
            if partes[0].isdigit() and len(partes) > 1:
                nome_carta = partes[1]
            else:
                nome_carta = linha
            data = fetch_card_data(nome_carta)
            if not data:
                return (nome_carta, "❓ Not Found", "gray")
            status_text, status_type = check_legality(data["name"], data["sets"])
            cor = {"success":"green","warning":"orange","danger":"red"}.get(status_type, "black")
            return (data["name"], status_text, cor)

        with ThreadPoolExecutor(max_workers=8) as executor:
            resultados = list(executor.map(processar_linha, linhas))

        # Mostra resultado
        for nome, status_text, cor in resultados:
            st.markdown(f"<span style='color:{cor}'>{status_text}</span> — {nome}",
                        unsafe_allow_html=True)
