import streamlit as st
import statsapi
import pandas as pd
import json
import os
import hashlib
import time
import secrets
from datetime import datetime
from streamlit_autorefresh import st_autorefresh
import extra_streamlit_components as stx

# --- MOBILE OPTIMIZED STYLING ---
def apply_mobile_pro_styles():
    st.markdown("""
        <style>
        /* Force side-by-side on mobile for key metrics */
        .mobile-row {
            display: flex;
            justify-content: space-between;
            align-items: center;
            margin-bottom: 15px;
            gap: 10px;
        }
        .metric-box {
            background: #1e293b;
            border: 1px solid #3b82f6;
            border-radius: 8px;
            padding: 12px;
            flex: 1;
            text-align: center;
        }
        .matchup-card {
            background: #0d1117;
            border: 1px solid #30363d;
            border-radius: 12px;
            padding: 15px;
            margin-bottom: 15px;
        }
        /* Pitcher Info Card */
        .pitcher-card {
            background: #161b22;
            border-left: 4px solid #3fb950;
            padding: 10px;
            margin-bottom: 10px;
            border-radius: 4px;
        }
        .pitcher-name { font-weight: bold; color: #e6edf3; }
        .pitcher-stat { font-size: 0.9em; color: #8b949e; }
        
        /* Make tables scrollable on small screens */
        .stDataFrame, .stTable { overflow-x: auto; }
        </style>
    """, unsafe_allow_html=True)

# --- USER MANAGEMENT & PERSISTENCE ---
USERS_FILE = "users_db.json"

def get_manager():
    return stx.CookieManager()

def load_users():
    if not os.path.exists(USERS_FILE):
        return {}
    with open(USERS_FILE, 'r') as f:
        return json.load(f)

def save_users(users):
    with open(USERS_FILE, 'w') as f:
        json.dump(users, f)

def hash_password(password):
    return hashlib.sha256(password.encode()).hexdigest()

# --- PAGE CONFIG ---
st.set_page_config(page_title="MLB AI Scout Pro", layout="wide", page_icon="⚾")
apply_mobile_pro_styles()
st_autorefresh(interval=60000, key="mlb_live_timer") # Refresh every 60s
cookie_manager = get_manager()

# --- AUTHENTICATION LOGIC ---
if "authenticated" not in st.session_state:
    st.session_state.authenticated = False
    st.session_state.username = None

# Check Cookies for Login
users_db = load_users()
cookie_user = cookie_manager.get(cookie="mlb_user")

if not st.session_state.authenticated and cookie_user:
    if cookie_user in users_db:
        st.session_state.authenticated = True
        st.session_state.username = cookie_user
        # Load user settings
        st.session_state.fav_team = users_db[cookie_user].get("fav_team", "None")

# --- LOGIN / REGISTER SCREEN ---
if not st.session_state.authenticated:
    st.markdown("<h1 style='text-align:center;'>⚾ MLB Scout Pro</h1>", unsafe_allow_html=True)
    tab1, tab2 = st.tabs(["Log In", "Register"])
    
    with tab1:
        l_user = st.text_input("Username", key="l_u")
        l_pass = st.text_input("Password", type="password", key="l_p")
        if st.button("Log In"):
            if l_user in users_db and users_db[l_user]['password'] == hash_password(l_pass):
                cookie_manager.set("mlb_user", l_user, expires_at=datetime(2026, 1, 1))
                st.session_state.authenticated = True
                st.session_state.username = l_user
                st.session_state.fav_team = users_db[l_user].get("fav_team", "None")
                st.rerun()
            else:
                st.error("Invalid username or password")

    with tab2:
        r_user = st.text_input("Choose Username", key="r_u")
        r_pass = st.text_input("Choose Password", type="password", key="r_p")
        if st.button("Create Account"):
            if r_user in users_db:
                st.error("User already exists!")
            elif r_user and r_pass:
                users_db[r_user] = {
                    "password": hash_password(r_pass),
                    "fav_team": "None"
                }
                save_users(users_db)
                st.success("Account created! Please log in.")
    st.stop()

