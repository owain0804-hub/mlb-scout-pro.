import streamlit as st
import statsapi
import pandas as pd
from datetime import datetime
from streamlit_autorefresh import st_autorefresh

st.set_page_config(page_title="MLB AI Scout Pro", layout="wide", page_icon="⚾")
st_autorefresh(interval=30000, key="mlb_live_timer")

# --- SIDEBAR TUNING ---
st.sidebar.header("⚙️ Probability Tuning")

if st.sidebar.button("🔄 Reset to Default"):
    st.session_state.w_standings = 42
    st.session_state.w_era = 15
    st.session_state.w_fip = 6
    st.session_state.w_avg = 11
    st.session_state.w_slg = 14
    st.session_state.w_bp = 12

# Initialize session state for weights
if 'w_standings' not in st.session_state: st.session_state.w_standings = 42
if 'w_era' not in st.session_state: st.session_state.w_era = 15
if 'w_fip' not in st.session_state: st.session_state.w_fip = 6
if 'w_avg' not in st.session_state: st.session_state.w_avg = 11
if 'w_slg' not in st.session_state: st.session_state.w_slg = 14
if 'w_bp' not in st.session_state: st.session_state.w_bp = 12

w_std = st.sidebar.slider("Standings Weight %", 0, 100, st.session_state.w_standings, key="slider_std")
w_era = st.sidebar.slider("Pitcher ERA Weight %", 0, 100, st.session_state.w_era, key="slider_era")
w_fip = st.sidebar.slider("Pitcher FIP Weight %", 0, 100, st.session_state.w_fip, key="slider_fip")
w_avg = st.sidebar.slider("Lineup AVG Weight %", 0, 100, st.session_state.w_avg, key="slider_avg")
w_slg = st.sidebar.slider("Lineup SLG Weight %", 0, 100, st.session_state.w_slg, key="slider_slg")
w_bp = st.sidebar.slider("Bullpen WAR Weight %", 0, 100, st.session_state.w_bp, key="slider_bp")

total_weight = w_std + w_era + w_fip + w_avg + w_slg + w_bp
st.sidebar.write(f"**Total Allocation: {total_weight}%**")
if total_weight != 100:
    st.sidebar.warning("⚠️ Weights should total 100% for best accuracy.")

# --- CORE FUNCTIONS ---
@st.cache_data(ttl=3600)
def get_advanced_stats(player_id, group):
    try:
        data = statsapi.player_stat_data(player_id, group=group, type="season")
        return data['stats'][0]['stats'] if data.get('stats') else {}
    except: return {}

@st.cache_data(ttl=300)
def get_team_info(team_name):
    try:
        standings = statsapi.standings_data(leagueId="103,104")
        for div_id, division in standings.items():
            for team in division['teams']:
                if team['name'] == team_name:
                    w, l = int(team.get('w', 1)), int(team.get('l', 1))
                    return {"div_id": div_id, "rank": int(team.get('div_rank', 5)), "wpct": w/(w+l)}
        return {"div_id": None, "rank": 5, "wpct": 0.500}
    except: return {"div_id": None, "rank": 5, "wpct": 0.500}

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

        def get_strength_metrics(side, team_name):
            t_info = get_team_info(team_name)
            lineup_names, l_avg, l_slg = process_lineup(side)
            sp_id = box[side].get('pitchers', [None])[0]
            sp_data = statsapi.player_stat_data(sp_id, group="pitching", type="season")['stats'][0]['stats'] if sp_id else {}
            p_era, p_fip = float(sp_data.get('era', 4.10)), float(sp_data.get('fip', 4.10))
            pitchers = box[side].get('pitchers', [])
            bp_war = sum([float(get_advanced_stats(p, "pitching").get('war', 0.05)) for p in pitchers[1:4]]) if len(pitchers) > 1 else 0.1
            
            # NORMALIZING FACTORS (to make weights behave properly)
            # Standings: 0-1, ERA/FIP: 4.1/score, AVG: score*4, SLG: score*2.5
            adj_wpct = (t_info['wpct'] * (w_std/100)) + \
                       (l_avg * 4 * (w_avg/100)) + \
                       (l_slg * 2.5 * (w_slg/100)) + \
                       ((4.1/p_era) * (w_era/100)) + \
                       ((4.1/p_fip) * (w_fip/100)) + \
                       (bp_war * (w_bp/100))
            
            # Spread 1.01
            spread_factor = 1.01 
            amplified_wpct = (adj_wpct**spread_factor) / ((adj_wpct**spread_factor) + ((1-adj_wpct)**spread_factor))
            return {"name": game_info.get(f'{side}_probable_pitcher', "TBD"), "stats": sp_data, "wpct": amplified_wpct, "div_id": t_info['div_id'], "lineup": lineup_names, "l_avg": l_avg, "l_slg": l_slg, "bp_war": bp_war}

        a, h = get_strength_metrics('away', game_info['away_name']), get_strength_metrics('home', game_info['home_name'])
        pa, pb = a['wpct'], h['wpct']
        prob_h = (pb - (pa * pb)) / (pa + pb - (2 * pa * pb)) + 0.04
        return {"a": a, "h": h, "prob_h": max(0.01, min(0.99, prob_h)), "box": box, "note": "Divisional battle." if a['div_id'] == h['div_id'] else "Inter-divisional matchup."}
    except: return None

