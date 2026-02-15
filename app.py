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
    .winner-box { background: #1b2838; border: 2px solid #4CAF50; border-radius: 10px; padding: 15px; margin-bottom: 10px; color: #e6edf3; text-align: center;}
    .pitcher-box { background: #0d1117; border: 1px solid #30363d; border-radius: 8px; padding: 8px; text-align: center; margin-bottom: 5px; }
    .confidence-badge { font-size: 0.8em; padding: 2px 8px; border-radius: 10px; font-weight: bold; margin-left: 10px;}
    </style>
    """, unsafe_allow_html=True)

# Initialize Session State
if "active_game_id" not in st.session_state:
    st.session_state.active_game_id = None
if "fav_team" not in st.session_state:
    st.session_state.fav_team = "None"

# --- SIDEBAR: PRESETS & TUNING ---
with st.sidebar:
    st.title("⚾ Model Intelligence")
    
    # Model Presets
    preset = st.radio("Model Presets", ["Balanced", "Pitching Heavy", "Offense Heavy", "Custom"], index=0)
    
    if preset == "Balanced":
        st.session_state.w_std, st.session_state.w_era, st.session_state.w_avg, st.session_state.w_slg = 40, 15, 20, 25
    elif preset == "Pitching Heavy":
        st.session_state.w_std, st.session_state.w_era, st.session_state.w_avg, st.session_state.w_slg = 20, 50, 15, 15
    elif preset == "Offense Heavy":
        st.session_state.w_std, st.session_state.w_era, st.session_state.w_avg, st.session_state.w_slg = 20, 10, 35, 35

    st.divider()
    w_std = st.slider("Standings Weight %", 0, 100, key="w_std")
    w_era = st.slider("Pitching ERA Weight %", 0, 100, key="w_era")
    w_avg = st.slider("Lineup AVG Weight %", 0, 100, key="w_avg")
    w_slg = st.slider("Lineup SLG Weight %", 0, 100, key="w_slg")
    
    sensitivity = st.slider("Stat Sensitivity (Multiplier)", 1.0, 3.0, value=1.2, step=0.1)

    st.divider()
    try:
        all_teams = statsapi.get('teams', {'sportId': 1})['teams']
        team_list = sorted([t['name'] for t in all_teams])
    except: team_list = []
    st.session_state.fav_team = st.selectbox("Your Favorite Team", ["None"] + team_list)

# --- CORE FUNCTIONS ---
@st.cache_data(ttl=3600)
def get_team_info(team_id, year):
    try:
        standings = statsapi.standings_data(leagueId="103,104", season=year) or statsapi.standings_data(leagueId="103,104", season=year-1)
        for div in standings.values():
            for t in div.get('teams', []):
                if t.get('team_id') == team_id:
                    w, l = t.get('w', 0), t.get('l', 0)
                    return f"{w}-{l}", (int(w) / max(1, int(w)+int(l)))
        return "0-0", 0.500
    except: return "0-0", 0.500

def get_detailed_data(game_id, g_info, selected_year):
    try:
        box = statsapi.boxscore_data(game_id)
        def fetch_metrics(side, tid):
            side_data = box.get(side, {})
            players = side_data.get('players', {})
            batters = side_data.get('batters', [])
            l_rows, avgs, slgs = [], [], []
            
            if not batters:
                l_rows = [{"Player": "TBD (Lineup not set)", "AVG": ".000"}] * 9
                avgs, slgs = [0.250]*9, [0.400]*9
            else:
                for pid in batters[:9]:
                    p = players.get(f"ID{pid}", {})
                    p_name = p.get('person', {}).get('fullName', "TBD Player")
                    try:
                        s_data = statsapi.player_stat_data(pid, group="hitting", type="season", season=selected_year)
                        stats_list = s_data.get('stats', [])
                        s = stats_list[0].get('stats', {}) if (stats_list and stats_list[0].get('stats', {}).get('atBats', 0) > 0) else {}
                        if not s:
                            s_data = statsapi.player_stat_data(pid, group="hitting", type="season", season=selected_year-1)
                            stats_list = s_data.get('stats', [])
                            s = stats_list[0].get('stats', {}) if stats_list else {}
                    except: s = {}
                    
                    p_avg = s.get('avg', '.000')
                    l_rows.append({"Player": p_name, "AVG": p_avg})
                    avgs.append(float(str(p_avg).replace('.','0.')) if s.get('avg') else 0.250)
                    slgs.append(float(str(s.get('slg', '.400')).replace('.','0.')) if s.get('slg') else 0.400)

            p_list = side_data.get('pitchers', [])
            sp_id = p_list[0] if p_list else None
            p_name, p_era = "TBD Pitcher", 4.10
            if sp_id:
                p_info = players.get(f"ID{sp_id}", {})
                p_name = p_info.get('person', {}).get('fullName', "TBD Pitcher")
                try:
                    sp_stat = statsapi.player_stat_data(sp_id, group="pitching", type="season", season=selected_year)
                    stats_list = sp_stat.get('stats', [])
                    s_p = stats_list[0].get('stats', {}) if (stats_list and stats_list[0].get('stats', {}).get('inningsPitched', '0') != '0') else {}
                    if not s_p:
                        sp_stat = statsapi.player_stat_data(sp_id, group="pitching", type="season", season=selected_year-1)
                        stats_list = sp_stat.get('stats', [])
                        s_p = stats_list[0].get('stats', {}) if stats_list else {}
                    p_era = float(s_p.get('era', 4.10))
                except: p_era = 4.10
            
            _, wpct = get_team_info(tid, selected_year)
            std_part = wpct * (w_std/100)
            p_part = (4.1/max(0.5, p_era)) * (w_era/100)
            off_part = (sum(avgs)/9 * 4 * (w_avg/100)) + (sum(slgs)/9 * 2.5 * (w_slg/100))
            return {"lines": l_rows, "p_name": p_name, "p_era": p_era, "total": std_part + p_part + off_part, "parts": [std_part, p_part, off_part]}

        a_data = fetch_metrics('away', g_info['away_id'])
        h_data = fetch_metrics('home', g_info['home_id'])
        diff = (h_data['total'] - a_data['total']) * sensitivity
        prob_h = 0.5 + (diff / max(0.1, (h_data['total'] + a_data['total'])/2)) + 0.03
        return {"a": a_data, "h": h_data, "prob_h": max(0.01, min(0.99, prob_h)), "box": box}
    except: return None

# --- MAIN UI ---
st.title("⚾ MLB Intelligence Pro")
u_date = st.date_input("Select Date", datetime.now())
selected_year = u_date.year

# 2026 Season Labels
st_start, reg_start = datetime(2026, 2, 20).date(), datetime(2026, 3, 25).date()
phase_label = f"{selected_year} Spring Training" if st_start <= u_date < reg_start else f"{selected_year} Regular Season"

games = statsapi.schedule(date=u_date.strftime("%m/%d/%Y"))
# Fixed Sorting logic to prevent NameError
fav = st.session_state.fav_team
sorted_games = sorted(games, key=lambda x: (x.get('away_name') != fav and x.get('home_name') != fav))

for g in sorted_games:
    gid = g['game_id']
    rec_a, _ = get_team_info(g['away_id'], selected_year)
    rec_h, _ = get_team_info(g['home_id'], selected_year)

    with st.container():
        st.markdown(f'<div class="matchup-card">', unsafe_allow_html=True)
        c1, c2, c3 = st.columns([1, 4, 1.5])
        with c1: st.image(f"https://www.mlbstatic.com/team-logos/{g['away_id']}.svg", width=50)
        with c2:
            st.markdown(f"**{g.get('away_name')} ({rec_a}) @ {g.get('home_name')} ({rec_h})**")
            st.caption(f"{g.get('status')} | {phase_label}")
        with c3:
            if st.button("Analyze", key=f"btn_{gid}"): st.session_state.active_game_id = gid
        
        if st.session_state.active_game_id == gid:
            data = get_detailed_data(gid, g, selected_year)
            if data:
                p_h = data['prob_h']
                winner = g['home_name'] if p_h > 0.5 else g['away_name']
                win_pct = p_h if p_h > 0.5 else (1 - p_h)
                conf = "High" if win_pct > 0.62 else "Medium" if win_pct > 0.55 else "Low"
                conf_color = "#4CAF50" if conf == "High" else "#FFD700" if conf == "Medium" else "#8b949e"
                
                st.markdown(f"""<div class="winner-box">🏅 Projected Winner: <b>{winner}</b> ({win_pct*100:.1f}%) <span class="confidence-badge" style="background:{conf_color}; color:#000;">{conf} Confidence</span></div>""", unsafe_allow_html=True)
                
                with st.expander("📊 Why this prediction? (Drivers)"):
                    st.write("This projection is based on your current weight settings:")
                    st.progress(p_h, text=f"{g['home_name']} Advantage Meter")
                    st.caption("Includes Home Field Advantage (+3.0%) and current season/historical performance data.")

                l_col1, l_col2 = st.columns(2)
                for col, d_key, t_name in [(l_col1, 'a', g['away_name']), (l_col2, 'h', g['home_name'])]:
                    with col:
                        st.markdown(f"**{t_name}**")
                        st.markdown(f"<div class='pitcher-box'><b>SP:</b> {data[d_key]['p_name']} (ERA: {data[d_key]['p_era'] if data[d_key]['p_name'] != 'TBD Pitcher' else 'TBD'})</div>", unsafe_allow_html=True)
                        st.dataframe(pd.DataFrame(data[d_key]['lines']), use_container_width=True, hide_index=True)
                
                if g.get('status') in ["Final", "Game Over"]:
                    if st.button("📊 View Final Boxscore", key=f"box_{gid}"):
                        st.json({"Score": f"{g['away_name']} {data['box']['away']['teamStats']['batting'].get('runs',0)} - {g['home_name']} {data['box']['home']['teamStats']['batting'].get('runs',0)}"})
            else:
                st.info("Analysis unavailable for this game type (Exhibition/Non-MLB).")
        st.markdown('</div>', unsafe_allow_html=True)
                        