# --- SIDEBAR (User Settings) ---
with st.sidebar:
    st.title(f"👤 {st.session_state.username}")
    
    # Favorite Team Selector
    @st.cache_data(ttl=86400)
    def get_mlb_teams():
        try: return sorted([t['name'] for t in statsapi.get('teams', {'sportId': 1})['teams']])
        except: return []

    all_teams = get_mlb_teams()
    current_fav = st.session_state.get("fav_team", "None")
    
    # Handle index error safely
    try:
        idx = (["None"] + all_teams).index(current_fav)
    except ValueError:
        idx = 0
        
    new_fav = st.selectbox("Your Favorite Team", ["None"] + all_teams, index=idx)
    
    if new_fav != current_fav:
        users_db[st.session_state.username]['fav_team'] = new_fav
        save_users(users_db)
        st.session_state.fav_team = new_fav
        st.toast(f"Favorite team saved: {new_fav}")

    if st.button("Log Out"):
        cookie_manager.delete("mlb_user")
        st.session_state.authenticated = False
        st.session_state.username = None
        st.rerun()

# --- CORE LOGIC ---
@st.cache_data(ttl=3600)
def get_team_wpct(tid, year):
    try:
        standings = statsapi.standings_data(leagueId="103,104", season=year)
        for div in standings.values():
            for t in div.get('teams', []):
                if t['team_id'] == tid: return (int(t['w'])/max(1, int(t['w'])+int(t['l'])))
    except: return 0.50

def get_detailed_data(gid, g_info, year):
    try:
        box = statsapi.boxscore_data(gid)
        
        def fetch_side(side, tid):
            sd = box.get(side, {})
            ps = sd.get('players', {})
            
            # 1. Get Lineup
            starters = sorted([{'id': p['person']['id'], 'name': p['person']['fullName'], 'order': int(p['battingOrder'])} 
                               for p in ps.values() if p.get('battingOrder') and p['battingOrder'].endswith('00')], key=lambda x: x['order'])
            
            lineup, avgs, slgs = [], [], []
            for p in starters:
                try:
                    p_st = statsapi.player_stat_data(p['id'], group="hitting", type="season", season=year)['stats'][0]['stats']
                    # Format to 3 decimals without leading zero for baseball style
                    avg_str = f"{p_st.get('avg', '.000')}"
                    slg_str = f"{p_st.get('slg', '.000')}"
                    lineup.append({"#": f"{p['order']//100}", "Player": p['name'], "AVG": avg_str, "SLG": slg_str})
                    
                    avgs.append(float(avg_str.replace('.','0.')) if avg_str.startswith('.') else float(avg_str))
                    slgs.append(float(slg_str.replace('.','0.')) if slg_str.startswith('.') else float(slg_str))
                except:
                    lineup.append({"#": f"{p['order']//100}", "Player": p['name'], "AVG": ".250", "SLG": ".400"})
                    avgs.append(0.250); slgs.append(0.400)
            
            # 2. Get Pitcher
            p_name, era = "TBD", 4.50
            if sd.get('pitchers'):
                try: 
                    pid = sd['pitchers'][0]
                    p_name = ps.get(f"ID{pid}", {}).get('person', {}).get('fullName', "TBD")
                    era_val = statsapi.player_stat_data(pid, group="pitching", type="season", season=year)['stats'][0]['stats'].get('era', '4.50')
                    era = float(era_val) if era_val != '-.--' else 4.50
                except: pass
            
            # 3. Aggregates
            wpct = get_team_wpct(tid, year)
            team_avg = sum(avgs)/max(1,len(avgs))
            team_slg = sum(slgs)/max(1,len(slgs))
            
            return {
                "wpct": wpct, "era": era, "team_avg": team_avg, "team_slg": team_slg,
                "lineup": lineup, "p_name": p_name
            }
        
        a_d, h_d = fetch_side('away', g_info['away_id']), fetch_side('home', g_info['home_id'])
        
        # --- PROBABILITY ALGORITHM ---
        # Factors: Win% (30%), ERA (30%), AVG (20%), SLG (20%)
        # Normalize ERA (Lower is better, so we invert)
        era_factor = (a_d['era'] - h_d['era']) * 0.05 # If home ERA is lower, this is positive
        std_factor = (h_d['wpct'] - a_d['wpct']) * 0.5
        avg_factor = (h_d['team_avg'] - a_d['team_avg']) * 2.0
        slg_factor = (h_d['team_slg'] - a_d['team_slg']) * 1.5
        
        raw_prob = 0.50 + std_factor + era_factor + avg_factor + slg_factor + 0.03 # 3% Home Field
        
        return {"prob_h": max(0.01, min(0.99, raw_prob)), "box": box, "away": a_d, "home": h_d}
    except Exception as e:
        return None

# --- UI MAIN ---
u_date = st.date_input("Gameday", datetime.now())
sched = statsapi.schedule(date=u_date.strftime("%m/%d/%Y"))

