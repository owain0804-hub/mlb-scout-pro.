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
        .metric-box { background: #1e293b; border: 1px solid #3b82f6; border-radius: 8px; padding: 12px; flex: 1; text-align: center; }
        .metric-box-2 { background: #2b1d3d; border: 1px solid #8b5cf6; border-radius: 8px; padding: 12px; flex: 1; text-align: center; }
        .analysis-box { background: #161b22; border: 1px solid #30363d; border-radius: 8px; padding: 15px; margin-top: 10px; margin-bottom: 20px; }
        .matchup-card { background: #0d1117; border: 1px solid #30363d; border-radius: 12px; padding: 15px; margin-bottom: 15px; display: flex; align-items: center; justify-content: space-between; }
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
            with open(USERS_FILE, 'r') as f:
                users = json.load(f)
            for u in users:
                if "weights" not in users[u] or len(users[u]["weights"]) < 5:
                    users[u]["weights"] = [25, 25, 15, 20, 15]
            return users
        except: return {}
    return {}

def save_users(users):
    with open(USERS_FILE, 'w') as f:
        json.dump(users, f)

def hash_pw(password):
    return hashlib.sha256(password.encode()).hexdigest()

# --- INITIALIZATION ---
st.set_page_config(page_title="MLB AI Scout Pro", layout="wide")
apply_pro_styles()
st_autorefresh(interval=60000, key="mlb_timer")
cookie_manager = stx.CookieManager()
users_db = load_users()

if "auth" not in st.session_state:
    st.session_state.auth = False
if "is_guest" not in st.session_state:
    st.session_state.is_guest = False

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
                    st.session_state.auth = True
                    st.session_state.username = u
                    cookie_manager.set("mlb_login", u, expires_at=datetime(2026, 12, 31))
                    st.rerun()
                else: st.error("Invalid Login.")
        with col2:
            if st.button("Continue without Account", use_container_width=True):
                st.session_state.is_guest = True
                st.session_state.username = "Guest"
                st.rerun()
    with t2:
        nu = st.text_input("New Username", key="reg_u")
        np = st.text_input("New Password", type="password", key="reg_p")
        if st.button("Create Account"):
            if nu and np:
                users_db[nu] = {"pw": hash_pw(np), "fav": "None", "weights": [25, 25, 15, 20, 15], "display_model": 1}
                save_users(users_db); st.success("Created! Go to Login.")
    st.stop()

# --- SIDEBAR ---
user_data = users_db.get(st.session_state.username, {"weights": [25, 25, 15, 20, 15], "display_model": 1, "fav": "None"})
weights_list = user_data.get("weights", [25, 25, 15, 20, 15])

with st.sidebar:
    st.write(f"Logged in as: **{st.session_state.username}**")
    sel_m = st.radio("Model Selection", [1, 2], index=0 if user_data.get("display_model", 1) == 1 else 1)
    
    st.write("### 🎚️ Model 2 Weights")
    w_win = st.slider("Win %", 0, 100, weights_list[0])
    w_era = st.slider("Starter ERA", 0, 100, weights_list[1])
    w_bp = st.slider("Bullpen ERA", 0, 100, weights_list[2])
    w_avg = st.slider("Lineup AVG", 0, 100, weights_list[3])
    w_slg = st.slider("Lineup SLG", 0, 100, weights_list[4])
    
    if st.button("Logout / Exit"):
        st.session_state.auth = False; st.session_state.is_guest = False; st.rerun()

# --- UPDATED BULLPEN ENGINE ---
@st.cache_data(ttl=3600)
def get_bp_era(tid, year):
    try:
        # Tries specific relief pitching stats first
        data = statsapi.get("team_stats", {"teamId": tid, "season": year, "group": "pitching", "stats": "statSplits", "sitCodes": "rp"})
        val = float(data[0]['stat']['era'])
        return val if val > 1.0 else 4.25 # Ignore impossible 0.0 ERAs
    except:
        try:
            # Fallback to general team pitching if bullpen-specific data is missing
            general = statsapi.get("team_stats", {"teamId": tid, "season": year, "group": "pitching", "stats": "season"})
            return float(general[0]['stat']['era'])
        except: return 4.25

@st.cache_data(ttl=3600)
def get_win_pct(tid, year):
    try:
        s = statsapi.standings_data(leagueId="103,104", season=year)
        for div in s.values():
            for t in div['teams']:
                if t['team_id'] == tid: return t['w']/(t['w']+t['l'])
    except: return 0.50

def analyze_game(gid, g_info, year, weights):
    box = statsapi.boxscore_data(gid)
    def process(side, tid):
        sd = box.get(side, {}); ps = sd.get('players', {})
        starters = sorted([p for p in ps.values() if p.get('battingOrder', '') and p.get('battingOrder', '').endswith('00')], key=lambda x: x['battingOrder'])
        lineup, avgs, slgs = [], [], []
        for p in starters:
            try:
                st_data = statsapi.player_stat_data(p['person']['id'], group="hitting", type="season")['stats'][0]['stats']
                lineup.append({"Order": int(p['battingOrder'][0]), "Player": p['person']['fullName'], "AVG": st_data.get('avg', '.250'), "SLG": st_data.get('slg', '.400')})
                avgs.append(float(st_data.get('avg', '.250').replace('.','0.'))); slgs.append(float(st_data.get('slg', '.400').replace('.','0.')))
            except: avgs.append(0.25); slgs.append(0.40)
        p_name, era = "TBD", 4.50
        if sd.get('pitchers'):
            try:
                pid = sd['pitchers'][0]; p_name = ps[f"ID{pid}"]['person']['fullName']
                era = float(statsapi.player_stat_data(pid, group="pitching")['stats'][0]['stats'].get('era', '4.50'))
            except: pass
        return {"wpct": get_win_pct(tid, year), "era": era, "bp_era": get_bp_era(tid, year), "avg": sum(avgs)/max(1, len(avgs)), "slg": sum(slgs)/max(1, len(slgs)), "p": p_name, "lineup": lineup}

    a, h = process('away', g_info['away_id']), process('home', g_info['home_id'])
    
    uw = [v/100 for v in weights]
    # Calculated impact deltas
    imp2 = {
        "Win %": (h['wpct'] - a['wpct']) * uw[0],
        "Starter": ((4.5/max(0.1, h['era'])) - (4.5/max(0.1, a['era']))) * uw[1],
        "Bullpen": ((4.5/max(0.1, h['bp_era'])) - (4.5/max(0.1, a['bp_era']))) * uw[2],
        "AVG": (h['avg'] - a['avg']) * (uw[3]*10),
        "SLG": (h['slg'] - a['slg']) * (uw[4]*7.5)
    }
    p2 = 0.5 + sum(imp2.values()) + 0.02
    return {"prob2": max(0.01, min(0.99, p2)), "away": a, "home": h, "imp2": imp2}

# --- MAIN UI ---
dt = st.date_input("Select Date", datetime.now())
sched = statsapi.schedule(date=dt.strftime("%m/%d/%Y"))

for g in sched:
    st.markdown(f'<div class="matchup-card"><img src="https://www.mlbstatic.com/team-logos/{g["away_id"]}.svg" class="team-logo"><div><b>{g["away_name"]} @ {g["home_name"]}</b></div><img src="https://www.mlbstatic.com/team-logos/{g["home_id"]}.svg" class="team-logo"></div>', unsafe_allow_html=True)
    if st.button("Analyze", key=g['game_id'], use_container_width=True):
        data = analyze_game(g['game_id'], g, dt.year, [w_win, w_era, w_bp, w_avg, w_slg])
        res = g['home_name'] if data['prob2'] > 0.5 else g['away_name']
        st.markdown(f'<div class="mobile-row"><div class="metric-box-2"><small>WIN PROBABILITY</small><br><b>{max(data["prob2"], 1-data["prob2"])*100:.1f}%</b> <span style="color:#4ade80">{res}</span></div></div>', unsafe_allow_html=True)
        
        st.write("### 🧠 AI Logic Breakdown")
        st.markdown('<div class="analysis-box">', unsafe_allow_html=True)
        for cat, imp in data['imp2'].items():
            team_edge = g['home_name'] if imp > 0 else g['away_name']
            st.markdown(f"**{cat}:** <span style='color:#4ade80'>{team_edge} Edge</span> <span class='impact-tag'>(+{abs(imp)*100:.1f}% Impact)</span>", unsafe_allow_html=True)
        st.markdown('</div>', unsafe_allow_html=True)
        st.table(pd.DataFrame({"Team": [g['away_name'], g['home_name']], "R": [g.get('away_score', 0), g.get('home_score', 0)], "Bullpen ERA": [data['away']['bp_era'], data['home']['bp_era']]}))
    
