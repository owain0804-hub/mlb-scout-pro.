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

# --- SECURE CONFIGURATION ---
SMTP_SERVER = "smtp.gmail.com"
SMTP_PORT = 587
SENDER_EMAIL = st.secrets.get("SENDER_EMAIL", "owainbaseball@gmail.com") 
SENDER_PASSWORD = st.secrets.get("SENDER_PASSWORD", "lixs qgpo ihyd ikiq") 
ADMIN_EMAIL = st.secrets.get("ADMIN_EMAIL", "owainbaseball@gmail.com")

# --- CUSTOM "PRO" STYLING ---
def apply_pro_styles():
    st.markdown("""
        <style>
        @import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;700;900&display=swap');
        
        html, body, [class*="st-"] { font-family: 'Inter', sans-serif; }
        
        /* Card Styling */
        .matchup-card {
            background: #0d1117;
            border: 1px solid #30363d;
            border-radius: 12px;
            padding: 24px;
            margin-bottom: 20px;
            transition: transform 0.2s;
        }
        .matchup-card:hover { border-color: #58a6ff; transform: translateY(-2px); }
        
        /* Prediction Banner */
        .prediction-banner {
            background: linear-gradient(90deg, #1e3a8a 0%, #1e40af 100%);
            border-radius: 8px;
            padding: 20px;
            text-align: center;
            margin-bottom: 15px;
            border: 1px solid #3b82f6;
        }
        
        /* Stat Pill */
        .stat-pill {
            background: #161b22;
            padding: 4px 12px;
            border-radius: 20px;
            border: 1px solid #30363d;
            font-size: 0.85em;
            font-weight: 600;
        }
        
        /* Metric Edge Colors */
        .edge-green { color: #3fb950; font-weight: bold; }
        .edge-red { color: #f85149; font-weight: bold; }
        </style>
    """, unsafe_allow_html=True)

# --- SECURITY HELPERS ---
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
apply_pro_styles()
st_autorefresh(interval=30000, key="mlb_live_timer")
cookie_manager = stx.CookieManager()

if "authenticated" not in st.session_state:
    st.session_state.authenticated = False

# Session Check (Shortened for brevity - keeps existing auth logic)
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
    c1, c2, c3 = st.columns([1, 2, 1])
    with c2:
        tab1, tab2 = st.tabs(["Login", "Register"])
        with tab1:
            u_in = st.text_input("Username")
            p_in = st.text_input("Password", type="password")
            if st.button("Access Dashboard"):
                u_data = load_user_data(u_in)
                if u_data and 'salt' in u_data:
                    salt = bytes.fromhex(u_data['salt'])
                    if u_data['pwd_hash'] == get_hash(p_in, salt):
                        new_token = secrets.token_urlsafe(32)
                        u_data['session_token'] = new_token
                        save_user_data(u_in, u_data)
                        cookie_manager.set("mlb_session_token", f"{u_in}:{new_token}", key="login_cook")
                        st.session_state.authenticated = True
                        st.session_state.current_user = u_in
                        st.session_state.saved_settings = u_data['settings']
                        st.rerun()
                st.error("Invalid credentials")
        with tab2:
            nu, np = st.text_input("New Username"), st.text_input("New Password", type="password")
            if st.button("Create Account"):
                if nu and np:
                    salt = os.urandom(16)
                    save_user_data(nu, {
                        "pwd_hash": get_hash(np, salt),
                        "salt": salt.hex(),
                        "settings": {"fav_team": "None", "w_std": 25, "w_era": 25, "w_rpg": 20, "w_avg": 5, "w_slg": 25, "preset": "Pro Optimized (v2)"},
                        "login_count": 0
                    })
                    st.success("Account created!")
    st.stop()

# --- SIDEBAR ---
with st.sidebar:
    st.title(f"👋 {st.session_state.current_user}")
    if st.button("Log Out"):
        cookie_manager.delete("mlb_session_token")
        st.session_state.authenticated = False
        st.rerun()
    st.divider()
    w_std, w_era, w_rpg, w_avg, w_slg = 25, 25, 20, 5, 25 
    sensitivity = 1.3

# --- CORE LOGIC (Dynamic Stat Fetching) ---
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

