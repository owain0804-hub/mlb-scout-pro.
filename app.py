import streamlit as st
import statsapi
import pandas as pd
import json
import os
import hashlib
from datetime import datetime
from streamlit_autorefresh import st_autorefresh
import extra_streamlit_components as stx

# --- MOBILE & UI STYLING ---
def apply_pro_styles():
    st.markdown("""
        <style>
        .mobile-row { display: flex; justify-content: space-between; gap: 10px; margin-bottom: 15px; }
        .metric-box-2 { background: #2b1d3d; border: 1px solid #8b5cf6; border-radius: 8px; padding: 12px; flex: 1; text-align: center; }
        .analysis-box { background: #161b22; border: 1px solid #30363d; border-radius: 8px; padding: 15px; margin-top: 10px; margin-bottom: 20px; }
        .matchup-card { background: #0d1117; border: 1px solid #30363d; border-radius: 12px; padding: 15px; margin-bottom: 5px; display: flex; align-items: center; justify-content: space-between; }
        .status-tag { font-size: 0.7em; padding: 2px 6px; border-radius: 4px; background: #30363d; color: #8b949e; }
        .pitcher-header { background: #161b22; border-bottom: 2px solid #3fb950; padding: 8px; margin-bottom: 5px; border-radius: 4px 4px 0 0; font-weight: bold; display: flex; align-items: center; gap: 10px; }
        .team-logo { width: 40px; height: 40px; }
        .impact-tag { font-size: 0.85em; color: #94a3b8; margin-left: 8px; }
        </style>
    """, unsafe_allow_html=True)

# --- PERSISTENCE ---
USERS_FILE = "users_db.json"
def load_users():
    if os.path.exists(USERS_FILE):
        try:
            with open(USERS_FILE, 'r') as f: return json.load(f)
        except: return {}
    return {}

def save_users(users):
    with open(USERS_FILE, 'w') as f: json.dump(users, f)

def hash_pw(password): return hashlib.sha256(password.encode()).hexdigest()

# --- INITIALIZATION ---
st.set_page_config(page_title="MLB AI Scout Pro", layout="wide")
apply_pro_styles()
st_autorefresh(interval=60000, key="mlb_timer")
cookie_manager = stx.CookieManager()
users_db = load_users()

if "auth" not in st.session_state: st.session_state.auth = False
if "is_guest" not in st.session_state: st.session_state.is_guest = False

saved_user = cookie_manager.get(cookie="mlb_login")
if not st.session_state.auth and saved_user and saved_user in users_db:
    st.session_state.auth, st.session_state.username = True, saved_user

# --- LOGIN FLOW ---
if not st.session_state.auth and not st.session_state.is_guest:
    st.title("⚾ MLB Scout Pro")
    t1, t2 = st.tabs(["Login", "Register"])
    with t1:
        u = st.text_input("Username", key="login_u")
        p = st.text_input("Password", type="password", key="login_p")
        col1, col2 = st.columns(2)
        with col1:
            if st.button("Enter", use_container_width=True):
                if u in users_db and users_db[u].get('pw') == hash_pw(p):
                    st.session_state.auth, st.session_state.username = True, u
                    cookie_manager.set("mlb_login", u, expires_at=datetime(2026, 12, 31))
                    st.rerun()
                else: st.error("Invalid Login.")
        with col2:
            if st.button("Continue without Account", use_container_width=True):
                st.session_state.is_guest, st.session_state.username = True, "Guest"
                st.rerun()
    st.stop()

# --- SIDEBAR ---
user_data = users_db.get(st.session_state.username, {"weights": [30, 40, 15, 15]})
weights_list = user_data.get("weights", [30, 40, 15, 15])

with st.sidebar:
    st.write(f"Logged in as: **{st.session_state.username}**")
    w_win = st.slider("Win %", 0, 100, weights_list[0])
    w_era = st.slider("Starter ERA", 0, 100, weights_list[1])
    w_avg = st.slider("Lineup AVG", 0, 100, weights_list[2])
    w_slg = st.slider("Lineup SLG", 0, 100, weights_list[3])
    if st.button("Logout / Exit"):
        st.session_state.auth = False; st.session_state.is_guest = False; st.rerun()

# --- DATA ENGINE (WITH SPRING TRAINING FALLBACK) ---
@st.cache_data(ttl=3600)
def get_win_pct(tid, year):
    # Use 2025 data if it's currently Spring Training 2026
    lookup_year = year - 1 if datetime.now().month < 4 else year
    try:
        s = statsapi.standings_data(leagueId="103,104", season=lookup_year)
        for div in s.values():
            for t in div['teams']:
                if t['team_id'] == tid: return t['w']/(max(1, t['w']+t['l']))
    except: return 0.50

