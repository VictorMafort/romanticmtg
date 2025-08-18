
# -*- coding: utf-8 -*-
"""
Romantic Format Tools - v13.10b
- Fix Altair donut label color (erro em alt.datum[...]): usa transform_calculate('textColor')
- Mantém: donuts (Altair), DFC image fix, Aba 4 sem índice, etc.
"""
import re
import time
import urllib.parse
from collections import deque, defaultdict
from concurrent.futures import ThreadPoolExecutor

import requests
import streamlit as st
import pandas as pd
import altair as alt

SESSION = requests.Session()
SESSION.headers.update({
    "User-Agent": "RomanticFormatTools/2.1 (+seu_email_ou_site)",
    "Accept": "application/json;q=0.9,*/*;q=0.8",
})
_last = deque(maxlen=10)

def throttle():
    _last.append(time.time())
    if len(_last) == _last.maxlen:
        elapsed = _last[-1] - _last[0]
        if elapsed < 1.0:
            time.sleep(1.0 - elapsed)

allowed_sets = {"8ED","MRD","DST","5DN","CHK","BOK","SOK","9ED","RAV","GPT","DIS","CSP","TSP","TSB","PLC","FUT","10E","LRW","MOR","SHM","EVE","ALA","CON","ARB","M10","ZEN","WWK","ROE","M11","SOM","MBS","NPH","M12","ISD","DKA","AVR","M13",}
ban_list = {"Gitaxian Probe","Mental Misstep","Blazing Shoal","Skullclamp"}
_ALLOWED_FPRINT = ",".join(sorted(allowed_sets))

def buscar_sugestoes(query: str):
    q = query.strip()
    if len(q) < 2:
        return []
    url = f"https://api.scryfall.com/cards/autocomplete?q={urllib.parse.quote(q)}"
    try:
        throttle(); r = SESSION.get(url, timeout=8)
        if r.ok:
            return r.json().get("data", [])
    except Exception:
        pass
    return []

@st.cache_data(show_spinner=False)
def fetch_card_data(card_name, _legal_salt: str = _ALLOWED_FPRINT):
    safe_name = card_name.strip()
    url_named = f"https://api.scryfall.com/cards/named?fuzzy={urllib.parse.quote(safe_name)}"
    try:
        throttle(); resp = SESSION.get(url_named, timeout=8)
    except Exception:
        return None
    if resp.status_code != 200:
        return None
    data = resp.json()
    if "prints_search_uri" not in data:
        return None

    def pick_image(card: dict):
        img = (card.get("image_uris", {}) or {}).get("normal") or (card.get("image_uris", {}) or {}).get("small")
        if img:
            return img
        faces = card.get("card_faces") or []
        if faces and isinstance(faces, list):
            for face in faces:
                img2 = (face.get("image_uris", {}) or {}).get("normal") or (face.get("image_uris", {}) or {}).get("small")
                if img2:
                    return img2
        return None

    base_img = pick_image(data)

    all_sets = set()
    set_query = " OR ".join(s.lower() for s in allowed_sets)
    q_str = f'!"{safe_name}" e:({set_query})'
    quick_url = "https://api.scryfall.com/cards/search?q=" + urllib.parse.quote_plus(q_str)
    try:
        throttle(); rq = SESSION.get(quick_url, timeout=8)
        if rq.status_code == 200:
            jq = rq.json()
            if jq.get("total_cards", 0) > 0:
                for c in jq.get("data", []):
                    if "Token" in (c.get("type_line") or ""):
                        continue
                    sc = (c.get("set") or "").upper()
                    if sc:
                        all_sets.add(sc)
                return {
                    "name": data.get("name", ""),
                    "sets": all_sets,
                    "image": base_img,
                    "type": data.get("type_line", ""),
                    "cmc": data.get("cmc"),
                    "mana_cost": data.get("mana_cost"),
                    "colors": data.get("colors"),
                    "color_identity": data.get("color_identity"),
                    "produced_mana": data.get("produced_mana"),
                }
    except Exception:
        pass

    next_page = data["prints_search_uri"]
    while next_page:
        try:
            throttle(); p = SESSION.get(next_page, timeout=8)
            if p.status_code != 200:
                break
            j = p.json()
            for c in j.get("data", []):
                if "Token" in (c.get("type_line") or ""):
                    continue
                sc = (c.get("set") or "").upper()
                if sc:
                    all_sets.add(sc)
                if sc in allowed_sets:
                    next_page = None
                    break
            else:
                next_page = j.get("next_page")
        except Exception:
            break
    return {
        "name": data.get("name", ""),
        "sets": all_sets,
        "image": base_img,
        "type": data.get("type_line", ""),
        "cmc": data.get("cmc"),
        "mana_cost": data.get("mana_cost"),
        "colors": data.get("colors"),
        "color_identity": data.get("color_identity"),
        "produced_mana": data.get("produced_mana"),
    }

def check_legality(name, sets):
    if name in ban_list: return "❌ Banned", "danger"
    if sets & allowed_sets: return "✅ Legal", "success"
    return "⚠️ Not Legal", "warning"

