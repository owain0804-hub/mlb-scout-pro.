import streamlit as st
import statsapi
import pandas as pd
import json
import os
import hashlib
from datetime import datetime, timedelta
from streamlit_autorefresh import st_autorefresh
import extra_streamlit_components as stx

# --- MOBILE & UI STYLING ---
def apply_pro_styles():
    st.markdown("""
        <style>
        .mobile-row { display: flex; justify-content: space-between; gap: 10px; margin-bottom: 15px; }
        .metric-box-2 { background: #2b1d3d; border: 1px solid #8b5cf6; border-radius: 8px; padding: 12px; flex: 1; text-align: center; }
        .analysis-box { background: #161b22; border: 1px solid #30363d; border-radius: 8px; padding: 15px; margin-top: 10px; margin-bottom: 20px; }
        .matchup-card { background: #0d1117; border: 1px solid #30363d; border-radius: 12px; padding: 15px; margin-bottom: 5px; display: flex; align-items: center; justify-content: space-between; }
        .status-tag { font-size: 0.7em; padding: 2px 6px; border-radius: 4px; background: #30363d; color: #8b949e; }
        .pitcher-header { background: #161b22; border-bottom: 2px solid #3fb950; padding: 8px; margin-bottom: 5px; border-radius: 4px 4px 0 0; font-weight: bold; display: flex; align-items: center; gap: 10px; }
        .team-logo { width: 40px; height: 40px; }
        .impact-tag { font-size: 0.85em; color: #4ade80; font-weight: bold; margin-left: 8px; }
        </style>
    """, unsafe_allow_html=True)

# --- PERSISTENCE ---
USERS_FILE = "users_db.json"
def load_users():
    if os.path.exists(USERS_FILE):
        try:
            with open(USERS_FILE, 'r') as f: return json.load(f)
        except: return {}
    return {}

def save_users(users):
    with open(USERS_FILE, 'w') as f: json.dump(users, f)

def hash_pw(password): return hashlib.sha256(password.encode()).hexdigest()

# --- INITIALIZATION ---
st.set_page_config(page_title="MLB AI Scout Pro", layout="wide")
apply_pro_styles()
st_autorefresh(interval=60000, key="mlb_timer")
cookie_manager = stx.CookieManager()
users_db = load_users()

saved_user = cookie_manager.get("mlb_pro_user")
if "auth" not in st.session_state:
    if saved_user and saved_user in users_db:
        st.session_state.auth, st.session_state.username = True, saved_user
    else: st.session_state.auth = False
if "is_guest" not in st.session_state: st.session_state.is_guest = False

# --- LOGIN FLOW ---
if not st.session_state.auth and not st.session_state.is_guest:
    st.title("⚾ MLB Scout Pro")
    t1, t2 = st.tabs(["Login", "Register"])
    with t1:
        u = st.text_input("Username", key="login_u")
        p = st.text_input("Password", type="password", key="login_p")
        remember = st.checkbox("Remember Me", value=True)
        if st.button("Enter", use_container_width=True):
            if u in users_db and users_db[u].get('pw') == hash_pw(p):
                st.session_state.auth, st.session_state.username = True, u
                if remember: cookie_manager.set("mlb_pro_user", u, expires_at=datetime.now() + timedelta(days=30))
                st.rerun()
            else: st.error("Invalid Login.")
        if st.button("Continue as Guest", use_container_width=True):
            st.session_state.is_guest, st.session_state.username = True, "Guest"
            st.rerun()
    with t2:
        nu = st.text_input("New Username", key="reg_u")
        np = st.text_input("New Password", type="password", key="reg_p")
        if st.button("Create Account", use_container_width=True):
            if nu and np and nu not in users_db:
                users_db[nu] = {"pw": hash_pw(np), "weights": [30, 40, 15, 15], "fav_team": None}
                save_users(users_db)
                st.session_state.auth, st.session_state.username = True, nu
                st.rerun()
    st.stop()

