import streamlit as st
import statsapi
import pandas as pd
import json
import os
import hashlib
import smtplib
import time
import secrets
from email.mime.text import MIMEText
from datetime import datetime
from streamlit_autorefresh import st_autorefresh
import extra_streamlit_components as stx

# --- MOBILE OPTIMIZED STYLING ---
def apply_mobile_pro_styles():
    st.markdown("""
        <style>
        /* Force side-by-side on mobile for key metrics */
        .mobile-row {
            display: flex;
            justify-content: space-between;
            align-items: center;
            margin-bottom: 15px;
            gap: 10px;
        }
        .metric-box {
            background: #1e293b;
            border: 1px solid #3b82f6;
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
        /* Make tables scrollable on small screens */
        .stDataFrame, .stTable {
            overflow-x: auto;
        }
        </style>
    """, unsafe_allow_html=True)

# --- SECURITY & UTILS (Kept same as original) ---
def get_hash(password, salt):
    return hashlib.pbkdf2_hmac('sha256', password.encode(), salt, 100000).hex()

def get_user_file(username):
    safe_name = "".join(x for x in username if x.isalnum())
    return f"profile_{safe_name}.json"

def save_user_data(username, data):
    with open(get_user_file(username), "w") as f:
        json.dump(data, f)

def load_user_data(username):
    path = get_user_file(username)
    if os.path.exists(path):
        try:
            with open(path, "r") as f:
                return json.load(f)
        except: return None
    return None

# --- PAGE CONFIG ---
st.set_page_config(page_title="MLB AI Scout Pro", layout="wide", page_icon="⚾")
apply_mobile_pro_styles()
st_autorefresh(interval=30000, key="mlb_live_timer")
cookie_manager = stx.CookieManager()

if "authenticated" not in st.session_state:
    st.session_state.authenticated = False

# Session Check (Shortened logic for performance)
auth_cookie = cookie_manager.get(cookie="mlb_session_token")
if not st.session_state.authenticated and auth_cookie and ":" in auth_cookie:
    u_name, u_token = auth_cookie.split(":", 1)
    u_data = load_user_data(u_name)
    if u_data and u_data.get("session_token") == u_token:
        st.session_state.authenticated = True
        st.session_state.current_user = u_name
        st.session_state.saved_settings = u_data.get("settings")

if not st.session_state.authenticated:
    st.markdown("<h1 style='text-align:center;'>⚾ MLB Scout Pro</h1>", unsafe_allow_html=True)
    u_in = st.text_input("Username")
    p_in = st.text_input("Password", type="password")
    if st.button("Access System"):
        u_data = load_user_data(u_in)
        if u_data and 'salt' in u_data:
            salt = bytes.fromhex(u_data['salt'])
            if u_data['pwd_hash'] == get_hash(p_in, salt):
                st.session_state.authenticated = True
                st.session_state.current_user = u_in
                st.rerun()
    st.stop()

# --- CORE LOGIC ---
@st.cache_data(ttl=3600)
def get_team_rpg(tid, year):
    try:
        stats = statsapi.team_stats(tid, groups='hitting', season=year)
        for s_set in stats:
            if s_set.get('group') == 'hitting':
                return s_set['stats'].get('runs', 0) / max(1, s_set['stats'].get('gamesPlayed', 1))
    except: return 4.40

@st.cache_data(ttl=3600)
def get_team_wpct(tid, year):
    try:
        standings = statsapi.standings_data(leagueId="103,104", season=year)
        for div in standings.values():
            for t in div.get('teams', []):
                if t['team_id'] == tid: return (int(t['w'])/max(1, int(t['w'])+int(t['l'])))
    except: return 0.50

