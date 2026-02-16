import streamlit as st
import statsapi
import pandas as pd  # FIXED: Corrected import from 'pd' to 'pandas as pd'
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
            users = json.load(f)
            # REPAIR LOGIC: Ensure all users have 5 weights and valid structure
            for u in users:
                if "weights" in users[u] and len(users[u]["weights"]) < 5:
                    users[u]["weights"] = [25, 25, 15, 20, 15]
            return users
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
saved_user = cookie_manager.get(cookie="mlb_login")
if not st.session_state.auth and saved_user and saved_user in users_db:
    st.session_state.auth, st.session_state.username = True, saved_user

# --- LOGIN (FIXED KEYERROR) ---
if not st.session_state.auth:
    st.title("⚾ MLB Scout Pro")
    t1, t2 = st.tabs(["Login", "Register"])
    with t1:
        u, p = st.text_input("Username"), st.text_input("Password", type="password")
        if st.button("Enter"):
            # FIXED: Safer dictionary access to prevent KeyError
            if u in users_db and users_db[u].get('pw') == hash_pw(p):
                st.session_state.auth, st.session_state.username = True, u
                cookie_manager.set("mlb_login", u, expires_at=datetime(2026, 12, 31))
                st.rerun()
            else: st.error("Incorrect Username or Password.")
    with t2:
        nu, np = st.text_input("New Username"), st.text_input("New Password", type="password")
        if st.button("Create Account") and nu and np:
            users_db[nu] = {"pw": hash_pw(np), "fav": "None", "weights": [25, 25, 15, 20, 15], "display_model": 1}
            save_users(users_db); st.success("Account Created! Please Login.")
    st.stop()

# --- SIDEBAR & DATA VALIDATION (FIXED INDEXERROR) ---
user_data = users_db.get(st.session_state.username, {})
weights_list = user_data.get("weights", [25, 25, 15, 20, 15])
# Ensure we have exactly 5 weights for the 5 sliders
if len(weights_list) != 5:
    weights_list = [25, 25, 15, 20, 15]

with st.sidebar:
    st.write(f"User: **{st.session_state.username}**")
    cur_m = user_data.get("display_model", 1)
    sel_m = st.radio("Model Selection", [1, 2], index=0 if cur_m == 1 else 1)
    st.divider()
    all_teams = sorted([t['name'] for t in statsapi.get('teams', {'sportId': 1})['teams']])
    fav_team_val = user_data.get("fav", "None")
    fav_idx = (["None"] + all_teams).index(fav_team_val) if fav_team_val in (["None"] + all_teams) else 0
    fav = st.selectbox("Favorite Team", ["None"] + all_teams, index=fav_idx)
    st.divider()
    st.write("### 🎚️ Model 2 Weights")
    w_win = st.slider("Win %", 0, 100, weights_list[0])
    w_era = st.slider("Starter ERA", 0, 100, weights_list[1])
    w_bp = st.slider("Bullpen ERA", 0, 100, weights_list[2])
    w_avg = st.slider("Lineup AVG", 0, 100, weights_list[3])
    w_slg = st.slider("Lineup SLG", 0, 100, weights_list[4])
    if st.button("Save All Settings"):
        users_db[st.session_state.username].update({"fav": fav, "weights": [w_win, w_era, w_bp, w_avg, w_slg], "display_model": sel_m})
        save_users(users_db); st.toast("Saved!"); st.rerun()
    if st.button("Logout"): cookie_manager.delete("mlb_login"); st.session_state.auth = False; st.rerun()

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
        return {"wpct": get_win_pct(tid, year), "era": era, "bp_era": get_bp_era(tid, year), "avg": sum(avgs)/max(1, len(avgs)), "slg": sum(slgs)/max(1, len(slgs)), "p": p_name, "lineup": lineup}

    a, h = process('away', g_info['away_id']), process('home', g_info['home_id'])
    
    imp1 = {
        "Win %": (h['wpct'] - a['wpct']) * 0.25,
        "Starter": ((4.5/max(0.1, h['era'])) - (4.5/max(0.1, a['era']))) * 0.25,
        "Bullpen": ((4.5/max(0.1, h['bp_era'])) - (4.5/max(0.1, a['bp_era']))) * 0.15,
        "AVG": (h['avg'] - a['avg']) * 1.5,
        "SLG": (h['slg'] - a['slg']) * 1.2
    }
    p1 = 0.5 + sum(imp1.values()) + 0.02
    
    uw = [v/100 for v in weights]
    imp2 = {
        "Win %": (h['wpct'] - a['wpct']) * uw[0],
        "Starter": ((4.5/max(0.1, h['era'])) - (4.5/max(0.1, a['era']))) * uw[1],
        "Bullpen": ((4.5/max(0.1, h['bp_era'])) - (4.5/max(0.1, a['bp_era']))) * uw[2],
        "AVG": (h['avg'] - a['avg']) * (uw[3]*10),
        "SLG": (h['slg'] - a['slg']) * (uw[4]*7.5)
    }
    p2 = 0.5 + sum(imp2.values()) + 0.02
    
    return {"prob1": max(0.01, min(0.99, p1)), "prob2": max(0.01, min(0.99, p2)), "away": a, "home": h, "imp1": imp1, "imp2": imp2}

