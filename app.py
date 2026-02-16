import streamlit as st
import statsapi
import pandas as pd
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
SENDER_EMAIL = "your-email@gmail.com" 
SENDER_PASSWORD = "your-app-password" 
ADMIN_EMAIL = "your-receiving-email@gmail.com"

def send_admin_notification(new_user):
    try:
        subject = f"⚾ New Account Alert: {new_user}"
        body = f"A new user has just registered on MLB AI Scout Pro.\n\nUsername: {new_user}\nTimestamp: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"
        msg = MIMEText(body)
        msg['Subject'] = subject
        msg['From'] = SENDER_EMAIL
        msg['To'] = ADMIN_EMAIL
        with smtplib.SMTP(SMTP_SERVER, SMTP_PORT) as server:
            server.starttls()
            server.login(SENDER_EMAIL, SENDER_PASSWORD)
            server.send_message(msg)
    except Exception as e:
        print(f"Notification failed: {e}")

# --- PAGE CONFIG & THEME ---
st.set_page_config(page_title="MLB AI Scout Pro", layout="wide", page_icon="⚾")
st_autorefresh(interval=30000, key="mlb_live_timer")

st.markdown("""
    <style>
    .main { background-color: #0e1117; }
    .stButton>button { width: 100%; border-radius: 5px; height: 3em; background-color: #262730; color: white; border: 1px solid #444; }
    .matchup-card { border-radius: 15px; padding: 20px; background: #161b22; border: 1px solid #30363d; margin-bottom: 20px; }
    .winner-box { background: #1b2838; border: 2px solid #4CAF50; border-radius: 10px; padding: 15px; margin-bottom: 10px; color: #e6edf3; text-align: center;}
    .login-header { text-align: center; padding-top: 50px; padding-bottom: 20px; }
    .login-subtitle { text-align: center; color: #8b949e; margin-bottom: 30px; }
    .details-text { font-size: 0.9em; color: #8b949e; line-height: 1.4; }
    .advantage-text { color: #4CAF50; font-weight: bold; }
    </style>
    """, unsafe_allow_html=True)

# --- SECURE STORAGE & SESSION PERSISTENCE ---
SESSION_FILE = "active_session.json"

def hash_password(password):
    return hashlib.sha256(str.encode(password)).hexdigest()

def get_user_file(username):
    clean_name = "".join(x for x in username if x.isalnum())
    return f"profile_{clean_name}.json"

def save_settings(username, password, settings_data):
    filename = get_user_file(username)
    data_to_save = {"password_hash": hash_password(password), "settings": settings_data}
    with open(filename, "w") as f:
        json.dump(data_to_save, f)

def load_settings(username, password):
    filename = get_user_file(username)
    if os.path.exists(filename):
        with open(filename, "r") as f:
            data = json.load(f)
            if data.get("password_hash") == hash_password(password):
                return data.get("settings"), True
    return None, False

def manage_persistent_session(username=None, password=None, action="check"):
    if action == "save":
        with open(SESSION_FILE, "w") as f:
            json.dump({"user": username, "pwd": password, "count": 1}, f)
    elif action == "check":
        if os.path.exists(SESSION_FILE):
            with open(SESSION_FILE, "r") as f:
                data = json.load(f)
                if data["count"] < 10:
                    data["count"] += 1
                    with open(SESSION_FILE, "w") as fw:
                        json.dump(data, fw)
                    return data["user"], data["pwd"], True
                else:
                    os.remove(SESSION_FILE)
        return None, None, False
    elif action == "logout":
        if os.path.exists(SESSION_FILE):
            os.remove(SESSION_FILE)

# --- INITIALIZE SESSION STATE ---
if "authenticated" not in st.session_state:
    u, p, success = manage_persistent_session(action="check")
    if success:
        sets, valid = load_settings(u, p)
        if valid:
            st.session_state.authenticated = True
            st.session_state.current_user = u
            st.session_state.user_pwd = p
            st.session_state.saved_settings = sets
        else: st.session_state.authenticated = False
    else: st.session_state.authenticated = False