def get_detailed_data(gid, g_info, year, w_std, w_era, w_rpg, w_avg, w_slg, sensitivity):
    try:
        box = statsapi.boxscore_data(gid)
        def fetch_side(side, tid):
            sd = box.get(side, {})
            ps = sd.get('players', {})
            starters = sorted([{'id': p['person']['id'], 'name': p['person']['fullName'], 'order': int(p['battingOrder'])} 
                               for p in ps.values() if p.get('battingOrder') and p['battingOrder'].endswith('00')], key=lambda x: x['order'])
            
            lineup, avgs, slgs = [], [], []
            for player in starters:
                try:
                    p_st = statsapi.player_stat_data(player['id'], group="hitting", type="season", season=year)['stats'][0]['stats']
                    lineup.append({"Order": f"{player['order']//100}", "Player": player['name'], "AVG": p_st.get('avg', '.250')})
                    avgs.append(float(str(p_st.get('avg', '.250')).replace('.','0.')))
                    slgs.append(float(str(p_st.get('slg', '.400')).replace('.','0.')))
                except:
                    lineup.append({"Order": f"{player['order']//100}", "Player": player['name'], "AVG": ".250"})
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
            c_score = (wpct * w_std) + ((4.25/max(0.1,era)) * w_era) + ((rpg/4.4) * w_rpg) + ((sum(avgs)/max(1,len(avgs))*4) * w_avg) + ((sum(slgs)/max(1,len(slgs))*2.5) * w_slg)
            return {"score": c_score, "lineup": lineup, "p_name": p_name, "era": era, "wpct": wpct, "rpg": rpg, "avg_team": sum(avgs)/max(1,len(avgs)), "slg_team": sum(slgs)/max(1,len(slgs))}
        
        a_d, h_d = fetch_side('away', g_info['away_id']), fetch_side('home', g_info['home_id'])
        prob_h = 0.5 + ((h_d['score'] - a_d['score']) * sensitivity / 100) + 0.035
        return {"prob_h": max(0.01, min(0.99, prob_h)), "box": box, "away": a_d, "home": h_d}
    except: return None

# --- UI MAIN ---
st.markdown("<h2 style='text-align:center;'>MLB ANALYTICS CONSOLE</h2>", unsafe_allow_html=True)
u_date = st.date_input("Select Gameday", datetime.now())
sched = statsapi.schedule(date=u_date.strftime("%m/%d/%Y"))

if not sched:
    st.info("📅 All quiet in the ballpark. Check another date.")
else:
    for g in {g['game_id']: g for g in sched}.values():
        with st.container():
            st.markdown(f"""
                <div class="matchup-card">
                    <div style="display: flex; align-items: center; justify-content: space-between;">
                        <div style="display: flex; align-items: center;">
                            <img src="https://www.mlbstatic.com/team-logos/{g['away_id']}.svg" width="60" style="margin-right: 20px;">
                            <div>
                                <h2 style="margin: 0;">{g['away_name']} <span style="color: #8b949e; font-size: 0.7em;">@</span> {g['home_name']}</h2>
                                <span class="stat-pill">{g.get('status', 'Scheduled')}</span>
                            </div>
                        </div>
                        <img src="https://www.mlbstatic.com/team-logos/{g['home_id']}.svg" width="60">
                    </div>
                </div>
            """, unsafe_allow_html=True)
            
            if st.button("LAUNCH DATA ANALYSIS", key=f"b_{g['game_id']}"): 
                st.session_state.active_game_id = g['game_id']

            if st.session_state.get("active_game_id") == g['game_id']:
                data = get_detailed_data(g['game_id'], g, u_date.year, w_std, w_era, w_rpg, w_avg, w_slg, sensitivity)
                if data:
                    res = g['home_name'] if data['prob_h'] > 0.5 else g['away_name']
                    conf = (data['prob_h'] if data['prob_h'] > 0.5 else 1-data['prob_h']) * 100
                    
                    st.markdown(f"""
                        <div class="prediction-banner">
                            <h3 style="margin:0; font-size: 0.9em; opacity: 0.8;">WINNER PROBABILITY</h3>
                            <h1 style="margin:0; color: #fff;">{res} {conf:.1f}%</h1>
                        </div>
                    """, unsafe_allow_html=True)

                    # --- PRO METRIC GRID ---
                    h, a = data['home'], data['away']
                    m1, m2, m3, m4 = st.columns(4)
                    m1.metric("Win Rate", f"{h['wpct']:.3f}", f"{h['wpct']-a['wpct']:.3f} Edge")
                    m2.metric("Starter ERA", f"{h['era']:.2f}", f"{a['era']-h['era']:.2f} Edge", delta_color="inverse")
                    m3.metric("Runs/G", f"{h['rpg']:.2f}", f"{h['rpg']-a['rpg']:.2f} Edge")
                    m4.metric("Lineup SLG", f"{h['slg_team']:.3f}", f"{h['slg_team']-a['slg_team']:.3f} Edge")

                    # --- BOX SCORE & LINEUPS ---
                    tab_scout, tab_lineup = st.tabs(["📊 Game Intelligence", "📋 Rosters & Box"])
                    
                    with tab_scout:
                        st.markdown("### Power Index Comparison")
                        st.progress(data['prob_h'], text=f"{g['home_name']} Advantage Index")
                    
                    with tab_lineup:
                        c_a, c_h = st.columns(2)
                        with c_a:
                            st.write(f"**{g['away_name']} Lineup**")
                            st.dataframe(pd.DataFrame(data['away']['lineup']), hide_index=True, use_container_width=True)
                        with c_h:
                            st.write(f"**{g['home_name']} Lineup**")
                            st.dataframe(pd.DataFrame(data['home']['lineup']), hide_index=True, use_container_width=True)
    