# --- MAIN UI ---
dt = st.date_input("Date", datetime.now())
sched = statsapi.schedule(date=dt.strftime("%m/%d/%Y"))
sorted_sched = sorted(sched, key=lambda x: (x['home_name'] != fav and x['away_name'] != fav))

for g in sorted_sched:
    is_f = (g['home_name'] == fav or g['away_name'] == fav)
    st.markdown(f'<div class="matchup-card" style="{"border: 2px solid #eab308;" if is_f else ""}"><img src="https://www.mlbstatic.com/team-logos/{g["away_id"]}.svg" class="team-logo"><div style="text-align:center;"><b>{g["away_name"]} @ {g["home_name"]}</b></div><img src="https://www.mlbstatic.com/team-logos/{g["home_id"]}.svg" class="team-logo"></div>', unsafe_allow_html=True)
    if st.button("Analyze", key=g['game_id'], use_container_width=True):
        data = analyze_game(g['game_id'], g, dt.year, weights_list)
        p_val = data['prob1'] if sel_m == 1 else data['prob2']
        active_imps = data['imp1'] if sel_m == 1 else data['imp2']
        res = g['home_name'] if p_val > 0.5 else g['away_name']
        
        st.markdown(f'<div class="mobile-row"><div class="{"metric-box" if sel_m==1 else "metric-box-2"}"><small>PROBABILITY {sel_m}</small><br><b>{max(p_val, 1-p_val)*100:.1f}%</b> <span style="color:#4ade80">{res}</span></div></div>', unsafe_allow_html=True)
        
        st.write("### 🧠 AI Logic Breakdown")
        with st.container():
            st.markdown('<div class="analysis-box">', unsafe_allow_html=True)
            for cat, imp in active_imps.items():
                team_edge = g['home_name'] if imp > 0 else g['away_name']
                color = "#4ade80" if team_edge == g['home_name'] else "#3b82f6"
                st.markdown(f"**{cat}:** <span style='color:{color}'>{team_edge} Edge</span> <span class='impact-tag'>(+{abs(imp)*100:.1f}% to Win Prob)</span>", unsafe_allow_html=True)
            st.write(f"*Includes +2.0% Home Edge for {g['home_name']}.*")
            st.markdown('</div>', unsafe_allow_html=True)
        
        st.write("### 🏟️ Live Score")
        st.table(pd.DataFrame({"Team": [g['away_name'], g['home_name']], "R": [g.get('away_score', 0), g.get('home_score', 0)]}))
        c1, c2 = st.columns(2)
        with c1:
            st.markdown(f'<div class="pitcher-header"><img src="https://www.mlbstatic.com/team-logos/{g["away_id"]}.svg" width="20"> {data["away"]["p"]} ({data["away"]["era"]})</div>', unsafe_allow_html=True)
            st.dataframe(pd.DataFrame(data['away']['lineup']), hide_index=True)
        with c2:
            st.markdown(f'<div class="pitcher-header"><img src="https://www.mlbstatic.com/team-logos/{g["home_id"]}.svg" width="20"> {data["home"]["p"]} ({data["home"]["era"]})</div>', unsafe_allow_html=True)
            st.dataframe(pd.DataFrame(data['home']['lineup']), hide_index=True)
    
