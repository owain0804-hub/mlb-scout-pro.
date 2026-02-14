import streamlit as st
import statsapi
import pandas as pd
from datetime import datetime
from streamlit_autorefresh import st_autorefresh

# App Configuration
st.set_page_config(page_title="MLB AI Scout", layout="centered", page_icon="⚾")
st_autorefresh(interval=30000, key="mlb_live_timer")

@st.cache_data(ttl=600)
def get_player_stats(player_id, group):
    try:
        data = statsapi.player_stat_data(player_id, group=group, type="season")
        return data['stats'][0]['stats'] if data.get('stats') else {}
    except: return {}

@st.cache_data(ttl=15)
def get_detailed_data(game_id, game_info):
    try:
        box = statsapi.boxscore_data(game_id)
        
        def build_lineup(side):
            players = []
            batters_list = box[side].get('batters', [])[:9]
            if not batters_list: return ["Lineup TBD"] * 9
            for pid in batters_list:
                p = box[side]['players'][f"ID{pid}"]
                s = p['stats']['batting']
                line = f"{s.get('hits',0)}/{s.get('atBats',0)}"
                if s.get('homeRuns',0) > 0: line += " HR"
                players.append(f"{p['person']['fullName']} ({line})")
            return players + ["-"] * (9 - len(players))

        def get_sp_info(side):
            # Explicitly maps correct pitcher to correct team stats
            name = game_info.get(f'{side}_probable_pitcher', "TBD")
            p_list = box[side].get('pitchers', [])
            p_id = p_list[0] if p_list else None
            stats = get_player_stats(p_id, "pitching") if p_id else {}
            
            # Strength calc
            batters = box[side].get('batters', [])[:9]
            avg_ops = sum([float(get_player_stats(b, "hitting").get('ops', 0.720)) for b in batters])/9 if batters else 0.720
            resistance = (float(stats.get('era', 4.50)) * 0.75) + (float(stats.get('whip', 1.35)) * 2.0)
            
            return {"name": name, "stats": stats, "power": (avg_ops ** 1.85), "res": resistance}

        a_sp = get_sp_info('away')
        h_sp = get_sp_info('home')

        # Logic: Away power vs Home resistance and vice-versa
        s_away = a_sp['power'] / (h_sp['res'] ** 0.5)
        s_home = h_sp['power'] / (a_sp['res'] ** 0.5)
        
        prob_home = (s_home / (s_away + s_home)) + 0.04
        return {"a_l": build_lineup('away'), "h_l": build_lineup('home'), "prob": prob_home, "box": box, "a_sp": a_sp, "h_sp": h_sp}
    except: return None

st.title("⚾ MLB Intelligence: Live")
u_date = st.text_input("Gameday Date", value=datetime.now().strftime("%m/%d/%Y"))
games = statsapi.schedule(date=u_date)

for g in games:
    with st.container(border=True):
        st.write(f"### {g['away_name']} @ {g['home_name']}")
        if st.button("Analyze", key=str(g['game_id'])):
            data = get_detailed_data(g['game_id'], g)
            if data:
                p_h, p_a = data['prob']*100, (1-data['prob'])*100
                st.markdown(f"""<div style="display:flex; justify-content:space-around; background:#111; padding:15px; border-radius:10px; border:1px solid #333; color:white;">
                    <div style="text-align:center;">{g['away_name']}<br><b style="font-size:24px; color:#4CAF50;">{p_a:.1f}%</b></div>
                    <div style="text-align:center;">{g['home_name']}<br><b style="font-size:24px; color:#4CAF50;">{p_h:.1f}%</b></div>
                </div>""", unsafe_allow_html=True)
                
                st.subheader("🏟️ Starters")
                c1, c2 = st.columns(2)
                c1.write(f"**{data['a_sp']['name']}** ({g['away_name']})")
                c1.caption(f"ERA: {data['a_sp']['stats'].get('era','-.--')} | WHIP: {data['a_sp']['stats'].get('whip','-.--')}")
                c2.write(f"**{data['h_sp']['name']}** ({g['home_name']})")
                c2.caption(f"ERA: {data['h_sp']['stats'].get('era','-.--')} | WHIP: {data['h_sp']['stats'].get('whip','-.--')}")
                
                st.subheader("📋 Lineups")
                st.table(pd.DataFrame({g['away_name']: data['a_l'], g['home_name']: data['h_l']}))

                st.subheader("📝 Scoreboard")
                b, aw_r, hm_r = data['box'], data['box']['away']['teamStats']['batting'].get('runs', 0), data['box']['home']['teamStats']['batting'].get('runs', 0)
                box_df = pd.DataFrame({"Team": [g['away_name'], g['home_name']], "R": [aw_r, hm_r], "H": [b['away']['teamStats']['batting'].get('hits', 0), b['home']['teamStats']['batting'].get('hits', 0)]})
                st.table(box_df)
                
                if "Final" in g['status']:
                    st.success(f"🏆 Winner: {g['away_name'] if aw_r > hm_r else g['home_name']}")
                    st.write(f"**WP:** {g.get('winning_pitcher', 'N/A')} | **LP:** {g.get('losing_pitcher', 'N/A')}")
