
# -*- coding: utf-8 -*-
"""
Romantic Format Tools - v13.10e
- Aba 4: adiciona **ícones de mana** (emoji) nos rótulos, mostra **porcentagem** dentro de cada fatia
  e **centraliza** o texto dos donuts (Altair)
- Mantém: DFC image fix, Aba 1 com chip de legalidade, Aba 3 sem cards invisíveis, init seguro do session_state
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

# ===== Estado global seguro =====
if 'deck' not in st.session_state:
    st.session_state.deck = {}
if 'last_change' not in st.session_state:
    st.session_state.last_change = None
if 'last_action' not in st.session_state:
    st.session_state.last_action = None

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
    """Busca dados via Scryfall (com suporte a DFC e quick-scan de sets)."""
    safe_name = card_name.strip()
    url_named = f"https://api.scryfall.com/cards/named?fuzzy={urllib.parse.quote(safe_name)}"

    def _get(url, timeout=8, tries=2):
        for t in range(tries):
            try:
                throttle(); resp = SESSION.get(url, timeout=timeout)
                if resp.status_code == 200:
                    return resp
            except Exception:
                pass
            time.sleep(0.25 * (t+1))
        return None

    resp = _get(url_named)
    if not resp: return None
    data = resp.json()
    if "prints_search_uri" not in data: return None

    def pick_image(card: dict):
        img = (card.get("image_uris", {}) or {}).get("normal") or (card.get("image_uris", {}) or {}).get("small")
        if img: return img
        faces = card.get("card_faces") or []
        if faces and isinstance(faces, list):
            for face in faces:
                img2 = (face.get("image_uris", {}) or {}).get("normal") or (face.get("image_uris", {}) or {}).get("small")
                if img2: return img2
        return None

    base_img = pick_image(data)

    all_sets = set()
    set_query = " OR ".join(s.lower() for s in allowed_sets)
    q_str = f'!"{safe_name}" e:({set_query})'
    quick_url = "https://api.scryfall.com/cards/search?q=" + urllib.parse.quote_plus(q_str)
    rq = _get(quick_url)
    if rq:
        jq = rq.json()
        if jq.get("total_cards", 0) > 0:
            for c in jq.get("data", []):
                if "Token" in (c.get("type_line") or ""): continue
                sc = (c.get("set") or "").upper()
                if sc: all_sets.add(sc)
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

    # fallback prints
    next_page = data["prints_search_uri"]
    while next_page:
        p = _get(next_page)
        if not p: break
        j = p.json()
        for c in j.get("data", []):
            if "Token" in (c.get("type_line") or ""): continue
            sc = (c.get("set") or "").upper()
            if sc: all_sets.add(sc)
            if sc in allowed_sets:
                next_page = None; break
        else:
            next_page = j.get("next_page")

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
# App + CSS base (mantém classes e estilos anteriores)
# --------------------
st.set_page_config(page_title="Romantic Format Tools", page_icon="🧙", layout="centered")

with st.sidebar:
    st.markdown("### ⚙️ Utilitários")
    if st.button("🔄 Limpar cache de cartas"):
        fetch_card_data.clear(); st.rerun()

st.markdown(
    """
    <style>
    :root{ --rf-container-w: min(1200px, calc(100vw - 6rem)); --rf-col-gap: 1.2rem; --rf-col-pad: .35rem;
           --rf-card-max: calc((var(--rf-container-w) - (2 * var(--rf-col-pad) * 3) - (2 * var(--rf-col-gap))) / 3);
           --rf-card-max: clamp(220px, var(--rf-card-max), 44vw); --rf-card3-max: 300px; --rf-overlimit: #ef4444; }
    .rf-card{ position:relative; border-radius:12px; overflow:hidden; box-shadow:0 2px 10px rgba(0,0,0,.12); }
    .rf-card img.rf-img{ display:block; width:100%; height:auto; }
    .rf-fixed{ max-width: var(--rf-card-max); margin:0 auto; }
    .rf-fixed3{ max-width: var(--rf-card3-max); margin:0 auto; }
    .rf-name-badge{ position:absolute; left:50%; transform:translateX(-50%); top:40px; padding:4px 10px; border-radius:999px; font-weight:700; font-size:12px; background:rgba(255,255,255,.96); color:#0f172a; box-shadow:0 1px 4px rgba(0,0,0,.18); border:1px solid rgba(0,0,0,.08); white-space:nowrap; max-width:92%; overflow:hidden; text-overflow:ellipsis; }
    .rf-qty-badge{ position:absolute; right:8px; bottom:8px; background:rgba(0,0,0,.65); color:#fff; padding:2px 8px; border-radius:999px; font-weight:800; font-size:12px; border:1px solid rgba(255,255,255,.25); backdrop-filter:saturate(120%) blur(1px); }
    .rf-qty-badge.rf-over{ color: var(--rf-overlimit) !important; }
    .rf-legal-chip{ display:inline-block; margin-left:6px; padding:2px 8px; border-radius:999px; font-weight:800; font-size:11px; border:1px solid rgba(0,0,0,.08); }
    .rf-chip-warning{ color:#92400e; background:#fef3c7; border-color:#fde68a } .rf-chip-danger{ color:#991b1b; background:#fee2e2; border-color:#fecaca }
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

# Helper HTML do card (mesmo das versões anteriores)

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
# Tab 1 — Sugestões (com chip de legalidade)
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
                    label = "Banned" if status_type=="danger" else ("Not Legal" if status_type=="warning" else "Legal")
                    chip_class = "" if status_type=="success" else (" rf-chip-danger" if status_type=="danger" else " rf-chip-warning")
                    legal_chip = f"<span class='rf-legal-chip{chip_class}'>{label}</span>"
                    badge = f"<div class='rf-name-badge'>{legal_chip}</div>"
                    ph.markdown(html_card(img, badge, qty, extra_cls="rf-fixed", overlimit=False), unsafe_allow_html=True)

                    bcols = st.columns([1,1,1,1,1,1], gap="small")
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

# --------------------
# Tab 3 — (mantém: ignora cartas sem imagem, qty>4 vermelho, sumir ao zerar)
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
            with ThreadPoolExecutor(max_workers=min(6, max(1, len(names)))) as ex:
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
        skipped = 0
        for sec in order:
            if sec not in buckets: continue
            group = buckets[sec]
            st.markdown(f"<div class='rf-sec-title'>{sec} — {sum(q for _, q, _, _, _, _ in group)}</div>", unsafe_allow_html=True)
            for i in range(0, len(group), cols_per_row):
                row = group[i:i+cols_per_row]
                cols = st.columns(len(row))
                for col, (name, qty_init, _t, img, s_text, s_type) in zip(cols, row):
                    qty = st.session_state.deck.get(name, 0)
                    if qty <= 0: continue
                    if not img: skipped += 1; continue
                    with col:
                        card_ph = st.empty()
                        chip_class = "" if s_type=="success" else (" rf-chip-danger" if s_type=="danger" else " rf-chip-warning")
                        legal_html = f"<span class='rf-legal-chip{chip_class}'>" + ("Banned" if s_type=="danger" else ("Not Legal" if s_type=="warning" else "")) + "</span>" if s_type!="success" else ""
                        overlay = f"<div class='rf-name-badge'>{name}{legal_html}</div>"
                        card_ph.markdown(html_card(img, overlay, qty, extra_cls="rf-fixed3", overlimit=(qty>4)), unsafe_allow_html=True)
                        st.markdown("<div class='rf-inart-belt'></div>", unsafe_allow_html=True)
                        left_sp, mid, right_sp = st.columns([1, 2, 1])
                        with mid:
                            minus_c, plus_c = st.columns([1, 1], gap="small")
                            if minus_c.button("➖", key=f"b_m1_{sec}_{i}_{name}"):
                                st.session_state.deck[name] = max(0, st.session_state.deck.get(name,0)-1)
                                if st.session_state.deck.get(name, 0) <= 0: st.rerun()
                                new_qty = st.session_state.deck.get(name, 0)
                                card_ph.markdown(html_card(img, overlay, new_qty, extra_cls="rf-fixed3", overlimit=(new_qty>4)), unsafe_allow_html=True)
                            if plus_c.button("➕", key=f"b_p1_{sec}_{i}_{name}"):
                                st.session_state.deck[name] = st.session_state.deck.get(name,0)+1
                                new_qty = st.session_state.deck.get(name, 0)
                                card_ph.markdown(html_card(img, overlay, new_qty, extra_cls="rf-fixed3", overlimit=(new_qty>4)), unsafe_allow_html=True)
            st.markdown("---")
        if skipped:
            st.caption(f"ℹ️ {skipped} carta(s) não renderizada(s) por falta de imagem no momento (evitando espaços invisíveis).")

# --------------------
# Tab 4 — Análise (ícones + % nos donuts, texto centralizado)
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
                    'color_identity': (d.get('color_identity') if d else None),
                    'produced_mana': (d.get('produced_mana') if d else None),
                }
            except Exception:
                return {'name': nm, 'qty': snap.get(nm,0), 'type_line': '', 'color_identity': None, 'produced_mana': None}
        with ThreadPoolExecutor(max_workers=min(8, max(1, len(names)))) as ex:
            meta = list(ex.map(load_meta, names))
        df = pd.DataFrame(meta)

        # --- Subtipos de Criaturas (sem índice) ---
        st.markdown("### 🧩 Subtipos de **Criaturas**")
        def extract_subtypes(tline:str):
            if not tline or 'Creature' not in tline: return []
            parts = re.split(r'\s+[—\-–]\s+', tline)
            if len(parts) < 2: return []
            subs = parts[1]
            return [s.strip() for s in re.split(r'[\s/]+', subs) if s.strip()]
        rows = []
        for _, r in df.iterrows():
            if 'Creature' not in (r['type_line'] or ''): continue
            for s in extract_subtypes(r['type_line']):
                rows.append({'Subtipo': s, 'Carta': r['name'], 'Cópias': int(r['qty'])})
        if rows:
            dsubs = pd.DataFrame(rows)
            agg = dsubs.groupby('Subtipo', as_index=False)['Cópias'].sum().sort_values('Cópias', ascending=False)
            cards_by_sub = dsubs.groupby('Subtipo')['Carta'].apply(lambda s: ", ".join(sorted(set(s)))).reset_index(name='Cartas')
            st.dataframe(agg.merge(cards_by_sub, on='Subtipo', how='left'), use_container_width=True, hide_index=True)
        else:
            st.info("Nenhuma criatura com subtipo identificada no deck.")

        # --- Funções utilitárias para donuts com ícones e % ---
        mana_icons = {'W':'⚪','U':'🔵','B':'⚫','R':'🔴','G':'🟢','C':'⬜️'}
        color_map = {'W':'#d6d3c2','U':'#2b6cb0','B':'#1f2937','R':'#c53030','G':'#2f855a','C':'#6b7280'}

        def build_donut_df(values: dict, order=('W','U','B','R','G','C'), label='Cor', val_name='Valor'):
            rows = []
            for k in order:
                rows.append({label: k, val_name: int(values.get(k, 0))})
            dfx = pd.DataFrame(rows)
            total = dfx[val_name].sum()
            dfx['pct'] = dfx[val_name].apply(lambda v: (v/total*100.0) if total else 0.0)
            # Label com ícone + número + %
            dfx['label_text'] = dfx.apply(lambda r: f"{mana_icons[r[label]]} {int(r[val_name])} ({r['pct']:.1f}%)", axis=1)
            return dfx

        def donut_altair(df_vals: pd.DataFrame, label_col: str, value_col: str, color_map: dict):
            # filtra zeros para não poluir o donut
            dff = df_vals[df_vals[value_col] > 0].copy()
            if dff.empty:
                return alt.Chart(pd.DataFrame({'v':[1]})).mark_text(text='(vazio)').properties(height=200)
            domain = [c for c in ['W','U','B','R','G','C'] if c in dff[label_col].tolist()]
            rng = [color_map[c] for c in domain]
            base = alt.Chart(dff)
            chart = (
                base.transform_calculate(
                        textColor=f"indexof(['W','C'], toString(datum.{label_col})) >= 0 ? 'black' : 'white'"
                    )
                    .encode(
                        theta=alt.Theta(field=value_col, type='quantitative'),
                        color=alt.Color(field=label_col, type='nominal', scale=alt.Scale(domain=domain, range=rng), legend=alt.Legend(title=None)),
                        tooltip=[alt.Tooltip(label_col, title='Cor'), alt.Tooltip(value_col, title='Qtd'), alt.Tooltip('pct:Q', title='%')]
                    )
            )
            arc = chart.mark_arc(innerRadius=70, outerRadius=120)
            # Texto centralizado no anel (valor + % + ícone)
            txt = chart.mark_text(radius=95, size=12, align='center', baseline='middle') \
                        .encode(text='label_text:N', color=alt.Color('textColor:N', scale=None))
            return (arc + txt).properties(height=320)

        # --- 🎨 Distribuição de cores (por identidade de cor) ---
        st.markdown("### 🎨 Distribuição de cores (por **identidade de cor**)")
        dist_vals = {k:0 for k in ['W','U','B','R','G','C']}
        for _, r in df.iterrows():
            ci = r['color_identity'] or []
            if ci:
                for k in ci:
                    if k in dist_vals: dist_vals[k] += int(r['qty'])
            else:
                dist_vals['C'] += int(r['qty'])
        dist_df = build_donut_df(dist_vals, val_name='Cópias')
        st.altair_chart(donut_altair(dist_df, 'Cor', 'Cópias', color_map), use_container_width=True)
        st.caption("* Cartas multicoloridas contam em **cada** cor que possuem; por isso as porcentagens podem somar mais de 100%.")

        # --- ⛲ Fontes de mana por cor (todas vs. somente terrenos) ---
        st.markdown("### ⛲ Fontes de mana por cor")
        is_source = df['produced_mana'].apply(lambda v: isinstance(v, (list, tuple)) and len(v) > 0)
        sources_df = df[is_source].copy()
        land_src_df = df[is_source & df['type_line'].apply(lambda t: isinstance(t, str) and ('Land' in t))].copy()
        def count_src(dframe, letter):
            return int(dframe[dframe['produced_mana'].apply(lambda lst: isinstance(lst,list) and (letter in lst))]['qty'].sum())
        vals_all = {k: count_src(sources_df, k) for k in ['W','U','B','R','G','C']}
        vals_land = {k: count_src(land_src_df, k) for k in ['W','U','B','R','G','C']}
        pie_all = build_donut_df(vals_all, val_name='Fontes')
        pie_land = build_donut_df(vals_land, val_name='Fontes')
        c1, c2 = st.columns(2)
        with c1:
            st.caption("Todas as permanentes")
            st.altair_chart(donut_altair(pie_all, 'Cor', 'Fontes', color_map), use_container_width=True)
        with c2:
            st.caption("Somente terrenos")
            st.altair_chart(donut_altair(pie_land, 'Cor', 'Fontes', color_map), use_container_width=True)

        # Pequena legenda visual com ícones
        st.markdown("**Legenda:** ⚪ W &nbsp;&nbsp; 🔵 U &nbsp;&nbsp; ⚫ B &nbsp;&nbsp; 🔴 R &nbsp;&nbsp; 🟢 G &nbsp;&nbsp; ⬜️ C")