# --- SIDEBAR & PREFERENCES ---
user_data = users_db.get(st.session_state.username, {"weights": [30, 40, 15, 15], "fav_team": None})
weights_list = user_data.get("weights", [30, 40, 15, 15])

with st.sidebar:
    st.write(f"User: **{st.session_state.username}**")
    
    teams = statsapi.get('teams', {'sportId': 1})['teams']
    team_list = sorted([t['name'] for t in teams])
    idx = team_list.index(user_data["fav_team"]) if user_data.get("fav_team") in team_list else 0
    fav_select = st.selectbox("Favorite Team", team_list, index=idx)
    
    w_win = st.slider("Win % Weight", 0, 100, weights_list[0])
    w_era = st.slider("Starter ERA Weight", 0, 100, weights_list[1])
    w_avg = st.slider("Lineup AVG Weight", 0, 100, weights_list[2])
    w_slg = st.slider("Lineup SLG Weight", 0, 100, weights_list[3])
    
    if st.button("💾 Save Preferences", use_container_width=True):
        users_db[st.session_state.username]["fav_team"] = fav_select
        users_db[st.session_state.username]["weights"] = [w_win, w_era, w_avg, w_slg]
        save_users(users_db)
        st.success("Settings Saved!")

    if st.button("Logout"):
        cookie_manager.delete("mlb_pro_user")
        st.session_state.auth = False; st.session_state.is_guest = False; st.rerun()

# --- DATA ENGINE ---
@st.cache_data(ttl=3600)
def get_win_pct(tid, year):
    try:
        s = statsapi.standings_data(leagueId="103,104", season=2025) # Use last full season for baseline
        for div in s.values():
            for t in div['teams']:
                if t['team_id'] == tid: return t['w']/(max(1, t['w']+t['l']))
    except: return 0.50

def analyze_game(gid, g_info, year, weights):
    try: box = statsapi.boxscore_data(gid)
    except: box = {}
    
    def process(side, tid):
        sd = box.get(side, {}); ps = sd.get('players', {})
        # Filter for position players (No Pitchers in the lineup)
        starters = [p for p in ps.values() if p.get('battingOrder', '') and p.get('battingOrder', '').endswith('00') and p['position']['code'] != '1']
        starters = sorted(starters, key=lambda x: x.get('battingOrder', '999'))
        
        is_projected = False
        if len(starters) < 9:
            is_projected = True
            try:
                roster = statsapi.get('team_roster', {'teamId': tid})['roster']
                hitters = [p for p in roster if p['position']['type'] != 'Pitcher']
                for r_player in hitters[:9]:
                    if len(starters) < 9 and r_player['person']['id'] not in [s['person']['id'] for s in starters]:
                        starters.append({'person': r_player['person'], 'battingOrder': f"{len(starters)+1}00"})
            except: pass
            
        lineup, avgs, slgs = [], [], []
        for i, p in enumerate(starters[:9]):
            p_id = p['person']['id']
            try:
                st_data = statsapi.player_stat_data(p_id, group="hitting", type="season")['stats'][0]['stats']
                if float(st_data.get('avg', '0').replace('.','0.')) == 0: raise Exception
            except:
                try: st_data = statsapi.player_stat_data(p_id, group="hitting", type="career")['stats'][0]['stats']
                except: st_data = {'avg': '.250', 'slg': '.400'}
            lineup.append({"Order": i+1, "Player": p['person']['fullName'], "AVG": st_data.get('avg', '.250'), "SLG": st_data.get('slg', '.400')})
            avgs.append(float(st_data.get('avg', '.250').replace('.','0.')))
            slgs.append(float(st_data.get('slg', '.400').replace('.','0.')))
            
        p_name = g_info.get(f'{side}_probable_pitcher', "TBD")
        era = 4.50
        if p_name != "TBD":
            try:
                p_search = statsapi.lookup_player(p_name)[0]
                try: era = float(statsapi.player_stat_data(p_search['id'], group="pitching", type="season")['stats'][0]['stats'].get('era', 4.50))
                except: era = float(statsapi.player_stat_data(p_search['id'], group="pitching", type="career")['stats'][0]['stats'].get('era', 4.50))
            except: pass
        return {"wpct": get_win_pct(tid, year), "era": era, "avg": sum(avgs)/9 if avgs else 0.25, "slg": sum(slgs)/9 if slgs else 0.4, "p": p_name, "lineup": lineup, "proj": is_projected}
    
    a, h = process('away', g_info['away_id']), process('home', g_info['home_id'])
    uw = [v/100 for v in weights]
    
    # Impact Calculation (Percentage added to Win Prob)
    impacts = {
        "Record Edge": (h['wpct'] - a['wpct']) * uw[0],
        "Pitching Edge": ((4.5/max(0.1, h['era'])) - (4.5/max(0.1, a['era']))) * uw[1],
        "Contact Edge": (h['avg'] - a['avg']) * (uw[2] * 5), # Scaled for readability
        "Power Edge": (h['slg'] - a['slg']) * (uw[3] * 3)
    }
    
    prob = 0.50 + sum(impacts.values()) + 0.02 # Home field advantage +2%
    return {"prob": max(0.01, min(0.99, prob)), "away": a, "home": h, "impacts": impacts}