# --- UI RENDERING ---
col_logo, col_title = st.columns([1, 6])
with col_logo: st.image("https://www.mlbstatic.com/team-logos/league-laundry/mlb.svg", width=70)
with col_title: st.title("MLB Intelligence: Pro Custom")

u_date = st.text_input("Gameday Date", value=datetime.now().strftime("%m/%d/%Y"))
games = statsapi.schedule(date=u_date)

for g in games:
    with st.container(border=True):
        st.write(f"### {g['away_name']} @ {g['home_name']}")
        if st.button("Analyze", key=str(g['game_id'])):
            data = get_detailed_data(g['game_id'], g)
            if data:
                p_h, p_a = data['prob_h']*100, (1-data['prob_h'])*100
                st.markdown(f"""<div style="display:flex; justify-content:space-around; background:#111; padding:15px; border-radius:10px; border:1px solid #333; color:white; align-items:center;">
                    <div style="text-align:center;">{g['away_name']}<br><b style="font-size:28px; color:#FF5252;">{p_a:.1f}%</b></div>
                    <div style="text-align:center;"><img src="https://www.mlbstatic.com/team-logos/league-laundry/mlb.svg" width="45"><br><small>LIVE MODEL</small></div>
                    <div style="text-align:center;">{g['home_name']}<br><b style="font-size:28px; color:#4CAF50;">{p_h:.1f}%</b></div>
                </div>""", unsafe_allow_html=True)
                
                st.info(f"💡 **AI Insight:** {data['note']} | **SLG:** {data['a']['l_slg']:.3f} vs {data['h']['l_slg']:.3f} | **Bullpen WAR:** {data['a']['bp_war']:.2f} vs {data['h']['bp_war']:.2f}")
                
                c1, c2 = st.columns(2)
                for col, key in zip([c1, c2], ['a', 'h']):
                    s = data[key]
                    col.subheader(f"🏟️ {s['name']}")
                    col.caption(f"ERA: {s['stats'].get('era','-.--')} | FIP: {s['stats'].get('fip','-.--')}")
                st.table(pd.DataFrame({g['away_name']: data['a']['lineup'], g['home_name']: data['h']['lineup']}))
                
                b = data['box']
                aw_r, hm_r = b['away']['teamStats']['batting'].get('runs', 0), b['home']['teamStats']['batting'].get('runs', 0)
                df = pd.DataFrame({"Team": [g['away_name'], g['home_name']], "R": [aw_r, hm_r], "H": [b['away']['teamStats']['batting'].get('hits', 0), b['home']['teamStats']['batting'].get('hits', 0)]})
                st.table(df)
        
