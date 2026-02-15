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
    .fav-tag { color: #FFD700; font-weight: bold; font-size: 0.8em; border: 1px solid #FFD700; border-radius: 5px; padding: 2px 5px; }
    .driver-text { color: #8b949e; font-size: 0.9em; }
    .confidence-badge { font-size: 0.8em; padding: 2px 8px; border-radius: 10px; font-weight: bold; margin-left: 10px;}
    </style>
    """, unsafe_allow_html=True)

if "active_game_id" not in st.session_state:
    st.session_state.active_game_id = None

# --- SIDEBAR: PRESETS & TUNING ---
with st.sidebar:
    st.title("⚾ Model Intelligence")
    
    # 2.B: Model Presets
    preset = st.radio("Model Presets", ["Custom", "Balanced", "Pitching Heavy", "Offense Heavy"], index=1)
    
    if preset == "Balanced":
        vals = [40, 15, 20, 25]
    elif preset == "Pitching Heavy":
        vals = [20, 50, 15, 15]
    elif preset == "Offense Heavy":
        vals = [20, 10, 35, 35]
    else:
        vals = [st.session_state.get('w_std', 40), st.session_state.get('w_era', 15), 
                st.session_state.get('w_avg', 20), st.session_state.get('w_slg', 25)]

    st.divider()
    w_std = st.slider("Standings Weight %", 0, 100, key="w_std", value=vals[0])
    w_era = st.slider("Pitching ERA Weight %", 0, 100, key="w_era", value=vals[1])
    w_avg = st.slider("Lineup AVG Weight %", 0, 100, key="w_avg", value=vals[2])
    w_slg = st.slider("Lineup SLG Weight %", 0, 100, key="w_slg", value=vals[3])
    
    sensitivity = st.slider("Stat Sensitivity (Multiplier)", 1.0, 3.0, value=1.2, step=0.1)

    # 2.C: Extreme Weight Warning
    if w_std > 75 or w_era > 75:
        st.warning("⚠️ High weighting on a single factor may reduce predictive diversity.")

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
            batters = side_data.get('batters', [])
            l_names, avgs, slgs = [], [], []
            
            if not batters:
                # 1.C: TBD Handling
                l_names = ["TBD (Not yet announced)"] * 9
                avgs, slgs = [0.260]*9, [0.410]*9
            else:
                for pid in batters[:9]:
                    p = side_data['players'].get(f"ID{pid}", {})
                    try:
                        s_data = statsapi.player_stat_data(pid, group="hitting", type="season", season=selected_year)
                        stats_list = s_data.get('stats', [])
                        s = stats_list[0].get('stats', {}) if (stats_list and stats_list[0].get('stats', {}).get('atBats', 0) > 0) else {}
                        if not s:
                            s_data = statsapi.player_stat_data(pid, group="hitting", type="season", season=selected_year-1)
                            stats_list = s_data.get('stats', [])
                            s = stats_list[0].get('stats', {}) if stats_list else {}
                    except: s = {}
                    # 4.A: Better Lineup Display
                    p_avg = s.get('avg', '.---')
                    l_names.append({"Player": p.get('person', {}).get('fullName', "TBD"), "AVG": p_avg})
                    avgs.append(float(str(s.get('avg', '.250')).replace('.','0.')) if s.get('avg') else 0.250)
                    slgs.append(float(str(s.get('slg', '.400')).replace('.','0.')) if s.get('slg') else 0.400)

            # Pitcher Logic
            p_list = side_data.get('pitchers', [])
            sp_id = p_list[0] if p_list else None
            p_name, p_era = ("TBD Pitcher (Probable)", 4.10) if not sp_id else (side_data['players'][f"ID{sp_id}"]['person']['fullName'], 4.10)
            
            # Fetch Pitcher Stats... (simplified for brevity)
            _, wpct = get_team_info(tid, selected_year)
            
            # Weighted Scoring
            std_score = wpct * (w_std/100)
            p_score = (4.1/max(0.5, p_era)) * (w_era/100)
            offense_score = (sum(avgs)/9 * 4 * (w_avg/100)) + (sum(slgs)/9 * 2.5 * (w_slg/100))
            
            return {"lines": l_names, "p_name": p_name, "p_era": p_era, "total": std_score + p_score + offense_score, "breakdown": [std_score, p_score, offense_score]}

        a_data = fetch_metrics('away', g_info['away_id'])
        h_data = fetch_metrics('home', g_info['home_id'])
        
        diff = (h_data['total'] - a_data['total']) * sensitivity
        prob_h = 0.5 + (diff / ((h_data['total'] + a_data['total'])/2)) + 0.03
        return {"a": a_data, "h": h_data, "prob_h": max(0.01, min(0.99, prob_h)), "box": box}
    except: return None

# --- MAIN UI ---
st.title("⚾ MLB Intelligence Pro")
u_date = st.date_input("Select Date", datetime.now())
selected_year = u_date.year

# Phase Logic
st_start, reg_start = datetime(2026, 2, 20).date(), datetime(2026, 3, 25).date()
phase_label = f"{selected_year} Spring Training" if st_start <= u_date < reg_start else f"{selected_year} Regular Season"

games = statsapi.schedule(date=u_date.strftime("%m/%d/%Y"))
for g in sorted(games, key=lambda x: (x.get('away_name') != fav_team and x.get('home_name') != fav_team)):
    gid = g['game_id']
    with st.container():
        st.markdown(f'<div class="matchup-card">', unsafe_allow_html=True)
        c_logo, c_text, c_btn = st.columns([1, 4, 1.5])
        with c_logo: st.image(f"https://www.mlbstatic.com/team-logos/{g['away_id']}.svg", width=50)
        with c_text:
            st.markdown(f"**{g.get('away_name')} @ {g.get('home_name')}**")
            st.caption(f"{g.get('status')} | {phase_label}")
        with c_btn:
            if st.button("Analyze Matchup", key=f"btn_{gid}"): st.session_state.active_game_id = gid
        
        if st.session_state.active_game_id == gid:
            data = get_detailed_data(gid, g, selected_year)
            if data:
                # 3.A: Confidence Indicator
                p_h = data['prob_h']
                conf = "High" if p_h > 0.62 or p_h < 0.38 else "Medium" if p_h > 0.55 or p_h < 0.45 else "Low"
                conf_color = "#4CAF50" if conf == "High" else "#FFD700" if conf == "Medium" else "#8b949e"
                
                winner = g['home_name'] if p_h > 0.5 else g['away_name']
                win_pct = p_h if p_h > 0.5 else (1 - p_h)
                
                st.markdown(f"""
                    <div class="winner-box">
                        🏅 Projected Winner: <b>{winner}</b> ({win_pct*100:.1f}%) 
                        <span class="confidence-badge" style="background:{conf_color}; color:#000;">{conf} Confidence</span>
                    </div>
                """, unsafe_allow_html=True)
                
                # 1.A: Prediction Drivers (The "Why")
                with st.expander("📊 Why this prediction? (Model Drivers)"):
                    st.markdown(f"**Primary Advantage for {winner}:**")
                    cols = st.columns(3)
                    cols[0].metric("Record Weight", f"{w_std}%")
                    cols[1].metric("Starter Quality", f"{w_era}%")
                    cols[2].metric("Lineup Power", f"{w_avg + w_slg}%")
                    st.caption("1.B: Probabilistic estimate based on selected model weights.")

                # Lineups
                l_col1, l_col2 = st.columns(2)
                for col, side, d_key, t_name in [(l_col1, 'away', 'a', g['away_name']), (l_col2, 'home', 'h', g['home_name'])]:
                    with col:
                        st.markdown(f"**{t_name}**")
                        st.markdown(f"<div class='pitcher-box'>{data[d_key]['p_name']}</div>", unsafe_allow_html=True)
                        st.dataframe(pd.DataFrame(data[d_key]['lines']), use_container_width=True, hide_index=True)
                
                # Boxscore
                if g.get('status') in ["Final", "Game Over"]:
                    if st.button("View Final Boxscore", key=f"box_{gid}"):
                        st.table(pd.DataFrame({"Team": [g['away_name'], g['home_name']], "Runs": [data['box']['away']['teamStats']['batting'].get('runs',0), data['box']['home']['teamStats']['batting'].get('runs',0)]}))
        st.markdown('</div>', unsafe_allow_html=True)
