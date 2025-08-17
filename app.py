def fetch_card_data(card_name):
    import urllib.parse
    safe_name = urllib.parse.quote(card_name)
    url = f"https://api.scryfall.com/cards/named?fuzzy={safe_name}"

    try:
        resp = requests.get(url, timeout=8)
    except requests.RequestException as e:
        st.error(f"❌ Falha na conexão para '{card_name}': {e}")
        return None

    if resp.status_code != 200:
        st.warning(f"⚠️ API retornou {resp.status_code} para '{card_name}'")
        return None

    data = resp.json()
    if "prints_search_uri" not in data:
        st.warning(f"⚠️ Resposta sem prints_search_uri para '{card_name}'")
        st.write("Resposta bruta:", data)  # DEBUG
        return None

    all_sets = set()
    next_page = data["prints_search_uri"]

    page_count = 1
    while next_page:
        st.write(f"📄 Página {page_count} URL:", next_page)  # DEBUG
        try:
            p = requests.get(next_page, timeout=8)
        except requests.RequestException as e:
            st.error(f"❌ Erro na página {page_count}: {e}")
            break

        st.write("HTTP status:", p.status_code)  # DEBUG
        if p.status_code != 200:
            break

        j = p.json()
        st.write(f"📦 Registros nesta página: {len(j.get('data', []))}")  # DEBUG
        if not j.get("data"):
            st.warning("⚠️ Nenhum registro retornado nesta página.")
            break

        # Mostra um exemplo da resposta bruta
        st.write("🔍 Amostra de registro:", j["data"][0])

        for c in j["data"]:
            if "Token" not in c.get("type_line", ""):
                set_code = c["set"].upper()
                all_sets.add(set_code)
                if set_code in allowed_sets:
                    next_page = None
                    break
        else:
            next_page = j.get("next_page", None)

        page_count += 1

    return {
        "name": data.get("name", ""),
        "sets": all_sets,
        "image": data.get("image_uris", {}).get("normal", None),
        "type": data.get("type_line", ""),
        "mana": data.get("mana_cost", ""),
        "oracle": data.get("oracle_text", "")
    }
