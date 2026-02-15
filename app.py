import streamlit as st
import statsapi
import pandas as pd
import json
import os
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
    .box-score-table { background-color: #1c2128; border-radius: 10px; padding: 10px; margin-top: 15px; border: 1px solid #444; }
    .confidence-badge { font-size: 0.8em; padding: 2px 8px; border-radius: 10px; font-weight: bold; margin-left: 10px;}
    .driver-val { font-weight: bold; color: #4CAF50; }
    </style>
    """, unsafe_allow_html=True)

# --- PERSISTENT STORAGE LOGIC ---
CONFIG_FILE = "user_settings.json"

def load_settings():
    if os.path.exists(CONFIG_FILE):
        with open(CONFIG_FILE, "r") as f:
            return json.load(f)
    return {
        "fav_team": "None",
        "w_std": 40, "w_era": 15, "w_avg": 20, "w_slg": 25,
        "preset": "Balanced"
    }

def save_settings(data):
    with open(CONFIG_FILE, "w") as f:
        json.dump(data, f)

if "saved_settings" not in st.session_state:
    st.session_state.saved_settings = load_settings()
if "active_game_id" not in st.session_state:
    st.session_state.active_game_id = None

# --- SIDEBAR ---
with st.sidebar:
    st.title("⚾ Model Intelligence")
    s = st.session_state.saved_settings
    current_preset = s.get("preset", "Balanced")
    preset_options = ["Balanced", "Pitching Heavy", "Offense Heavy", "Custom"]
    preset = st.radio("Model Presets", preset_options, index=preset_options.index(current_preset))
    
    if preset == "Balanced": w_std, w_era, w_avg, w_slg = 40, 15, 20, 25
    elif preset == "Pitching Heavy": w_std, w_era, w_avg, w_slg = 20, 50, 15, 15
    elif preset == "Offense Heavy": w_std, w_era, w_avg, w_slg = 20, 10, 35, 35
    else:
        w_std = st.slider("Standings Weight %", 0, 100, value=s["w_std"])
        w_era = st.slider("Pitching ERA Weight %", 0, 100, value=s["w_era"])
        w_avg = st.slider("Lineup AVG Weight %", 0, 100, value=s["w_avg"])
        w_slg = st.slider("Lineup SLG Weight %", 0, 100, value=s["w_slg"])
    
    sensitivity = st.slider("Stat Sensitivity (Multiplier)", 1.0, 3.0, value=1.2, step=0.1)
    st.divider()
    
    try:
        all_teams = statsapi.get('teams', {'sportId': 1})['teams']
        team_list = sorted([t['name'] for t in all_teams])
    except: team_list = []
    
    fav_team = st.selectbox("Your Favorite Team", ["None"] + team_list, 
                            index=(["None"] + team_list).index(s["fav_team"]) if s["fav_team"] in (["None"] + team_list) else 0)

    if st.button("💾 Save Settings Permanently"):
        new_settings = {"fav_team": fav_team, "w_std": w_std, "w_era": w_era, "w_avg": w_avg, "w_slg": w_slg, "preset": preset}
        save_settings(new_settings)
        st.session_state.saved_settings = new_settings
        st.success("Settings saved!")

# --- CORE FUNCTIONS ---
@st.cache_data(ttl=3600)
def get_team_info(team_id, year):
    try:
        standings = statsapi.standings_data(leagueId="103,104", season=year) or statsapi.standings_data(leagueId="103,104", season=year-1)
        for div in standings.values():
            for t in div.get('teams', []):
                if t.get('team_id') == team_id:
                    return f"{t['w']}-{t['l']}", (int(t['w']) / max(1, int(t['w'])+int(t['l'])))
        return "0-0", 0.500
    except: return "0-0", 0.500

def get_detailed_data(game_id, g_info, selected_year, w_std, w_era, w_avg, w_slg, sensitivity):
    try:
        box = statsapi.boxscore_data(game_id)
        if not box: return None

        def fetch_metrics(side, tid):
            side_data = box.get(side, {})
            players, batters = side_data.get('players', {}), side_data.get('batters', [])
            l_rows, avgs, slgs = [], [], []
            
            if not batters:
                l_rows = [{"Player": "Lineup TBD", "AVG": ".000"}] * 9
                avgs, slgs = [0.250]*9, [0.400]*9
            else:
                for pid in batters[:9]:
                    p = players.get(f"ID{pid}", {})
                    try:
                        s_data = statsapi.player_stat_data(pid, group="hitting", type="season", season=selected_year)
                        stats_list = s_data.get('stats', [])
                        s = stats_list[0].get('stats', {}) if (stats_list and stats_list[0].get('stats', {}).get('atBats', 0) > 0) else {}
                    except: s = {}
                    p_avg = s.get('avg', '.000')
                    l_rows.append({"Player": p.get('person', {}).get('fullName', "TBD"), "AVG": p_avg})
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
                    s_p = stats_list[0].get('stats', {}) if stats_list else {}
                    p_era = float(s_p.get('era', 4.10))
                except: p_era = 4.10
            
            _, wpct = get_team_info(tid, selected_year)
            std_part = wpct * (w_std/100)
            era_part = (4.1/max(0.5, p_era)) * (w_era/100)
            avg_part = (sum(avgs)/9 * 4 * (w_avg/100))
            slg_part = (sum(slgs)/9 * 2.5 * (w_slg/100))
            
            return {
                "lines": l_rows, "p_name": p_name, "p_era": p_era, 
                "total": std_part + era_part + avg_part + slg_part, 
                "std": std_part, "era_val": era_part, "avg_val": avg_part, "slg_val": slg_part
            }

        a_data = fetch_metrics('away', g_info['away_id'])
        h_data = fetch_metrics('home', g_info['home_id'])
        
        avg_score = (h_data['total'] + a_data['total']) / 2
        diff = (h_data['total'] - a_data['total']) * sensitivity
        prob_h = 0.5 + (diff / max(0.1, avg_score)) + 0.03 
        
        drivers = {
            "Standings": (h_data['std'] - a_data['std']) * sensitivity * 10,
            "ERA Matchup": (h_data['era_val'] - a_data['era_val']) * sensitivity * 10,
            "Lineup AVG": (h_data['avg_val'] - a_data['avg_val']) * sensitivity * 10,
            "Lineup SLG": (h_data['slg_val'] - a_data['slg_val']) * sensitivity * 10
        }
        return {"a": a_data, "h": h_data, "prob_h": max(0.01, min(0.99, prob_h)), "drivers": drivers, "box": box}
    except Exception: return None

# --- MAIN UI ---
st.title("⚾ MLB Intelligence Pro")
u_date = st.date_input("Select Date", datetime.now())
selected_year = u_date.year

raw_sched = statsapi.schedule(date=u_date.strftime("%m/%d/%Y"))
unique_games = []
seen_ids = set()
for g in raw_sched:
    if g['game_id'] not in seen_ids:
        unique_games.append(g)
        seen_ids.add(g['game_id'])

fav = st.session_state.saved_settings["fav_team"]
sorted_games = sorted(unique_games, key=lambda x: (x.get('away_name') != fav and x.get('home_name') != fav))

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
            st.caption(f"{g.get('status')} | {selected_year} Season")
        with c3:
            if st.button("Analyze Matchup", key=f"btn_{gid}"): st.session_state.active_game_id = gid
        
        if st.session_state.active_game_id == gid:
            data = get_detailed_data(gid, g, selected_year, w_std, w_era, w_avg, w_slg, sensitivity)
            if data:
                p_h = data['prob_h']
                winner = g['home_name'] if p_h > 0.5 else g['away_name']
                win_pct = p_h if p_h > 0.5 else (1 - p_h)
                conf = "High" if win_pct > 0.62 else "Medium" if win_pct > 0.55 else "Low"
                conf_color = "#4CAF50" if conf == "High" else "#FFD700" if conf == "Medium" else "#8b949e"
                
                st.markdown(f"""<div class="winner-box">🏅 Projected Winner: <b>{winner}</b> ({win_pct*100:.1f}%) <span class="confidence-badge" style="background:{conf_color}; color:#000;">{conf} Confidence</span></div>""", unsafe_allow_html=True)
                
                # --- BOX SCORE LOGIC (Directly Visible) ---
                if g.get('status') in ["Final", "Game Over", "Live", "In Progress"]:
                    try:
                        aw_stats = data['box']['away'].get('teamStats', {}).get('batting', {})
                        hm_stats = data['box']['home'].get('teamStats', {}).get('batting', {})
                        box_df = pd.DataFrame({
                            "Team": [g['away_name'], g['home_name']],
                            "R": [aw_stats.get('runs', 0), hm_stats.get('runs', 0)],
                            "H": [aw_stats.get('hits', 0), hm_stats.get('hits', 0)],
                            "E": [data['box']['away'].get('teamStats', {}).get('fielding', {}).get('errors', 0), 
                                  data['box']['home'].get('teamStats', {}).get('fielding', {}).get('errors', 0)]
                        })
                        st.markdown("**Live/Final Box Score**")
                        st.dataframe(box_df, use_container_width=True, hide_index=True)
                    except: pass

                with st.expander("📊 Why this prediction? (Detailed Drivers)"):
                    st.write(f"Advantage breakdown for **{winner}**:")
                    d, mult = data['drivers'], (1 if p_h > 0.5 else -1)
                    st.markdown(f"* Standings Edge: <span class='driver-val'>{'+' if d['Standings']*mult > 0 else ''}{d['Standings']*mult:.1f}%</span>", unsafe_allow_html=True)
                    st.markdown(f"* Pitching ERA Impact: <span class='driver-val'>{'+' if d['ERA Matchup']*mult > 0 else ''}{d['ERA Matchup']*mult:.1f}%</span>", unsafe_allow_html=True)
                    st.markdown(f"* Lineup AVG (Consistency): <span class='driver-val'>{'+' if d['Lineup AVG']*mult > 0 else ''}{d['Lineup AVG']*mult:.1f}%</span>", unsafe_allow_html=True)
                    st.markdown(f"* Lineup SLG (Power): <span class='driver-val'>{'+' if d['Lineup SLG']*mult > 0 else ''}{d['Lineup SLG']*mult:.1f}%</span>", unsafe_allow_html=True)

                l_col1, l_col2 = st.columns(2)
                for col, d_key, t_name in [(l_col1, 'a', g['away_name']), (l_col2, 'h', g['home_name'])]:
                    with col:
                        st.markdown(f"**{t_name}**")
                        st.markdown(f"<div class='pitcher-box'><b>SP:</b> {data[d_key]['p_name']} (ERA: {data[d_key]['p_era']})</div>", unsafe_allow_html=True)
                        st.dataframe(pd.DataFrame(data[d_key]['lines']), use_container_width=True, hide_index=True)
            else: st.info("Detailed data unavailable.")
        st.markdown('</div>', unsafe_allow_html=True)
