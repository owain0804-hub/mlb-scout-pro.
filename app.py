import streamlit as st
import statsapi
import pandas as pd
from datetime import datetime
from streamlit_autorefresh import st_autorefresh

st.set_page_config(page_title="MLB AI Scout Pro", layout="wide", page_icon="⚾")
st_autorefresh(interval=30000, key="mlb_live_timer")

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
st.sidebar.header("⭐ User Preferences")
try:
    all_teams_data = statsapi.get('teams', {'sportId': 1})['teams']
    team_list = sorted([t['name'] for t in all_teams_data])
except:
    team_list = []
fav_team = st.sidebar.selectbox("Select Favorite Team", ["None"] + team_list)

st.sidebar.divider()
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

# --- SAFE DATA FUNCTIONS ---
@st.cache_data(ttl=3600)
def get_player_streak(player_id):
    try:
        data_s = statsapi.player_stat_data(player_id, group="hitting", type="season")
        data_r = statsapi.player_stat_data(player_id, group="hitting", type="last7")
        # SAFETY CHECK: Ensure 'stats' list is not empty before indexing [0]
        if not data_s.get('stats') or not data_r.get('stats'): return ""
        s_avg = float(data_s['stats'][0]['stats'].get('avg', '.250').replace('.','0.'))
        r_avg = float(data_r['stats'][0]['stats'].get('avg', '.250').replace('.','0.'))
        if r_avg > s_avg + 0.050: return "🔥"
        if r_avg < s_avg - 0.050: return "❄️"
        return ""
    except: return ""

@st.cache_data(ttl=3600)
def get_bullpen_war(team_id):
    try:
        roster = statsapi.get('team_roster', {'teamId': team_id})['roster']
        relievers = [p['person']['id'] for p in roster if p['position']['code'] == '1']
        total_war = 0.0
        for pid in relievers[:5]:
            data = statsapi.player_stat_data(pid, group="pitching", type="season")
            if data.get('stats') and len(data['stats']) > 0:
                total_war += float(data['stats'][0]['stats'].get('war', 0.1))
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

def get_detailed_data(game_id, game_info):
    try:
        box = statsapi.boxscore_data(game_id)
        def process_lineup(side):
            players, avgs, slgs = [], [], []
            batters_list = box[side].get('batters', [])[:9]
            if not batters_list: return ["Lineup TBD"] * 9, 0.250, 0.400
            for pid in batters_list:
                p = box[side]['players'][f"ID{pid}"]
                streak = get_player_streak(pid)
                # SAFETY CHECK: Season data fetch
                s_data = statsapi.player_stat_data(pid, group="hitting", type="season")
                if s_data.get('stats') and len(s_data['stats']) > 0:
                    st_vals = s_data['stats'][0]['stats']
                    avgs.append(float(st_vals.get('avg', '.250').replace('.','0.')))
                    slgs.append(float(st_vals.get('slg', '.400').replace('.','0.')))
                else:
                    avgs.append(0.250); slgs.append(0.400)
                players.append(f"{streak} {p['person']['fullName']}")
            return players, sum(avgs)/len(avgs), sum(slgs)/len(slgs)

        def get_strength_metrics(side, team_id):
            wpct, bp_war = get_wpct(team_id), get_bullpen_war(team_id)
            lineup_names, l_avg, l_slg = process_lineup(side)
            sp_id = box[side].get('pitchers', [None])[0]
            sp_data_raw = statsapi.player_stat_data(sp_id, group="pitching", type="season") if sp_id else {}
            # SAFETY CHECK: Pitcher stats indexing
            sp_stats = sp_data_raw['stats'][0]['stats'] if sp_data_raw.get('stats') else {}
            p_era, p_fip = float(sp_stats.get('era', 4.10)), float(sp_stats.get('fip', 4.10))
            
            adj_wpct = (wpct * (w_std/100)) + (l_avg * 4 * (w_avg/100)) + (l_slg * 2.5 * (w_slg/100)) + \
                       ((4.1/p_era) * (w_era/100)) + ((4.1/p_fip) * (w_fip/100)) + (bp_war * (w_bp/100))
            return {"name": game_info.get(f'{side}_probable_pitcher', "TBD"), "stats": sp_stats, "wpct": adj_wpct, 
                    "logo": f"https://www.mlbstatic.com/team-logos/{team_id}.svg", "lineup": lineup_names, 
                    "l_avg": l_avg, "l_slg": l_slg, "bp_war": bp_war}

        a, h = get_strength_metrics('away', game_info['away_id']), get_strength_metrics('home', game_info['home_id'])
        prob_h = (h['wpct'] - (a['wpct'] * h['wpct'])) / (a['wpct'] + h['wpct'] - (2 * a['wpct'] * h['wpct'])) + 0.04
        return {"a": a, "h": h, "prob_h": max(0.01, min(0.99, prob_h)), "box": box}
    except Exception as e:
        st.error(f"Analysis Failed: {e}")
        return None

