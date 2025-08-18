
# -*- coding: utf-8 -*-
"""
Romantic Format Tools - v13.10
- Aba 4:
  * Tabela de subtipos (criaturas) **sem coluna de índice**
  * **Gráficos circulares (donut)** para: distribuição de cores e fontes de mana (todas / só terrenos)
- Aba 1: **corrigido suporte a cartas dupla-face** (DFC) como *Delver of Secrets* — busca imagem na primeira face quando `image_uris` não existe no nível raiz
- Mantém: Aba 3 (qty>4 em vermelho, tamanho fixo, remover ao zerar), botão para limpar cache, query Scryfall codificada
"""
import re
import time
import urllib.parse
from collections import deque, defaultdict
from concurrent.futures import ThreadPoolExecutor

import requests
import streamlit as st
import pandas as pd
import plotly.express as px

# --------------------
# Sessão HTTP + throttle
# --------------------
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

# --------------------
# Config & listas
# --------------------
allowed_sets = {
    "8ED","MRD","DST","5DN","CHK","BOK","SOK","9ED","RAV","GPT","DIS","CSP","TSP","TSB","PLC","FUT","10E","LRW","MOR","SHM","EVE","ALA","CON","ARB","M10","ZEN","WWK","ROE","M11","SOM","MBS","NPH","M12","ISD","DKA","AVR","M13",
}
ban_list = {"Gitaxian Probe","Mental Misstep","Blazing Shoal","Skullclamp"}
_ALLOWED_FPRINT = ",".join(sorted(allowed_sets))

# --------------------
# Utilidades
# --------------------

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
    """Busca dados via Scryfall.
    * Corrige DFC: se não houver image_uris no topo, usa card_faces[0].image_uris
    * Limita sets pelo allowed_sets para checar legalidade
    """
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

    # --- imagem (inclui DFC) ---
    def pick_image(card: dict):
        # tenta raiz
        img = (card.get("image_uris", {}) or {}).get("normal") or (card.get("image_uris", {}) or {}).get("small")
        if img:
            return img
        # tenta primeira face (DFC / transform / modal)
        faces = card.get("card_faces") or []
        if faces and isinstance(faces, list):
            for face in faces:
                img2 = (face.get("image_uris", {}) or {}).get("normal") or (face.get("image_uris", {}) or {}).get("small")
                if img2:
                    return img2
        return None

    base_img = pick_image(data)

    # --- quick scan por sets ---
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

    # fallback varredura
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

# --------------------
# Estado do deck
# --------------------
if "deck" not in st.session_state: st.session_state.deck = {}
if "last_change" not in st.session_state: st.session_state.last_change = None
if "last_action" not in st.session_state: st.session_state.last_action = None

def add_card(card_name, qty=1):
    st.session_state.deck[card_name] = st.session_state.deck.get(card_name, 0) + qty
    st.session_state.last_change = card_name; st.session_state.last_action = "add"

def remove_card(card_name, qty=1):
    if card_name in st.session_state.deck:
        st.session_state.deck[card_name] -= qty
        if st.session_state.deck[card_name] <= 0:
            del st.session_state.deck[card_name]
    st.session_state.last_change = card_name; st.session_state.last_action = "remove"

# --------------------
# App + CSS
# --------------------
st.set_page_config(page_title="Romantic Format Tools", page_icon="🧙", layout="centered")

with st.sidebar:
    st.markdown("### ⚙️ Utilitários")
    if st.button("🔄 Limpar cache de cartas"):
        fetch_card_data.clear(); st.rerun()

