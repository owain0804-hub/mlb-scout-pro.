import streamlit as st
import statsapi
import pandas as pd # Fixed import
import json
import os
import hashlib
import smtplib
from email.mime.text import MIMEText
from datetime import datetime
from streamlit_autorefresh import st_autorefresh

# --- EMAIL CONFIGURATION ---
SMTP_SERVER = "smtp.gmail.com"
SMTP_PORT = 587
SENDER_EMAIL = "owainbaseball@gmail.com" 
SENDER_PASSWORD = "YOUR_16_DIGIT_APP_PASSWORD" 
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
    except:
        pass

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

# --- SESSION & STORAGE ---
SESSION_FILE = "active_session.json"
def hash_password(password): return hashlib.sha256(str.encode(password)).hexdigest()
def get_user_file(username): return f"profile_{''.join(x for x in username if x.isalnum())}.json"

def save_settings(username, password, settings_data):
    with open(get_user_file(username), "w") as f:
        json.dump({"password_hash": hash_password(password), "settings": settings_data}, f)

def load_settings(username, password):
    filename = get_user_file(username)
    if os.path.exists(filename):
        with open(filename, "r") as f:
            data = json.load(f)
            if data.get("password_hash") == hash_password(password): return data.get("settings"), True
    return None, False

def manage_persistent_session(username=None, password=None, action="check"):
    if action == "save":
        with open(SESSION_FILE, "w") as f: json.dump({"user": username, "pwd": password, "count": 1}, f)
    elif action == "check" and os.path.exists(SESSION_FILE):
        with open(SESSION_FILE, "r") as f:
            data = json.load(f)
            if data["count"] < 10:
                data["count"] += 1
                with open(SESSION_FILE, "w") as fw: json.dump(data, fw)
                return data["user"], data["pwd"], True
            else: os.remove(SESSION_FILE)
    elif action == "logout" and os.path.exists(SESSION_FILE): os.remove(SESSION_FILE)
    return None, None, False

# --- AUTH LOGIC ---
if "authenticated" not in st.session_state:
    u, p, success = manage_persistent_session(action="check")
    if success:
        sets, valid = load_settings(u, p)
        if valid:
            st.session_state.authenticated, st.session_state.current_user = True, u
            st.session_state.user_pwd, st.session_state.saved_settings = p, sets
        else: st.session_state.authenticated = False
    else: st.session_state.authenticated = False

if not st.session_state.authenticated:
    st.markdown("<h1 style='text-align:center;'>⚾ MLB Intelligence Pro</h1>", unsafe_allow_html=True)
    c1, c2, c3 = st.columns([1, 2, 1])
    with c2:
        m = st.tabs(["Login", "Register"])
        with m[0]:
            uid, pwd = st.text_input("User"), st.text_input("Pass", type="password")
            if st.button("Access"):
                s, ok = load_settings(uid, pwd)
                if ok:
                    st.session_state.authenticated, st.session_state.current_user = True, uid
                    st.session_state.user_pwd, st.session_state.saved_settings = pwd, s
                    manage_persistent_session(uid, pwd, action="save"); st.rerun()
        with m[1]:
            nu, np = st.text_input("New User"), st.text_input("New Pass", type="password")
            if st.button("Create"):
                save_settings(nu, np, {"fav_team": "None", "w_std": 40, "w_era": 15, "w_avg": 20, "w_slg": 25, "preset": "Balanced"})
                send_admin_notification(nu); st.success("Created!")
    st.stop()

# --- SIDEBAR ---
with st.sidebar:
    st.title("⚾ Settings")
    if st.button("Log Out"): manage_persistent_session(action="logout"); st.session_state.authenticated = False; st.rerun()
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
    
    try: all_teams = sorted([t['name'] for t in statsapi.get('teams', {'sportId': 1})['teams']])
    except: all_teams = []
    fav_team = st.selectbox("Favorite Team", ["None"] + all_teams, 
                            index=(["None"] + all_teams).index(s.get("fav_team", "None")) if s.get("fav_team") in all_teams else 0)

    if st.button("💾 Save Preferences"):
        new_settings = {"fav_team": fav_team, "w_std": w_std, "w_era": w_era, "w_avg": w_avg, "w_slg": w_slg, "preset": preset}
        save_settings(st.session_state.current_user, st.session_state.user_pwd, new_settings)
        st.session_state.saved_settings = new_settings
        st.success("Preferences Saved!")

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
            return {"score": c_std+c_era+c_avg+c_slg, "lineup": lineup, "c_std": c_std, "c_era": c_era, "c_avg": c_avg, "c_slg": c_slg, "p_name": p_name, "era": era}

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
                
                with st.expander("📊 Percentage Contribution by Stat"):
                    h, a = data['home'], data['away']
                    total_h = max(0.01, h['c_std'] + h['c_era'] + h['c_avg'] + h['c_slg'])
                    total_a = max(0.01, a['c_std'] + a['c_era'] + a['c_avg'] + a['c_slg'])
                    impact_df = pd.DataFrame([
                        {"Stat": "Standings", g['home_name']: f"{(h['c_std']/total_h)*100:.1f}%", g['away_name']: f"{(a['c_std']/total_a)*100:.1f}%"},
                        {"Stat": "Pitching", g['home_name']: f"{(h['c_era']/total_h)*100:.1f}%", g['away_name']: f"{(a['c_era']/total_a)*100:.1f}%"},
                        {"Stat": "Batting AVG", g['home_name']: f"{(h['c_avg']/total_h)*100:.1f}%", g['away_name']: f"{(a['c_avg']/total_a)*100:.1f}%"},
                        {"Stat": "Slugging", g['home_name']: f"{(h['c_slg']/total_h)*100:.1f}%", g['away_name']: f"{(a['c_slg']/total_a)*100:.1f}%"},
                    ])
                    st.table(impact_df)

                if g.get('status') in ["Final", "Live", "In Progress", "Game Over"]:
                    st.write("### 📊 Box Score")
                    r_a, r_h = g.get('away_score', 0), g.get('home_score', 0)
                    # Fixed potential KeyError with .get() safety checks
                    h_a = data['box'].get('away', {}).get('teamStats', {}).get('batting', {}).get('hits', '-')
                    h_h = data['box'].get('home', {}).get('teamStats', {}).get('batting', {}).get('hits', '-')
                    e_a = data['box'].get('away', {}).get('teamStats', {}).get('fielding', {}).get('errors', '-')
                    e_h = data['box'].get('home', {}).get('teamStats', {}).get('fielding', {}).get('errors', '-')
                    
                    box_df = pd.DataFrame({
                        "Team": [g['away_name'], g['home_name']],
                        "R": [r_a, r_h],
                        "H": [h_a, h_h],
                        "E": [e_a, e_h]
                    })
                    
                    def highlight_winner(row):
                        styles = [''] * len(row)
                        if r_a > r_h and row['Team'] == g['away_name']:
                            styles = ['background-color: #06402B; color: white; font-weight: bold'] * len(row)
                        elif r_h > r_a and row['Team'] == g['home_name']:
                            styles = ['background-color: #06402B; color: white; font-weight: bold'] * len(row)
                        return styles

                    st.dataframe(box_df.style.apply(highlight_winner, axis=1), hide_index=True, use_container_width=True)

                st.write("### 📋 Lineups")
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
                    
