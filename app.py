import streamlit as st
import statsapi
import pandas as pd
from datetime import datetime
from streamlit_autorefresh import st_autorefresh

st.set_page_config(page_title="MLB AI Scout Pro", layout="centered", page_icon="⚾")
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

        def get_team_metrics(side, opp_side):
            # 1. Batter Power (OPS)
            batters = box[side].get('batters', [])[:9]
            avg_ops = sum([float(get_player_stats(b, "hitting").get('ops', 0.720)) for b in batters])/9 if batters else 0.720
            
            # 2. Pitcher Resistance (ERA/WHIP)
            p_id = box[side].get('pitchers', [None])[0]
            p_stats = get_player_stats(p_id, "pitching") if p_id else {}
            era, whip = float(p_stats.get('era', 4.50)), float(p_stats.get('whip', 1.35))
            resistance = 1 / ((era * 0.15) + (whip * 0.85) + 0.1) # Defensive value
            
            # 3. Winning Percentage (Historical Quality)
            rec = game_info.get(f'{side}_record', "0-0").split('-')
            w, l = (float(rec[0]), float(rec[1])) if len(rec)==2 else (1.0, 1.0)
            win_pct = w / (w + l) if (w + l) > 0 else 0.500
            
            # Weighted Strength: Power + Team Success
            strength = (avg_ops * 0.4) + (win_pct * 0.4) + (resistance * 0.2)
            return {"name": game_info.get(f'{side}_probable_pitcher', "TBD"), "stats": p_stats, "str": strength}

        away = get_team_metrics('away', 'home')
        home = get_team_metrics('home', 'away')

        # Log-5 Probability Formula
        # P = (A - AB) / (A + B - 2AB)
        a, b = away['str'], home['str']
        prob_a = (a - (a * b)) / (a + b - (2 * a * b) + 0.0001)
        
        # Adjust for Home Field Advantage (~4% boost for Home)
        prob_h = (1 - prob_a) + 0.04
        return {"a_l": build_lineup('away'), "h_l": build_lineup('home'), "prob_h": max(0.01, min(0.99, prob_h)), "box": box, "a_sp": away, "h_sp": home}
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
                p_h, p_a = data['prob_h']*100, (1-data['prob_h'])*100
                st.markdown(f"""<div style="display:flex; justify-content:space-around; background:#111; padding:15px; border-radius:10px; border:1px solid #333; color:white;">
                    <div style="text-align:center;">{g['away_name']}<br><b style="font-size:24px; color:#4CAF50;">{p_a:.1f}%</b></div>
                    <div style="text-align:center;">{g['home_name']}<br><b style="font-size:24px; color:#4CAF50;">{p_h:.1f}%</b></div>
                </div>""", unsafe_allow_html=True)
                
                st.subheader("🏟️ Starters")
                c1, c2 = st.columns(2)
                for col, team, key in zip([c1, c2], [g['away_name'], g['home_name']], ['a_sp', 'h_sp']):
                    s = data[key]
                    col.write(f"**{s['name']}** ({team})")
                    col.caption(f"ERA: {s['stats'].get('era','-.--')} | WHIP: {s['stats'].get('whip','-.--')}")
                
                st.subheader("📋 Lineups")
                st.table(pd.DataFrame({g['away_name']: data['a_l'], g['home_name']: data['h_l']}))

                st.subheader("📝 Scoreboard")
                b, aw_r, hm_r = data['box'], data['box']['away']['teamStats']['batting'].get('runs', 0), data['box']['home']['teamStats']['batting'].get('runs', 0)
                box_df = pd.DataFrame({"Team": [g['away_name'], g['home_name']], "R": [aw_r, hm_r], "H": [b['away']['teamStats']['batting'].get('hits', 0), b['home']['teamStats']['batting'].get('hits', 0)]})
                st.table(box_df)
                
                if "Final" in g['status']:
                    st.success(f"🏆 Winner: {g['away_name'] if aw_r > hm_r else g['home_name']}")
                    st.write(f"**WP:** {g.get('winning_pitcher', 'N/A')} | **LP:** {g.get('losing_pitcher', 'N/A')}")
            