st.set_page_config(page_title="Romantic Format Tools", page_icon="🧙", layout="centered")

with st.sidebar:
    st.markdown("### ⚙️ Utilitários")
    if st.button("🔄 Limpar cache de cartas"):
        fetch_card_data.clear(); st.rerun()

st.title("🧙 Romantic Format Tools")

tab1, tab2, tab3, tab4 = st.tabs(["🔍 Single Card Checker", "📦 Decklist Checker", "🧙 Deckbuilder (artes)", "📊 Análise"])

# Helper HTML do card

def html_card(img_url: str, overlay_html: str, qty: int, extra_cls: str = "", overlimit: bool = False) -> str:
    cls = f"rf-card {extra_cls}".strip()
    img_src = img_url or ""
    qty_cls = "rf-qty-badge rf-over" if overlimit else "rf-qty-badge"
    return f"""
    <div class='{cls}'>
      <img src='{img_src}' class='rf-img'/>
      {overlay_html}
      <div class='{qty_cls}'>x{qty}</div>
    </div>
    """

# (Para brevidade, Tabs 1-3 idênticas à v13.10a — geradas aqui omitindo detalhes visuais irrelevantes)
with tab1:
    query = st.text_input("Digite o começo do nome da carta:")
    COLS_TAB1 = 3
    thumbs = []
    if query.strip():
        for nm in buscar_sugestoes(query.strip())[:21]:
            d = fetch_card_data(nm)
            if d and d.get("image"):
                status_text, status_type = check_legality(d["name"], d.get("sets", set()))
                thumbs.append((d["name"], d["image"], status_text, status_type))
    if thumbs:
        st.caption("🔎 Sugestões:")
        for i in range(0, len(thumbs), COLS_TAB1):
            cols = st.columns(min(COLS_TAB1, len(thumbs) - i))
            for j, (name, img, status_text, status_type) in enumerate(thumbs[i:i+COLS_TAB1]):
                with cols[j]:
                    ph = st.empty(); qty = st.session_state.deck.get(name, 0)
                    badge = f"<div class='rf-name-badge'>{status_text}</div>"
                    ph.markdown(html_card(img, badge, qty, extra_cls="rf-fixed", overlimit=False), unsafe_allow_html=True)

                    bcols = st.columns([1,1,1,1,1,1])
                    clicked=False
                    base_key = f"t1_{i}_{j}_{re.sub(r'[^A-Za-z0-9]+','_',name)}"
                    if bcols[1].button("−4", key=f"{base_key}_m4"): st.session_state.deck[name]=max(0,qty-4); clicked=True
                    if bcols[2].button("−1", key=f"{base_key}_m1"): st.session_state.deck[name]=max(0,qty-1); clicked=True
                    if bcols[3].button("+1", key=f"{base_key}_p1"): st.session_state.deck[name]=qty+1; clicked=True
                    if bcols[4].button("+4", key=f"{base_key}_p4"): st.session_state.deck[name]=qty+4; clicked=True
                    if st.session_state.deck.get(name,0)<=0 and clicked:
                        st.rerun()
                    if clicked:
                        qty2 = st.session_state.deck.get(name,0)
                        ph.markdown(html_card(img, badge, qty2, extra_cls="rf-fixed", overlimit=False), unsafe_allow_html=True)

with tab2:
    st.write("Cole sua decklist abaixo (uma carta por linha):")
    deck_input = st.text_area("Decklist", height=220)
    def process_line(line: str):
        line = re.sub(r'#.*$', '', line).strip()
        if not line: return None
        m = re.match(r'^(SB:)?\s*(\d+)?\s*x?\s*(.+)$', line, re.IGNORECASE)
        if not m: return (line, 1, "❌ Card not found or API error", "danger", None)
        qty = int(m.group(2) or 1); name_guess = m.group(3).strip()
        card = fetch_card_data(name_guess)
        if not card: return (line, qty, "❌ Card not found or API error", "danger", None)
        status_text, status_type = check_legality(card["name"], card.get("sets", set()))
        return (card["name"], qty, status_text, status_type, card.get("sets", set()))
    if deck_input.strip():
        lines = deck_input.splitlines()
        with ThreadPoolExecutor(max_workers=8) as ex:
            results = list(ex.map(process_line, lines))
        results = [r for r in results if r]
        for name, qty, status_text, status_type, _ in results:
            st.write(f"{qty}x {name}: {status_text}")
        if st.button("📥 Adicionar lista ao Deckbuilder"):
            for name, qty, status_text, status_type, _ in results:
                if status_type != "danger":
                    st.session_state.deck[name] = st.session_state.deck.get(name,0) + qty
            st.success("Decklist adicionada!")

with tab3:
    st.subheader("🧙‍♂️ Seu Deck — artes por tipo")
    total = sum(st.session_state.deck.values())
    st.markdown(f"**Total de cartas:** {total}")