st.markdown(
    """
    <style>
    :root{
      --rf-container-w: min(1200px, calc(100vw - 6rem));
      --rf-col-gap: 1.2rem;  --rf-col-pad: .35rem;
      --rf-card-max: calc((var(--rf-container-w) - (2 * var(--rf-col-pad) * 3) - (2 * var(--rf-col-gap))) / 3);
      --rf-card-max: clamp(220px, var(--rf-card-max), 44vw);
      --rf-card3-max: 300px; --rf-overlimit: #ef4444;
    }
    .rf-card{ position:relative; border-radius:12px; overflow:hidden; box-shadow:0 2px 10px rgba(0,0,0,.12); }
    .rf-card img.rf-img{ display:block; width:100%; height:auto; }
    .rf-fixed{ max-width: var(--rf-card-max); margin:0 auto; }
    .rf-fixed3{ max-width: var(--rf-card3-max); margin:0 auto; }
    .rf-name-badge{ position:absolute; left:50%; transform:translateX(-50%); top:40px; padding:4px 10px; border-radius:999px; font-weight:700; font-size:12px; background:rgba(255,255,255,.96); color:#0f172a; box-shadow:0 1px 4px rgba(0,0,0,.18); border:1px solid rgba(0,0,0,.08); white-space:nowrap; max-width:92%; overflow:hidden; text-overflow:ellipsis; }
    .rf-qty-badge{ position:absolute; right:8px; bottom:8px; background:rgba(0,0,0,.65); color:#fff; padding:2px 8px; border-radius:999px; font-weight:800; font-size:12px; border:1px solid rgba(255,255,255,.25); backdrop-filter:saturate(120%) blur(1px); }
    .rf-qty-badge.rf-over{ color: var(--rf-overlimit) !important; }
    .rf-legal-chip{ display:inline-block; margin-left:6px; padding:2px 8px; border-radius:999px; font-weight:800; font-size:11px; border:1px solid rgba(0,0,0,.08); }
    .rf-chip-warning{ color:#92400e; background:#fef3c7; border-color:#fde68a }
    .rf-chip-danger{ color:#991b1b; background:#fee2e2; border-color:#fecaca }
    .rf-inart-belt{ max-width: var(--rf-card3-max); margin:-36px auto 8px; display:flex; justify-content:center; gap:10px; position:relative; z-index:20; }
    .rf-inart-belt + div [data-testid="column"] div.stButton>button,
    .rf-inart-belt ~ div [data-testid="column"] div.stButton>button{ width:auto; min-width:40px; height:40px; padding:0 14px; border-radius:999px; font-size:18px; font-weight:800; line-height:1; display:inline-flex; align-items:center; justify-content:center; color:#0f172a !important; background:rgba(255,255,255,.95); border:1px solid rgba(0,0,0,.10); box-shadow:0 1px 4px rgba(0,0,0,.18); }
    .rf-inart-belt + div [data-testid="column"] div.stButton>button:hover,
    .rf-inart-belt ~ div [data-testid="column"] div.stButton>button:hover{ background:#eef2f7 }
    [data-testid="column"]{ padding-left:.35rem; padding-right:.35rem }
    @media (max-width:1100px){ [data-testid="column"]{ padding-left:.25rem; padding-right:.25rem } }
    @media (max-width:820px){  [data-testid="column"]{ padding-left:.20rem; padding-right:.20rem } }
    </style>
    """,
    unsafe_allow_html=True,
)

st.title("🧙 Romantic Format Tools")

tab1, tab2, tab3, tab4 = st.tabs([
    "🔍 Single Card Checker", "📦 Decklist Checker", "🧙 Deckbuilder (artes)", "📊 Análise"
])

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

# --------------------
# Tab 1 — Sugestões
# --------------------
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
                    badge_cls = "rf-success" if status_type=="success" else ("rf-danger" if status_type=="danger" else "rf-warning")
                    badge = f"<div class='rf-name-badge {badge_cls}'>{status_text}</div>"
                    ph.markdown(html_card(img, badge, qty, extra_cls="rf-fixed", overlimit=False), unsafe_allow_html=True)

                    bcols = st.columns([1,1,1,1,1,1], gap="small")
                    clicked=False
                    base_key = f"t1_{i}_{j}_{re.sub(r'[^A-Za-z0-9]+','_',name)}"
                    if bcols[1].button("−4", key=f"{base_key}_m4"): remove_card(name,4); clicked=True
                    if bcols[2].button("−1", key=f"{base_key}_m1"): remove_card(name,1); clicked=True
                    if bcols[3].button("+1", key=f"{base_key}_p1"): add_card(name,1); clicked=True
                    if bcols[4].button("+4", key=f"{base_key}_p4"): add_card(name,4); clicked=True
                    if clicked:
                        qty2 = st.session_state.deck.get(name,0)
                        ph.markdown(html_card(img, badge, qty2, extra_cls="rf-fixed", overlimit=False), unsafe_allow_html=True)

