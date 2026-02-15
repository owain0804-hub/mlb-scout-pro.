import streamlit as st
import statsapi
import pandas as pd
import json
import os
import streamlit_authenticator as stauth
from datetime import datetime
from streamlit_autorefresh import st_autorefresh

# --- PAGE CONFIG ---
st.set_page_config(page_title="MLB AI Scout Pro", layout="wide", page_icon="⚾")
st_autorefresh(interval=30000, key="mlb_live_timer")

# Custom CSS for that "Pro" look
st.markdown("""
    <style>
    .main { background-color: #0e1117; }
    .matchup-card { border-radius: 15px; padding: 20px; background: #161b22; border: 1px solid #30363d; margin-bottom: 20px; }
    .winner-box { background: #1b2838; border: 2px solid #4CAF50; border-radius: 10px; padding: 15px; margin-bottom: 10px; text-align: center;}
    .pitcher-box { background: #0d1117; border: 1px solid #30363d; border-radius: 8px; padding: 8px; text-align: center; margin-bottom: 5px; }
    </style>
    """, unsafe_allow_html=True)

# --- AUTHENTICATION ---
# Pre-defined users (You can add more here)
names = ['User One', 'Admin']
usernames = ['user@example.com', 'admin@example.com']
passwords = ['baseball2025', 'admin123'] 

hashed_passwords = stauth.Hasher(passwords).generate()
authenticator = stauth.Authenticate(
    {'usernames': {un: {'name': n, 'password': p} for n, un, p in zip(names, usernames, hashed_passwords)}},
    'mlb_scout_cookie', 'auth_key', cookie_expiry_days=30
)

name, authentication_status, username = authenticator.login('Login', 'main')

if authentication_status == False:
    st.error('Username/password is incorrect')
elif authentication_status == None:
    st.warning('Please enter your email and password to access the model.')
