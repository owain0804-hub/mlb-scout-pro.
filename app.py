import streamlit as st
import statsapi
import pandas as pd
from datetime import datetime
from streamlit_autorefresh import st_autorefresh

st.set_page_config(page_title="MLB AI Scout Pro", layout="centered", page_icon="⚾")
st_autorefresh(interval=30000, key="mlb_live_timer")

@st.cache_data(ttl=3600)
def get_advanced_stats(player_id, group):
    try:
        data = statsapi.player_stat_data(player_id, group=group, type="sabermetric")
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

        def get_strength_metrics(side):
            # 1. Lineup Total WAR (measures hitting + defense)
            batters = box[side].get('batters', [])[:9]
            l_war = sum([float(get_advanced_stats(b, "hitting").get('war', 0.1)) for b in batters])
            
            # 2. Bullpen Strength (Top Relievers WAR)
            pitchers = box[side].get('pitchers', [])
            bp_war = sum([float(get_advanced_stats(p, "pitching").get('war', 0.05)) for p in pitchers[1:4]]) if len(pitchers) > 1 else 0.1
            
            # 3. Starter FIP Resistance
            sp_id = box[side].get('pitchers', [None])[0]
            sp_data = statsapi.player_stat_data(sp_id, group="pitching", type="season")['stats'][0]['stats'] if sp_id else {}
            fip = float(sp_data.get('fip', 4.20))
            
            # 4. Team Success
            rec = game_info.get(f'{side}_record', "1-1").split('-')
            win_pct = int(rec[0])/(int(rec[0])+int(rec[1])) if len(rec)==2 else 0.5
            
            # Weighted calculation
            score = (l_war * 0.35) + (bp_war * 2.5) + ((1/fip) * 15.0) + (win_pct * 10)
            return {"name": game_info.get(f'{side}_probable_pitcher', "TBD"), "stats": sp_data, "score": score, "l_war": l_war, "bp_war": bp_war}

        a, h = get_strength_metrics('away'), get_strength_metrics('home')
        prob_h = (h['score'] / (a['score'] + h['score'])) + 0.04 # Home Edge
        
        # Matchup Note Logic
        note = "Evenly matched contest."
        if h['bp_war'] > a['bp_war'] + 0.5: note = f"Advantage: {game_info['home_name']} Bullpen."
        elif a['bp_war'] > h['bp_war'] + 0.5: note = f"Advantage: {game_info['away_name']} Bullpen."
        elif h['l_war'] > a['l_war'] + 2: note = f"Advantage: {game_info['home_name']} Lineup (Higher WAR)."
        
        return {"a_l": build_lineup('away'), "h_l": build_lineup('home'), "prob_h": max(0.01, min(0.99, prob_h)), "box": box, "a_sp": a, "h_sp": h, "note": note}
    except: return None

st.title("⚾ MLB Intelligence: Pro")
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
                st.caption(f"💡 **Matchup Note:** {data['note']}")
                
                st.subheader("🏟️ Starters")
                c1, c2 = st.columns(2)
                for col, team, key in zip([c1, c2], [g['away_name'], g['home_name']], ['a_sp', 'h_sp']):
                    s = data[key]
                    col.write(f"**{s['name']}** ({team})")
                    col.caption(f"ERA: {s['stats'].get('era','-.--')} | FIP: {s['stats'].get('fip','-.--')}")
                
                st.subheader("📋 Lineups")
                st.table(pd.DataFrame({g['away_name']: data['a_l'], g['home_name']: data['h_l']}))

                st.subheader("📝 Scoreboard")
                b = data['box']
                box_df = pd.DataFrame({"Team": [g['away_name'], g['home_name']], 
                                       "R": [b['away']['teamStats']['batting'].get('runs', 0), b['home']['teamStats']['batting'].get('runs', 0)],
                                       "H": [b['away']['teamStats']['batting'].get('hits', 0), b['home']['teamStats']['batting'].get('hits', 0)]})
                st.table(box_df)
            