def analyze_game(gid, g_info, year, weights):
    try: box = statsapi.boxscore_data(gid)
    except: box = {}
    
    def process(side, tid):
        sd = box.get(side, {}); ps = sd.get('players', {})
        starters = sorted([p for p in ps.values() if p.get('battingOrder', '') and p.get('battingOrder', '').endswith('00')], key=lambda x: x['battingOrder'])
        lineup, avgs, slgs = [], [], []
        
        # If no live lineup (Spring Training), use placeholder league averages
        if not starters:
            lineup = [{"Order": i, "Player": "Spring Roster", "AVG": ".260", "SLG": ".410"} for i in range(1, 10)]
            avg, slg = 0.260, 0.410
        else:
            for p in starters:
                try:
                    st_data = statsapi.player_stat_data(p['person']['id'], group="hitting", type="season")['stats'][0]['stats']
                    lineup.append({"Order": int(p['battingOrder'][0]), "Player": p['person']['fullName'], "AVG": st_data.get('avg', '.250'), "SLG": st_data.get('slg', '.400')})
                    avgs.append(float(st_data.get('avg', '.250').replace('.','0.'))); slgs.append(float(st_data.get('slg', '.400').replace('.','0.')))
                except: avgs.append(0.25); slgs.append(0.40)
            avg, slg = sum(avgs)/max(1, len(avgs)), sum(slgs)/max(1, len(slgs))
            
        p_name = g_info.get(f'{side}_probable_pitcher', "TBD")
        era = 4.50
        return {"wpct": get_win_pct(tid, year), "era": era, "avg": avg, "slg": slg, "p": p_name, "lineup": lineup}

    a, h = process('away', g_info['away_id']), process('home', g_info['home_id'])
    uw = [v/100 for v in weights]
    imp = {
        "Win %": (h['wpct'] - a['wpct']) * uw[0],
        "Starter": ((4.5/max(0.1, h['era'])) - (4.5/max(0.1, a['era']))) * uw[1],
        "AVG": (h['avg'] - a['avg']) * (uw[2]*10),
        "SLG": (h['slg'] - a['slg']) * (uw[3]*7.5)
    }
    p_final = 0.5 + sum(imp.values()) + 0.02
    return {"prob": max(0.01, min(0.99, p_final)), "away": a, "home": h, "imp": imp}

# --- MAIN UI ---
dt = st.date_input("Select Date", datetime.now())
sched = statsapi.schedule(date=dt.strftime("%m/%d/%Y"))

for g in sched:
    status = g.get('status', 'Scheduled')
    st.markdown(f'''
        <div class="matchup-card">
            <img src="https://www.mlbstatic.com/team-logos/{g["away_id"]}.svg" class="team-logo">
            <div style="text-align:center">
                <b>{g["away_name"]} @ {g["home_name"]}</b><br>
                <span class="status-tag">{status}</span>
            </div>
            <img src="https://www.mlbstatic.com/team-logos/{g["home_id"]}.svg" class="team-logo">
        </div>
    ''', unsafe_allow_html=True)
    
    if st.button("Analyze", key=g['game_id'], use_container_width=True):
        data = analyze_game(g['game_id'], g, dt.year, [w_win, w_era, w_avg, w_slg])
        res = g['home_name'] if data['prob'] > 0.5 else g['away_name']
        
        st.markdown(f'<div class="mobile-row"><div class="metric-box-2"><small>WIN PROBABILITY</small><br><b>{max(data["prob"], 1-data["prob"])*100:.1f}%</b> <span style="color:#4ade80">{res}</span></div></div>', unsafe_allow_html=True)
        
        st.write("### 🧠 AI Logic Breakdown")
        st.markdown('<div class="analysis-box">', unsafe_allow_html=True)
        for cat, val in data['imp'].items():
            team_edge = g['home_name'] if val > 0 else g['away_name']
            st.markdown(f"**{cat}:** <span style='color:#4ade80'>{team_edge} Edge</span> <span class='impact-tag'>(+{abs(val)*100:.1f}% Impact)</span>", unsafe_allow_html=True)
        st.markdown('</div>', unsafe_allow_html=True)
        
        st.table(pd.DataFrame({"Team": [g['away_name'], g['home_name']], "R": [g.get('away_score', 0), g.get('home_score', 0)]}))
        c1, c2 = st.columns(2)
        with c1:
            st.markdown(f'<div class="pitcher-header">{data["away"]["p"]} (Away)</div>', unsafe_allow_html=True)
            st.dataframe(pd.DataFrame(data['away']['lineup']), hide_index=True)
        with c2:
            st.markdown(f'<div class="pitcher-header">{data["home"]["p"]} (Home)</div>', unsafe_allow_html=True)
            st.dataframe(pd.DataFrame(data['home']['lineup']), hide_index=True)
    