if "active_game_id" not in st.session_state:
    st.session_state.active_game_id = None

# --- AUTHENTICATION SCREEN ---
if not st.session_state.authenticated:
    st.markdown("<h1 class='login-header'>⚾ MLB Intelligence Pro</h1>", unsafe_allow_html=True)
    col1, col2, col3 = st.columns([1, 2, 1])
    with col2:
        mode = st.tabs(["Secure Login", "Register Account"])
        with mode[0]:
            user_id = st.text_input("Username", key="login_user")
            input_pwd = st.text_input("Password", type="password", key="login_pwd")
            if st.button("Access Dashboard"):
                settings, success = load_settings(user_id, input_pwd)
                if success:
                    st.session_state.authenticated = True
                    st.session_state.current_user = user_id
                    st.session_state.user_pwd = input_pwd
                    st.session_state.saved_settings = settings
                    manage_persistent_session(user_id, input_pwd, action="save")
                    st.rerun()
                else: st.error("❌ Invalid credentials.")
        with mode[1]:
            new_user = st.text_input("New Username", key="reg_user")
            new_pwd = st.text_input("New Password", type="password", key="reg_pwd")
            if st.button("Create Professional Profile"):
                if new_user and new_pwd:
                    if os.path.exists(get_user_file(new_user)): st.warning("⚠️ Profile already exists.")
                    else:
                        init_s = {"fav_team": "None", "w_std": 40, "w_era": 15, "w_avg": 20, "w_slg": 25, "preset": "Balanced"}
                        save_settings(new_user, new_pwd, init_s)
                        send_admin_notification(new_user)
                        st.success(f"✅ Account Created! Notification sent.")
    st.stop()

# --- SIDEBAR ---
with st.sidebar:
    st.title("⚾ Settings")
    if st.button("Log Out"):
        manage_persistent_session(action="logout")
        st.session_state.authenticated = False
        st.rerun()
    st.divider()
    s = st.session_state.saved_settings
    preset_options = ["Balanced", "Pitching Heavy", "Offense Heavy", "Custom"]
    preset = st.radio("Model Presets", preset_options, index=preset_options.index(s.get("preset", "Balanced")))
    if preset == "Balanced": w_std, w_era, w_avg, w_slg = 40, 15, 20, 25
    elif preset == "Pitching Heavy": w_std, w_era, w_avg, w_slg = 20, 50, 15, 15
    elif preset == "Offense Heavy": w_std, w_era, w_avg, w_slg = 20, 10, 35, 35
    else:
        w_std = st.slider("Standings %", 0, 100, value=s["w_std"])
        w_era = st.slider("Pitching %", 0, 100, value=s["w_era"])
        w_avg = st.slider("Lineup AVG %", 0, 100, value=s["w_avg"])
        w_slg = st.slider("Lineup SLG %", 0, 100, value=s["w_slg"])
    sensitivity = st.slider("Stat Sensitivity", 1.0, 3.0, value=1.2, step=0.1)
    
    try:
        all_teams = sorted([t['name'] for t in statsapi.get('teams', {'sportId': 1})['teams']])
    except: all_teams = []
    fav_team = st.selectbox("Favorite Team", ["None"] + all_teams, 
                            index=(["None"] + all_teams).index(s["fav_team"]) if s["fav_team"] in all_teams else 0)

    if st.button("💾 Save Preferences"):
        new_settings = {"fav_team": fav_team, "w_std": w_std, "w_era": w_era, "w_avg": w_avg, "w_slg": w_slg, "preset": preset}
        save_settings(st.session_state.current_user, st.session_state.user_pwd, new_settings)
        st.session_state.saved_settings = new_settings
        st.success("Preferences Saved!")