def get_detailed_data(gid, g_info, year):
    try:
        box = statsapi.boxscore_data(gid)
        def fetch_side(side, tid):
            sd = box.get(side, {})
            ps = sd.get('players', {})
            starters = sorted([{'id': p['person']['id'], 'name': p['person']['fullName'], 'order': int(p['battingOrder'])} 
                               for p in ps.values() if p.get('battingOrder') and p['battingOrder'].endswith('00')], key=lambda x: x['order'])
            
            lineup, avgs, slgs = [], [], []
            for p in starters:
                try:
                    p_st = statsapi.player_stat_data(p['id'], group="hitting", type="season", season=year)['stats'][0]['stats']
                    lineup.append({"#": f"{p['order']//100}", "Player": p['name'], "AVG": p_st.get('avg', '.250')})
                    avgs.append(float(str(p_st.get('avg', '.250')).replace('.','0.')))
                    slgs.append(float(str(p_st.get('slg', '.400')).replace('.','0.')))
                except:
                    lineup.append({"#": f"{p['order']//100}", "Player": p['name'], "AVG": ".250"})
                    avgs.append(0.25); slgs.append(0.40)
            
            p_name, era = "TBD", 4.25
            if sd.get('pitchers'):
                try: 
                    pid = sd['pitchers'][0]
                    p_name = ps.get(f"ID{pid}", {}).get('person', {}).get('fullName', "TBD")
                    era_val = statsapi.player_stat_data(pid, group="pitching", type="season", season=year)['stats'][0]['stats'].get('era', '4.25')
                    era = float(era_val) if era_val != '-.--' else 4.25
                except: pass
            
            wpct, rpg = get_team_wpct(tid, year), get_team_rpg(tid, year)
            # Default weight calculation
            score = (wpct * 25) + ((4.25/max(0.1,era)) * 25) + ((rpg/4.4) * 20) + ((sum(slgs)/max(1,len(slgs))*2.5) * 30)
            return {"score": score, "lineup": lineup, "p_name": p_name, "era": era, "wpct": wpct, "rpg": rpg, "slg": sum(slgs)/max(1,len(slgs))}
        
        a_d, h_d = fetch_side('away', g_info['away_id']), fetch_side('home', g_info['home_id'])
        prob_h = 0.5 + ((h_d['score'] - a_d['score']) * 1.3 / 100) + 0.035
        return {"prob_h": max(0.01, min(0.99, prob_h)), "box": box, "away": a_d, "home": h_d}
    except: return None

# --- UI MAIN ---
u_date = st.date_input("Gameday", datetime.now())
sched = statsapi.schedule(date=u_date.strftime("%m/%d/%Y"))

for g in {g['game_id']: g for g in sched}.values():
    st.markdown(f"""
        <div class="matchup-card">
            <div style="display: flex; justify-content: space-between; align-items: center;">
                <img src="https://www.mlbstatic.com/team-logos/{g['away_id']}.svg" width="40">
                <span style="font-weight: bold; font-size: 1.1em;">{g['away_name']} @ {g['home_name']}</span>
                <img src="https://www.mlbstatic.com/team-logos/{g['home_id']}.svg" width="40">
            </div>
        </div>
    """, unsafe_allow_html=True)
    
    if st.button("Analyze", key=f"btn_{g['game_id']}", use_container_width=True):
        st.session_state.active_game_id = g['game_id']

    if st.session_state.get("active_game_id") == g['game_id']:
        data = get_detailed_data(g['game_id'], g, u_date.year)
        if data:
            h, a = data['home'], data['away']
            res = g['home_name'] if data['prob_h'] > 0.5 else g['away_name']
            conf = (data['prob_h'] if data['prob_h'] > 0.5 else 1-data['prob_h']) * 100
            
            # --- BOX SCORE (Mobile Priority) ---
            st.write("### 🏟️ Live Box Score")
            away_b = data['box'].get('away', {}).get('teamStats', {}).get('batting', {})
            home_b = data['box'].get('home', {}).get('teamStats', {}).get('batting', {})
            st.table(pd.DataFrame({
                "Team": ["Away", "Home"],
                "R": [g.get('away_score', 0), g.get('home_score', 0)],
                "H": [away_b.get('hits', 0), home_b.get('hits', 0)],
                "E": [away_b.get('errors', 0), home_b.get('errors', 0)]
            }))

            # --- SIDE-BY-SIDE PROBABILITY & EDGE ---
            st.markdown(f"""
                <div class="mobile-row">
                    <div class="metric-box">
                        <small>PROBABILITY</small><br>
                        <b style="font-size: 1.2em; color: #60a5fa;">{conf:.1f}%</b>
                    </div>
                    <div class="metric-box">
                        <small>PROJECTED EDGE</small><br>
                        <b style="font-size: 1.2em; color: #4ade80;">{res}</b>
                    </div>
                </div>
            """, unsafe_allow_html=True)

            # --- SCOUTING & LINEUPS ---
            with st.expander("📊 Detailed Scouting"):
                st.table(pd.DataFrame([
                    {"Stat": "Win %", "Home": f"{h['wpct']:.3f}", "Away": f"{a['wpct']:.3f}"},
                    {"Stat": "ERA", "Home": f"{h['era']:.2f}", "Away": f"{a['era']:.2f}"},
                    {"Stat": "Runs/G", "Home": f"{h['rpg']:.2f}", "Away": f"{a['rpg']:.2f}"}
                ]))
                st.write(f"**{g['away_name']} Lineup**")
                st.dataframe(pd.DataFrame(a['lineup']), hide_index=True)
                st.write(f"**{g['home_name']} Lineup**")
                st.dataframe(pd.DataFrame(h['lineup']), hide_index=True)
                    
