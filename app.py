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
SENDER_EMAIL = "owainbaseball@gmail.com" 
SENDER_PASSWORD = "lixs qgpo ihyd ikiq" 
ADMIN_EMAIL = "owainbaseball@gmail.com"

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

def send_admin_notification(new_user):
    try:
        msg = MIMEText(f"New user registered: {new_user}")
        msg['Subject'] = "⚾ New Account: " + new_user
        msg['From'], msg['To'] = SENDER_EMAIL, ADMIN_EMAIL
        with smtplib.SMTP(SMTP_SERVER, SMTP_PORT) as server:
            server.starttls()
            server.login(SENDER_EMAIL, SENDER_PASSWORD)
            server.send_message(msg)
    except: pass

# --- PAGE CONFIG ---
st.set_page_config(page_title="MLB AI Scout Pro", layout="wide", page_icon="⚾")
st_autorefresh(interval=30000, key="mlb_live_timer")
cookie_manager = stx.CookieManager()

if "authenticated" not in st.session_state:
    st.session_state.authenticated = False

# Session Check
auth_cookie = cookie_manager.get(cookie="mlb_session_token")
if not st.session_state.authenticated and auth_cookie and ":" in auth_cookie:
    u_name, u_token = auth_cookie.split(":", 1)
    u_data = load_user_data(u_name)
    if u_data and u_data.get("session_token") == u_token:
        if u_data.get("login_count", 0) < 10:
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
                # Check if file exists AND has the new security keys
                if u_data and 'salt' in u_data and 'pwd_hash' in u_data:
                    salt = bytes.fromhex(u_data['salt'])
                    if u_data['pwd_hash'] == get_hash(p_in, salt):
                        new_token = secrets.token_urlsafe(32)
                        u_data['session_token'] = new_token
                        u_data['login_count'] = u_data.get('login_count', 0) + 1
                        save_user_data(u_in, u_data)
                        cookie_manager.set("mlb_session_token", f"{u_in}:{new_token}", key="login_cook")
                        st.session_state.authenticated = True
                        st.session_state.current_user = u_in
                        st.session_state.saved_settings = u_data['settings']
                        st.rerun()
                st.error("Invalid credentials or account needs re-registration")
        with tab2:
            nu, np = st.text_input("New Username"), st.text_input("New Password", type="password")
            if st.button("Create Account"):
                if nu and np:
                    salt = os.urandom(16)
                    save_user_data(nu, {
                        "pwd_hash": get_hash(np, salt),
                        "salt": salt.hex(),
                        "settings": {"fav_team": "None", "w_std": 40, "w_era": 15, "w_avg": 20, "w_slg": 25, "preset": "Balanced"},
                        "login_count": 0
                    })
                    send_admin_notification(nu)
                    st.success("Account created!")
    st.stop()

# --- APP CONTENT ---
with st.sidebar:
    st.title(f"👋 {st.session_state.current_user}")
    u_data = load_user_data(st.session_state.current_user)
    remains = 10 - u_data.get('login_count', 0)
    st.caption(f"Security sessions remaining: {remains}/10")

    if st.button("📖 How It Works"):
        @st.dialog("Why this pick?")
        def show_help():
            st.write("### 🧠 The Logic Breakdown")
            st.info("The AI compares team strengths by multiplying your weights against Season WP% (Standings), ERA (Pitching), and combined AVG/SLG (Lineup).")
        show_help()

    if st.button("Log Out"):
        cookie_manager.delete("mlb_session_token")
        st.session_state.authenticated = False
        st.rerun()
    st.divider()

    s = st.session_state.saved_settings
    preset = st.radio("Presets", ["Balanced", "Pitching Heavy", "Offense Heavy", "Custom"], index=["Balanced", "Pitching Heavy", "Offense Heavy", "Custom"].index(s.get('preset','Balanced')))
    
    if preset == "Balanced": w_std, w_era, w_avg, w_slg = 40, 15, 20, 25
    elif preset == "Pitching Heavy": w_std, w_era, w_avg, w_slg = 20, 50, 15, 15
    elif preset == "Offense Heavy": w_std, w_era, w_avg, w_slg = 20, 10, 35, 35
    else:
        w_std = st.slider("Standings %", 0, 100, s.get('w_std', 40))
        w_era = st.slider("Pitching %", 0, 100, s.get('w_era', 15))
        w_avg = st.slider("AVG %", 0, 100, s.get('w_avg', 20))
        w_slg = st.slider("SLG %", 0, 100, s.get('w_slg', 25))

    sensitivity = st.slider("Sensitivity", 1.0, 3.0, 1.2)

    @st.cache_data(ttl=3600)
    def get_all_teams():
        try: return sorted([t['name'] for t in statsapi.get('teams', {'sportId': 1})['teams']])
        except: return []

    all_teams = get_all_teams()
    fav_team = st.selectbox("Favorite Team", ["None"] + all_teams, index=(["None"] + all_teams).index(s.get('fav_team', 'None')))

    if st.button("💾 Save Settings"):
        u_data['settings'] = {"fav_team": fav_team, "w_std": w_std, "w_era": w_era, "w_avg": w_avg, "w_slg": w_slg, "preset": preset}
        save_user_data(st.session_state.current_user, u_data)
        st.session_state.saved_settings = u_data['settings']
        st.success("Saved!")

