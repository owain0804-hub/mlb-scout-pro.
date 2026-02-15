import streamlit as st
import statsapi
import pandas as pd
from datetime import datetime
from streamlit_autorefresh import st_autorefresh

st.set_page_config(page_title="MLB AI Scout Pro", layout="wide", page_icon="⚾")
st_autorefresh(interval=30000, key="mlb_live_timer")

# --- RESET LOGIC ---
def reset_weights():
    st.session_state["slider_std"] = 42
    st.session_state["slider_era"] = 15
    st.session_state["slider_fip"] = 6
    st.session_state["slider_avg"] = 11
    st.session_state["slider_slg"] = 14
    st.session_state["slider_bp"] = 12

# --- SIDEBAR TUNING ---
st.sidebar.header("⚙️ Model Tuning")
if st.sidebar.button("🔄 Reset to Default"):
    reset_weights()
    st.rerun()

w_std = st.sidebar.slider("Standings Weight %", 0, 100, key="slider_std", value=42)
w_era = st.sidebar.slider("Pitcher ERA Weight %", 0, 100, key="slider_era", value=15)
w_fip = st.sidebar.slider("Pitcher FIP Weight %", 0, 100, key="slider_fip", value=6)
w_avg = st.sidebar.slider("Lineup AVG Weight %", 0, 100, key="slider_avg", value=11)
w_slg = st.sidebar.slider("Lineup SLG Weight %", 0, 100, key="slider_slg", value=14)
w_bp = st.sidebar.slider("Bullpen WAR Weight %", 0, 100, key="slider_bp", value=12)

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
        # Pulling Season Relief Pitching stats for the team to get varied WAR
        roster = statsapi.get('team_roster', {'teamId': team_id})['roster']
        relievers = [p['person']['id'] for p in roster if p['position']['code'] == '1']
        total_war = 0.0
        # Check top 5 relievers by season performance to get a dynamic score
        for pid in relievers[:5]:
            stats = get_advanced_stats(pid, "pitching")
            total_war += float(stats.get('war', 0.1))
        return total_war / 2 # Scaled for 12% weight impact
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

@st.cache_data(ttl=15)
def get_detailed_data(game_id, game_info):
    try:
        box = statsapi.boxscore_data(game_id)
        
        def process_lineup(side):
            players, avgs, slgs = [], [], []
            batters_list = box[side].get('batters', [])[:9]
            if not batters_list: return ["Lineup TBD"] * 9, 0.250, 0.400
            for pid in batters_list:
                p = box[side]['players'][f"ID{pid}"]
                season = get_advanced_stats(pid, "hitting")
                avgs.append(float(season.get('avg', '.250').replace('.','0.')))
                slgs.append(float(season.get('slg', '.400').replace('.','0.')))
                players.append(f"{p['person']['fullName']} ({p['stats']['batting'].get('hits',0)}/{p['stats']['batting'].get('atBats',0)})")
            return players, sum(avgs)/9, sum(slgs)/9

        def get_strength_metrics(side, team_id, team_name):
            wpct = get_wpct(team_id)
            lineup_names, l_avg, l_slg = process_lineup(side)
            sp_id = box[side].get('pitchers', [None])[0]
            sp_data = statsapi.player_stat_data(sp_id, group="pitching", type="season")['stats'][0]['stats'] if sp_id else {}
            p_era, p_fip = float(sp_data.get('era', 4.10)), float(sp_data.get('fip', 4.10))
            
            # FIXED: Dynamic Bullpen WAR based on team roster season stats
            bp_war = get_bullpen_war(team_id)
            
            adj_wpct = (wpct * (w_std/100)) + (l_avg * 4 * (w_avg/100)) + (l_slg * 2.5 * (w_slg/100)) + \
                       ((4.1/p_era) * (w_era/100)) + ((4.1/p_fip) * (w_fip/100)) + (bp_war * (w_bp/100))
            
            return {"name": game_info.get(f'{side}_probable_pitcher', "TBD"), "stats": sp_data, "wpct": adj_wpct, 
                    "logo": f"https://www.mlbstatic.com/team-logos/{team_id}.svg", "lineup": lineup_names, 
                    "l_avg": l_avg, "l_slg": l_slg, "bp_war": bp_war}

        a = get_strength_metrics('away', game_info['away_id'], game_info['away_name'])
        h = get_strength_metrics('home', game_info['home_id'], game_info['home_name'])
        
        prob_h = (h['wpct'] - (a['wpct'] * h['wpct'])) / (a['wpct'] + h['wpct'] - (2 * a['wpct'] * h['wpct'])) + 0.04
        return {"a": a, "h": h, "prob_h": max(0.01, min(0.99, prob_h)), "box": box}
    except: return None

