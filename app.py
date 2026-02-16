import streamlit as st
import statsapi
import pandas as pd
import json
import os
import hashlib
from datetime import datetime
from streamlit_autorefresh import st_autorefresh

# --- PAGE CONFIG & THEME ---
st.set_page_config(page_title="MLB AI Scout Pro", layout="wide", page_icon="⚾")
st_autorefresh(interval=30000, key="mlb_live_timer")

st.markdown("""
    <style>
    .main { background-color: #0e1117; }
    .stButton>button { width: 100%; border-radius: 5px; height: 3em; background-color: #262730; color: white; border: 1px solid #444; }
    .matchup-card { border-radius: 15px; padding: 20px; background: #161b22; border: 1px solid #30363d; margin-bottom: 20px; }
    .winner-box { background: #1b2838; border: 2px solid #4CAF50; border-radius: 10px; padding: 15px; margin-bottom: 10px; color: #e6edf3; text-align: center;}
    .pitcher-box { background: #0d1117; border: 1px solid #30363d; border-radius: 8px; padding: 8px; text-align: center; margin-bottom: 5px; }
    </style>
    """, unsafe_allow_html=True)

# --- SECURE STORAGE LOGIC ---
def hash_password(password):
    return hashlib.sha256(str.encode(password)).hexdigest()

def get_user_file(username):
    clean_name = "".join(x for x in username if x.isalnum())
    return f"profile_{clean_name}.json"

def load_settings(username, password):
    filename = get_user_file(username)
    if os.path.exists(filename):
        with open(filename, "r") as f:
            data = json.load(f)
            if data.get("password_hash") == hash_password(password):
                return data.get("settings"), True
            else:
                return None, False
    return {
        "fav_team": "None", "w_std": 40, "w_era": 15, "w_avg": 20, "w_slg": 25, "preset": "Balanced"
    }, True

def save_settings(username, password, settings_data):
    filename = get_user_file(username)
    data_to_save = {"password_hash": hash_password(password), "settings": settings_data}
    with open(filename, "w") as f:
        json.dump(data_to_save, f)

# --- INITIALIZE SESSION STATE ---
if "active_game_id" not in st.session_state:
    st.session_state.active_game_id = None

# --- SIDEBAR ---
with st.sidebar:
    st.title("⚾ MLB Intelligence Pro")
    user_id = st.text_input("Profile Name", value="DefaultUser")
    password = st.text_input("Password", type="password", value="1234")
    
    user_settings, auth_success = load_settings(user_id, password)
    
    if not auth_success:
        st.error("❌ Incorrect password.")
        st.stop()
    
    st.session_state.saved_settings = user_settings
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

    if st.button(f"💾 Save Profile"):
        new_settings = {"fav_team": fav_team, "w_std": w_std, "w_era": w_era, "w_avg": w_avg, "w_slg": w_slg, "preset": preset}
        save_settings(user_id, password, new_settings)
        st.success("Profile saved!")

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
            
            # Fetch Lineup (top 9)
            lineup = []
            avgs, slgs = [], []
            for pid in batters[:9]:
                p_info = players.get(f"ID{pid}", {}).get('person', {})
                name = p_info.get('fullName', "TBD")
                try:
                    p_stat = statsapi.player_stat_data(pid, group="hitting", type="season", season=year)
                    s = p_stat['stats'][0]['stats'] if p_stat.get('stats') else {}
                    avg_val = s.get('avg', '.000')
                    lineup.append({"Player": name, "AVG": avg_val})
                    avgs.append(float(str(avg_val).replace('.','0.')))
                    slgs.append(float(str(s.get('slg', '.400')).replace('.','0.')))
                except:
                    lineup.append({"Player": name, "AVG": ".250"})
                    avgs.append(0.250); slgs.append(0.400)

            # Fetch Pitcher
            p_list = side_data.get('pitchers', [])
            p_name, era = "TBD", 4.10
            if p_list:
                p_name = players.get(f"ID{p_list[0]}", {}).get('person', {}).get('fullName', "TBD")
                try:
                    sp_stat = statsapi.player_stat_data(p_list[0], group="pitching", type="season", season=year)
                    era = float(sp_stat['stats'][0]['stats'].get('era', 4.10))
                except: pass
            
            _, wpct = get_team_info(tid, year)
            score = (wpct*(w_std/100)) + ((4.1/max(0.1,era))*(w_era/100)) + ((sum(avgs)/max(1,len(avgs))*4)*(w_avg/100)) + ((sum(slgs)/max(1,len(slgs))*2.5)*(w_slg/100))
            return {"score": score, "lineup": lineup, "p_name": p_name, "era": era}

        away_results = fetch_side_data('away', g_info['away_id'])
        home_results = fetch_side_data('home', g_info['home_id'])
        
        diff = (home_results['score'] - away_results['score']) * sensitivity
        prob_h = 0.5 + (diff / max(0.1, (home_results['score'] + away_results['score'])/2)) + 0.03 
        
        return {
            "prob_h": max(0.01, min(0.99, prob_h)), 
            "box": box,
            "away": away_results,
            "home": home_results
        }
    except: return None