# --- CORE LOGIC ---
@st.cache_data(ttl=3600)
def get_team_info(tid, year):
    try:
        standings = statsapi.standings_data(leagueId="103,104", season=year)
        for div in standings.values():
            for t in div.get('teams', []):
                if t['team_id'] == tid: return (int(t['w'])/max(1, int(t['w'])+int(t['l'])))
    except: pass
    return 0.50

def get_detailed_data(gid, g_info, year, w_std, w_era, w_avg, w_slg, sensitivity):
    try:
        box = statsapi.boxscore_data(gid)
        def fetch_side(side, tid):
            sd = box.get(side, {})
            ps, bt = sd.get('players', {}), sd.get('batters', [])
            lineup, avgs, slgs = [], [], []
            for pid in bt[:9]:
                p_inf = ps.get(f"ID{pid}", {}).get('person', {})
                try:
                    p_st = statsapi.player_stat_data(pid, group="hitting", type="season", season=year)['stats'][0]['stats']
                    lineup.append({"Player": p_inf.get('fullName', "TBD"), "AVG": p_st.get('avg', '.000')})
                    avgs.append(float(str(p_st.get('avg', '.000')).replace('.','0.')))
                    slgs.append(float(str(p_st.get('slg', '.400')).replace('.','0.')))
                except: avgs.append(0.25); slgs.append(0.40)
            p_name, era = "TBD", 4.10
            if sd.get('pitchers'):
                try: 
                    pid = sd['pitchers'][0]
                    p_name = ps.get(f"ID{pid}", {}).get('person', {}).get('fullName', "TBD")
                    era = float(statsapi.player_stat_data(pid, group="pitching", type="season", season=year)['stats'][0]['stats'].get('era', 4.10))
                except: pass
            wpct = get_team_info(tid, year)
            c_std = wpct * (w_std/100)
            c_era = (4.1/max(0.1,era)) * (w_era/100)
            c_avg = (sum(avgs)/max(1,len(avgs))*4) * (w_avg/100)
            c_slg = (sum(slgs)/max(1,len(slgs))*2.5) * (w_slg/100)
            return {"score": c_std+c_era+c_avg+c_slg, "lineup": lineup, "c_std": c_std, "c_era": c_era, "c_avg": c_avg, "c_slg": c_slg, "p_name": p_name, "era": era, "wpct": wpct, "avg_team": sum(avgs)/max(1,len(avgs)), "slg_team": sum(slgs)/max(1,len(slgs))}
        
        a_d, h_d = fetch_side('away', g_info['away_id']), fetch_side('home', g_info['home_id'])
        prob_h = 0.5 + ((h_d['score'] - a_d['score']) * sensitivity / max(0.1, (h_d['score'] + a_d['score'])/2)) + 0.03 
        return {"prob_h": max(0.01, min(0.99, prob_h)), "box": box, "away": a_d, "home": h_d}
    except: return None

