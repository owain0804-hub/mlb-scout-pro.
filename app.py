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
    .stButton>button:hover { border-color: #FFD700; color: #FFD700; }
    .matchup-card { border-radius: 15px; padding: 20px; background: #161b22; border: 1px solid #30363d; margin-bottom: 20px; }
    .winner-box { background: #1b2838; border: 2px solid #4CAF50; border-radius: 10px; padding: 15px; margin-bottom: 20px; color: #e6edf3; }
    .pitcher-box { background: #0d1117; border: 1px solid #30363d; border-radius: 8px; padding: 8px; text-align: center; margin-bottom: 5px; }
    </style>
    """, unsafe_allow_html=True)

if "active_game_id" not in st.session_state:
    st.session_state.active_game_id = None

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
        def fetch_metrics(side, tid):
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
            
            # Simple weighting for win probability
            adj = (0.5 * 0.4) + (sum(avgs)/9 * 0.1) + (sum(slgs)/9 * 0.1) + ((4.1/float(p_era)) * 0.4)
            return {"names": l_names, "p_name": box[side]['players'].get(f"ID{sp_id}", {}).get('person', {}).get('fullName', 'TBD'), 
                    "p_era": p_era, "wpct": adj, "logo": f"https://www.mlbstatic.com/team-logos/{tid}.svg"}

        a_data = fetch_metrics('away', g_info['away_id'])
        h_data = fetch_metrics('home', g_info['home_id'])
        prob_h = (h_data['wpct'] / (a_data['wpct'] + h_data['wpct'])) + 0.04
        return {"a": a_data, "h": h_data, "prob_h": max(0.01, min(0.99, prob_h)), "box": box}
    except: return None

# --- MAIN UI ---
st.title("⚾ MLB Intelligence Pro")
u_date = st.date_input("Select Date", datetime.now())
games = statsapi.schedule(date=u_date.strftime("%m/%d/%Y"))

for g in games:
    gid = g['game_id']
    with st.container():
        st.markdown(f"""<div class="matchup-card">""", unsafe_allow_html=True)
        cols = st.columns([1, 3, 1])
        with cols[0]: st.image(f"https://www.mlbstatic.com/team-logos/{g['away_id']}.svg", width=70)
        with cols[1]: 
            st.subheader(f"{g['away_name']} @ {g['home_name']}")
            st.caption(f"Status: {g.get('status', 'Scheduled')}")
        with cols[2]: 
            if st.button("Analyze", key=f"btn_{gid}"): st.session_state.active_game_id = gid
        
        if st.session_state.active_game_id == gid:
            data = get_detailed_data(gid, g)
            if data:
                p_h, p_a = data['prob_h'], 1 - data['prob_h']
                winner = g['home_name'] if p_h > p_a else g['away_name']
                
                st.markdown(f"<div class='winner-box'>🏅 <b>Projected Winner: {winner}</b></div>", unsafe_allow_html=True)
                st.progress(p_h, text=f"Win Probability: {p_h*100:.1f}%")

                # Lineup & Pitcher Layout
                col_a, col_h = st.columns(2)
                for side, col, d in [('Away', col_a, data['a']), ('Home', col_h, data['h'])]:
                    with col:
                        st.markdown(f"""<div class="pitcher-box"><b>{d['p_name']}</b><br>ERA: {d['p_era']}</div>""", unsafe_allow_html=True)
                        st.table(pd.DataFrame(d['names'], columns=[f"{side} Lineup"]))

                # HIGHLIGHTED BOX SCORE
                if st.button("📊 Show Box Score", key=f"box_{gid}"):
                    b = data['box']
                    aw_r = b['away']['teamStats']['batting'].get('runs', 0)
                    hm_r = b['home']['teamStats']['batting'].get('runs', 0)
                    
                    df_box = pd.DataFrame({
                        "Team": [g['away_name'], g['home_name']],
                        "Runs": [aw_r, hm_r],
                        "Hits": [b['away']['teamStats']['batting'].get('hits', 0), b['home']['teamStats']['batting'].get('hits', 0)],
                        "Errors": [b['away'].get('fielding', {}).get('errors', 0), b['home'].get('fielding', {}).get('errors', 0)]
                    })

                    def highlight_winner(row):
                        if (aw_r > hm_r and row.Team == g['away_name']) or (hm_r > aw_r and row.Team == g['home_name']):
                            return ['background-color: #1d3521'] * len(row)
                        return [''] * len(row)

                    st.dataframe(df_box.style.apply(highlight_winner, axis=1), use_container_width=True)
        st.markdown("</div>", unsafe_allow_html=True)
        
