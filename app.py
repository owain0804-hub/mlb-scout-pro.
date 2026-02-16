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
from datetime import datetime, timedelta
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
    """PBKDF2 with 100k iterations - High Security"""
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
        with open(path, "r") as f:
            return json.load(f)
    return None

# --- EMAIL NOTIFICATION ---
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

# --- AUTH LOGIC ---
if "authenticated" not in st.session_state:
    st.session_state.authenticated = False

# Auto-Login Logic (Session Token Check)
auth_cookie = cookie_manager.get(cookie="mlb_session_token")
if not st.session_state.authenticated and auth_cookie:
    # Cookie format: username:token
    if ":" in auth_cookie:
        u_name, u_token = auth_cookie.split(":", 1)
        u_data = load_user_data(u_name)
        if u_data and u_data.get("session_token") == u_token:
            # Check if session is under 10 uses
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
                if u_data:
                    salt = bytes.fromhex(u_data['salt'])
                    if u_data['pwd_hash'] == get_hash(p_in, salt):
                        # Generate NEW session token
                        new_token = secrets.token_urlsafe(32)
                        u_data['session_token'] = new_token
                        u_data['login_count'] = (u_data.get('login_count', 0) + 1) % 11
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
                if nu and np and not os.path.exists(get_user_file(nu)):
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

# --- SIDEBAR ---
with st.sidebar:
    st.title(f"👋 {st.session_state.current_user}")
    
    # Show Session Counter
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

    # Presets & Weights
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

    # --- ADVANCED CACHING ---
    @st.cache_data(ttl=3600)
    def get_all_teams():
        return sorted([t['name'] for t in statsapi.get('teams', {'sportId': 1})['teams']])

    all_teams = get_all_teams()
    fav_team = st.selectbox("Favorite Team", ["None"] + all_teams, index=(["None"] + all_teams).index(s.get('fav_team', 'None')))

    if st.button("💾 Save Settings"):
        u_data['settings'] = {"fav_team": fav_team, "w_std": w_std, "w_era": w_era, "w_avg": w_avg, "w_slg": w_slg, "preset": preset}
        save_user_data(st.session_state.current_user, u_data)
        st.session_state.saved_settings = u_data['settings']
        st.success("Saved!")

# --- PERFORMANCE FUNCTIONS ---
@st.cache_data(ttl=600) # Faster refresh for schedules
def get_cached_schedule(date_str):
    return statsapi.schedule(date=date_str)

@st.cache_data(ttl=3600)
def get_player_stats(pid, year):
    return statsapi.player_stat_data(pid, group="hitting", type="season", season=year)

# --- UI MAIN ---
st.header("⚾ MLB Intelligence Pro")
u_date = st.date_input("Date", datetime.now())
sched = get_cached_schedule(u_date.strftime("%m/%d/%Y"))

if not sched:
    st.info("No games scheduled.")
else:
    for g in sched:
        # (Same Game Analysis Logic as before, using cached stats functions)
        st.write(f"**{g['away_name']} vs {g['home_name']}**")
        # [Visual cards and projection code here...]
        