# --- UI MAIN ---
st.header("⚾ MLB Intelligence Pro")
u_date = st.date_input("Select Date", datetime.now())
sched = statsapi.schedule(date=u_date.strftime("%m/%d/%Y"))

if not sched:
    st.info("📅 No games today ⚾")
else:
    unique_g = {g['game_id']: g for g in sched}.values()
    fav = st.session_state.get("saved_settings", {}).get("fav_team", "None")
    sorted_games = sorted(unique_g, key=lambda x: (x.get('away_name') != fav and x.get('home_name') != fav))

    for g in sorted_games:
        with st.container():
            st.markdown('<div class="matchup-card" style="border-radius: 15px; padding: 20px; background: #161b22; border: 1px solid #30363d; margin-bottom: 20px;">', unsafe_allow_html=True)
            c1, c2, c3 = st.columns([1, 4, 1.5])
            with c1: st.image(f"https://www.mlbstatic.com/team-logos/{g['away_id']}.svg", width=50)
            with c2: 
                status_label = " LIVE" if g.get('status') in ["In Progress", "Live"] else ""
                st.markdown(f"**{g['away_name']} @ {g['home_name']}** {status_label}")
                st.write(f"Status: {g.get('status', 'Unknown')}")
            with c3:
                if st.button("Analyze", key=f"b_{g['game_id']}"): st.session_state.active_game_id = g['game_id']
            
            if st.session_state.get("active_game_id") == g['game_id']:
                data = get_detailed_data(g['game_id'], g, u_date.year, w_std, w_era, w_avg, w_slg, sensitivity)
                if data:
                    res = g['home_name'] if data['prob_h'] > 0.5 else g['away_name']
                    conf = (data['prob_h'] if data['prob_h'] > 0.5 else 1-data['prob_h'])*100
                    st.markdown(f'<div style="background: #1b2838; border: 2px solid #4CAF50; border-radius: 10px; padding: 15px; margin-bottom: 10px; color: #e6edf3; text-align: center;">🏅 Projection: <b>{res}</b> ({conf:.1f}%)</div>', unsafe_allow_html=True)
                    
                    st.write("### 📊 AI Weight Comparison")
                    h, a = data['home'], data['away']
                    impact_df = pd.DataFrame([
                        {"Category": "Record (Win %)", g['home_name']: f"{h['wpct']:.3f}", g['away_name']: f"{a['wpct']:.3f}"},
                        {"Category": "Starter ERA", g['home_name']: f"{h['era']:.2f}", g['away_name']: f"{a['era']:.2f}"},
                        {"Category": "Lineup AVG", g['home_name']: f"{h['avg_team']:.3f}", g['away_name']: f"{a['avg_team']:.3f}"},
                        {"Category": "Lineup Power (SLG)", g['home_name']: f"{h['slg_team']:.3f}", g['away_name']: f"{a['slg_team']:.3f}"},
                    ])
                    st.table(impact_df)

                    st.write("### 🏟️ Live Boxscore")
                    box_data = data['box']
                    away_stats = box_data.get('away', {}).get('teamStats', {}).get('batting', {})
                    home_stats = box_data.get('home', {}).get('teamStats', {}).get('batting', {})
                    live_df = pd.DataFrame({
                        "Team": [g['away_name'], g['home_name']],
                        "Runs": [g.get('away_score', 0), g.get('home_score', 0)],
                        "Hits": [away_stats.get('hits', 0), home_stats.get('hits', 0)],
                        "Errors": [away_stats.get('errors', 0), home_stats.get('errors', 0)]
                    })
                    st.table(live_df)
                    
                    st.write("### 📋 Lineups & Starters")
                    la, lh = st.columns(2)
                    with la:
                        st.write(f"**{g['away_name']} Starter:** {data['away']['p_name']} (ERA: {data['away']['era']})")
                        st.dataframe(pd.DataFrame(data['away']['lineup']), hide_index=True)
                    with lh:
                        st.write(f"**{g['home_name']} Starter:** {data['home']['p_name']} (ERA: {data['home']['era']})")
                        st.dataframe(pd.DataFrame(data['home']['lineup']), hide_index=True)
            st.markdown('</div>', unsafe_allow_html=True)
                              