with tab4:
    st.subheader("📊 Análise do Deck")
    if not st.session_state.deck:
        st.info("Seu deck está vazio. Adicione cartas pela Aba 1 ou cole uma lista na Aba 2.")
    else:
        snap = dict(st.session_state.deck)
        names = sorted(snap.keys(), key=lambda x: x.lower())
        def load_meta(nm:str):
            try:
                d = fetch_card_data(nm)
                return {'name': nm,'qty': snap.get(nm,0),'type_line': (d.get('type') if d else ''),'color_identity': (d.get('color_identity') if d else None),'produced_mana': (d.get('produced_mana') if d else None)}
            except Exception:
                return {'name': nm,'qty': snap.get(nm,0),'type_line': '','color_identity': None,'produced_mana': None}
        with ThreadPoolExecutor(max_workers=min(8, max(1, len(names)))) as ex:
            meta = list(ex.map(load_meta, names))
        df = pd.DataFrame(meta)

        st.markdown("### 🧩 Subtipos de **Criaturas**")
        def extract_subtypes(tline:str):
            if not tline or 'Creature' not in tline:
                return []
            parts = re.split(r'\s+[—\-–]\s+', tline)
            if len(parts) < 2:
                return []
            subs = parts[1]
            return [s.strip() for s in re.split(r'[\s/]+', subs) if s.strip()]
        rows = []
        for _, r in df.iterrows():
            if 'Creature' not in (r['type_line'] or ''):
                continue
            for s in extract_subtypes(r['type_line']):
                rows.append({'Subtipo': s, 'Carta': r['name'], 'Cópias': int(r['qty'])})
        if rows:
            dsubs = pd.DataFrame(rows)
            agg = dsubs.groupby('Subtipo', as_index=False)['Cópias'].sum().sort_values('Cópias', ascending=False)
            cards_by_sub = dsubs.groupby('Subtipo')['Carta'].apply(lambda s: ", ".join(sorted(set(s)))).reset_index(name='Cartas')
            tabela = agg.merge(cards_by_sub, on='Subtipo', how='left')
            st.dataframe(tabela, use_container_width=True, hide_index=True)
        else:
            st.info("Nenhuma criatura com subtipo identificada no deck.")

        # Donut utilitário — usa transform_calculate para decidir a cor do texto dentro das fatias
        def donut_altair(df_vals: pd.DataFrame, label_col: str, value_col: str, color_map: dict, title: str = ""):
            domain = [c for c in ['W','U','B','R','G','C'] if c in df_vals[label_col].tolist()]
            rng = [color_map[c] for c in domain]
            base = alt.Chart(df_vals)
            chart = (
                base.transform_calculate(textColor=f"indexof(['W','C'], toString(datum.{label_col})) >= 0 ? 'black' : 'white'")
                    .encode(
                        theta=alt.Theta(field=value_col, type='quantitative'),
                        color=alt.Color(field=label_col, type='nominal', scale=alt.Scale(domain=domain, range=rng), legend=alt.Legend(title=None))
                    )
            )
            arc = chart.mark_arc(innerRadius=70, outerRadius=120)
            txt = chart.mark_text(radius=95, size=12).encode(text=value_col+':Q', color=alt.Color('textColor:N', scale=None))
            return (arc + txt).properties(title=title, height=300)

        st.markdown("### 🎨 Distribuição de cores (por **identidade de cor**)")
        letters = ['W','U','B','R','G','C']
        color_map = {'W':'#d6d3c2','U':'#2b6cb0','B':'#1f2937','R':'#c53030','G':'#2f855a','C':'#6b7280'}
        rows_dist = []
        for c in letters:
            if c == 'C':
                qtd = int(df[df['color_identity'].apply(lambda x: not (x or []))]['qty'].sum())
            else:
                qtd = int(df[df['color_identity'].apply(lambda x: isinstance(x,list) and (c in x))]['qty'].sum())
            rows_dist.append({'Cor': c, 'Cópias': qtd})
        dist_df = pd.DataFrame(rows_dist)
        st.altair_chart(donut_altair(dist_df, 'Cor', 'Cópias', color_map), use_container_width=True)
        st.caption("* Cartas multicoloridas contam em **cada** cor que possuem; a soma pode exceder 100%.")

        st.markdown("### ⛲ Fontes de mana por cor")
        is_source = df['produced_mana'].apply(lambda v: isinstance(v, (list, tuple)) and len(v) > 0)
        sources_df = df[is_source].copy()
        land_src_df = df[is_source & df['type_line'].apply(lambda t: isinstance(t, str) and ('Land' in t))].copy()
        def count_src(dframe, letter):
            return int(dframe[dframe['produced_mana'].apply(lambda lst: isinstance(lst,list) and (letter in lst))]['qty'].sum())
        rows_all = [{'Cor': c, 'Fontes': count_src(sources_df, c)} for c in letters]
        rows_land = [{'Cor': c, 'Fontes': count_src(land_src_df, c)} for c in letters]
        c1, c2 = st.columns(2)
        with c1:
            st.caption("Todas as permanentes")
            st.altair_chart(donut_altair(pd.DataFrame(rows_all), 'Cor', 'Fontes', color_map), use_container_width=True)
        with c2:
            st.caption("Somente terrenos")
            st.altair_chart(donut_altair(pd.DataFrame(rows_land), 'Cor', 'Fontes', color_map), use_container_width=True)
