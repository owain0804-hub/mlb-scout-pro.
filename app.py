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
                if u_data and 'salt' in u_data:
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
                    send_admin_notification(nu)
                    st.success("Account created!")
    st.stop()

# --- SIDEBAR ---
with st.sidebar:
    st.title(f"👋 {st.session_state.current_user}")
    u_data = load_user_data(st.session_state.current_user)
    remains = 10 - u_data.get('login_count', 0)
    st.caption(f"Security sessions remaining: {remains}/10")

    if st.button("Log Out"):
        cookie_manager.delete("mlb_session_token")
        st.session_state.authenticated = False
        st.rerun()
    st.divider()

    s = st.session_state.saved_settings
    preset_list = ["Pro Optimized (v2)", "Balanced", "Custom"]
    current_p = s.get('preset', 'Pro Optimized (v2)')
    
    preset_choice = st.radio("Model Presets", preset_list, index=preset_list.index(current_p) if current_p in preset_list else 0)
    
    # Updated weights to include Runs Per Game (RPG)
    if preset_choice == "Pro Optimized (v2)": w_std, w_era, w_rpg, w_avg, w_slg = 25, 25, 20, 5, 25
    elif preset_choice == "Balanced": w_std, w_era, w_rpg, w_avg, w_slg = 20, 20, 20, 20, 20
    else:
        w_std = st.slider("Standings %", 0, 100, s.get('w_std', 25))
        w_era = st.slider("Pitching %", 0, 100, s.get('w_era', 25))
        w_rpg = st.slider("Runs Per Game %", 0, 100, s.get('w_rpg', 20))
        w_avg = st.slider("AVG %", 0, 100, s.get('w_avg', 5))
        w_slg = st.slider("SLG %", 0, 100, s.get('w_slg', 25))

    sensitivity = st.slider("Sensitivity", 1.0, 3.0, 1.3)

    @st.cache_data(ttl=3600)
    def get_all_teams():
        try: return sorted([t['name'] for t in statsapi.get('teams', {'sportId': 1})['teams']])
        except: return []

    all_teams = get_all_teams()
    fav_team = st.selectbox("Favorite Team", ["None"] + all_teams, index=(["None"] + all_teams).index(s.get('fav_team', 'None')))

    if st.button("💾 Save Settings"):
        u_data['settings'] = {"fav_team": fav_team, "w_std": w_std, "w_era": w_era, "w_rpg": w_rpg, "w_avg": w_avg, "w_slg": w_slg, "preset": preset_choice}
        save_user_data(st.session_state.current_user, u_data)
        st.session_state.saved_settings = u_data['settings']
        st.success("Saved!")

# --- CORE LOGIC ---
@st.cache_data(ttl=3600)
def get_team_stats(tid, year):
    try:
        # Get overall team hitting stats for RPG
        stats = statsapi.team_stats(tid, groups='hitting', season=year)
        for s_set in stats:
            if s_set.get('group') == 'hitting':
                r = s_set['stats'].get('runs', 0)
                g = s_set['stats'].get('gamesPlayed', 1)
                return r / max(1, g)
    except: pass
    return 4.40 # League average fallback