# --- MAIN UI ---
dt = st.date_input("Date", datetime.now())
sched = statsapi.schedule(date=dt.strftime("%m/%d/%Y"))
fav = user_data.get("fav_team")
if fav:
    sched = sorted(sched, key=lambda x: (fav not in x['away_name'] and fav not in x['home_name']))

for g in sched:
    is_fav = fav and (fav in g['away_name'] or fav in g['home_name'])
    st.markdown(f'<div class="matchup-card" style="border-color: {"#8b5cf6" if is_fav else "#30363d"}"><img src="https://www.mlbstatic.com/team-logos/{g["away_id"]}.svg" class="team-logo"><div style="text-align:center"><b>{g["away_name"]} @ {g["home_name"]}</b><br><span class="status-tag">{g.get("status")}</span></div><img src="https://www.mlbstatic.com/team-logos/{g["home_id"]}.svg" class="team-logo"></div>', unsafe_allow_html=True)
    
    if st.button("Analyze", key=g['game_id'], use_container_width=True):
        data = analyze_game(g['game_id'], g, dt.year, [w_win, w_era, w_avg, w_slg])
        winner = g['home_name'] if data['prob'] > 0.5 else g['away_name']
        
        st.markdown(f'<div class="mobile-row"><div class="metric-box-2"><small>WIN PROBABILITY</small><br><b>{max(data["prob"], 1-data["prob"])*100:.1f}%</b> <span style="color:#4ade80">{winner}</span></div></div>', unsafe_allow_html=True)
        
        # --- NEW WHY TEAM WINS SECTION ---
        st.write(f"### 🧠 Why {winner} is Favored")
        st.markdown('<div class="analysis-box">', unsafe_allow_html=True)
        for factor, val in data['impacts'].items():
            if (data['prob'] > 0.5 and val > 0) or (data['prob'] < 0.5 and val < 0):
                st.markdown(f"✅ **{factor}:** Contributes <span class='impact-tag'>+{abs(val)*100:.1f}%</span> to victory chance.", unsafe_allow_html=True)
        st.markdown('</div>', unsafe_allow_html=True)

        c1, c2 = st.columns(2)
        for side, t_data, col in [('Away', data['away'], c1), ('Home', data['home'], c2)]:
            with col:
                st.markdown(f'<div class="pitcher-header">{t_data["p"]} (ERA: {t_data["era"]})</div>', unsafe_allow_html=True)
                st.caption("Projected Starters" if t_data["proj"] else "Live Lineup")
                st.dataframe(pd.DataFrame(t_data['lineup']), hide_index=True)
                    
