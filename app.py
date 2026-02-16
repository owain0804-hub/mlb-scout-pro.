import streamlit as st
import statsapi
import pandas as pd
import json
import os
import hashlib
import time
from datetime import datetime
from streamlit_autorefresh import st_autorefresh
import extra_streamlit_components as stx

# --- MOBILE & UI STYLING ---
def apply_pro_styles():
    # NOTE: This is a standard string (not an f-string) to avoid CSS syntax errors
    st.markdown("""
        <style>
        .mobile-row {
            display: flex;
            justify-content: space-between;
            gap: 10px;
            margin-bottom: 15px;
        }
        .metric-box {
            background: #1e293b;
            border: 1px solid #3b82f6;
            border-radius: 8px;
            padding: 12px;
            flex: 1;
            text-align: center;
        }
        .metric-box-2 {
            background: #2b1d3d; /* Purple tint for Prob 2 */
            border: 1px solid #8b5cf6;
            border-radius: 8px;
            padding: 12px;
            flex: 1;
            text-align: center;
        }
        .matchup-card {
            background: #0d1117;
            border: 1px solid #30363d;
            border-radius: 12px;
            padding: 15px;
            margin-bottom: 15px;
        }
        .pitcher-header {
            background: #161b22;
            border-bottom: 2px solid #3fb950;
            padding: 8px;
            margin-bottom: 5px;
            border-radius: 4px 4px 0 0;
            font-weight: bold;
        }
        </style>
    """, unsafe_allow_html=True)

# --- USER & PERSISTENCE LOGIC ---
USERS_FILE = "users_db.json"

def load_users():
    if os.path.exists(USERS_FILE):
        with open(USERS_FILE, 'r') as f: return json.load(f)
    return {}

def save_users(users):
    with open(USERS_FILE, 'w') as f: json.dump(users, f)

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

# Cookie Persistence
saved_user = cookie_manager.get(cookie="mlb_login")
if not st.session_state.auth and saved_user in users_db:
    st.session_state.auth = True
    st.session_state.username = saved_user

# --- LOGIN SCREEN ---
if not st.session_state.auth:
    st.title("⚾ MLB Scout Pro")
    t1, t2 = st.tabs(["Login", "Register"])
    with t1:
        u = st.text_input("Username")
        p = st.text_input("Password", type="password")
        if st.button("Enter"):
            if u in users_db and users_db[u]['pw'] == hash_pw(p):
                st.session_state.auth = True
                st.session_state.username = u
                cookie_manager.set("mlb_login", u, expires_at=datetime(2026, 12, 31))
                st.rerun()
            else: st.error("Try again.")
    with t2:
        nu = st.text_input("New Username")
        np = st.text_input("New Password", type="password")
        if st.button("Create Account"):
            if nu and np and nu not in users_db:
                # Default weights: 30, 30, 20, 20
                users_db[nu] = {"pw": hash_pw(np), "fav": "None", "weights": [30, 30, 20, 20]}
                save_users(users_db)
                st.success("Account ready!")
    st.stop()

# --- SIDEBAR (Settings & Sliders) ---
with st.sidebar:
    st.write(f"Logged in as: **{st.session_state.username}**")
    
    # Favorite Team
    all_teams = sorted([t['name'] for t in statsapi.get('teams', {'sportId': 1})['teams']])
    curr_fav = users_db[st.session_state.username].get("fav", "None")
    # Safe index finding
    fav_idx = (["None"] + all_teams).index(curr_fav) if curr_fav in (["None"] + all_teams) else 0
    fav = st.selectbox("Favorite Team", ["None"] + all_teams, index=fav_idx)
    
    st.divider()
    st.write("### 🎚️ Probability 2 Settings")
    st.caption("Adjust how much each stat matters for your custom model.")
    
    # Load current weights or default
    current_weights = users_db[st.session_state.username].get("weights", [30, 30, 20, 20])
    
    w_win = st.slider("Win % Weight", 0, 100, current_weights[0])
    w_era = st.slider("Pitcher ERA Weight", 0, 100, current_weights[1])
    w_avg = st.slider("Lineup AVG Weight", 0, 100, current_weights[2])
    w_slg = st.slider("Lineup SLG Weight", 0, 100, current_weights[3])
    
    if st.button("Save Settings"):
        users_db[st.session_state.username]['fav'] = fav
        users_db[st.session_state.username]['weights'] = [w_win, w_era, w_avg, w_slg]
        save_users(users_db)
        st.toast("Settings Saved!")
        time.sleep(1)
        st.rerun()

    if st.button("Logout"):
        cookie_manager.delete("mlb_login")
        st.session_state.auth = False
        st.rerun()

# --- DATA ENGINE ---
@st.cache_data(ttl=3600)
def get_stats(tid, year):
    try:
        s = statsapi.standings_data(leagueId="103,104", season=year)
        for div in s.values():
            for t in div['teams']:
                if t['team_id'] == tid: return (t['w']/(t['w']+t['l']))
    except: return 0.50