# --------------------
# Tab 2 — Decklist Checker (igual)
# --------------------
with tab2:
    st.write("Cole sua decklist abaixo (uma carta por linha):")
    deck_input = st.text_area("Decklist", height=260)

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
        with st.spinner("Checando decklist..."):
            with ThreadPoolExecutor(max_workers=8) as ex:
                results = list(ex.map(process_line, lines))
        results = [r for r in results if r]
        st.subheader("📋 Resultados:")
        for name, qty, status_text, status_type, _ in results:
            color = {"success":"green","warning":"orange","danger":"red"}[status_type]
            st.markdown(f"{qty}x {name}: <span style='color:{color}'>{status_text}</span>", unsafe_allow_html=True)

        c1, c2, c3 = st.columns([1,1,1])
        with c2:
            if st.button("📥 Adicionar lista ao Deckbuilder"):
                for name, qty, status_text, status_type, _ in results:
                    if status_type != "danger":
                        st.session_state.deck[name] = st.session_state.deck.get(name,0) + qty
                st.success("Decklist adicionada ao Deckbuilder!")

# --------------------
# Tab 3 — Artes (igual, tamanho fixo, qty>4 vermelho, sumir ao zerar)
# --------------------
with tab3:
    st.subheader("🧙‍♂️ Seu Deck — artes por tipo")
    cols_per_row = st.slider("Colunas por linha", 4, 8, 6)
    total = sum(st.session_state.deck.values())
    st.markdown(f"**Total de cartas:** {total}")

    if not st.session_state.deck:
        st.info("Seu deck está vazio. Adicione cartas pela Aba 1 ou cole uma lista na Aba 2.")
    else:
        snap = dict(st.session_state.deck)
        names = sorted(snap.keys(), key=lambda x: x.lower())

        def load_one(nm:str):
            try:
                d = fetch_card_data(nm)
                sets = d.get("sets", set()) if d else set()
                status_text, status_type = check_legality(nm, sets)
                return (nm, snap.get(nm,0), (d.get("type","") if d else ''), (d.get("image") if d else None), status_text, status_type)
            except Exception:
                return (nm, snap.get(nm,0), '', None, '', 'warning')

        with st.spinner("Carregando artes..."):
            with ThreadPoolExecutor(max_workers=min(8, max(1, len(names)))) as ex:
                items = list(ex.map(load_one, names))

        def bucket(tline:str)->str:
            tl = tline or ''
            if 'Land' in tl: return 'Terrenos'
            if 'Creature' in tl: return 'Criaturas'
            if 'Instant' in tl: return 'Instantâneas'
            if 'Sorcery' in tl: return 'Feitiços'
            if 'Planeswalker' in tl: return 'Planeswalkers'
            if 'Enchantment' in tl: return 'Encantamentos'
            if 'Artifact' in tl: return 'Artefatos'
            return 'Outros'

        buckets = defaultdict(list)
        for name, qty, tline, img, s_text, s_type in items:
            buckets[bucket(tline)].append((name, qty, tline, img, s_text, s_type))

        order = ["Criaturas","Instantâneas","Feitiços","Artefatos","Encantamentos","Planeswalkers","Terrenos","Outros"]
        for sec in order:
            if sec not in buckets: continue
            group = buckets[sec]
            st.markdown(f"<div class='rf-sec-title'>{sec} — {sum(q for _, q, _, _, _, _ in group)}</div>", unsafe_allow_html=True)

            for i in range(0, len(group), cols_per_row):
                row = group[i:i+cols_per_row]
                cols = st.columns(len(row))
                for col, (name, qty_init, _t, img, s_text, s_type) in zip(cols, row):
                    qty = st.session_state.deck.get(name, 0)
                    if qty <= 0:
                        continue
                    with col:
                        card_ph = st.empty()
                        chip_class = "" if s_type=="success" else (" rf-chip-danger" if s_type=="danger" else " rf-chip-warning")
                        legal_html = f"<span class='rf-legal-chip{chip_class}'>" + ("Banned" if s_type=="danger" else ("Not Legal" if s_type=="warning" else "")) + "</span>" if s_type!="success" else ""
                        overlay = f"<div class='rf-name-badge'>{name}{legal_html}</div>"
                        card_ph.markdown(html_card(img, overlay, qty, extra_cls="rf-fixed3", overlimit=(qty>4)), unsafe_allow_html=True)

                        st.markdown("<div class='rf-inart-belt'></div>", unsafe_allow_html=True)
                        left_sp, mid, right_sp = st.columns([1,2,1])
                        with mid:
                            minus_c, plus_c = st.columns([1,1], gap="small")
                            if minus_c.button("➖", key=f"b_m1_{sec}_{i}_{name}"):
                                remove_card(name, 1)
                                if st.session_state.deck.get(name, 0) <= 0:
                                    st.rerun()
                                else:
                                    new_qty = st.session_state.deck.get(name, 0)
                                    card_ph.markdown(html_card(img, overlay, new_qty, extra_cls="rf-fixed3", overlimit=(new_qty>4)), unsafe_allow_html=True)
                            if plus_c.button("➕", key=f"b_p1_{sec}_{i}_{name}"):
                                add_card(name, 1)
                                new_qty = st.session_state.deck.get(name, 0)
                                card_ph.markdown(html_card(img, overlay, new_qty, extra_cls="rf-fixed3", overlimit=(new_qty>4)), unsafe_allow_html=True)
                st.markdown("---")

        lines = [f"{q}x {n}" for n, q in sorted(st.session_state.deck.items(), key=lambda x: x[0].lower())]
        d1, d2, d3 = st.columns([1,1,1])
        with d2:
            st.download_button("⬇️ Baixar deck (.txt)", "\n".join(lines), file_name="deck.txt", mime="text/plain")