# Filter Favorite Team to Top
if st.session_state.fav_team != "None":
    sched.sort(key=lambda x: 0 if (x['home_name'] == st.session_state.fav_team or x['away_name'] == st.session_state.fav_team) else 1)

if not sched:
    st.info("No games scheduled.")
else:
    for g in {g['game_id']: g for g in sched}.values():
        is_fav = (g['home_name'] == st.session_state.fav_team or g['away_name'] == st.session_state.fav_team)
        card_style = "border: 2px solid #eab308;" if is_fav else "border: 1px solid #30363d;"
        
        st.markdown(f"""
            <div class="matchup-card" style="{card_style}">
                <div style="display: flex; justify-content: space-between; align-items: center;">
                    <img src="https://www.mlbstatic.com/team-logos/{g['away_id']}.svg" width="40">
                    <span style="font-weight: bold; font-size: 1.1em;">{g['away_name']} @ {g['home_name']}</span>
                    <img src="https://www.mlbstatic.com/team-logos/{g['home_id']}.svg" width="40">
                </div>
            </div>
        """, unsafe_allow_html=True)
        
        if st.button("Analyze", key=f"btn_{g['game_id']}", use_container_width=True):
            st.session_state.active_game_id = g['game_id']

        if st.session_state.get("active_game_id") == g['game_id']:
            data = get_detailed_data(g['game_id'], g, u_date.year)
            if data:
                h, a = data['home'], data['away']
                res = g['home_name'] if data['prob_h'] > 0.5 else g['away_name']
                conf = (data['prob_h'] if data['prob_h'] > 0.5 else 1-data['prob_h']) * 100
                
                # --- BOX SCORE (Always Top) ---
                st.write("### 🏟️ Live Box Score")
                away_b = data['box'].get('away', {}).get('teamStats', {}).get('batting', {})
                home_b = data['box'].get('home', {}).get('teamStats', {}).get('batting', {})
                st.table(pd.DataFrame({
                    "Team": ["Away", "Home"],
                    "R": [g.get('away_score', 0), g.get('home_score', 0)],
                    "H": [away_b.get('hits', 0), home_b.get('hits', 0)],
                    "E": [away_b.get('errors', 0), home_b.get('errors', 0)]
                }))

                # --- SIDE-BY-SIDE PROBABILITY & EDGE ---
                st.markdown(f"""
                    <div class="mobile-row">
                        <div class="metric-box">
                            <small>PROBABILITY</small><br>
                            <b style="font-size: 1.2em; color: #60a5fa;">{conf:.1f}%</b>
                        </div>
                        <div class="metric-box">
                            <small>PROJECTED EDGE</small><br>
                            <b style="font-size: 1.2em; color: #4ade80;">{res}</b>
                        </div>
                    </div>
                """, unsafe_allow_html=True)

                # --- STATS BREAKDOWN (Requested Factors) ---
                with st.expander("📊 Factor Analysis"):
                    st.table(pd.DataFrame([
                        {"Factor": "Standings (Win%)", "Home": f"{h['wpct']:.3f}", "Away": f"{a['wpct']:.3f}"},
                        {"Factor": "Pitcher ERA", "Home": f"{h['era']:.2f}", "Away": f"{a['era']:.2f}"},
                        {"Factor": "Lineup AVG", "Home": f"{h['team_avg']:.3f}", "Away": f"{a['team_avg']:.3f}"},
                        {"Factor": "Lineup SLG", "Home": f"{h['team_slg']:.3f}", "Away": f"{a['team_slg']:.3f}"}
                    ]))
                
                # --- PITCHERS & LINEUPS ---
                c1, c2 = st.columns(2)
                
                with c1:
                    st.markdown(f"""
                        <div class="pitcher-card">
                            <div class="pitcher-name">{a['p_name']}</div>
                            <div class="pitcher-stat">ERA: {a['era']:.2f}</div>
                        </div>
                    """, unsafe_allow_html=True)
                    st.write(f"**{g['away_name']} Lineup**")
                    st.dataframe(pd.DataFrame(a['lineup']), hide_index=True, use_container_width=True)

                with c2:
                    st.markdown(f"""
                        <div class="pitcher-card">
                            <div class="pitcher-name">{h['p_name']}</div>
                            <div class="pitcher-stat">ERA: {h['era']:.2f}</div>
                        </div>
                    """, unsafe_allow_html=True)
                    st.write(f"**{g['home_name']} Lineup**")
                    st.dataframe(pd.DataFrame(h['lineup']), hide_index=True, use_container_width=True)
        
