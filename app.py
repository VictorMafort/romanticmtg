
# -*- coding: utf-8 -*-
"""
Romantic Format Tools - v13.8.1
- Fix Aba 4: tratamento robusto de CMC (NaN/None) para evitar ValueError ao converter para inteiro
- Aba 3: mantém quantidade >4 em vermelho, tamanho fixo e remoção imediata quando qty==0
- Aba 4: Curva de Mana + Subtipos (com pandas/Altair)
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
def fetch_card_data(card_name):
    """Busca dados principais da carta via Scryfall.
    Retorna dict com: name, sets, image, type, cmc (mana value), mana_cost
    """
    safe = urllib.parse.quote(card_name)
    url = f"https://api.scryfall.com/cards/named?fuzzy={safe}"
    try:
        throttle(); resp = SESSION.get(url, timeout=8)
    except Exception:
        return None
    if resp.status_code != 200:
        return None
    data = resp.json()
    if "prints_search_uri" not in data:
        return None

    all_sets = set()
    set_query = " OR ".join(s.lower() for s in allowed_sets)
    quick_url = f"https://api.scryfall.com/cards/search?q=!\"{safe}\"+e:({set_query})"
    try:
        throttle(); rq = SESSION.get(quick_url, timeout=8)
        if rq.status_code == 200 and rq.json().get("total_cards", 0) > 0:
            for c in rq.json().get("data", []):
                if "Token" not in c.get("type_line", ""):
                    all_sets.add(c["set"].upper())
            return {
                "name": data.get("name", ""),
                "sets": all_sets,
                # Preferir 'normal' com fallback 'small'
                "image": data.get("image_uris", {}).get("normal") or data.get("image_uris", {}).get("small"),
                "type": data.get("type_line", ""),
                "cmc": data.get("cmc"),
                "mana_cost": data.get("mana_cost"),
            }
    except Exception:
        pass

    # full scan fallback
    next_page = data["prints_search_uri"]
    while next_page:
        try:
            throttle(); p = SESSION.get(next_page, timeout=8)
            if p.status_code != 200:
                break
            j = p.json()
            for c in j.get("data", []):
                if "Token" not in c.get("type_line", ""):
                    set_code = c.get("set", "").upper(); all_sets.add(set_code)
                if set_code in allowed_sets:
                    next_page = None; break
            else:
                next_page = j.get("next_page")
        except Exception:
            break
    return {
        "name": data.get("name", ""),
        "sets": all_sets,
        "image": data.get("image_uris", {}).get("normal") or data.get("image_uris", {}).get("small"),
        "type": data.get("type_line", ""),
        "cmc": data.get("cmc"),
        "mana_cost": data.get("mana_cost"),
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

st.markdown(
    """
    <style>
    :root{
      /* ===== Aba 1 (dinâmico ~ 3 por linha) ===== */
      --rf-container-w: min(1200px, calc(100vw - 6rem));
      --rf-col-gap: 1.2rem;  /* gap aproximado */
      --rf-col-pad: .35rem;  /* padding de coluna */
      --rf-card-max: calc(
        (var(--rf-container-w) - (2 * var(--rf-col-pad) * 3) - (2 * var(--rf-col-gap))) / 3
      );
      --rf-card-max: clamp(220px, var(--rf-card-max), 44vw);

      /* ===== Aba 3 (FIXO) ===== */
      --rf-card3-max: 300px; /* ajuste fino: 280px, 300px, 320px... */
      --rf-overlimit: #ef4444; /* Vermelho para quando passar de 4 cópias */
    }

    .rf-card{ position:relative; border-radius:12px; overflow:hidden; box-shadow:0 2px 10px rgba(0,0,0,.12); }
    .rf-card img.rf-img{ display:block; width:100%; height:auto; }

    /* Aba 1/geral: não crescer além do “3 por linha” calculado */
    .rf-fixed{ max-width: var(--rf-card-max); margin:0 auto; }

    /* Aba 3: tamanho FIXO máximo */
    .rf-fixed3{ max-width: var(--rf-card3-max); margin:0 auto; }

    /* Nome/legenda */
    .rf-name-badge{
      position:absolute; left:50%; transform:translateX(-50%);
      top:40px; padding:4px 10px; border-radius:999px; font-weight:700; font-size:12px;
      background:rgba(255,255,255,.96); color:#0f172a; box-shadow:0 1px 4px rgba(0,0,0,.18); border:1px solid rgba(0,0,0,.08);
      white-space:nowrap; max-width:92%; overflow:hidden; text-overflow:ellipsis;
    }

    /* Quantidade */
    .rf-qty-badge{
      position:absolute; right:8px; bottom:8px; background:rgba(0,0,0,.65);
      color:#fff; padding:2px 8px; border-radius:999px; font-weight:800; font-size:12px;
      border:1px solid rgba(255,255,255,.25); backdrop-filter:saturate(120%) blur(1px);
    }
    /* Quando passar de 4, só o número fica vermelho (mantém o fundo) */
    .rf-qty-badge.rf-over{ color: var(--rf-overlimit) !important; }

    /* Chips de legalidade */
    .rf-legal-chip{ display:inline-block; margin-left:6px; padding:2px 8px; border-radius:999px; font-weight:800; font-size:11px; border:1px solid rgba(0,0,0,.08); }
    .rf-chip-warning{ color:#92400e; background:#fef3c7; border-color:#fde68a }
    .rf-chip-danger{ color:#991b1b; background:#fee2e2; border-color:#fecaca }

    /* Barra -/+ "sobre" a arte (Aba 3) -> alinhada ao tamanho FIXO */
    .rf-inart-belt{
      max-width: var(--rf-card3-max);
      margin:-36px auto 8px; display:flex; justify-content:center; gap:10px; position:relative; z-index:20;
    }

    /* Estilo dos botões após a belt */
    .rf-inart-belt + div [data-testid="column"] div.stButton>button,
    .rf-inart-belt ~ div [data-testid="column"] div.stButton>button{
      width:auto; min-width:40px; height:40px; padding:0 14px; border-radius:999px; font-size:18px; font-weight:800; line-height:1; display:inline-flex; align-items:center; justify-content:center;
      color:#0f172a !important; background:rgba(255,255,255,.95); border:1px solid rgba(0,0,0,.10); box-shadow:0 1px 4px rgba(0,0,0,.18);
    }
    .rf-inart-belt + div [data-testid="column"] div.stButton>button:hover,
    .rf-inart-belt ~ div [data-testid="column"] div.stButton>button:hover{ background:#eef2f7 }

    /* columns padding geral */
    [data-testid="column"]{ padding-left:.35rem; padding-right:.35rem }
    @media (max-width:1100px){ [data-testid="column"]{ padding-left:.25rem; padding-right:.25rem } }
    @media (max-width:820px){  [data-testid="column"]{ padding-left:.20rem; padding-right:.20rem } }
    </style>
    """,
    unsafe_allow_html=True,
)

st.title("🧙 Romantic Format Tools")

tab1, tab2, tab3, tab4 = st.tabs([
    "🔍 Single Card Checker", "📦 Decklist Checker", "🧙 Deckbuilder (artes)", "📊 Análise (curva & subtipos)"
])

# Helper HTML do card (permite classe extra e flag de overlimit)

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
# Tab 1 — Sugestões com -1/+1 e -4/+4 (colunas FIXAS em 3)
# --------------------
with tab1:
    query = st.text_input("Digite o começo do nome da carta:")
    COLS_TAB1 = 3  # <- fixo, sem slider
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

                    # Centraliza o grupo de botões usando colunas-espaçadoras
                    bcols = st.columns([1, 1, 1, 1, 1, 1], gap="small")
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
# Tab 2 — Decklist Checker
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

        # Botão centralizado
        c1, c2, c3 = st.columns([1, 1, 1])
        with c2:
            if st.button("📥 Adicionar lista ao Deckbuilder"):
                for name, qty, status_text, status_type, _ in results:
                    if status_type != "danger":
                        st.session_state.deck[name] = st.session_state.deck.get(name,0) + qty
                st.success("Decklist adicionada ao Deckbuilder!")

# --------------------
# Tab 3 — Artes por tipo (tamanho FIXO) + +/- centralizado
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
                    # Quantidade ATUAL
                    qty = st.session_state.deck.get(name, 0)
                    if qty <= 0:
                        continue

                    with col:
                        card_ph = st.empty()
                        chip_class = "" if s_type=="success" else (" rf-chip-danger" if s_type=="danger" else " rf-chip-warning")
                        legal_html = f"<span class='rf-legal-chip{chip_class}'>" + ("Banned" if s_type=="danger" else ("Not Legal" if s_type=="warning" else "")) + "</span>" if s_type!="success" else ""
                        overlay = f"<div class='rf-name-badge'>{name}{legal_html}</div>"
                        card_ph.markdown(html_card(img, overlay, qty, extra_cls="rf-fixed3", overlimit=(qty>4)), unsafe_allow_html=True)

                        # Barra +/- alinhada ao card fixo
                        st.markdown("<div class='rf-inart-belt'></div>", unsafe_allow_html=True)

                        # Botões centralizados
                        left_sp, mid, right_sp = st.columns([1, 2, 1])
                        with mid:
                            minus_c, plus_c = st.columns([1, 1], gap="small")
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

        # Export (centralizado)
        lines = [f"{q}x {n}" for n, q in sorted(st.session_state.deck.items(), key=lambda x: x[0].lower())]
        d1, d2, d3 = st.columns([1, 1, 1])
        with d2:
            st.download_button("⬇️ Baixar deck (.txt)", "\n".join(lines), file_name="deck.txt", mime="text/plain")

# --------------------
# Tab 4 — Análise: Curva de mana & Subtipos
# --------------------
with tab4:
    st.subheader("📊 Analisador — Curva de Mana & Subtipos")
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
                    'cmc': (d.get('cmc') if d else None),
                    'type_line': (d.get('type') if d else ''),
                }
            except Exception:
                return {'name': nm, 'qty': snap.get(nm,0), 'cmc': None, 'type_line': ''}

        with st.spinner("Calculando estatísticas..."):
            with ThreadPoolExecutor(max_workers=min(8, max(1, len(names)))) as ex:
                meta = list(ex.map(load_meta, names))
        df = pd.DataFrame(meta)

        # ===== Curva de mana =====
        st.markdown("### ⚡ Curva de Mana")
        # Converte CMC de forma robusta (NaN/None -> NaN), arredonda e usa dtype Int64 (aceita NA)
        cmc_numeric = pd.to_numeric(df['cmc'], errors='coerce')
        df['cmc_i'] = cmc_numeric.round().astype('Int64')
        curve = (
            df.dropna(subset=['cmc_i'])
              .groupby('cmc_i', as_index=False)['qty']
              .sum()
              .sort_values('cmc_i')
        )
        if not curve.empty:
            chart = alt.Chart(curve).mark_bar(color='#60a5fa').encode(
                x=alt.X('cmc_i:O', title='Mana Value (CMC)'),
                y=alt.Y('qty:Q', title='Cópias no deck'),
                tooltip=['cmc_i','qty']
            ).properties(height=260)
            st.altair_chart(chart, use_container_width=True)
            st.dataframe(curve.rename(columns={'cmc_i':'CMC','qty':'Cópias'}), use_container_width=True)
        else:
            st.info("Não foi possível calcular a curva (sem CMC disponível nas cartas).")

        # ===== Subtipos =====
        st.markdown("### 🧩 Subtipos (quantidade & quais existem)")
        def extract_subtypes(tline:str):
            if not tline:
                return []
            # Divide em 'Types — Subtypes' (usa em-dash, ndash ou hyphen)
            parts = re.split(r'\s+[—\-–]\s+', tline)
            if len(parts) < 2:
                return []
            subs = parts[1]
            # separa por espaço ou barra e remove vazios
            tokens = [s.strip() for s in re.split(r'[\s/]+', subs) if s.strip() and s.lower() != '—']
            return tokens

        rows = []
        for _, r in df.iterrows():
            subs = extract_subtypes(r['type_line'])
            for s in subs:
                rows.append({'subtype': s, 'name': r['name'], 'qty': r['qty']})
        if rows:
            dsubs = pd.DataFrame(rows)
            agg = dsubs.groupby('subtype', as_index=False)['qty'].sum().sort_values('qty', ascending=False)
            st.bar_chart(agg.set_index('subtype'))

            # Tabela com lista de cartas por subtipo
            st.markdown("#### Detalhamento por subtipo")
            cards_by_sub = (
                dsubs.groupby('subtype')['name']
                     .apply(lambda s: ", ".join(sorted(set(s))))
                     .reset_index(name='Cartas')
            )
            agg2 = agg.merge(cards_by_sub, on='subtype', how='left')
            st.dataframe(agg2.rename(columns={'subtype':'Subtipo','qty':'Cópias'}), use_container_width=True)
        else:
            st.info("Nenhuma carta com subtipo foi encontrada no deck.")