# --------------------
# Tab 4 — Análise
# --------------------
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
                return {
                    'name': nm,
                    'qty': snap.get(nm, 0),
                    'type_line': (d.get('type') if d else ''),
                    'colors': (d.get('colors') if d else None),
                    'color_identity': (d.get('color_identity') if d else None),
                    'produced_mana': (d.get('produced_mana') if d else None),
                }
            except Exception:
                return {'name': nm, 'qty': snap.get(nm,0), 'type_line': '', 'colors': None, 'color_identity': None, 'produced_mana': None}

        with st.spinner("Carregando metadados..."):
            with ThreadPoolExecutor(max_workers=min(8, max(1, len(names)))) as ex:
                meta = list(ex.map(load_meta, names))
        df = pd.DataFrame(meta)

        # ====== 4.1 Subtipos DE CRIATURAS (tabela, sem índice) ======
        st.markdown("### 🧩 Subtipos de **Criaturas**")
        def extract_subtypes(tline:str):
            if not tline or 'Creature' not in tline:
                return []
            parts = re.split(r'\s+[—\-–]\s+', tline)
            if len(parts) < 2:
                return []
            subs = parts[1]
            tokens = [s.strip() for s in re.split(r'[\s/]+', subs) if s.strip() and s.lower() != '—']
            return tokens

        rows = []
        for _, r in df.iterrows():
            if 'Creature' not in (r['type_line'] or ''):
                continue
            subs = extract_subtypes(r['type_line'])
            for s in subs:
                rows.append({'Subtipo': s, 'Carta': r['name'], 'Cópias': int(r['qty'])})
        if rows:
            dsubs = pd.DataFrame(rows)
            agg = dsubs.groupby('Subtipo', as_index=False)['Cópias'].sum().sort_values('Cópias', ascending=False)
            cards_by_sub = (
                dsubs.groupby('Subtipo')['Carta']
                     .apply(lambda s: ", ".join(sorted(set(s))))
                     .reset_index(name='Cartas')
            )
            tabela = agg.merge(cards_by_sub, on='Subtipo', how='left')
            st.dataframe(tabela, use_container_width=True, hide_index=True)
        else:
            st.info("Nenhuma criatura com subtipo identificada no deck.")

        # ====== Paleta de cores (padrão MTG) para os gráficos ======
        color_map = {
            'W':'#d6d3c2',  # "white" mais escuro p/ texto branco legível
            'U':'#2b6cb0',  # blue
            'B':'#1f2937',  # black (gray-800)
            'R':'#c53030',  # red
            'G':'#2f855a',  # green
            'C':'#6b7280',  # colorless
        }

        # ====== 4.2 Distribuição de cores (donut) ======
        st.markdown("### 🎨 Distribuição de cores (por **identidade de cor**)")
        def has_color(ci, c):
            try:
                return c in (ci or [])
            except Exception:
                return False
        letters = ['W','U','B','R','G','C']
        dist_rows = []
        total_copias = int(df['qty'].sum()) if not df.empty else 0
        for c in letters:
            if c == 'C':
                qtd = int(df[df['color_identity'].apply(lambda x: not (x or []))]['qty'].sum())
            else:
                qtd = int(df[df['color_identity'].apply(lambda x: has_color(x, c))]['qty'].sum())
            dist_rows.append({'Cor': c, 'Cópias': qtd})
        dist_df = pd.DataFrame(dist_rows)
        fig1 = px.pie(dist_df, values='Cópias', names='Cor', color='Cor',
                      color_discrete_map=color_map, hole=0.55)
        fig1.update_traces(textinfo='value', textposition='inside', insidetextfont=dict(color='white', size=14))
        fig1.update_layout(showlegend=True, legend_title_text='Cor')
        st.plotly_chart(fig1, use_container_width=True)
        st.caption("* Cartas multicoloridas contam em **cada** cor que possuem; a soma pode exceder 100%.")

        # ====== 4.3 Fontes de mana (donuts lado a lado) ======
        st.markdown("### ⛲ Fontes de mana por cor")
        is_source = df['produced_mana'].apply(lambda v: isinstance(v, (list, tuple)) and len(v) > 0)
        sources_df = df[is_source].copy()
        land_src_df = df[is_source & df['type_line'].apply(lambda t: isinstance(t, str) and ('Land' in t))].copy()

        def count_sources(dframe, letter):
            def produces(lst):
                try:
                    return letter in (lst or [])
                except Exception:
                    return False
            return int(dframe[dframe['produced_mana'].apply(produces)]['qty'].sum())

        src_rows_all, src_rows_land = [], []
        for c in letters:
            src_rows_all.append({'Cor': c, 'Fontes': count_sources(sources_df, c)})
            src_rows_land.append({'Cor': c, 'Fontes': count_sources(land_src_df, c)})
        pie_all = pd.DataFrame(src_rows_all)
        pie_land = pd.DataFrame(src_rows_land)

        col_a, col_b = st.columns(2)
        with col_a:
            st.caption("Todas as permanentes")
            fig2 = px.pie(pie_all, values='Fontes', names='Cor', color='Cor', color_discrete_map=color_map, hole=0.55)
            fig2.update_traces(textinfo='value', textposition='inside', insidetextfont=dict(color='white', size=14))
            fig2.update_layout(showlegend=False)
            st.plotly_chart(fig2, use_container_width=True)
        with col_b:
            st.caption("Somente terrenos")
            fig3 = px.pie(pie_land, values='Fontes', names='Cor', color='Cor', color_discrete_map=color_map, hole=0.55)
            fig3.update_traces(textinfo='value', textposition='inside', insidetextfont=dict(color='white', size=14))
            fig3.update_layout(showlegend=False)
            st.plotly_chart(fig3, use_container_width=True)