# --- UI ---
st.title("⚾ MLB Intelligence: Pro Custom")
u_date = st.text_input("Gameday Date (MM/DD/YYYY)", value=datetime.now().strftime("%m/%d/%Y"))
games = statsapi.schedule(date=u_date)

for g in games:
    with st.container(border=True):
        st.write(f"### {g['away_name']} @ {g['home_name']}")
        if st.button("Analyze Matchup", key=str(g['game_id'])):
            data = get_detailed_data(g['game_id'], g)
            if data:
                p_h, p_a = data['prob_h']*100, (1-data['prob_h'])*100
                st.markdown(f"""<div style="display:flex; justify-content:space-around; background:#111; padding:20px; border-radius:10px; border:1px solid #333; color:white; align-items:center;">
                    <div style="text-align:center;"><img src="{data['a']['logo']}" width="80"><br>{g['away_name']}<br><b style="font-size:32px; color:#FF5252;">{p_a:.1f}%</b></div>
                    <div style="text-align:center; font-size:24px; opacity:0.5;">VS</div>
                    <div style="text-align:center;"><img src="{data['h']['logo']}" width="80"><br>{g['home_name']}<br><b style="font-size:32px; color:#4CAF50;">{p_h:.1f}%</b></div>
                </div>""", unsafe_allow_html=True)
                
                st.info(f"""**TEAM BREAKDOWN** **{g['away_name']}**: AVG {data['a']['l_avg']:.3f} | SLG {data['a']['l_slg']:.3f} | Bullpen WAR {data['a']['bp_war']:.2f}  
                **{g['home_name']}**: AVG {data['h']['l_avg']:.3f} | SLG {data['h']['l_slg']:.3f} | Bullpen WAR {data['h']['bp_war']:.2f}""")
                
                c1, c2 = st.columns(2)
                for col, key in zip([c1, c2], ['a', 'h']):
                    s = data[key]
                    col.subheader(f"🏟️ {s['name']}")
                    col.caption(f"ERA: {s['stats'].get('era','-.--')} | FIP: {s['stats'].get('fip','-.--')}")
                
                st.table(pd.DataFrame({g['away_name']: data['a']['lineup'], g['home_name']: data['h']['lineup']}))
                
                st.subheader("📊 Box Score")
                b, status = data['box'], g.get('status', 'Final')
                aw_r, hm_r = b['away']['teamStats']['batting'].get('runs', 0), b['home']['teamStats']['batting'].get('runs', 0)
                aw_e, hm_e = b['away']['teamStats'].get('fielding', {}).get('errors', 0), b['home']['teamStats'].get('fielding', {}).get('errors', 0)

                box_df = pd.DataFrame({"Team": [g['away_name'], g['home_name']], "R": [aw_r, hm_r], 
                                      "H": [b['away']['teamStats']['batting'].get('hits', 0), b['home']['teamStats']['batting'].get('hits', 0)], 
                                      "E": [aw_e, hm_e]})

                def highlight_winner(row):
                    if "Final" in status and aw_r != hm_r:
                        winner = g['away_name'] if aw_r > hm_r else g['home_name']
                        if row.Team == winner: return ['background-color: #2e7d32; color: white; font-weight: bold'] * len(row)
                    return [''] * len(row)
                st.table(box_df.style.apply(highlight_winner, axis=1))
