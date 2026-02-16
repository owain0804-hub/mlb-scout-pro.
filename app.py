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
st_autorefresh(interval=30000, key="mlb_live_timer")
cookie_manager = stx.CookieManager()

if "authenticated" not in st.session_state:
    st.session_state.authenticated = False

# Session Check (Simplified for speed)
auth_cookie = cookie_manager.get(cookie="mlb_session_token")
if not st.session_state.authenticated and auth_cookie and ":" in auth_cookie:
    u_name, u_token = auth_cookie.split(":", 1)
    u_data = load_user_data(u_name)
    if u_data and u_data.get("session_token") == u_token:
        st.session_state.authenticated = True
        st.session_state.current_user = u_name
        st.session_state.saved_settings = u_data.get("settings")

if not st.session_state.authenticated:
    st.markdown("<h1 style='text-align:center;'>⚾ MLB Intelligence Pro</h1>", unsafe_allow_html=True)
    c1, c2, c3 = st.columns([1, 2, 1])
    with c2:
        tab1, tab2 = st.tabs(["Login", "Register"])
        with tab1:
            u_in = st.text_input("Username")
            p_in = st.text_input("Password", type="password")
            if st.button("Access System"):
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

    s = st.session_state.saved_settings
    w_std, w_era, w_rpg, w_avg, w_slg = 25, 25, 20, 5, 25 # Default Pro Weights
    sensitivity = 1.3

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
st.header("⚾ MLB Intelligence Pro")
u_date = st.date_input("Select Date", datetime.now())
sched = statsapi.schedule(date=u_date.strftime("%m/%d/%Y"))

if not sched:
    st.info("📅 No games today.")
else:
    for g in {g['game_id']: g for g in sched}.values():
        with st.container():
            st.markdown('<div style="border-radius:15px; padding:20px; background:#161b22; border:1px solid #30363d; margin-bottom:20px;">', unsafe_allow_html=True)
            c1, c2, c3 = st.columns([1, 4, 1.5])
            with c1: st.image(f"https://www.mlbstatic.com/team-logos/{g['away_id']}.svg", width=55)
            with c2: st.markdown(f"### {g['away_name']} @ {g['home_name']}")
            with c3:
                if st.button("Analyze Matchup", key=f"b_{g['game_id']}"): st.session_state.active_game_id = g['game_id']
            
            if st.session_state.get("active_game_id") == g['game_id']:
                data = get_detailed_data(g['game_id'], g, u_date.year, w_std, w_era, w_rpg, w_avg, w_slg, sensitivity)
                if data:
                    res = g['home_name'] if data['prob_h'] > 0.5 else g['away_name']
                    conf = (data['prob_h'] if data['prob_h'] > 0.5 else 1-data['prob_h']) * 100
                    st.info(f"🏅 **AI Projection: {res} ({conf:.1f}%)**")

                    # --- SCOUTING DATA WITH "FAVORS" INDICATOR ---
                    st.write("### 📊 Scouting Intelligence")
                    h, a = data['home'], data['away']
                    
                    def get_edge(h_val, a_val, lower_is_better=False):
                        if lower_is_better:
                            return g['home_name'] if h_val < a_val else g['away_name']
                        return g['home_name'] if h_val > a_val else g['away_name']

                    scout_df = pd.DataFrame([
                        {"Stat": "Win %", g['home_name']: f"{h['wpct']:.3f}", g['away_name']: f"{a['wpct']:.3f}", "Favors": get_edge(h['wpct'], a['wpct'])},
                        {"Stat": "Starter ERA", g['home_name']: f"{h['era']:.2f}", g['away_name']: f"{a['era']:.2f}", "Favors": get_edge(h['era'], a['era'], True)},
                        {"Stat": "Runs / Game", g['home_name']: f"{h['rpg']:.2f}", g['away_name']: f"{a['rpg']:.2f}", "Favors": get_edge(h['rpg'], a['rpg'])},
                        {"Stat": "Lineup SLG", g['home_name']: f"{h['slg_team']:.3f}", g['away_name']: f"{a['slg_team']:.3f}", "Favors": get_edge(h['slg_team'], a['slg_team'])},
                    ])
                    st.table(scout_df)

                    # --- LIVE BOX SCORE ---
                    st.write("### 🏟️ Live Box Score")
                    box_data = data['box']
                    away_bat = box_data.get('away', {}).get('teamStats', {}).get('batting', {})
                    home_bat = box_data.get('home', {}).get('teamStats', {}).get('batting', {})
                    st.table(pd.DataFrame({
                        "Team": [g['away_name'], g['home_name']],
                        "Runs": [g.get('away_score', 0), g.get('home_score', 0)],
                        "Hits": [away_bat.get('hits', 0), home_bat.get('hits', 0)],
                        "Errors": [away_bat.get('errors', 0), home_bat.get('errors', 0)]
                    }))
                    
                    # --- LINEUPS ---
                    l_col, r_col = st.columns(2)
                    with l_col:
                        st.write(f"**{g['away_name']} Lineup** (Starter: {data['away']['p_name']})")
                        st.dataframe(pd.DataFrame(data['away']['lineup']), hide_index=True, use_container_width=True)
                    with r_col:
                        st.write(f"**{g['home_name']} Lineup** (Starter: {data['home']['p_name']})")
                        st.dataframe(pd.DataFrame(data['home']['lineup']), hide_index=True, use_container_width=True)
            st.markdown('</div>', unsafe_allow_html=True)
