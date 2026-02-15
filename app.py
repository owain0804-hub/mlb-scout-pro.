import streamlit as st
import statsapi
import pandas as pd
from datetime import datetime
from streamlit_autorefresh import st_autorefresh

# --- PAGE CONFIG & THEME ---
st.set_page_config(page_title="MLB Scout Pro", layout="wide", page_icon="⚾")
st_autorefresh(interval=30000, key="mlb_live_timer")

# Custom CSS for UI
st.markdown("""
    <style>
    .main { background-color: #0e1117; }
    .stButton>button { width: 100%; border-radius: 5px; height: 3em; background-color: #262730; color: white; border: 1px solid #444; }
    .stButton>button:hover { border-color: #FFD700; color: #FFD700; }
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
    st.session_state["slider_era"] = 30
    st.session_state["slider_avg"] = 30
    st.session_state["slider_slg"] = 40

# --- SIDEBAR (Model Control) ---
with st.sidebar:
    st.title("⚾ Settings")
    try:
        all_teams = statsapi.get('teams', {'sportId': 1})['teams']
        team_list = sorted([t['name'] for t in all_teams])
    except: team_list = []
    fav_team = st.selectbox("Your Favorite Team", ["None"] + team_list)
    
    st.divider()
    st.header("probability Tuning")
    st.caption("Adjust how much each stat affects the win %")
    
    if st.button("Reset to Default"):
        reset_weights()
        st.rerun()

    # Probability Sliders (using session_state keys for resetting)
    w_era = st.slider("Pitcher ERA Weight", 0, 100, key="slider_era", value=30)
    w_avg = st.slider("Lineup AVG Weight", 0, 100, key="slider_avg", value=30)
    w_slg = st.slider("Lineup SLG Weight", 0, 100, key="slider_slg", value=40)

# --- CORE FUNCTIONS ---
@st.cache_data(ttl=3600)
def get_advanced_stats(player_id, group):
    try:
        data = statsapi.player_stat_data(player_id, group=group, type="season")
        return data['stats'][0]['stats'] if data.get('stats') else {}
    except: return {}

def get_detailed_data(game_id, g_info):
    try:
        box = statsapi.boxscore_data(game_id)
        def fetch_metrics(side):
            batters = box[side].get('batters', [])[:9]
            l_names, avgs, slgs = [], [], []
            for pid in batters:
                p = box[side]['players'][f"ID{pid}"]
                l_names.append(f"{p['person']['fullName']} ({p['stats']['batting'].get('hits',0)}/{p['stats']['batting'].get('atBats',0)})")
                season = get_advanced_stats(pid, "hitting")
                avgs.append(float(str(season.get('avg', '.250')).replace('.','0.')))
                slgs.append(float(str(season.get('slg', '.400')).replace('.','0.')))
            
            sp_id = box[side].get('pitchers', [None])[0]
            sp_stat = get_advanced_stats(sp_id, "pitching") if sp_id else {}
            p_era = sp_stat.get('era', '4.10')
            
            # Dynamic Score based on Tuning Sliders
            score = ( (4.1 / float(p_era)) * (w_era/100) ) + \
                    ( (sum(avgs)/9) * 10 * (w_avg/100) ) + \
                    ( (sum(slgs)/9) * 5 * (w_slg/100) )
            return {"names": l_names, "p_name": box[side]['players'].get(f"ID{sp_id}", {}).get('person', {}).get('fullName', 'TBD'), 
                    "p_era": p_era, "score": score}

        a_data = fetch_metrics('away')
        h_data = fetch_metrics('home')
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
                        st.markdown(f"""<div class="pitcher-box"><b>{d['p_name']}</b><br>ERA: {d['p_era']}</div>""", unsafe_allow_html=True)
                        st.table(pd.DataFrame(d['names'], columns=["Lineup"]))

                if st.button(" Box Score", key=f"boxscore_{gid}"):
                    b = data['box']
                    aw_r, hm_r = b['away']['teamStats']['batting'].get('runs', 0), b['home']['teamStats']['batting'].get('runs', 0)
                    df_box = pd.DataFrame({
                        "Team": [g['away_name'], g['home_name']],
                        "Runs": [aw_r, hm_r],
                        "Hits": [b['away']['teamStats']['batting'].get('hits', 0), b['home']['teamStats']['batting'].get('hits', 0)],
                        "Errors": [b['away'].get('fielding', {}).get('errors', 0), b['home'].get('fielding', {}).get('errors', 0)]
                    })
                    st.dataframe(df_box.style.apply(lambda r: ['background-color: #1d3521']*4 if (aw_r > hm_r and r.Team == g['away_name']) or (hm_r > aw_r and r.Team == g['home_name']) else ['']*4, axis=1), use_container_width=True)
        st.markdown("</div>", unsafe_allow_html=True)
                                    
