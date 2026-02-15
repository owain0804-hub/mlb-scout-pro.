import streamlit as st
import statsapi
import pandas as pd
from datetime import datetime
from streamlit_autorefresh import st_autorefresh

# --- PAGE CONFIG & THEME ---
st.set_page_config(page_title="MLB AI Scout Pro", layout="wide", page_icon="⚾")
st_autorefresh(interval=30000, key="mlb_live_timer")

# Custom CSS for a sleek Dark Mode UI
st.markdown("""
    <style>
    .main { background-color: #0e1117; }
    .stButton>button { width: 100%; border-radius: 5px; height: 3em; background-color: #262730; color: white; border: 1px solid #444; }
    .stButton>button:hover { border-color: #FFD700; color: #FFD700; }
    .matchup-card { border-radius: 15px; padding: 20px; background: #161b22; border: 1px solid #30363d; margin-bottom: 20px; }
    .logo-container { display: flex; align-items: center; justify-content: space-between; margin-bottom: 10px; }
    </style>
    """, unsafe_allow_html=True)

if "active_game_id" not in st.session_state:
    st.session_state.active_game_id = None

# --- RESET LOGIC ---
def reset_weights():
    st.session_state["slider_std"] = 42
    st.session_state["slider_era"] = 15
    st.session_state["slider_fip"] = 6
    st.session_state["slider_avg"] = 11
    st.session_state["slider_slg"] = 14
    st.session_state["slider_bp"] = 12

# --- SIDEBAR ---
with st.sidebar:
    st.title("⚾ Settings")
    st.header("⭐ Favorites")
    try:
        all_teams = statsapi.get('teams', {'sportId': 1})['teams']
        team_list = sorted([t['name'] for t in all_teams])
    except: team_list = []
    fav_team = st.selectbox("Your Team", ["None"] + team_list)
    
    st.divider()
    st.header("⚙️ Model Tuning")
    if st.button("🔄 Reset Defaults"):
        reset_weights()
        st.rerun()

    w_std = st.slider("Standings Weight", 0, 100, key="slider_std", value=42)
    w_era = st.slider("Pitcher ERA Weight", 0, 100, key="slider_era", value=15)
    w_fip = st.slider("Pitcher FIP Weight", 0, 100, key="slider_fip", value=6)
    w_avg = st.slider("Lineup AVG Weight", 0, 100, key="slider_avg", value=11)
    w_slg = st.slider("Lineup SLG Weight", 0, 100, key="slider_slg", value=14)
    w_bp = st.slider("Bullpen WAR Weight", 0, 100, key="slider_bp", value=12)

# --- CORE FUNCTIONS ---
@st.cache_data(ttl=3600)
def get_advanced_stats(player_id, group):
    try:
        data = statsapi.player_stat_data(player_id, group=group, type="season")
        return data['stats'][0]['stats'] if data.get('stats') else {}
    except: return {}

@st.cache_data(ttl=3600)
def get_bullpen_war(team_id):
    try:
        roster = statsapi.get('team_roster', {'teamId': team_id})['roster']
        relievers = [p['person']['id'] for p in roster if p['position']['code'] == '1']
        total_war = 0.0
        for pid in relievers[:5]:
            stats = get_advanced_stats(pid, "pitching")
            total_war += float(stats.get('war', 0.1))
        return total_war / 2 
    except: return 0.55

@st.cache_data(ttl=300)
def get_wpct(team_id):
    try:
        standings = statsapi.standings_data(leagueId="103,104")
        for div in standings.values():
            for t in div['teams']:
                if t['team_id'] == team_id:
                    return int(t.get('w',1))/(int(t.get('w',1))+int(t.get('l',1)))
        return 0.500
    except: return 0.500

