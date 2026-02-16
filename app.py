import streamlit as st
import statsapi
import pandas as pd
import json
import os
import hashlib
import smtplib
import time
import extra_streamlit_components as stx
from email.mime.text import MIMEText
from datetime import datetime, timedelta
from streamlit_autorefresh import st_autorefresh

# --- EMAIL CONFIGURATION ---
SMTP_SERVER = "smtp.gmail.com"
SMTP_PORT = 587
SENDER_EMAIL = "owainbaseball@gmail.com" 
SENDER_PASSWORD = "lixs qgpo ihyd ikiq" 
ADMIN_EMAIL = "owainbaseball@gmail.com"

def send_admin_notification(new_user):
    try:
        subject = f"⚾ New Account Alert: {new_user}"
        body = f"A new user has registered: {new_user}\nTime: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"
        msg = MIMEText(body)
        msg['Subject'] = subject
        msg['From'] = SENDER_EMAIL
        msg['To'] = ADMIN_EMAIL
        with smtplib.SMTP(SMTP_SERVER, SMTP_PORT) as server:
            server.starttls()
            server.login(SENDER_EMAIL, SENDER_PASSWORD)
            server.send_message(msg)
    except: pass

# --- COOKIE MANAGER ---
cookie_manager = stx.CookieManager()

# --- PAGE CONFIG & THEME ---
st.set_page_config(page_title="MLB AI Scout Pro", layout="wide", page_icon="⚾")
st_autorefresh(interval=30000, key="mlb_live_timer")

st.markdown("""
    <style>
    .main { background-color: #0e1117; }
    .stButton>button { width: 100%; border-radius: 5px; height: 3em; background-color: #262730; color: white; border: 1px solid #444; }
    .matchup-card { border-radius: 15px; padding: 20px; background: #161b22; border: 1px solid #30363d; margin-bottom: 20px; }
    .winner-box { background: #1b2838; border: 2px solid #4CAF50; border-radius: 10px; padding: 15px; margin-bottom: 10px; color: #e6edf3; text-align: center;}
    </style>
    """, unsafe_allow_html=True)

# --- STORAGE LOGIC ---
def hash_password(password): return hashlib.sha256(str.encode(password)).hexdigest()
def get_user_file(username): return f"profile_{''.join(x for x in username if x.isalnum())}.json"

def save_settings(username, password, settings_data):
    with open(get_user_file(username), "w") as f:
        json.dump({"password_hash": hash_password(password), "settings": settings_data}, f)

def load_settings(username, password_hash, is_raw_password=True):
    filename = get_user_file(username)
    if os.path.exists(filename):
        with open(filename, "r") as f:
            data = json.load(f)
            target_hash = hash_password(password_hash) if is_raw_password else password_hash
            if data.get("password_hash") == target_hash: 
                return data.get("settings"), True
    return None, False

# --- AUTH LOGIC ---
if "authenticated" not in st.session_state:
    st.session_state.authenticated = False

# Cookie Auto-Login
if not st.session_state.authenticated:
    cookies = cookie_manager.get_all()
    saved_user = cookies.get("mlb_user")
    saved_token = cookies.get("mlb_token")
    if saved_user and saved_token:
        sets, ok = load_settings(saved_user, saved_token, is_raw_password=False)
        if ok:
            st.session_state.authenticated, st.session_state.current_user = True, saved_user
            st.session_state.user_pwd_hash, st.session_state.saved_settings = saved_token, sets

if not st.session_state.authenticated:
    st.markdown("<h1 style='text-align:center;'>⚾ MLB Intelligence Pro</h1>", unsafe_allow_html=True)
    c1, c2, c3 = st.columns([1, 2, 1])
    with c2:
        m = st.tabs(["Login", "Register"])
        with m[0]:
            uid = st.text_input("User", key="login_user")
            pwd = st.text_input("Pass", type="password", key="login_pass")
            if st.button("Access"):
                if uid and pwd:
                    s, ok = load_settings(uid, pwd)
                    if ok:
                        h = hash_password(pwd)
                        expiry = datetime.now() + timedelta(days=30)
                        cookie_manager.set("mlb_user", uid, expires_at=expiry)
                        cookie_manager.set("mlb_token", h, expires_at=expiry)
                        st.session_state.authenticated = True
                        st.session_state.current_user = uid
                        st.session_state.user_pwd_hash = h
                        st.session_state.saved_settings = s
                        st.success("Logging in...")
                        time.sleep(0.5) # Allow cookie to set
                        st.rerun()
                    else: st.error("Invalid Credentials")
                else: st.warning("Please enter username and password")
        with m[1]:
            nu = st.text_input("New User", key="reg_user")
            np = st.text_input("New Pass", type="password", key="reg_pass")
            if st.button("Create"):
                if nu and np:
                    save_settings(nu, np, {"fav_team": "None", "w_std": 40, "w_era": 15, "w_avg": 20, "w_slg": 25, "preset": "Balanced"})
                    send_admin_notification(nu)
                    st.success("Created! Switch to Login tab.")
                else: st.warning("Please enter a username and password")
    st.stop()