def analyze_game(gid, g_info, year, weights):
    box = statsapi.boxscore_data(gid)
    def process(side, tid):
        sd = box.get(side, {})
        ps = sd.get('players', {})
        # Lineup Stats
        starters = [p for p in ps.values() if p.get('battingOrder') and p['battingOrder'].endswith('00')]
        avgs, slgs, lineup = [], [], []
        for p in starters:
            try:
                st_data = statsapi.player_stat_data(p['person']['id'], group="hitting", type="season")['stats'][0]['stats']
                lineup.append({"Player": p['person']['fullName'], "AVG": st_data.get('avg', '.250'), "SLG": st_data.get('slg', '.400')})
                avgs.append(float(st_data.get('avg', '.250').replace('.','0.')))
                slgs.append(float(st_data.get('slg', '.400').replace('.','0.')))
            except: avgs.append(0.25); slgs.append(0.40)
        # Pitcher
        p_name, era = "TBD", 4.50
        if sd.get('pitchers'):
            try:
                pid = sd['pitchers'][0]
                p_name = ps[f"ID{pid}"]['person']['fullName']
                era = float(statsapi.player_stat_data(pid, group="pitching")['stats'][0]['stats'].get('era', '4.50'))
            except: pass
        return {"wpct": get_stats(tid, year), "era": era, "avg": sum(avgs)/max(1, len(avgs)), "slg": sum(slgs)/max(1, len(slgs)), "p": p_name, "lineup": lineup}

    a, h = process('away', g_info['away_id']), process('home', g_info['home_id'])
    
    # --- PROBABILITY 1 (STANDARD: 30/30/20/20) ---
    s1_h = (h['wpct']*0.3) + ((4.5/max(0.1, h['era']))*0.3) + (h['avg']*2.0) + (h['slg']*1.5)
    s1_a = (a['wpct']*0.3) + ((4.5/max(0.1, a['era']))*0.3) + (a['avg']*2.0) + (a['slg']*1.5)
    prob1 = 0.5 + (s1_h - s1_a) + 0.03 # 3% Home Field

    # --- PROBABILITY 2 (USER SLIDERS) ---
    # Normalize weights to ensure they don't break the math if they add up to weird numbers
    u_win, u_era, u_avg, u_slg = weights[0]/100, weights[1]/100, weights[2]/100, weights[3]/100
    
    s2_h = (h['wpct']*u_win) + ((4.5/max(0.1, h['era']))*u_era) + (h['avg']*(u_avg*10)) + (h['slg']*(u_slg*7.5))
    s2_a = (a['wpct']*u_win) + ((4.5/max(0.1, a['era']))*u_era) + (a['avg']*(u_avg*10)) + (a['slg']*(u_slg*7.5))
    prob2 = 0.5 + (s2_h - s2_a) + 0.03

    return {"prob1": max(0.01, min(0.99, prob1)), "prob2": max(0.01, min(0.99, prob2)), "box": box, "away": a, "home": h}

# --- MAIN UI ---
dt = st.date_input("Select Date", datetime.now())
sched = statsapi.schedule(date=dt.strftime("%m/%d/%Y"))
fav_team = users_db[st.session_state.username].get("fav", "None")
user_weights = users_db[st.session_state.username].get("weights", [30, 30, 20, 20])

for g in sched:
    is_fav = (g['home_name'] == fav_team or g['away_name'] == fav_team)
    
    # --- FIX: Define style outside f-string to prevent SyntaxError ---
    if is_fav:
        card_style = "border-color: #eab308; border-width: 2px;"
    else:
        card_style = ""
        
    with st.container():
        # Using the pre-calculated card_style variable
        st.markdown(f'<div class="matchup-card" style="{card_style}"><b>{g["away_name"]} @ {g["home_name"]}</b></div>', unsafe_allow_html=True)
        
        if st.button("Analyze", key=g['game_id'], use_container_width=True):
            data = analyze_game(g['game_id'], g, dt.year, user_weights)
            
            # 1. LIVE BOX SCORE
            st.write("### 🏟️ Live Score")
            st.table(pd.DataFrame({
                "Team": [g['away_name'], g['home_name']], 
                "R": [g.get('away_score', 0), g.get('home_score', 0)]
            }))
            
            # 2. PROBABILITY & EDGE (Side-by-Side)
            res1 = g['home_name'] if data['prob1'] > 0.5 else g['away_name']
            res2 = g['home_name'] if data['prob2'] > 0.5 else g['away_name']
            conf1 = max(data["prob1"], 1-data["prob1"])*100
            conf2 = max(data["prob2"], 1-data["prob2"])*100

            # Standard Prob
            st.markdown(f"""
            <div class="mobile-row">
                <div class="metric-box">
                    <small>PROBABILITY 1 (Standard)</small><br>
                    <b>{conf1:.1f}%</b> <span style="color:#4ade80">{res1}</span>
                </div>
            </div>
            """, unsafe_allow_html=True)

            # Custom Prob 2 (If sliders are used)
            st.markdown(f"""
            <div class="mobile-row">
                <div class="metric-box-2">
                    <small>PROBABILITY 2 (Custom)</small><br>
                    <b>{conf2:.1f}%</b> <span style="color:#a78bfa">{res2}</span>
                </div>
            </div>
            """, unsafe_allow_html=True)

            # 3. PITCHERS & LINEUPS
            c1, c2 = st.columns(2)
            with c1:
                st.markdown(f'<div class="pitcher-header">{data["away"]["p"]} (ERA: {data["away"]["era"]})</div>', unsafe_allow_html=True)
                st.dataframe(pd.DataFrame(data['away']['lineup']), hide_index=True)
            with c2:
                st.markdown(f'<div class="pitcher-header">{data["home"]["p"]} (ERA: {data["home"]["era"]})</div>', unsafe_allow_html=True)
                st.dataframe(pd.DataFrame(data['home']['lineup']), hide_index=True)
    