elif authentication_status:

    # --- PER-USER STORAGE ---
    USER_CONFIG = f"settings_{username.replace('@', '_').replace('.', '_')}.json"

    def load_user_settings():
        if os.path.exists(USER_CONFIG):
            try:
                with open(USER_CONFIG, "r") as f: return json.load(f)
            except: pass
        return {"fav_team": "None", "w_std": 40, "w_era": 15, "w_avg": 20, "w_slg": 25, "preset": "Balanced"}

    def save_user_settings(data):
        with open(USER_CONFIG, "w") as f: json.dump(data, f)

    if "saved_settings" not in st.session_state:
        st.session_state.saved_settings = load_user_settings()

    # --- SIDEBAR ---
    with st.sidebar:
        st.title(f"Welcome, {name}")
        authenticator.logout('Logout', 'sidebar')
        st.divider()
        
        s = st.session_state.saved_settings
        preset = st.radio("Model Presets", ["Balanced", "Pitching Heavy", "Offense Heavy", "Custom"], 
                          index=["Balanced", "Pitching Heavy", "Offense Heavy", "Custom"].index(s.get("preset", "Balanced")))
        
        if preset == "Balanced": w_std, w_era, w_avg, w_slg = 40, 15, 20, 25
        elif preset == "Pitching Heavy": w_std, w_era, w_avg, w_slg = 20, 50, 15, 15
        elif preset == "Offense Heavy": w_std, w_era, w_avg, w_slg = 20, 10, 35, 35
        else:
            w_std = st.slider("Standings %", 0, 100, value=s["w_std"])
            w_era = st.slider("Pitching %", 0, 100, value=s["w_era"])
            w_avg = st.slider("AVG %", 0, 100, value=s["w_avg"])
            w_slg = st.slider("SLG %", 0, 100, value=s["w_slg"])
        
        sensitivity = st.slider("Sensitivity", 1.0, 3.0, value=1.2)
        
        all_teams = [t['name'] for t in statsapi.get('teams', {'sportId': 1})['teams']]
        fav_team = st.selectbox("Favorite Team", ["None"] + sorted(all_teams), 
                                index=(["None"] + sorted(all_teams)).index(s["fav_team"]) if s["fav_team"] in all_teams else 0)

        if st.button("💾 Save My Profile"):
            new_settings = {"fav_team": fav_team, "w_std": w_std, "w_era": w_era, "w_avg": w_avg, "w_slg": w_slg, "preset": preset}
            save_user_settings(new_settings)
            st.session_state.saved_settings = new_settings
            st.success("Settings Saved!")

    # --- CORE FUNCTIONS ---
    @st.cache_data(ttl=3600)
    def get_team_info(team_id, year):
        try:
            standings = statsapi.standings_data(leagueId="103,104", season=year)
            for div in standings.values():
                for t in div.get('teams', []):
                    if t.get('team_id') == team_id:
                        return f"{t['w']}-{t['l']}", (t['w'] / max(1, t['w']+t['l']))
        except: pass
        return "0-0", 0.500

    def get_detailed_data(game_id, g_info, year, w_std, w_era, w_avg, w_slg, sensitivity):
        try:
            box = statsapi.boxscore_data(game_id)
            if not box: return None
            
            def fetch_side(side, tid):
                s_data = box.get(side, {})
                batters = s_data.get('batters', [])[:9]
                avgs, slgs = [], []
                for pid in batters:
                    try:
                        p_stat = statsapi.player_stat_data(pid, group="hitting", type="season", season=year)
                        stats = p_stat['stats'][0]['stats'] if p_stat.get('stats') else {}
                        avgs.append(float(stats.get('avg', '.250').replace('.','0.')))
                        slgs.append(float(stats.get('slg', '.400').replace('.','0.')))
                    except: avgs.append(0.250); slgs.append(0.400)
                
                p_list = s_data.get('pitchers', [])
                sp_id = p_list[0] if p_list else None
                era = 4.10
                if sp_id:
                    try:
                        p_stat = statsapi.player_stat_data(sp_id, group="pitching", type="season", season=year)
                        era = float(p_stat['stats'][0]['stats'].get('era', 4.10))
                    except: pass
                
                _, wpct = get_team_info(tid, year)
                score = (wpct*(w_std/100)) + ((4.1/max(0.1,era))*(w_era/100)) + ((sum(avgs)/9*4)*(w_avg/100)) + ((sum(slgs)/9*2.5)*(w_slg/100))
                return {"score": score, "era": era, "avg": sum(avgs)/9, "slg": sum(slgs)/9}

            a_vals = fetch_side('away', g_info['away_id'])
            h_vals = fetch_side('home', g_info['home_id'])
            
            diff = (h_vals['score'] - a_vals['score']) * sensitivity
            prob_h = 0.5 + (diff / max(0.1, (h_vals['score']+a_vals['score'])/2)) + 0.03
            return {"prob_h": max(0.01, min(0.99, prob_h)), "box": box}
        except: return None

    # --- MAIN UI ---
    st.title("⚾ MLB Intelligence Pro")
    u_date = st.date_input("Select Date", datetime.now())
    
    raw_sched = statsapi.schedule(date=u_date.strftime("%m/%d/%Y"))
    unique_games, seen = [], set()
    for g in raw_sched:
        if g['game_id'] not in seen:
            unique_games.append(g); seen.add(g['game_id'])

    fav = st.session_state.saved_settings["fav_team"]
    sorted_games = sorted(unique_games, key=lambda x: (x.get('away_name') != fav and x.get('home_name') != fav))

    for g in sorted_games:
        gid = g['game_id']
        with st.container():
            st.markdown('<div class="matchup-card">', unsafe_allow_html=True)
            c1, c2, c3 = st.columns([1, 4, 1.5])
            with c1: st.image(f"https://www.mlbstatic.com/team-logos/{g['away_id']}.svg", width=60)
            with c2: 
                st.markdown(f"**{g.get('away_name')} @ {g.get('home_name')}**")
                st.caption(f"Status: {g.get('status')}")
            with c3:
                if st.button("Analyze", key=f"btn_{gid}"): st.session_state.active_game_id = gid
            
            if st.session_state.active_game_id == gid:
                data = get_detailed_data(gid, g, u_date.year, w_std, w_era, w_avg, w_slg, sensitivity)
                if data:
                    p_h = data['prob_h']
                    win_pct = p_h if p_h > 0.5 else 1-p_h
                    winner = g['home_name'] if p_h > 0.5 else g['away_name']
                    st.markdown(f'<div class="winner-box">🏅 Winner: <b>{winner}</b> ({win_pct*100:.1f}%)</div>', unsafe_allow_html=True)
                else:
                    st.info("Detailed data not available for this game yet.")
            st.markdown('</div>', unsafe_allow_html=True)
            
