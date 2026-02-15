import streamlit as st
import statsapi
import pandas as pd
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
    .winner-box { background: #1b2838; border: 2px solid #4CAF50; border-radius: 10px; padding: 15px; margin-bottom: 20px; color: #e6edf3; }
    .pitcher-box { background: #0d1117; border: 1px solid #30363d; border-radius: 8px; padding: 8px; text-align: center; margin-bottom: 5px; }
    .fav-tag { color: #FFD700; font-weight: bold; font-size: 0.8em; border: 1px solid #FFD700; border-radius: 5px; padding: 2px 5px; }
    </style>
    """, unsafe_allow_html=True)

if "active_game_id" not in st.session_state:
    st.session_state.active_game_id = None

# --- RESET LOGIC ---
def reset_weights():
    st.session_state["w_std"] = 40
    st.session_state["w_era"] = 15
    st.session_state["w_avg"] = 20
    st.session_state["w_slg"] = 25

# --- SIDEBAR ---
with st.sidebar:
    st.title("⚾ Settings")
    try:
        all_teams = statsapi.get('teams', {'sportId': 1})['teams']
        team_list = sorted([t['name'] for t in all_teams])
    except: team_list = []
    fav_team = st.selectbox("Your Favorite Team", ["None"] + team_list)
    
    st.divider()
    st.header("⚙️ Model Tuning")
    if st.button("🔄 Reset to Default"):
        reset_weights()
        st.rerun()

    w_std = st.slider("Standings Weight %", 0, 100, key="w_std", value=40)
    w_era = st.slider("Starter ERA Weight %", 0, 100, key="w_era", value=15)
    w_avg = st.slider("Lineup AVG Weight %", 0, 100, key="w_avg", value=20)
    w_slg = st.slider("Lineup SLG Weight %", 0, 100, key="w_slg", value=25)

# --- CORE FUNCTIONS ---
@st.cache_data(ttl=3600)
def get_team_wpct(team_id):
    try:
        standings = statsapi.standings_data(leagueId="103,104")
        for div in standings.values():
            for t in div['teams']:
                if t['team_id'] == team_id:
                    return int(t.get('w', 1)) / (max(1, int(t.get('w', 1)) + int(t.get('l', 1))))
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
                s_data = statsapi.player_stat_data(pid, group="hitting", type="season")
                s = s_data['stats'][0]['stats'] if s_data.get('stats') else {}
                l_names.append(f"{p['person']['fullName']} ({p['stats']['batting'].get('hits',0)}/{p['stats']['batting'].get('atBats',0)})")
                avgs.append(float(str(s.get('avg', '.250')).replace('.','0.')))
                slgs.append(float(str(s.get('slg', '.400')).replace('.','0.')))
            
            sp_id = box[side].get('pitchers', [None])[0]
            sp_stat = statsapi.player_stat_data(sp_id, group="pitching", type="season") if sp_id else {}
            p_era = float(sp_stat['stats'][0]['stats'].get('era', 4.10)) if sp_stat.get('stats') else 4.10
            
            wpct = get_team_wpct(tid)
            # Logic: Standings 40%, Starter ERA 15%, Lineup AVG 20%, SLG 25%
            score = (wpct * (w_std/100)) + ((4.1/p_era) * (w_era/100)) + \
                    (sum(avgs)/9 * 4 * (w_avg/100)) + (sum(slgs)/9 * 2.5 * (w_slg/100))
            
            return {"names": l_names, "p_name": box[side]['players'].get(f"ID{sp_id}", {}).get('person', {}).get('fullName', 'TBD'), 
                    "p_era": p_era, "score": score}

        a_data = fetch_metrics('away', g_info['away_id'])
        h_data = fetch_metrics('home', g_info['home_id'])
        prob_h = (h_data['score'] / (a_data['score'] + h_data['score'])) + 0.04
        return {"a": a_data, "h": h_data, "prob_h": max(0.01, min(0.99, prob_h)), "box": box}
    except: return None

# --- MAIN UI ---
st.title("⚾ MLB Intelligence Pro")
u_date = st.date_input("Select Date", datetime.now())
games = statsapi.schedule(date=u_date.strftime("%m/%d/%Y"))
sorted_games = sorted(games, key=lambda x: (x['away_name'] != fav_team and x['home_name'] != fav_team))

for g in sorted_games:
    gid = g['game_id']
    is_fav = (g['away_name'] == fav_team or g['home_name'] == fav_team)
    with st.container():
        st.markdown(f"""<div class="matchup-card" style="border-left: 5px solid {'#FFD700' if is_fav else '#30363d'}">""", unsafe_allow_html=True)
        cols = st.columns([1, 3, 1])
        with cols[0]: st.image(f"https://www.mlbstatic.com/team-logos/{g['away_id']}.svg", width=60)
        with cols[1]: 
            fav_html = '<span class="fav-tag">⭐ FAVORITE</span>' if is_fav else ''
            st.markdown(f"### {g['away_name']} @ {g['home_name']} {fav_html}", unsafe_allow_html=True)
            st.caption(f"Status: {g['status']}")
        with cols[2]: 
            if st.button("Analyze", key=f"btn_{gid}"): st.session_state.active_game_id = gid
        
        if st.session_state.active_game_id == gid:
            data = get_detailed_data(gid, g)
            if data:
                p_h, p_a = data['prob_h'], 1 - data['prob_h']
                winner = g['home_name'] if p_h > p_a else g['away_name']
                st.markdown(f"<div class='winner-box'>🏅 <b>Projected Winner: {winner}</b></div>", unsafe_allow_html=True)
                st.progress(p_h, text=f"{g['home_name']} {p_h*100:.1f}% | {g['away_name']} {p_a*100:.1f}%")

                col_a, col_h = st.columns(2)
                for side, col, d, t_name in [('Away', col_a, data['a'], g['away_name']), ('Home', col_h, data['h'], g['home_name'])]:
                    with col:
                        st.markdown(f"**{t_name} Starter**")
                        st.markdown(f"""<div class="pitcher-box"><b>{d['p_name']}</b><br>Season ERA: {d['p_era']}</div>""", unsafe_allow_html=True)
                        st.table(pd.DataFrame(d['names'], columns=["Lineup"]))

                # Boxscore only for Finished Games
                if g['status'] in ["Final", "Game Over", "Completed Early"]:
                    if st.button("📊 View Final Box Score", key=f"box_{gid}"):
                        b = data['box']
                        aw_r, hm_r = b['away']['teamStats']['batting'].get('runs', 0), b['home']['teamStats']['batting'].get('runs', 0)
                        df_box = pd.DataFrame({
                            "Team": [g['away_name'], g['home_name']], "Runs": [aw_r, hm_r],
                            "Hits": [b['away']['teamStats']['batting'].get('hits', 0), b['home']['teamStats']['batting'].get('hits', 0)],
                            "Errors": [b['away'].get('fielding', {}).get('errors', 0), b['home'].get('fielding', {}).get('errors', 0)]
                        })
                        st.dataframe(df_box.style.apply(lambda r: ['background-color: #1d3521']*4 if (aw_r > hm_r and r.Team == g['away_name']) or (hm_r > aw_r and r.Team == g['home_name']) else ['']*4, axis=1), use_container_width=True)
        st.markdown("</div>", unsafe_allow_html=True)
                        
