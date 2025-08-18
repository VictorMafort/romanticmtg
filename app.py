# -*- coding: utf-8 -*-
"""
Romantic Format Tools — FINAL v18.0
Autor: Victor + Copilot

Mudanças nesta versão (v18):
- Remove o uso de st.rerun() em callbacks (evita no-op). 
- Implementa atualização IMEDIATA de quantidades processando os botões (+/−) ANTES do render das cartas.
- Mantém: slider removido na Aba 3; teto visual de 3 colunas via CSS; donuts com midAngle + legenda com contagens.
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

# ===== Sessão HTTP + throttle =====
SESSION = requests.Session()
SESSION.headers.update({
    "User-Agent": "RomanticFormatTools/2.2 (+seu_email_ou_site)",
    "Accept": "application/json;q=0.9,*/*;q=0.8",
})
_last = deque(maxlen=10)

def throttle():
    _last.append(time.time())
    if len(_last) == _last.maxlen:
        elapsed = _last[-1] - _last[0]
        if elapsed < 1.0:
            time.sleep(1.0 - elapsed)

# ===== Config & listas =====
allowed_sets = {
    "8ED","MRD","DST","5DN","CHK","BOK","SOK","9ED","RAV","GPT","DIS","CSP","TSP","TSB","PLC","FUT",
    "10E","LRW","MOR","SHM","EVE","ALA","CON","ARB","M10","ZEN","WWK","ROE","M11","SOM","MBS","NPH",
    "M12","ISD","DKA","AVR","M13",
}
ban_list = {"Gitaxian Probe","Mental Misstep","Blazing Shoal","Skullclamp"}
_ALLOWED_FPRINT = ",".join(sorted(allowed_sets))

# ===== Utilidades de busca =====

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

def buscar_sugestoes(query: str):
    q = query.strip()
    if len(q) < 2:
        return []
    url = f"https://api.scryfall.com/cards/autocomplete?q={urllib.parse.quote(q)}"
    r = _get(url)
    if r:
        try:
            return r.json().get("data", [])
        except Exception:
            return []
    return []

@st.cache_data(show_spinner=False)
def fetch_card_data(card_name, _legal_salt: str = _ALLOWED_FPRINT):
    """Busca dados via Scryfall (com fix DFC) e retorna dict enxuto."""
    safe_name = card_name.strip()
    url_named = f"https://api.scryfall.com/cards/named?fuzzy={urllib.parse.quote(safe_name)}"
    resp = _get(url_named)
    if not resp:
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

    # quick scan
    all_sets = set()
    set_query = " OR ".join(s.lower() for s in allowed_sets)
    q_str = f'!"{safe_name}" e:({set_query})'
    quick_url = "https://api.scryfall.com/cards/search?q=" + urllib.parse.quote_plus(q_str)
    rq = _get(quick_url)
    if rq:
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

    # fallback prints
    next_page = data["prints_search_uri"]
    while next_page:
        p = _get(next_page)
        if not p:
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
    if name in ban_list:
        return "❌ Banned", "danger"
    if sets & allowed_sets:
        return "✅ Legal", "success"
    return "⚠️ Not Legal", "warning"

# ===== App + CSS =====
st.set_page_config(page_title="Romantic Format Tools", page_icon="🧙", layout="centered")
with st.sidebar:
    st.markdown("### ⚙️ Utilitários")
    if st.button("🔄 Limpar cache de cartas"):
        fetch_card_data.clear(); st.rerun()

st.markdown(
    """
    <style>
    :root{
      /* Largura base do container */
      --rf-container-w: min(1200px, calc(100vw - 6rem));
      --rf-col-gap: 1.1rem; --rf-col-pad: .35rem;
      /* TAB 1 — cap rígido */
      --rf-card1-max: 300px;
      /* TAB 3 — cap = largura equivalente a 3 colunas */
      --rf-card3-max: calc(
          (var(--rf-container-w) - (3 - 1) * var(--rf-col-gap) - 3 * (2 * var(--rf-col-pad)))
          / 3
      );
      --rf-overlimit: #ef4444;
    }
    .rf-card{ position:relative; border-radius:12px; overflow:hidden; box-shadow:0 2px 10px rgba(0,0,0,.12); background:#0b0b0b08; }
    .rf-card img.rf-img{ display:block; width:100%; height:auto; }
    .rf-fixed1{ max-width: var(--rf-card1-max); margin:0 auto; }
    .rf-fixed3{ max-width: var(--rf-card3-max); margin:0 auto; }
    .rf-name-badge{
      position:absolute; left:50%; transform:translateX(-50%);
      top:40px; padding:4px 10px; border-radius:999px; font-weight:700; font-size:12px;
      background:rgba(255,255,255,.96); color:#0f172a; box-shadow:0 1px 4px rgba(0,0,0,.18);
      border:1px solid rgba(0,0,0,.08); white-space:nowrap; max-width:92%; overflow:hidden; text-overflow:ellipsis;
      z-index:5;
    }
    .rf-qty-badge{
      position:absolute; right:8px; bottom:8px; background:rgba(0,0,0,.65);
      color:#fff; padding:2px 8px; border-radius:999px; font-weight:800; font-size:12px;
      border:1px solid rgba(255,255,255,.25); backdrop-filter:saturate(120%) blur(1px); z-index:6;
    }
    .rf-qty-badge.rf-over{ color: var(--rf-overlimit) !important; }
    .rf-legal-chip{ display:inline-block; margin-left:6px; padding:2px 8px; border-radius:999px; font-weight:800; font-size:11px; border:1px solid rgba(0,0,0,.08); }
    .rf-chip-warning{ color:#92400e; background:#fef3c7; border-color:#fde68a }
    .rf-chip-danger{ color:#991b1b; background:#fee2e2; border-color:#fecaca }
    .rf-inart-belt{ max-width: var(--rf-card3-max); margin:-36px auto 8px; display:flex; justify-content:center; gap:10px; position:relative; z-index:20; }
    [data-testid="column"]{ padding-left:.35rem; padding-right:.35rem }
    @media (max-width:1100px){ [data-testid="column"]{ padding-left:.25rem; padding-right:.25rem } }
    @media (max-width:820px){ [data-testid="column"]{ padding-left:.20rem; padding-right:.20rem } }
    </style>
    """,
    unsafe_allow_html=True,
)

st.title("🧙 Romantic Format Tools")
tab1, tab2, tab3, tab4 = st.tabs([
    "🔍 Single Card Checker", "📦 Decklist Checker", "🧙 Deckbuilder (artes)", "📊 Análise"
])

# ===== Helper HTML do card =====
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

# =====================================================================
# TAB 1 — Sugestões
# =====================================================================
with tab1:
    import html as _html
    st.caption("Digite o começo do nome da carta e use +/− para ajustar no seu deck.")
    query = st.text_input("Buscar carta:")
    COLS_TAB1 = 3
    thumbs = []
    if query.strip():
        for nm in buscar_sugestoes(query.strip())[:24]:
            d = fetch_card_data(nm)
            if d and d.get("image"):
                status_text, status_type = check_legality(d["name"], d.get("sets", set()))
                thumbs.append((d["name"], d["image"], status_text, status_type))

    if thumbs:
        for i in range(0, len(thumbs), COLS_TAB1):
            cols = st.columns(min(COLS_TAB1, len(thumbs) - i))
            for j, (name, img, status_text, status_type) in enumerate(thumbs[i:i+COLS_TAB1]):
                with cols[j]:
                    base_key = f"t1_{i}_{j}_{re.sub(r'[^A-Za-z0-9]+','_',name)}"

                    # 1) PROCESSA BOTÕES PRIMEIRO (sem callbacks)
                    bcols = st.columns([1,1,1,1,1,1], gap="small")
                    if bcols[1].button("−4", key=f"{base_key}_m4"):
                        st.session_state.deck[name] = max(0, st.session_state.deck.get(name,0) - 4)
                        if st.session_state.deck.get(name,0) == 0:
                            st.session_state.deck.pop(name, None)
                    if bcols[2].button("−1", key=f"{base_key}_m1"):
                        st.session_state.deck[name] = max(0, st.session_state.deck.get(name,0) - 1)
                        if st.session_state.deck.get(name,0) == 0:
                            st.session_state.deck.pop(name, None)
                    if bcols[3].button("+1", key=f"{base_key}_p1"):
                        st.session_state.deck[name] = st.session_state.deck.get(name,0) + 1
                    if bcols[4].button("+4", key=f"{base_key}_p4"):
                        st.session_state.deck[name] = st.session_state.deck.get(name,0) + 4

                    # 2) RENDERIZA DEPOIS (mostra qty já atualizado neste run)
                    qty = st.session_state.deck.get(name, 0)
                    label = "Banned" if status_type == "danger" else ("Not Legal" if status_type == "warning" else "Legal")
                    chip_class = "" if status_type == "success" else (" rf-chip-danger" if status_type == "danger" else " rf-chip-warning")
                    legal_chip = f"<span class='rf-legal-chip{chip_class}'>{_html.escape(label)}</span>"
                    badge = f"<div class='rf-name-badge'>{legal_chip}</div>"
                    st.markdown(html_card(img, badge, qty, extra_cls="rf-fixed1", overlimit=False), unsafe_allow_html=True)

# =====================================================================
# TAB 2 — Decklist Checker
# =====================================================================
with tab2:
    st.subheader("📦 Decklist Checker")
    st.write("Cole sua decklist abaixo (1 por linha). Formatos aceitos: `4x Nome`, `4 Nome`, `Nome`.")
    deck_input = st.text_area("Decklist", height=260, key="deck_text_area")

    def process_line(line: str):
        line = re.sub(r'#.*$', '', line).strip()
        if not line:
            return None
        m = re.match(r'^(SB:)?\s*(\d+)?\s*x?\s*(.+)$', line, re.IGNORECASE)
        if not m:
            return (line, 1, "❌ Card not found or API error", "danger", None)
        qty = int(m.group(2) or 1)
        name_guess = m.group(3).strip()
        card = fetch_card_data(name_guess)
        if not card:
            return (name_guess, qty, "❌ Card not found or API error", "danger", None)
        status_text, status_type = check_legality(card["name"], card.get("sets", set()))
        return (card["name"], qty, status_text, status_type, card.get("sets", set()))

    if deck_input.strip():
        lines = deck_input.splitlines()
        with st.spinner("Checando decklist..."):
            with ThreadPoolExecutor(max_workers=8) as ex:
                results = list(ex.map(process_line, lines))
            results = [r for r in results if r]
        for name, qty, status_text, status_type, _ in results:
            color = {"success": "green", "warning": "orange", "danger": "red"}[status_type]
            st.markdown(f"{qty}x {name}: <span style='color:{color}'>{status_text}</span>", unsafe_allow_html=True)
        st.markdown("---")
        if st.button("📥 Enviar ao Deckbuilder"):
            for name, qty, status_text, status_type, _ in results:
                if status_type != "danger":
                    st.session_state.deck[name] = st.session_state.deck.get(name, 0) + qty
            st.success("Deck adicionado na Aba 3.")

# =====================================================================
# TAB 3 — Deckbuilder (artes)
# =====================================================================
with tab3:
    st.subheader("🧙‍♂️ Seu Deck — artes por tipo")
    total = sum(st.session_state.deck.values())
    st.markdown(f"**Total de cartas:** {total}")

    if not st.session_state.deck:
        st.info("Seu deck está vazio. Use as Abas 1 ou 2 para adicionar cartas.")
    else:
        snap = dict(st.session_state.deck)
        names = sorted(snap.keys(), key=lambda x: x.lower())

        def load_one(nm: str):
            try:
                d = fetch_card_data(nm)
                sets = d.get("sets", set()) if d else set()
                status_text, status_type = check_legality(nm, sets)
                return (
                    nm,
                    snap.get(nm, 0),
                    (d.get("type", "") if d else ''),
                    (d.get("image") if d else None),
                    status_text,
                    status_type
                )
            except Exception:
                return (nm, snap.get(nm, 0), '', None, '', 'warning')

        with st.spinner("Carregando artes..."):
            with ThreadPoolExecutor(max_workers=min(6, max(1, len(names)))) as ex:
                items = list(ex.map(load_one, names))

        def bucket(tline: str) -> str:
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

        order = ["Criaturas", "Instantâneas", "Feitiços", "Artefatos", "Encantamentos", "Planeswalkers", "Terrenos", "Outros"]
        skipped = 0
        cols_per_row = 6  # fixo; cap visual controlado por CSS (--rf-card3-max)

        for sec in order:
            if sec not in buckets:
                continue
            group = buckets[sec]
            st.markdown(f"### {sec} — {sum(q for _, q, _, _, _, _ in group)}")
            for i in range(0, len(group), cols_per_row):
                row = group[i:i+cols_per_row]
                cols = st.columns(len(row))
                for col, (name, _q0, _t, img, s_text, s_type) in zip(cols, row):
                    # 1) PROCESSA BOTÕES PRIMEIRO (sem callbacks)
                    with col:
                        mcol, pcol = st.columns([1, 1])
                        if mcol.button("➖", key=f"m1_{sec}_{i}_{name}"):
                            new_q = max(0, st.session_state.deck.get(name,0) - 1)
                            if new_q == 0:
                                st.session_state.deck.pop(name, None)
                            else:
                                st.session_state.deck[name] = new_q
                        if pcol.button("➕", key=f"p1_{sec}_{i}_{name}"):
                            st.session_state.deck[name] = st.session_state.deck.get(name,0) + 1

                        # 2) RENDERIZA CARTA COM ESTADO ATUAL
                        qty = st.session_state.deck.get(name, 0)
                        if qty <= 0 or not img:
                            if not img:
                                skipped += 1
                            continue
                        chip_class = "" if s_type == "success" else (" rf-chip-danger" if s_type == "danger" else " rf-chip-warning")
                        legal_html = (
                            f"<span class='rf-legal-chip{chip_class}'>" +
                            ("Banned" if s_type == "danger" else ("Not Legal" if s_type == "warning" else "")) +
                            "</span>"
                        ) if s_type != "success" else ""
                        overlay = f"<div class='rf-name-badge'>{name}{legal_html}</div>"
                        st.markdown(html_card(img, overlay, qty, extra_cls="rf-fixed3", overlimit=(qty > 4)), unsafe_allow_html=True)
                        st.markdown("<div class='rf-inart-belt'></div>", unsafe_allow_html=True)
            st.markdown("---")
        if skipped:
            st.caption(f"ℹ️ {skipped} carta(s) não renderizada(s) por falta de imagem (cache repovoa em seguida).")

# =====================================================================
# TAB 4 — Análise (donuts)
# =====================================================================
with tab4:
    st.subheader("📊 Análise do Deck")
    if not st.session_state.deck:
        st.info("Seu deck está vazio. Adicione cartas nas Abas 1/2/3.")
    else:
        snap = dict(st.session_state.deck)
        names = sorted(snap.keys(), key=lambda x: x.lower())

        def load_meta(nm: str):
            try:
                d = fetch_card_data(nm)
                return {
                    'name': nm,
                    'qty': snap.get(nm, 0),
                    'type_line': (d.get('type') if d else ''),
                    'color_identity': (d.get('color_identity') if d else []),
                    'produced_mana': (d.get('produced_mana') if d else []),
                }
            except Exception:
                return {'name': nm, 'qty': snap.get(nm,0), 'type_line': '', 'color_identity': [], 'produced_mana': []}

        with st.spinner("Calculando estatísticas..."):
            with ThreadPoolExecutor(max_workers=min(8, max(1, len(names)))) as ex:
                meta = list(ex.map(load_meta, names))
            df = pd.DataFrame(meta)

        # ===== Subtipos de Criaturas =====
        st.markdown("### 🪩 Subtipos de **Criaturas**")
        def extract_subtypes(tline: str):
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
            st.dataframe(agg.merge(cards_by_sub, on='Subtipo', how='left'), use_container_width=True, hide_index=True)
        else:
            st.info("Nenhuma criatura com subtipo identificada no deck.")

        # ===== Donuts =====
        letters = ['W','U','B','R','G','C']
        mana_icons = {'W':'⚪','U':'🔵','B':'⚫','R':'🔴','G':'🟢','C':'⬜️'}
        color_map = {'W':'#d6d3c2','U':'#2b6cb0','B':'#1f2937','R':'#c53030','G':'#2f855a','C':'#6b7280'}

        def build_donut_df(values: dict, label='Cor', val_name='Valor'):
            dfx = pd.DataFrame({label: letters, val_name: [int(values.get(k, 0)) for k in letters]})
            total = int(dfx[val_name].sum())
            dfx['pct'] = dfx[val_name].apply(lambda v: (v/total*100.0) if total else 0.0)
            dfx['label_text'] = dfx.apply(lambda r: f"{mana_icons[r[label]]} {int(r[val_name])} ({r['pct']:.1f}%)", axis=1)
            return dfx

        def donut_altair(df_vals: pd.DataFrame, label_col: str, value_col: str, legend_counts: dict | None = None, title: str | None = None):
            dff = df_vals[df_vals[value_col] > 0].copy()
            if dff.empty:
                return alt.Chart(pd.DataFrame({'v':[1]})).mark_text(text='(vazio)').properties(height=200)

            legend = alt.Legend(title=title)
            if legend_counts is not None:
                parts = []
                _letters = ['W','U','B','R','G','C']
                _icons = {'W':'⚪','U':'🔵','B':'⚫','R':'🔴','G':'🟢','C':'⬜️'}
                for k in _letters:
                    parts.append(f"(datum.label === '{k}') ? '{_icons[k]} {k} ({int(legend_counts.get(k,0))})'")
                label_expr = " : ".join(parts + ["datum.label"])
                legend = alt.Legend(title=title, labelExpr=label_expr)

            base = alt.Chart(dff)
            enc = dict(
                theta=alt.Theta(field=value_col, type='quantitative', stack=True),
                color=alt.Color(field=label_col, type='nominal',
                                scale=alt.Scale(domain=letters, range=[color_map[k] for k in letters]),
                                legend=legend),
                order=alt.Order(f'{label_col}:N', sort=letters),
                tooltip=[alt.Tooltip(label_col, title='Cor'), alt.Tooltip(value_col, title='Qtd'), alt.Tooltip('pct:Q', title='%')]
            )

            inner, outer = 70, 120
            mid = (inner + outer) // 2

            arc = base.encode(**enc).mark_arc(innerRadius=inner, outerRadius=outer)
            txt = (
                base
                .encode(**enc)
                .transform_calculate(midAngle="(datum.startAngle + datum.endAngle)/2")
                .mark_text(radius=mid, align='center', baseline='middle', dy=0)
                .encode(theta="midAngle:Q", text='label_text:N')
                .transform_calculate(textColor="indexof(['W','C'], toString(datum." + label_col + ")) >= 0 ? 'black' : 'white'")
                .encode(color=alt.Color('textColor:N', scale=None))
            )

            return (arc + txt).properties(height=320)

        # 🎨 Distribuição de cores
        st.markdown("### 🎨 Distribuição de cores (por **identidade de cor**)")
        ci_df = df[['qty','color_identity']].copy()
        ci_df['color_identity'] = ci_df['color_identity'].apply(lambda x: x if isinstance(x, list) else [])
        ex = ci_df.explode('color_identity')
        s_ci = ex.groupby('color_identity', dropna=True)['qty'].sum(min_count=1)
        dist_vals = {k: int(s_ci.get(k, 0)) for k in letters}
        colorless_qty = int(df[df['color_identity'].apply(lambda x: not bool(x))]['qty'].sum())
        dist_vals['C'] += colorless_qty
        dist_df = build_donut_df(dist_vals, val_name='Cópias')
        st.altair_chart(donut_altair(dist_df, 'Cor', 'Cópias', legend_counts=dist_vals), use_container_width=True)
        st.caption("* Cartas multicoloridas contam em **cada** cor que possuem; por isso as % podem somar >100%.")

        # ⛲ Fontes de mana
        st.markdown("### ⛲ Fontes de mana por cor")
        is_source = df['produced_mana'].apply(lambda v: isinstance(v, list) and len(v) > 0)
        sources_df = df.loc[is_source, ['qty','type_line','produced_mana']].copy()
        if not sources_df.empty:
            ex_all = sources_df.explode('produced_mana')
            ex_all = ex_all[ex_all['produced_mana'].isin(letters)]
            s_all = ex_all.groupby('produced_mana')['qty'].sum()
            vals_all = {k: int(s_all.get(k, 0)) for k in letters}
        else:
            vals_all = {k: 0 for k in letters}
        if not sources_df.empty:
            land_df = sources_df[sources_df['type_line'].apply(lambda t: isinstance(t,str) and ('Land' in t))][['qty','produced_mana']]
            if not land_df.empty:
                ex_land = land_df.explode('produced_mana')
                ex_land = ex_land[ex_land['produced_mana'].isin(letters)]
                s_land = ex_land.groupby('produced_mana')['qty'].sum()
                vals_land = {k: int(s_land.get(k, 0)) for k in letters}
            else:
                vals_land = {k: 0 for k in letters}
        else:
            vals_land = {k: 0 for k in letters}

        pie_all = build_donut_df(vals_all, val_name='Fontes')
        pie_land = build_donut_df(vals_land, val_name='Fontes')
        c1, c2 = st.columns(2)
        with c1:
            st.caption("Todas as permanentes")
            st.altair_chart(donut_altair(pie_all, 'Cor', 'Fontes', legend_counts=vals_all), use_container_width=True)
        with c2:
            st.caption("Somente terrenos")
            st.altair_chart(donut_altair(pie_land, 'Cor', 'Fontes', legend_counts=vals_land), use_container_width=True)
        st.markdown("**Legenda:** ⚪ W 🔵 U ⚫ B 🔴 R 🟢 G ⬜️ C")
