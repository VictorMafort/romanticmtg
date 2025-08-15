import streamlit as st
import requests

# Sets permitidos (baseado no seu filtro Scryfall)
sets_permitidos = {
    "M13", "AVR", "DKA", "ISD", "M12", "NPH", "MBS", "SOM", "M11", "ROE",
    "WWK", "ZEN", "M10", "ARB", "CON", "ALA", "EVE", "SHM", "MOR", "LRW",
    "10E", "FUT", "PLC", "TSP", "CSP", "DIS", "GPT", "RAV", "9E", "SOK", "8E"
}

# Ban list atual
ban_list = {
    "Gitaxian Probe",
    "Mental Misstep",
    "Blazing Shoal",
    "Skullclamp"
}

# Função para buscar impressões reais da carta
def buscar_impressoes_reais(carta):
    sets_encontrados = set()
    url_nome = f"https://api.scryfall.com/cards/named?fuzzy={carta}"
    resposta_nome = requests.get(url_nome)
    if resposta_nome.status_code != 200:
        return None, None
    dados_nome = resposta_nome.json()
    nome_padrao = dados_nome["name"]
    url_prints = dados_nome["prints_search_uri"]

    while url_prints:
        resposta = requests.get(url_prints)
        if resposta.status_code != 200:
            return None, None
        dados = resposta.json()
        for card in dados["data"]:
            sets_encontrados.add(card["set"].upper())
        url_prints = dados.get("next_page", None)

    return sets_encontrados, nome_padrao

# Função para verificar legalidade
def verificar_legalidade(nome_carta, sets_da_carta):
    if nome_carta in ban_list:
        return "❌ Banned"
    elif sets_da_carta & sets_permitidos:
        sets_validos = sets_da_carta & sets_permitidos
        return f"✅ Legal (printed in: {', '.join(sorted(sets_validos))})"
    else:
        return f"⚠️ Not Legal"

# Interface Streamlit
st.set_page_config(page_title="Romantic Legality Checker", page_icon="🧙", layout="centered")
st.title("🔍 Romantic Legality Checker")
st.caption("Checks the legality of a card in the Romantic format")

carta = st.text_input("Digite o nome da carta:")

if carta:
    with st.spinner("Consultando Scryfall..."):
        sets_da_carta, nome_corrigido = buscar_impressoes_reais(carta)
    if sets_da_carta:
        status = verificar_legalidade(nome_corrigido, sets_da_carta)
        st.success(f"{nome_corrigido}: {status}")
    else:
        st.error("Carta não encontrada no Scryfall.")