# --- UI ---
st.title("⚾ MLB Intelligence: Pro Custom")
u_date = st.text_input("Gameday Date (MM/DD/YYYY)", value=datetime.now().strftime("%m/%d/%Y"))
try:
    games = statsapi.schedule(date=u_date)
    sorted_games = sorted(games, key=lambda x: (x['away_name'] != fav_team and x['home_name'] != fav_team))
except:
    st.warning("Could not load schedule. Check your date format.")
    sorted_games = []

for g in sorted_games:
    gid = g['game_id']
    is_fav = (g['away_name'] == fav_team or g['home_name'] == fav_team)
    with st.container(border=True):
        if is_fav: st.markdown("<span style='color:#FFD700; font-weight:bold;'>⭐ FAVORITE MATCHUP</span>", unsafe_allow_html=True)
        st.write(f"### {g['away_name']} @ {g['home_name']}")
        if st.button("Analyze Matchup", key=f"btn_{gid}"):
            st.session_state.active_game_id = gid
        if st.session_state.active_game_id == gid:
            with st.spinner("Analyzing stats..."):
                data = get_detailed_data(gid, g)
                if data:
                    p_h, p_a = data['prob_h']*100, (1-data['prob_h'])*100
                    st.markdown(f"""<div style="display:flex; justify-content:space-around; background:#111; padding:20px; border-radius:10px; border:2px solid {'#FFD700' if is_fav else '#333'}; color:white; align-items:center;">
                        <div style="text-align:center;"><img src="{data['a']['logo']}" width="80"><br>{g['away_name']}<br><b style="font-size:32px; color:#FF5252;">{p_a:.1f}%</b></div>
                        <div style="text-align:center; font-size:24px; opacity:0.5;">VS</div>
                        <div style="text-align:center;"><img src="{data['h']['logo']}" width="80"><br>{g['home_name']}<br><b style="font-size:32px; color:#4CAF50;">{p_h:.1f}%</b></div>
                    </div>""", unsafe_allow_html=True)
                    st.info(f"**{g['away_name']}**: AVG {data['a']['l_avg']:.3f} | SLG {data['a']['l_slg']:.3f} | Bullpen WAR {data['a']['bp_war']:.2f}\n\n**{g['home_name']}**: AVG {data['h']['l_avg']:.3f} | SLG {data['h']['l_slg']:.3f} | Bullpen WAR {data['h']['bp_war']:.2f}")
                    lineup_df = pd.DataFrame({g['away_name']: data['a']['lineup'], g['home_name']: data['h']['lineup']})
                    st.table(lineup_df.style.applymap(lambda v: 'background-color: #1b5e20' if "🔥" in v else ('background-color: #b71c1c' if "❄️" in v else '')))
                    b = data['box']
                    box_df = pd.DataFrame({"Team": [g['away_name'], g['home_name']], "R": [b['away']['teamStats']['batting'].get('runs', 0), b['home']['teamStats']['batting'].get('runs', 0)], "H": [b['away']['teamStats']['batting'].get('hits', 0), b['home']['teamStats']['batting'].get('hits', 0)], "E": [b['away']['teamStats'].get('fielding', {}).get('errors', 0), b['home']['teamStats'].get('fielding', {}).get('errors', 0)]})
                    st.table(box_df)
            