def get_detailed_data(game_id, g_info):
    try:
        box = statsapi.boxscore_data(game_id)
        def fetch_metrics(side, tid):
            batters = box[side].get('batters', [])[:9]
            l_names, avgs, slgs = [], [], []
            for pid in batters:
                p = box[side]['players'][f"ID{pid}"]
                l_names.append(f"{p['person']['fullName']} ({p['stats']['batting'].get('hits',0)}/{p['stats']['batting'].get('atBats',0)})")
                season = get_advanced_stats(pid, "hitting")
                avgs.append(float(season.get('avg', '.250').replace('.','0.')))
                slgs.append(float(season.get('slg', '.400').replace('.','0.')))
            
            sp_id = box[side].get('pitchers', [None])[0]
            sp_stat = get_advanced_stats(sp_id, "pitching") if sp_id else {}
            p_era, p_fip = float(sp_stat.get('era', 4.10)), float(sp_stat.get('fip', 4.10))
            wpct = get_wpct(tid)
            bp_war = get_bullpen_war(tid)
            
            adj = (wpct * (w_std/100)) + (sum(avgs)/9 * 4 * (w_avg/100)) + (sum(slgs)/9 * 2.5 * (w_slg/100)) + \
                  ((4.1/p_era) * (w_era/100)) + ((4.1/p_fip) * (w_fip/100)) + (bp_war * (w_bp/100))
            
            return {"names": l_names, "p_name": g_info.get(f'{side}_probable_pitcher', "TBD"), "wpct": adj, "logo": f"https://www.mlbstatic.com/team-logos/{tid}.svg"}

        a_data = fetch_metrics('away', g_info['away_id'])
        h_data = fetch_metrics('home', g_info['home_id'])
        prob_h = (h_data['wpct'] - (a_data['wpct'] * h_data['wpct'])) / (a_data['wpct'] + h_data['wpct'] - (2 * a_data['wpct'] * h_data['wpct'])) + 0.04
        return {"a": a_data, "h": h_data, "prob_h": max(0.01, min(0.99, prob_h)), "box": box}
    except: return None

# --- MAIN UI ---
st.title("⚾ MLB Intelligence Pro")
c_date, c_spacer = st.columns([2, 5])
with c_date:
    u_date = st.date_input("Select Date", datetime.now())
    formatted_date = u_date.strftime("%m/%d/%Y")

games = statsapi.schedule(date=formatted_date)
sorted_games = sorted(games, key=lambda x: (x['away_name'] != fav_team and x['home_name'] != fav_team))

for g in sorted_games:
    gid = g['game_id']
    is_fav = (g['away_name'] == fav_team or g['home_name'] == fav_team)
    away_logo = f"https://www.mlbstatic.com/team-logos/{g['away_id']}.svg"
    home_logo = f"https://www.mlbstatic.com/team-logos/{g['home_id']}.svg"
    
    with st.container():
        st.markdown(f"""<div class="matchup-card" style="border-left: 5px solid {'#FFD700' if is_fav else '#30363d'}">""", unsafe_allow_html=True)
        cols = st.columns([1, 3, 1])
        with cols[0]: st.image(away_logo, width=70)
        with cols[1]: 
            st.subheader(f"{g['away_name']} @ {g['home_name']}")
            st.caption(f"🏟️ {g.get('venue_name', 'TBD')} | 🕒 {g.get('game_datetime', 'TBD')}")
        with cols[2]: 
            if st.button("Analyze", key=f"btn_{gid}"): st.session_state.active_game_id = gid
        
        if st.session_state.active_game_id == gid:
            data = get_detailed_data(gid, g)
            if data:
                p_h, p_a = data['prob_h'], 1 - data['prob_h']
                st.write("---")
                
                # Logos + Win Probability Bar
                prob_cols = st.columns([1, 8, 1])
                prob_cols[0].image(away_logo, width=50)
                prob_cols[1].progress(p_h, text=f"{g['home_name']} {p_h*100:.1f}% Win Probability")
                prob_cols[2].image(home_logo, width=50)
                
                tab1, tab2 = st.tabs(["📋 Scouting Report", "📊 Box Score"])
                with tab1:
                    col_a, col_h = st.columns(2)
                    with col_a:
                        st.markdown(f"#### <img src='{away_logo}' width='30'> {g['away_name']}", unsafe_allow_html=True)
                        st.table(pd.DataFrame(data['a']['names'], columns=["Starters"]))
                    with col_h:
                        st.markdown(f"#### <img src='{home_logo}' width='30'> {g['home_name']}", unsafe_allow_html=True)
                        st.table(pd.DataFrame(data['h']['names'], columns=["Starters"]))
                with tab2:
                    b = data['box']
                    box_df = pd.DataFrame({
                        "Team": [g['away_name'], g['home_name']],
                        "Runs": [b['away']['teamStats']['batting'].get('runs', 0), b['home']['teamStats']['batting'].get('runs', 0)],
                        "Hits": [b['away']['teamStats']['batting'].get('hits', 0), b['home']['teamStats']['batting'].get('hits', 0)],
                        "Errors": [b['away']['teamStats']['fielding'].get('errors', 0), b['home']['teamStats']['fielding'].get('errors', 0)]
                    })
                    st.table(box_df)
        st.markdown("</div>", unsafe_allow_html=True)
