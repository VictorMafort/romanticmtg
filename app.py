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

# CSS básico para caixinhas clicáveis
st.markdown("""
<style>
.sug-card {
  background-color: #f6f6f6;
  border: 1px solid #d0d0d0;
  border-radius: 10px;
  padding: 4px;
  transition: transform .05s ease, box-shadow .1s ease;
  display: block;
  text-decoration: none !important;
}
.sug-card:hover {
  transform: translateY(-2px);
  box-shadow: 0 4px 10px rgba(0,0,0,.15);
}
.sug-card img {
  width: 100%;
  border-radius: 6px;
  display: block;
}
</style>
""", unsafe_allow_html=True)

st.title("🧙 Romantic Format Tools")
tab1, tab2 = st.tabs(["🔍 Single Card Checker", "📦 Decklist Checker"])

# Captura de clique via query param (?pick=Nome)
picked = None
try:
    params = st.query_params
    if "pick" in params and params["pick"]:
        picked = params["pick"][0]
        st.query_params.clear()  # limpa a URL
except Exception:
    pass


# =========================
# Tab 1
# =========================

with tab1:
    query = st.text_input(
        "Digite o começo do nome da carta:",
        value=picked or ""
    )
    card_input = picked or None

    if query.strip():
        sugestoes = buscar_sugestoes(query.strip())  # busca clássica

        thumbs = []
        for nome in sugestoes[:21]:  # <- agora até 21
            data = fetch_card_data(nome)
            if data and data.get("image"):
                status_text, status_type = check_legality(data["name"], data.get("sets", []))
                thumbs.append((nome, data["image"], status_text, status_type))

        if thumbs:
            st.caption("🔍 Sugestões:")
            cols_per_row = 3
            for i in range(0, len(thumbs), cols_per_row):
                cols = st.columns(cols_per_row)
                for idx, (nome, img, status_text, status_type) in enumerate(thumbs[i:i+cols_per_row]):
                    color = {
                        "success": "green",
                        "warning": "orange",
                        "danger": "red"
                    }[status_type]
                    href = f"?pick={urllib.parse.quote(nome)}"
                    html = f'''
                    <a class="sug-card" href="{href}">
                        <img src="{img}" alt="{nome}" style="width:100%; height:auto;"/>
                        <div style="text-align:center; color:{color}; font-weight:bold; font-size:1em; margin-top:4px;">
                            {status_text}
                        </div>
                    </a>
                    '''
                    cols[idx].markdown(html, unsafe_allow_html=True)

# =========================
# Tab 2
# =========================
with tab2:
    st.write("Cole sua decklist abaixo (uma carta por linha):")
    deck_input = st.text_area("Decklist", height=300)

    if deck_input.strip():
        lines = [l.strip() for l in deck_input.splitlines() if l.strip()]

        def process_line(line):
            parts = line.split(" ",1)
            name_guess = parts[1] if parts[0].isdigit() and len(parts)>1 else line
            card = fetch_card_data(name_guess)
            if not card:
                return (line, "❌ Card not found or API error","danger", None)
            status_text, status_type = check_legality(card["name"], card["sets"])
            return (card["name"], status_text, status_type, card["sets"])

        with st.spinner("Checando decklist..."):
            with ThreadPoolExecutor(max_workers=8) as executor:
                results = list(executor.map(process_line, lines))

        st.subheader("📋 Resultados:")
        for name, status_text, status_type, sets in results:
            color = {"success":"green","warning":"orange","danger":"red"}[status_type]
            st.markdown(f"{name}: <span style='color:{color}'>{status_text}</span>", unsafe_allow_html=True)
            with st.expander(f"🗒️ Sets para {name} (debug)"):
                st.write(sorted(sets) if sets else "Nenhum set encontrado")









