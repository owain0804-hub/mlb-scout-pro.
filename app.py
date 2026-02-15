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
    .record-text { color: #8b949e; font-size: 0.85em; font-weight: normal; }
    </style>
    """, unsafe_allow_html=True)

if "active_game_id" not in st.session_state:
    st.session_state.active_game_id = None

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
    
    # NEW: Sensitivity Toggle
    sensitivity = st.slider("Stat Sensitivity (Impact Multiplier)", 1.0, 3.0, value=1.0, step=0.1, help="Higher values make stat differences create larger gaps in win %")
    
    if st.button("🔄 Reset to Default"):
        st.session_state["w_std"] = 40
        st.session_state["w_era"] = 15
        st.session_state["w_avg"] = 20
        st.session_state["w_slg"] = 25
        st.rerun()

    w_std = st.slider("Standings Weight %", 0, 100, key="w_std", value=40)
    w_era = st.slider("Starter ERA Weight %", 0, 100, key="w_era", value=15)
    w_avg = st.slider("Lineup AVG Weight %", 0, 100, key="w_avg", value=20)
    w_slg = st.slider("Lineup SLG Weight %", 0, 100, key="w_slg", value=25)

# --- CORE FUNCTIONS ---
@st.cache_data(ttl=3600)
def get_team_info(team_id, year):
    try:
        standings = statsapi.standings_data(leagueId="103,104", season=year)
        if not standings:
            standings = statsapi.standings_data(leagueId="103,104", season=year-1)
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
            l_names, avgs, slgs = [], [], []
            
            if not batters:
                l_names = ["TBD Player"] * 9
                avgs, slgs = [0.260]*9, [0.410]*9
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
                    b_stats = p.get('stats', {}).get('batting', {})
                    l_names.append(f"{p_name} ({b_stats.get('hits', 0)}/{b_stats.get('atBats', 0)})")
                    avgs.append(float(str(s.get('avg', '.250')).replace('.','0.')) if s.get('avg') else 0.250)
                    slgs.append(float(str(s.get('slg', '.400')).replace('.','0.')) if s.get('slg') else 0.400)

            pitchers_list = side_data.get('pitchers', [])
            sp_id = pitchers_list[0] if pitchers_list else None
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
            # Apply Sensitivity to the individual scores
            score = (wpct * (w_std/100)) + ((4.1/max(0.5, p_era)) * (w_era/100)) + \
                    (sum(avgs)/9 * 4 * (w_avg/100)) + (sum(slgs)/9 * 2.5 * (w_slg/100))
            return {"names": l_names, "p_name": p_name, "p_era": p_era, "score": score}

        a_data = fetch_metrics('away', g_info['away_id'])
        h_data = fetch_metrics('home', g_info['home_id'])
        
        # SENSITIVITY CALCULATION
        diff = (h_data['score'] - a_data['score']) * sensitivity
        avg_score = (h_data['score'] + a_data['score']) / 2
        prob_h = 0.5 + (diff / avg_score) + 0.04
        
        return {"a": a_data, "h": h_data, "prob_h": max(0.01, min(0.99, prob_h)), "box": box}
    except: return None

# --- MAIN UI ---
st.title("⚾ MLB Intelligence Pro")
u_date = st.date_input("Select Date", datetime.now())
selected_year = u_date.year

# 2026 Calendar Logic
st_start, reg_start = datetime(2026, 2, 20).date(), datetime(2026, 3, 25).date()
phase_label = f"{selected_year} Spring Training" if st_start <= u_date < reg_start else f"{selected_year} Regular Season"

games = statsapi.schedule(date=u_date.strftime("%m/%d/%Y"))
sorted_games = sorted(games, key=lambda x: (x.get('away_name') != fav_team and x.get('home_name') != fav_team))

for g in sorted_games:
    gid = g['game_id']
    is_fav = (g.get('away_name') == fav_team or g.get('home_name') == fav_team)
    rec_a, _ = get_team_info(g['away_id'], selected_year)
    rec_h, _ = get_team_info(g['home_id'], selected_year)

    with st.container():
        st.markdown(f"""<div class="matchup-card" style="border-left: 5px solid {'#FFD700' if is_fav else '#30363d'}">""", unsafe_allow_html=True)
        cols = st.columns([1, 3, 1])
        with cols[0]: st.image(f"https://www.mlbstatic.com/team-logos/{g['away_id']}.svg", width=60)
        with cols[1]: 
            fav_html = '<span class="fav-tag">⭐ FAVORITE</span>' if is_fav else ''
            st.markdown(f"### {g.get('away_name')} ({rec_a}) @ {g.get('home_name')} ({rec_h}) {fav_html}", unsafe_allow_html=True)
            st.caption(f"Status: {g.get('status')} | {phase_label}")
        with cols[2]: 
            if st.button("Analyze", key=f"btn_{gid}"): st.session_state.active_game_id = gid
        
        if st.session_state.active_game_id == gid:
            data = get_detailed_data(gid, g, selected_year)
            if data:
                p_h = data['prob_h']
                winner = g.get('home_name') if p_h > 0.5 else g.get('away_name')
                st.markdown(f"<div class='winner-box'>🏅 <b>Projected Winner: {winner}</b></div>", unsafe_allow_html=True)
                st.progress(p_h, text=f"{g.get('home_name')} {p_h*100:.1f}% | {g.get('away_name')} {(1-p_h)*100:.1f}%")

                c1, c2 = st.columns(2)
                for col, d, t_name in [(c1, data['a'], g.get('away_name')), (c2, data['h'], g.get('home_name'))]:
                    with col:
                        st.markdown(f"**{t_name} Starter**")
                        st.markdown(f"""<div class="pitcher-box"><b>{d['p_name']}</b><br>ERA: {d['p_era'] if d['p_name'] != "TBD Pitcher" else "TBD"}</div>""", unsafe_allow_html=True)
                        st.table(pd.DataFrame(d['names'], columns=["Lineup"]))
                
                # BOXSCORE BUTTON
                if g.get('status') in ["Final", "Game Over"]:
                    if st.button("📊 View Box Score", key=f"box_{gid}"):
                        b = data['box']
                        aw_r, hm_r = b['away']['teamStats']['batting'].get('runs', 0), b['home']['teamStats']['batting'].get('runs', 0)
                        df_box = pd.DataFrame({"Team": [g.get('away_name'), g.get('home_name')], "Runs": [aw_r, hm_r], "Hits": [b['away']['teamStats']['batting'].get('hits', 0), b['home']['teamStats']['batting'].get('hits', 0)]})
                        st.dataframe(df_box, use_container_width=True)
        st.markdown("</div>", unsafe_allow_html=True)
        
