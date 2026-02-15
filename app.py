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
    .stat-box { background: #0d1117; border-radius: 10px; padding: 15px; border-left: 5px solid #58a6ff; }
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

# --- CORE LOGIC (With Error Handling) ---
@st.cache_data(ttl=3600)
def get_player_streak(player_id):
    try:
        s = statsapi.player_stat_data(player_id, group="hitting", type="season")
        r = statsapi.player_stat_data(player_id, group="hitting", type="last7")
        if not s.get('stats') or not r.get('stats'): return ""
        s_avg = float(s['stats'][0]['stats'].get('avg', '.250').replace('.','0.'))
        r_avg = float(r['stats'][0]['stats'].get('avg', '.250').replace('.','0.'))
        return "🔥" if r_avg > s_avg + 0.06 else ("❄️" if r_avg < s_avg - 0.06 else "")
    except: return ""

def get_detailed_data(game_id, g_info):
    try:
        box = statsapi.boxscore_data(game_id)
        def fetch_metrics(side, tid):
            # Lineup processing
            batters = box[side].get('batters', [])[:9]
            l_names, avgs, slgs = [], [], []
            for pid in batters:
                p = box[side]['players'][f"ID{pid}"]
                streak = get_player_streak(pid)
                l_names.append(f"{streak} {p['person']['fullName']}")
                # Fallback for Spring Training missing stats
                try:
                    p_stat = statsapi.player_stat_data(pid, group="hitting", type="season")['stats'][0]['stats']
                    avgs.append(float(p_stat.get('avg', '.250').replace('.','0.')))
                    slgs.append(float(p_stat.get('slg', '.400').replace('.','0.')))
                except: avgs.append(0.250); slgs.append(0.400)
            
            # Pitching processing
            sp_id = box[side].get('pitchers', [None])[0]
            try:
                sp_stat = statsapi.player_stat_data(sp_id, group="pitching", type="season")['stats'][0]['stats']
            except: sp_stat = {'era': '4.10', 'fip': '4.10'}
            
            # Bullpen & Standing
            standings = statsapi.standings_data(leagueId="103,104")
            wpct = 0.500
            for div in standings.values():
                for t in div['teams']:
                    if t['team_id'] == tid: wpct = int(t.get('w',1))/(int(t.get('w',1))+int(t.get('l',1)))
            
            adj = (wpct * (w_std/100)) + (sum(avgs)/9 * 4 * (w_avg/100)) + (sum(slgs)/9 * 2.5 * (w_slg/100)) + \
                  ((4.1/float(sp_stat.get('era',4.1))) * (w_era/100))
            
            return {"names": l_names, "p_name": g_info.get(f'{side}_probable_pitcher', "TBD"), "wpct": adj, "logo": f"https://www.mlbstatic.com/team-logos/{tid}.svg"}

        a_data = fetch_metrics('away', g_info['away_id'])
        h_data = fetch_metrics('home', g_info['home_id'])
        prob_h = (h_data['wpct'] - (a_data['wpct'] * h_data['wpct'])) / (a_data['wpct'] + h_data['wpct'] - (2 * a_data['wpct'] * h_data['wpct'])) + 0.04
        return {"a": a_data, "h": h_data, "prob_h": max(0.01, min(0.99, prob_h)), "box": box}
    except: return None

# --- MAIN UI ---
st.title("⚾ MLB Intelligence Pro")
c1, c2 = st.columns([2, 5])
with c1:
    u_date = st.date_input("Select Date", datetime.now())
    formatted_date = u_date.strftime("%m/%d/%Y")

games = statsapi.schedule(date=formatted_date)
sorted_games = sorted(games, key=lambda x: (x['away_name'] != fav_team and x['home_name'] != fav_team))

for g in sorted_games:
    gid = g['game_id']
    is_fav = (g['away_name'] == fav_team or g['home_name'] == fav_team)
    
    with st.container():
        st.markdown(f"""<div class="matchup-card" style="border-left: 5px solid {'#FFD700' if is_fav else '#30363d'}">""", unsafe_allow_html=True)
        cols = st.columns([1, 3, 1])
        with cols[0]: st.image(f"https://www.mlbstatic.com/team-logos/{g['away_id']}.svg", width=60)
        with cols[1]: 
            st.subheader(f"{g['away_name']} @ {g['home_name']}")
            st.caption(f"Venue: {g.get('venue_name', 'TBD')} | Status: {g.get('status', 'Scheduled')}")
        with cols[2]: 
            if st.button("Analyze", key=f"btn_{gid}"): st.session_state.active_game_id = gid
        
        if st.session_state.active_game_id == gid:
            data = get_detailed_data(gid, g)
            if data:
                # Predictive Win Probability Bar
                p_h, p_a = data['prob_h'], 1 - data['prob_h']
                st.write("---")
                st.write("### 🎯 Win Probability")
                st.progress(p_h, text=f"{g['home_name']} {p_h*100:.1f}% vs {g['away_name']} {p_a*100:.1f}%")
                
                tab1, tab2 = st.tabs(["📋 Scouting Report", "📊 Box Score"])
                with tab1:
                    st.info(f"**AI Insight:** Today's matchup favors the **{g['home_name'] if p_h > p_a else g['away_name']}** based on {w_std}% weighted standings and pitcher ERA efficiency.")
                    col_a, col_h = st.columns(2)
                    col_a.write(f"**{g['away_name']} Lineup**")
                    col_a.table(pd.DataFrame(data['a']['names'], columns=["Starters"]))
                    col_h.write(f"**{g['home_name']} Lineup**")
                    col_h.table(pd.DataFrame(data['h']['names'], columns=["Starters"]))
                with tab2:
                    b = data['box']
                    box_df = pd.DataFrame({
                        "Team": [g['away_name'], g['home_name']],
                        "Runs": [b['away']['teamStats']['batting'].get('runs', 0), b['home']['teamStats']['batting'].get('runs', 0)],
                        "Hits": [b['away']['teamStats']['batting'].get('hits', 0), b['home']['teamStats']['batting'].get('hits', 0)]
                    })
                    st.dataframe(box_df, use_container_width=True, hide_index=True)
        st.markdown("</div>", unsafe_allow_html=True)
                    
