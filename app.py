# -*- coding: utf-8 -*-
"""
Romantic Format Tools - v13.3
Fixes: smaller fixed width (~260px), + button visible, remove tile at qty 0 (st.rerun)
"""
import re, time, urllib.parse
from collections import defaultdict, deque
from concurrent.futures import ThreadPoolExecutor
import requests, streamlit as st

SESSION=requests.Session(); SESSION.headers.update({"User-Agent":"RomanticFormatTools/2.2","Accept":"application/json"})
_last=deque(maxlen=10)

def throttle():
    _last.append(time.time())
    if len(_last)==_last.maxlen:
        dt=_last[-1]-_last[0]
        if dt<1.0: time.sleep(1.0-dt)

allowed_sets={"8ED","MRD","DST","5DN","CHK","BOK","SOK","9ED","RAV","GPT","DIS","CSP","TSP","TSB","PLC","FUT","10E","LRW","MOR","SHM","EVE","ALA","CON","ARB","M10","ZEN","WWK","ROE","M11","SOM","MBS","NPH","M12","ISD","DKA","AVR","M13"}
ban_list={"Gitaxian Probe","Mental Misstep","Blazing Shoal","Skullclamp"}

def buscar_sugestoes(q:str):
    q=q.strip();
    if len(q)<2: return []
    url=f"https://api.scryfall.com/cards/autocomplete?q={urllib.parse.quote(q)}"
    try:
        throttle(); r=SESSION.get(url,timeout=8)
        if r.ok: return r.json().get("data",[])
    except Exception: pass
    return []

@st.cache_data(show_spinner=False)
def fetch_card_data(name:str):
    safe=urllib.parse.quote(name)
    url=f"https://api.scryfall.com/cards/named?fuzzy={safe}"
    try:
        throttle(); resp=SESSION.get(url,timeout=8)
    except Exception:
        return None
    if resp.status_code!=200: return None
    data=resp.json()
    if "prints_search_uri" not in data: return None
    sets=set()
    set_query=" OR ".join(s.lower() for s in allowed_sets)
    qurl=f"https://api.scryfall.com/cards/search?q=!%22{safe}%22+e:({set_query})"
    try:
        throttle(); rq=SESSION.get(qurl,timeout=8)
        if rq.status_code==200 and rq.json().get("total_cards",0)>0:
            for c in rq.json().get("data",[]):
                if "Token" not in c.get("type_line",""):
                    sets.add(c["set"].upper())
            return {"name":data.get("name",""),"sets":sets,"image":data.get("image_uris",{}).get("small") or data.get("image_uris",{}).get("normal"),"type":data.get("type_line","")}
    except Exception: pass
    nextp=data["prints_search_uri"]
    while nextp:
        try:
            throttle(); p=SESSION.get(nextp,timeout=8)
            if p.status_code!=200: break
            j=p.json()
            for c in j.get("data",[]):
                if "Token" not in c.get("type_line",""):
                    sc=c.get("set"," ").upper(); sets.add(sc)
                    if sc in allowed_sets:
                        nextp=None; break
            else:
                nextp=j.get("next_page")
        except Exception:
            break
    return {"name":data.get("name",""),"sets":sets,"image":data.get("image_uris",{}).get("small") or data.get("image_uris",{}).get("normal"),"type":data.get("type_line","")}

def check_legality(name, sets):
    if name in ban_list: return "❌ Banned","danger"
    if sets & allowed_sets: return "✅ Legal","success"
    return "⚠️ Not Legal","warning"

if "deck" not in st.session_state: st.session_state.deck={}
if "last_change" not in st.session_state: st.session_state.last_change=None
if "last_action" not in st.session_state: st.session_state.last_action=None

def add_card(card,qty=1):
    st.session_state.deck[card]=st.session_state.deck.get(card,0)+qty
    st.session_state.last_change=card; st.session_state.last_action="add"

def remove_card(card,qty=1):
    if card in st.session_state.deck:
        st.session_state.deck[card]-=qty
        if st.session_state.deck[card]<=0:
            del st.session_state.deck[card]
    st.session_state.last_change=card; st.session_state.last_action="remove"

st.set_page_config(page_title="Romantic Format Tools", page_icon="\U0001F9D9", layout="centered")

