import streamlit as st
import requests

# Allowed sets for Romantic format
allowed_sets = {
    "8ED", 
    "MRD", "DST", "5DN",
    "CHK", "BOK", "SOK",
    "9ED", 
    "RAV", "GPT", "DIS",
    "CSP", "TSP", "TSB", "PLC", "FUT",
    "10E",
    "LRW", "MOR", "SHM", "EVE",
    "ALA", "CON", "ARB",
    "M10", 
    "ZEN", "WWK", "ROE",
    "M11",
    "SOM", "MBS", "NPH",
    "M12",
    "ISD", "DKA", "AVR",
    "M13"
}

# Banned cards
ban_list = {
    "Gitaxian Probe",
    "Mental Misstep",
    "Blazing Shoal",
    "Skullclamp"
}

def buscar_sugestoes(query):
    url = f"https://api.scryfall.com/cards/autocomplete?q={query}"
    r = requests.get(url)
    if r.status_code == 200:
        return r.json()["data"]
    return []

def fetch_card_data(card_name):
    url = f"https://api.scryfall.com/cards/named?fuzzy={card_name}"
    resp = requests.get(url)
    if resp.status_code != 200:
        return None

    data = resp.json()
    all_sets = set()
    next_page = data["prints_search_uri"]

    while next_page:
        p = requests.get(next_page)
        if p.status_code != 200:
            break
        j = p.json()
        for c in j["data"]:
            if "Token" not in c.get("type_line", ""):
                all_sets.add(c["set"].upper())
        next_page = j.get("next_page", None)

    return {
        "name": data["name"],
        "sets": all_sets,
        "image": data.get("image_uris", {}).get("normal", None),
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

# --- UI ---
st.set_page_config(page_title="Romantic Format Tools", page_icon="🧙", layout="centered")
st.title("🧙 Romantic Format Tools")
tab1, tab2 = st.tabs(["🔍 Single Card Checker", "📦 Decklist Checker"])

# Tab 1: Single Card Checker
with tab1:
    card_input = st.text_input("Digite o nome da carta:")
    
    if card_input and len(card_input) >= 3:
        sugestoes = buscar_sugestoes(card_input)
        if sugestoes:
            st.caption("🔍 Sugestões:")
            for s in sugestoes[:5]:
                st.markdown(f"- {s}")

    if card_input:
        with st.spinner("Consultando Scryfall..."):
            card = fetch_card_data(card_input)

        if not card:
            st.error("Card not found.")
        else:
            status_text, status_type = check_legality(card["name"], card["sets"])
            color = {"success": "green", "warning": "orange", "danger": "red"}[status_type]
            st.markdown(f"{card['name']}: <span style='color:{color}'>{status_text}</span>", unsafe_allow_html=True)

            if card["image"]:
                cols = st.columns([1, 2, 1])
                with cols[1]:
                    st.image(card["image"], caption=card["name"], width=300)

            with st.expander("📋 Card Details"):
                st.markdown(f"**Type:** {card['type']}")
                st.markdown(f"**Mana Cost:** {card['mana']}")
                st.markdown(f"**Oracle Text:** {card['oracle']}")

            if status_type == "warning":
                with st.expander("🗒️ Print sets found (for debugging)"):
                    st.write(sorted(card["sets"]))

# Tab 2: Decklist Checker
with tab2:
    st.write("Paste your decklist below (one card per line, with or without quantity):")
    deck_input = st.text_area("Decklist", height=300)

    if deck_input:
        lines = [l.strip() for l in deck_input.splitlines() if l.strip()]
        results = []

        with st.spinner("Checking decklist..."):
            for line in lines:
                parts = line.split(" ", 1)
                name_guess = parts[1] if parts[0].isdigit() and len(parts) > 1 else line
                card = fetch_card_data(name_guess)
                if not card:
                    results.append((line, "❌ Card not found", "danger", None))
                else:
                    status_text, status_type = check_legality(card["name"], card["sets"])
                    results.append((card["name"], status_text, status_type, card["sets"]))

        st.subheader("📋 Decklist Results:")
        for name, status_text, status_type, sets in results:
            color = {"success": "green", "warning": "orange", "danger": "red"}[status_type]
            st.markdown(f"{name}: <span style='color:{color}'>{status_text}</span>", unsafe_allow_html=True)
            if status_type == "warning":
                with st.expander(f"🗒️ Print sets for {name} (debug)"):
                    st.write(sorted(sets))