@st.cache_data(ttl=3600)
def get_team_wpct(tid, year):
    try:
        standings = statsapi.standings_data(leagueId="103,104", season=year)
        for div in standings.values():
            for t in div.get('teams', []):
                if t['team_id'] == tid: return (int(t['w'])/max(1, int(t['w'])+int(t['l'])))
    except: pass
    return 0.50

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
            
            p_name, era, is_tbd = "TBD", 4.25, True
            if sd.get('pitchers'):
                try: 
                    pid = sd['pitchers'][0]
                    p_name = ps.get(f"ID{pid}", {}).get('person', {}).get('fullName', "TBD")
                    era_val = statsapi.player_stat_data(pid, group="pitching", type="season", season=year)['stats'][0]['stats'].get('era', '4.25')
                    era = float(era_val) if era_val != '-.--' else 4.25
                    is_tbd = False
                except: pass
            
            wpct = get_team_wpct(tid, year)
            rpg = get_team_stats(tid, year)
            
            # Weighted calculation
            c_std = wpct * (w_std/100)
            c_era = (4.25/max(0.1,era)) * (w_era/100)
            c_rpg = (rpg/4.4) * (w_rpg/100)
            c_avg = (sum(avgs)/max(1,len(avgs))*4) * (w_avg/100)
            c_slg = (sum(slgs)/max(1,len(slgs))*2.5) * (w_slg/100)
            
            return {"score": c_std+c_era+c_rpg+c_avg+c_slg, "lineup": lineup, "c_std": c_std, "c_era": c_era, "c_rpg": c_rpg, "c_avg": c_avg, "c_slg": c_slg, "p_name": p_name, "era": era, "wpct": wpct, "rpg": rpg, "avg_team": sum(avgs)/max(1,len(avgs)), "slg_team": sum(slgs)/max(1,len(slgs)), "is_tbd": is_tbd}
        
        a_d, h_d = fetch_side('away', g_info['away_id']), fetch_side('home', g_info['home_id'])
        prob_h = 0.5 + ((h_d['score'] - a_d['score']) * sensitivity) + 0.035
        return {"prob_h": max(0.01, min(0.99, prob_h)), "box": box, "away": a_d, "home": h_d}
    except: return None

# --- UI MAIN ---
st.header("⚾ MLB Intelligence Pro")
u_date = st.date_input("Select Date", datetime.now())
sched = statsapi.schedule(date=u_date.strftime("%m/%d/%Y"))

if not sched:
    st.info("📅 No games today ⚾")
else:
    for g in {g['game_id']: g for g in sched}.values():
        with st.container():
            st.markdown('<div style="border-radius:15px; padding:20px; background:#161b22; border:1px solid #30363d; margin-bottom:20px;">', unsafe_allow_html=True)
            c1, c2, c3 = st.columns([1, 4, 1.5])
            with c1: st.image(f"https://www.mlbstatic.com/team-logos/{g['away_id']}.svg", width=50)
            with c2: st.markdown(f"**{g['away_name']} @ {g['home_name']}**")
            with c3:
                if st.button("Analyze", key=f"b_{g['game_id']}"): st.session_state.active_game_id = g['game_id']
            
            if st.session_state.get("active_game_id") == g['game_id']:
                data = get_detailed_data(g['game_id'], g, u_date.year, w_std, w_era, w_rpg, w_avg, w_slg, sensitivity)
                if data:
                    res = g['home_name'] if data['prob_h'] > 0.5 else g['away_name']
                    conf_pct = (data['prob_h'] if data['prob_h'] > 0.5 else 1-data['prob_h']) * 100
                    st.success(f"🏅 Optimized Projection: {res} ({conf_pct:.1f}%)")

                    with st.expander("🔍 Prediction Breakdown"):
                        h, a = data['home'], data['away']
                        drivers = [("Record", h['c_std'], a['c_std']), ("Pitching", h['c_era'], a['c_era']), 
                                   ("Runs/Game", h['c_rpg'], a['c_rpg']), ("SLG", h['c_slg'], a['c_slg'])]
                        for label, hv, av in drivers:
                            st.write(f"**{label}**")
                            st.progress(hv / (hv + av))

                    st.write("### 📊 Scouting Data")
                    st.table(pd.DataFrame([
                        {"Category": "Win %", g['home_name']: f"{h['wpct']:.3f}", g['away_name']: f"{a['wpct']:.3f}"},
                        {"Category": "Starter ERA", g['home_name']: f"{h['era']:.2f}", g['away_name']: f"{a['era']:.2f}"},
                        {"Category": "Runs Per Game", g['home_name']: f"{h['rpg']:.2f}", g['away_name']: f"{a['rpg']:.2f}"},
                        {"Category": "Lineup SLG", g['home_name']: f"{h['slg_team']:.3f}", g['away_name']: f"{a['slg_team']:.3f}"},
                    ]))
            st.markdown('</div>', unsafe_allow_html=True)
            
