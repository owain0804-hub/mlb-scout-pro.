import streamlit as st
import statsapi
import pandas as pd  # FIXED: Ensures 'pd' is recognized throughout the app
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

# --- PERSISTENCE & AUTO-REPAIR ---
USERS_FILE = "users_db.json"

def load_users():
    if os.path.exists(USERS_FILE):
        try:
            with open(USERS_FILE, 'r') as f:
                users = json.load(f)
            # Repair legacy users to ensure 5 weights exist
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

saved_user = cookie_manager.get(cookie="mlb_login")
if not st.session_state.auth and saved_user and saved_user in users_db:
    st.session_state.auth, st.session_state.username = True, saved_user

# --- LOGIN FLOW ---
if not st.session_state.auth:
    st.title("⚾ MLB Scout Pro")
    t1, t2 = st.tabs(["Login", "Register"])
    with t1:
        u = st.text_input("Username", key="login_u")
        p = st.text_input("Password", type="password", key="login_p")
        if st.button("Enter"):
            if u in users_db and users_db[u].get('pw') == hash_pw(p):
                st.session_state.auth = True
                st.session_state.username = u
                cookie_manager.set("mlb_login", u, expires_at=datetime(2026, 12, 31))
                st.rerun()
            else:
                st.error("Invalid Username or Password.")
    with t2:
        nu = st.text_input("New Username", key="reg_u")
        np = st.text_input("New Password", type="password", key="reg_p")
        if st.button("Create Account"):
            if nu and np:
                if nu in users_db: st.error("Username already exists!")
                else:
                    users_db[nu] = {"pw": hash_pw(np), "fav": "None", "weights": [25, 25, 15, 20, 15], "display_model": 1}
                    save_users(users_db)
                    st.success("Account created! Please switch to 'Login' tab.")
    st.stop()

# --- SIDEBAR & WEIGHTS ---
user_data = users_db.get(st.session_state.username, {})
weights_list = user_data.get("weights", [25, 25, 15, 20, 15])

with st.sidebar:
    st.write(f"User: **{st.session_state.username}**")
    cur_m = user_data.get("display_model", 1)
    sel_m = st.radio("Model Selection", [1, 2], index=0 if cur_m == 1 else 1)
    st.divider()
    
    try:
        all_teams = sorted([t['name'] for t in statsapi.get('teams', {'sportId': 1})['teams']])
    except: all_teams = []
        
    fav = st.selectbox("Favorite Team", ["None"] + all_teams, index=0)
    st.divider()
    
    st.write("### 🎚️ Model 2 Weights")
    w_win = st.slider("Win %", 0, 100, weights_list[0])
    w_era = st.slider("Starter ERA", 0, 100, weights_list[1])
    w_bp = st.slider("Bullpen ERA", 0, 100, weights_list[2])
    w_avg = st.slider("Lineup AVG", 0, 100, weights_list[3])
    w_slg = st.slider("Lineup SLG", 0, 100, weights_list[4])
    
    if st.button("Save All Settings"):
        users_db[st.session_state.username].update({"fav": fav, "weights": [w_win, w_era, w_bp, w_avg, w_slg], "display_model": sel_m})
        save_users(users_db)
        st.toast("Settings Saved!"); st.rerun()
    
    if st.button("Logout"):
        cookie_manager.delete("mlb_login"); st.session_state.auth = False; st.rerun()

# --- DATA ENGINE ---
@st.cache_data(ttl=3600)
def get_bp_era(tid, year):
    try:
        data = statsapi.get("team_stats", {"teamId": tid, "season": year, "group": "pitching", "stats": "statSplits", "sitCodes": "rp"})
        return float(data[0]['stat']['era'])
    except: return 4.20

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
        return {"wpct": get_win_pct(tid, year), "era": era, "bp_era": get_bp_era(tid, year), "avg": sum(avgs)/max(1, len(avgs)), "slg":
    