st.markdown(r"""
<style>
.rf-card{position:relative;border-radius:12px;overflow:hidden;box-shadow:0 2px 10px rgba(0,0,0,.12)}
.rf-card img.rf-img{display:block;width:100%;height:auto}
.rf-fixed{width:260px;max-width:260px;margin:0 auto}
.rf-name-badge{position:absolute;left:50%;transform:translateX(-50%);top:36px;padding:4px 10px;border-radius:999px;font-weight:700;font-size:12px;background:rgba(255,255,255,.96);color:#0f172a;box-shadow:0 1px 4px rgba(0,0,0,.18);border:1px solid rgba(0,0,0,.08);white-space:nowrap;max-width:92%;overflow:hidden;text-overflow:ellipsis}
.rf-qty-badge{position:absolute;right:8px;bottom:8px;background:rgba(0,0,0,.65);color:#fff;padding:2px 8px;border-radius:999px;font-weight:800;font-size:12px;border:1px solid rgba(255,255,255,.25);backdrop-filter:saturate(120%) blur(1px)}
.rf-legal-chip{display:inline-block;margin-left:6px;padding:2px 8px;border-radius:999px;font-weight:800;font-size:11px;border:1px solid rgba(0,0,0,.08)}
.rf-chip-warning{color:#92400e;background:#fef3c7;border-color:#fde68a}
.rf-chip-danger{color:#991b1b;background:#fee2e2;border-color:#fecaca}
.rf-inart-belt{width:260px;margin:-34px auto 8px;display:flex;justify-content:center;gap:12px;position:relative;z-index:3}
.rf-inart-belt div.stButton>button{width:44px;height:40px;padding:0;border-radius:10px;font-size:20px;font-weight:900;line-height:38px;color:#0f172a;background:rgba(255,255,255,.95);border:1px solid rgba(0,0,0,.1);box-shadow:0 1px 4px rgba(0,0,0,.18)}
.rf-inart-belt div.stButton>button:hover{background:#eef2f7}
[data-testid="column"]{padding-left:.35rem;padding-right:.35rem}
@media (max-width:1100px){[data-testid="column"]{padding-left:.25rem;padding-right:.25rem}}
@media (max-width:820px){[data-testid="column"]{padding-left:.20rem;padding-right:.20rem}}
</style>
""", unsafe_allow_html=True)

st.title("\U0001F9D9 Romantic Format Tools")

# --- Deckbuilder only (Aba 3) ---
cols_per_row=st.slider("Colunas por linha",4,8,6)

total=sum(st.session_state.deck.values())
st.markdown(f"**Total de cartas:** {total}")

if not st.session_state.deck:
    st.info("Seu deck está vazio. Adicione cartas na Aba 1 ou cole uma lista no checker.")
else:
    snap=dict(st.session_state.deck)
    names=sorted(snap.keys(), key=lambda x:x.lower())

    def load_one(nm):
        try:
            d=fetch_card_data(nm)
            sets=d.get("sets",set()) if d else set()
            stext,stype=check_legality(nm,sets)
            return (nm,snap.get(nm,0),d.get("type","") if d else "",d.get("image") if d else None,stext,stype)
        except Exception:
            return (nm,snap.get(nm,0),"",None,"","warning")

    with st.spinner("Carregando artes..."):
        with ThreadPoolExecutor(max_workers=min(8,max(1,len(names)))) as ex:
            items=list(ex.map(load_one,names))

    def bucket(tline):
        tl=tline or ""
        if "Land" in tl: return "Terrenos"
        if "Creature" in tl: return "Criaturas"
        if "Instant" in tl: return "Instantâneas"
        if "Sorcery" in tl: return "Feitiços"
        if "Planeswalker" in tl: return "Planeswalkers"
        if "Enchantment" in tl: return "Encantamentos"
        if "Artifact" in tl: return "Artefatos"
        return "Outros"

    buckets=defaultdict(list)
    for nm,qty,tline,img,stext,stype in items:
        buckets[bucket(tline)].append((nm,qty,tline,img,stext,stype))

    for sec in ["Criaturas","Instantâneas","Feitiços","Artefatos","Encantamentos","Planeswalkers","Terrenos","Outros"]:
        if sec not in buckets: continue
        group=buckets[sec]
        st.markdown(f"**{sec} — {sum(q for _,q,_,_,_,_ in group)}**")

        for i in range(0,len(group),cols_per_row):
            row=group[i:i+cols_per_row]
            cols=st.columns(len(row))
            for col,(nm,qty_init,_t,img,stext,stype) in zip(cols,row):
                with col:
                    card_ph=st.empty()
                    qty=st.session_state.deck.get(nm,0)
                    chip_class="" if stype=="success" else (" rf-chip-danger" if stype=="danger" else " rf-chip-warning")
                    legal_html=f"<span class='rf-legal-chip{chip_class}'>"+("Banned" if stype=="danger" else ("Not Legal" if stype=="warning" else ""))+"</span>" if stype!="success" else ""
                    overlay=f"<div class='rf-name-badge'>{nm}{legal_html}</div>"
                    html=f"""
                    <div class='rf-card rf-fixed'>
                      <img src='{img}' class='rf-img'/>
                      {overlay}
                      <div class='rf-qty-badge'>x{qty}</div>
                    </div>"""
                    card_ph.markdown(html, unsafe_allow_html=True)

                    st.markdown("<div class='rf-inart-belt'>", unsafe_allow_html=True)
                    minus_c, plus_c = st.columns([1,1])
                    clicked=False
                    if minus_c.button("−", key=f"belt_m_{sec}_{i}_{nm}"):
                        remove_card(nm,1)
                        if nm not in st.session_state.deck: st.rerun()
                        clicked=True
                    if plus_c.button("+", key=f"belt_p_{sec}_{i}_{nm}"):
                        add_card(nm,1); clicked=True
                    st.markdown("</div>", unsafe_allow_html=True)

                    if clicked:
                        newq=st.session_state.deck.get(nm,0)
                        if newq==0: st.rerun()
                        new_html=f"""
                        <div class='rf-card rf-fixed'>
                          <img src='{img}' class='rf-img'/>
                          {overlay}
                          <div class='rf-qty-badge'>x{newq}</div>
                        </div>"""
                        card_ph.markdown(new_html, unsafe_allow_html=True)