# --- CORE FUNCTIONS ---
@st.cache_data(ttl=3600)
def get_team_info(team_id, year):
    try:
        standings = statsapi.standings_data(leagueId="103,104", season=year)
        for div in standings.values():
            for t in div.get('teams', []):
                if t.get('team_id') == team_id:
                    return f"{t['w']}-{t['l']}", (int(t['w']) / max(1, int(t['w'])+int(t['l'])))
    except: pass
    return "0-0", 0.500

def get_detailed_data(game_id, g_info, year, w_std, w_era, w_avg, w_slg, sensitivity):
    try:
        box = statsapi.boxscore_data(game_id)
        if not box: return None
        
        def fetch_side_data(side, tid):
            side_data = box.get(side, {})
            players = side_data.get('players', {})
            batters = side_data.get('batters', [])
            lineup = []
            avgs, slgs = [], []
            for pid in batters[:9]:
                p_info = players.get(f"ID{pid}", {}).get('person', {})
                try:
                    p_stat = statsapi.player_stat_data(pid, group="hitting", type="season", season=year)
                    s = p_stat['stats'][0]['stats'] if p_stat.get('stats') else {}
                    avg_v = s.get('avg', '.000')
                    lineup.append({"Player": p_info.get('fullName', "TBD"), "AVG": avg_v})
                    avgs.append(float(str(avg_v).replace('.','0.')))
                    slgs.append(float(str(s.get('slg', '.400')).replace('.','0.')))
                except:
                    lineup.append({"Player": p_info.get('fullName', "TBD"), "AVG": ".250"})
                    avgs.append(0.250); slgs.append(0.400)
            
            p_list = side_data.get('pitchers', [])
            p_name, era = "TBD", 4.10
            if p_list:
                p_name = players.get(f"ID{p_list[0]}", {}).get('person', {}).get('fullName', "TBD")
                try:
                    sp_stat = statsapi.player_stat_data(p_list[0], group="pitching", type="season", season=year)
                    era = float(sp_stat['stats'][0]['stats'].get('era', 4.10))
                except: pass
            record, wpct = get_team_info(tid, year)
            
            # Weighted calculation components
            comp_std = wpct * (w_std/100)
            comp_era = (4.1/max(0.1,era)) * (w_era/100)
            comp_avg = (sum(avgs)/max(1,len(avgs))*4) * (w_avg/100)
            comp_slg = (sum(slgs)/max(1,len(slgs))*2.5) * (w_slg/100)
            
            score = comp_std + comp_era + comp_avg + comp_slg
            return {"score": score, "lineup": lineup, "p_name": p_name, "era": era, "wpct": wpct, 
                    "avg": sum(avgs)/max(1,len(avgs)), "slg": sum(slgs)/max(1,len(slgs))}

        a_data = fetch_side_data('away', g_info['away_id'])
        h_data = fetch_side_data('home', g_info['home_id'])
        
        # Win Probability Calculation
        prob_h = 0.5 + ((h_data['score'] - a_data['score']) * sensitivity / max(0.1, (h_data['score'] + a_data['score'])/2)) + 0.03 
        return {"prob_h": max(0.01, min(0.99, prob_h)), "box": box, "away": a_data, "home": h_data}
    except: return None

# --- MAIN UI ---
st.header("⚾ MLB Intelligence Pro")
u_date = st.date_input("Select Date", datetime.now())
raw_sched = statsapi.schedule(date=u_date.strftime("%m/%d/%Y"))
unique_games, seen_ids = [], set()
for g in raw_sched:
    if g['game_id'] not in seen_ids:
        unique_games.append(g); seen_ids.add(g['game_id'])

fav = st.session_state.saved_settings.get("fav_team", "None")
sorted_games = sorted(unique_games, key=lambda x: (x.get('away_name') != fav and x.get('home_name') != fav))