# --- SIDEBAR ---
with st.sidebar:
    st.title(f"👋 {st.session_state.current_user}")
    if st.button("Log Out"):
        cookie_manager.delete("mlb_user")
        cookie_manager.delete("mlb_token")
        st.session_state.authenticated = False
        st.rerun()
    st.divider()
    s = st.session_state.saved_settings
    preset = st.radio("Model Presets", ["Balanced", "Pitching Heavy", "Offense Heavy", "Custom"], index=["Balanced", "Pitching Heavy", "Offense Heavy", "Custom"].index(s.get("preset", "Balanced")))
    
    if preset == "Balanced": w_std, w_era, w_avg, w_slg = 40, 15, 20, 25
    elif preset == "Pitching Heavy": w_std, w_era, w_avg, w_slg = 20, 50, 15, 15
    elif preset == "Offense Heavy": w_std, w_era, w_avg, w_slg = 20, 10, 35, 35
    else:
        w_std = st.slider("Standings %", 0, 100, s["w_std"])
        w_era = st.slider("Pitching %", 0, 100, s["w_era"])
        w_avg = st.slider("Lineup AVG %", 0, 100, s["w_avg"])
        w_slg = st.slider("Lineup SLG %", 0, 100, s["w_slg"])
    
    sensitivity = st.slider("Sensitivity", 1.0, 3.0, 1.2)
    
    try:
        all_teams_data = statsapi.get('teams', {'sportId': 1})['teams']
        all_teams = sorted([t['name'] for t in all_teams_data])
    except: all_teams = []
    
    fav_team = st.selectbox("Favorite Team", ["None"] + all_teams, index=(["None"] + all_teams).index(s.get("fav_team", "None")) if s.get("fav_team") in all_teams else 0)

    if st.button("💾 Save Preferences"):
        new_settings = {"fav_team": fav_team, "w_std": w_std, "w_era": w_era, "w_avg": w_avg, "w_slg": w_slg, "preset": preset}
        save_settings(st.session_state.current_user, "", new_settings)
        st.session_state.saved_settings = new_settings
        st.success("Saved!")

# --- CORE FUNCTIONS ---
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
u_date = st.date_input("Date", datetime.now())
sched = statsapi.schedule(date=u_date.strftime("%m/%d/%Y"))
unique_g = {g['game_id']: g for g in sched}.values()
fav = st.session_state.saved_settings.get("fav_team", "None")
sorted_games = sorted(unique_g, key=lambda x: (x.get('away_name') != fav and x.get('home_name') != fav))

for g in sorted_games:
    with st.container():
        st.markdown('<div class="matchup-card">', unsafe_allow_html=True)
        c1, c2, c3 = st.columns([1, 4, 1.5])
        with c1: st.image(f"https://www.mlbstatic.com/team-logos/{g['away_id']}.svg", width=50)
        with c2: st.markdown(f"**{g['away_name']} @ {g['home_name']}**")
        with c3:
            if st.button("Analyze", key=f"b_{g['game_id']}"): st.session_state.active_game_id = g['game_id']
        
        if st.session_state.get("active_game_id") == g['game_id']:
            data = get_detailed_data(g['game_id'], g, u_date.year, w_std, w_era, w_avg, w_slg, sensitivity)
            if data:
                res = g['home_name'] if data['prob_h'] > 0.5 else g['away_name']
                conf = (data['prob_h'] if data['prob_h'] > 0.5 else 1-data['prob_h'])*100
                st.markdown(f'<div class="winner-box">🏅 Projection: <b>{res}</b> ({conf:.1f}%)</div>', unsafe_allow_html=True)
                
                with st.expander("📊 Strength Comparison"):
                    h, a = data['home'], data['away']
                    t_h, t_a = max(0.01, h['score']), max(0.01, a['score'])
                    impact_df = pd.DataFrame([
                        {"Category": "Team Record", g['home_name']: f"{h['wpct']:.3f} ({(h['c_std']/t_h)*100:.1f}%)", g['away_name']: f"{a['wpct']:.3f} ({(a['c_std']/t_a)*100:.1f}%)"},
                        {"Category": "Pitching (ERA)", g['home_name']: f"{h['era']:.2f} ({(h['c_era']/t_h)*100:.1f}%)", g['away_name']: f"{a['era']:.2f} ({(a['c_era']/t_a)*100:.1f}%)"},
                        {"Category": "Lineup AVG", g['home_name']: f"{h['avg_team']:.3f} ({(h['c_avg']/t_h)*100:.1f}%)", g['away_name']: f"{a['avg_team']:.3f} ({(a['c_avg']/t_a)*100:.1f}%)"},
                        {"Category": "Lineup Power", g['home_name']: f"{h['slg_team']:.3f} ({(h['c_slg']/t_h)*100:.1f}%)", g['away_name']: f"{a['slg_team']:.3f} ({(a['c_slg']/t_a)*100:.1f}%)"},
                    ])
                    st.table(impact_df)
                
                if g.get('status') in ["Final", "Live", "In Progress", "Game Over"]:
                    st.write("### 📊 Box Score")
                    r_a, r_h = g.get('away_score', 0), g.get('home_score', 0)
                    h_a = data['box'].get('away', {}).get('teamStats', {}).get('batting', {}).get('hits', '-')
                    h_h = data['box'].get('home', {}).get('teamStats', {}).get('batting', {}).get('hits', '-')
                    box_df = pd.DataFrame({"Team": [g['away_name'], g['home_name']], "R": [r_a, r_h], "H": [h_a, h_h]})
                    st.dataframe(box_df, hide_index=True, use_container_width=True)
                
                la, lh = st.columns(2)
                with la:
                    st.write(f"**{g['away_name']}**")
                    st.markdown(f"**SP: {data['away']['p_name']}** (ERA: {data['away']['era']})")
                    st.dataframe(pd.DataFrame(data['away']['lineup']), hide_index=True, use_container_width=True)
                with lh:
                    st.write(f"**{g['home_name']}**")
                    st.markdown(f"**SP: {data['home']['p_name']}** (ERA: {data['home']['era']})")
                    st.dataframe(pd.DataFrame(data['home']['lineup']), hide_index=True, use_container_width=True)
            else: st.info("Analyzing...")
        st.markdown('</div>', unsafe_allow_html=True)
            