# --- MAIN UI ---
st.header("⚾ MLB Intelligence Pro")
u_date = st.date_input("Select Game Date", datetime.now())

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
        st.markdown(f'<div class="matchup-card">', unsafe_allow_html=True)
        c1, c2, c3 = st.columns([1, 4, 1.5])
        with c1: st.image(f"https://www.mlbstatic.com/team-logos/{g['away_id']}.svg", width=50)
        with c2: 
            st.markdown(f"**{g.get('away_name')} @ {g.get('home_name')}**")
            st.caption(f"{g.get('status')} | {u_date.year} Season")
        with c3:
            if st.button("Analyze Matchup", key=f"btn_{gid}"): 
                st.session_state.active_game_id = gid
        
        if st.session_state.active_game_id == gid:
            with st.spinner("Crunching numbers..."):
                data = get_detailed_data(gid, g, u_date.year, w_std, w_era, w_avg, w_slg, sensitivity)
            
            if data:
                p_h = data['prob_h']
                winner = g['home_name'] if p_h > 0.5 else g['away_name']
                win_pct = p_h if p_h > 0.5 else 1-p_h
                st.markdown(f'<div class="winner-box">🏅 Projected Winner: <b>{winner}</b> ({win_pct*100:.1f}%)</div>', unsafe_allow_html=True)
                
                # Lineup & Pitcher Info
                col_a, col_h = st.columns(2)
                with col_a:
                    st.markdown(f"**{g['away_name']}**")
                    st.markdown(f"<div class='pitcher-box'>SP: {data['away']['p_name']} (ERA: {data['away']['era']})</div>", unsafe_allow_html=True)
                    st.table(pd.DataFrame(data['away']['lineup']))
                with col_h:
                    st.markdown(f"**{g['home_name']}**")
                    st.markdown(f"<div class='pitcher-box'>SP: {data['home']['p_name']} (ERA: {data['home']['era']})</div>", unsafe_allow_html=True)
                    st.table(pd.DataFrame(data['home']['lineup']))

                # Box Score
                if g.get('status') in ["Final", "Live", "In Progress", "Game Over"]:
                    try:
                        b = data['box']
                        box_df = pd.DataFrame({
                            "Team": [g['away_name'], g['home_name']],
                            "R": [b['away']['teamStats']['batting']['runs'], b['home']['teamStats']['batting']['runs']],
                            "H": [b['away']['teamStats']['batting']['hits'], b['home']['teamStats']['batting']['hits']],
                            "E": [b['away']['teamStats']['fielding'].get('errors', 0), b['home']['teamStats']['fielding'].get('errors', 0)]
                        })
                        st.markdown("**Game Box Score**")
                        st.dataframe(box_df, use_container_width=True, hide_index=True)
                    except: st.caption("Box score data updating...")
            else: st.info("Detailed data not available yet.")
        st.markdown('</div>', unsafe_allow_html=True)
                