for g in sorted_games:
    gid = g['game_id']
    with st.container():
        st.markdown('<div class="matchup-card">', unsafe_allow_html=True)
        c1, c2, c3 = st.columns([1, 4, 1.5])
        with c1: st.image(f"https://www.mlbstatic.com/team-logos/{g['away_id']}.svg", width=50)
        with c2: 
            st.markdown(f"**{g.get('away_name')} @ {g.get('home_name')}**")
            st.caption(f"{g.get('status')} | {u_date.year} Season")
        with c3:
            if st.button("Analyze Matchup", key=f"btn_{gid}"): st.session_state.active_game_id = gid
        
        if st.session_state.active_game_id == gid:
            data = get_detailed_data(gid, g, u_date.year, w_std, w_era, w_avg, w_slg, sensitivity)
            if data:
                p_h = data['prob_h']
                is_home_win = p_h > 0.5
                winner = g['home_name'] if is_home_win else g['away_name']
                confidence = (p_h if is_home_win else 1-p_h)*100
                st.markdown(f'<div class="winner-box">🏅 Projected Winner: <b>{winner}</b> ({confidence:.1f}%)</div>', unsafe_allow_html=True)
                
                # --- NEW DETAILS BOX ---
                with st.expander("🔍 Why these odds? Matchup Breakdown"):
                    st.markdown("### Model Factors")
                    h, a = data['home'], data['away']
                    
                    # Determine advantage for each category
                    adv_pitch = g['home_name'] if h['era'] < a['era'] else g['away_name']
                    adv_bat = g['home_name'] if h['avg'] > a['avg'] else g['away_name']
                    adv_pow = g['home_name'] if h['slg'] > a['slg'] else g['away_name']
                    adv_record = g['home_name'] if h['wpct'] > a['wpct'] else g['away_name']

                    st.markdown(f"""
                    <div class="details-text">
                    This projection is built by weighing current season data. Here is where <b>{winner}</b> gained the edge:
                    <br><br>
                    • <b>Pitching:</b> {adv_pitch} has the advantage here ({h['p_name']} ERA: {h['era']} vs {a['p_name']} ERA: {a['era']}).<br>
                    • <b>Contact:</b> The {adv_bat} lineup is currently averaging a higher team BA ({h['avg']:.3f} vs {a['avg']:.3f}).<br>
                    • <b>Power:</b> {adv_pow} holds the Slug percentage lead ({h['slg']:.3f} vs {a['slg']:.3f}).<br>
                    • <b>Season Form:</b> {adv_record} enters with a superior overall win percentage ({h['wpct']*100:.1f}% vs {a['wpct']*100:.1f}%).<br>
                    <br>
                    <i>*Odds also include a +3.0% Home Field Advantage adjustment.</i>
                    </div>
                    """, unsafe_allow_html=True)

                if g.get('status') in ["Final", "Live", "In Progress", "Game Over"]:
                    st.markdown("### 📊 Box Score")
                    r_a, r_h = g.get('away_score', 0), g.get('home_score', 0)
                    b_data = data['box']
                    h_a = b_data.get('away', {}).get('teamStats', {}).get('batting', {}).get('hits', '-')
                    h_h = b_data.get('home', {}).get('teamStats', {}).get('batting', {}).get('hits', '-')
                    box_df = pd.DataFrame({"Team": [g['away_name'], g['home_name']], "R": [r_a, r_h], "H": [h_a, h_h]})
                    st.dataframe(box_df, use_container_width=True, hide_index=True)

                st.markdown("### 📋 Lineups & Pitching")
                col_a, col_h = st.columns(2)
                with col_a:
                    st.write(f"**{g['away_name']}**")
                    st.caption(f"SP: {a['p_name']} ({a['era']})")
                    st.dataframe(pd.DataFrame(a['lineup']), hide_index=True)
                with col_h:
                    st.write(f"**{g['home_name']}**")
                    st.caption(f"SP: {h['p_name']} ({h['era']})")
                    st.dataframe(pd.DataFrame(h['lineup']), hide_index=True)
            else: st.info("Loading detailed analysis...")
        st.markdown('</div>', unsafe_allow_html=True)
                    
