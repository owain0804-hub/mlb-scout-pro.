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
            # 1. Lineup Impact (WAR x OPS) - Amplifying the best hitters
            batters = box[side].get('batters', [])[:9]
            l_score = 0
            for b_id in batters:
                adv = get_advanced_stats(b_id, "hitting")
                # Squaring OPS to reward elite hitters more than average ones
                l_score += (float(adv.get('ops', 0.720)) ** 2) + float(adv.get('war', 0.1))
            
            # 2. Elite Bullpen (Looking for 'Shutdown' arms)
            pitchers = box[side].get('pitchers', [])
            bp_score = 0
            if len(pitchers) > 1:
                for p_id in pitchers[1:4]:
                    p_adv = get_advanced_stats(p_id, "pitching")
                    # Penalty for high FIP, reward for high WAR
                    bp_score += (float(p_adv.get('war', 0.05)) * 5) - (float(p_adv.get('fip', 4.20)) / 10)

            # 3. Starter 'Shutout' Potential
            sp_id = box[side].get('pitchers', [None])[0]
            sp_data = statsapi.player_stat_data(sp_id, group="pitching", type="season")['stats'][0]['stats'] if sp_id else {}
            # Lower FIP is better; we invert it and square it for more "spread"
            fip = float(sp_data.get('fip', 4.20))
            sp_score = (10 / (fip + 0.1)) ** 1.5 
            
            # 4. Momentum (Win %)
            rec = game_info.get(f'{side}_record', "1-1").split('-')
            win_pct = int(rec[0])/(int(rec[0])+int(rec[1])) if len(rec)==2 else 0.5
            
            total_strength = (l_score * 2.5) + (bp_score * 4.0) + (sp_score * 1.2) + (win_pct * 25)
            return {"name": game_info.get(f'{side}_probable_pitcher', "TBD"), "stats": sp_data, "score": total_strength, "l_score": l_score, "bp_score": bp_score}

        a, h = get_strength_metrics('away'), get_strength_metrics('home')
        
        # Pythagorean-style spread to prevent the "54% trap"
        # Using an exponent of 3.0 pushes the favorites higher and dogs lower
        power_h = h['score'] ** 3.0
        power_a = a['score'] ** 3.0
        prob_h = (power_h / (power_h + power_a)) + 0.03 # Slight home field nudge
        
        # Determine specific advantage for the Note
        note = "Projected as a high-variance matchup."
        if h['bp_score'] > a['bp_score'] + 1.0: note = f"Advantage: {game_info['home_name']} Bullpen depth."
        elif a['l_score'] > h['l_score'] + 1.5: note = f"Advantage: {game_info['away_name']} Elite Lineup WAR."
        
        return {"a_l": build_lineup('away'), "h_l": build_lineup('home'), "prob_h": max(0.05, min(0.95, prob_h)), "box": box, "a_sp": a, "h_sp": h, "note": note}
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
                    <div style="text-align:center;">{g['away_name']}<br><b style="font-size:24px; color:#FF5252;">{p_a:.1f}%</b></div>
                    <div style="text-align:center;">{g['home_name']}<br><b style="font-size:24px; color:#4CAF50;">{p_h:.1f}%</b></div>
                </div>""", unsafe_allow_html=True)
                st.info(f"💡 **AI Insight:** {data['note']}")
                
                st.subheader("🏟️ Matchup Starters")
                c1, c2 = st.columns(2)
                for col, team, key in zip([c1, c2], [g['away_name'], g['home_name']], ['a_sp', 'h_sp']):
                    s = data[key]
                    col.write(f"**{s['name']}**")
                    col.caption(f"ERA: {s['stats'].get('era','-.--')} | FIP: {s['stats'].get('fip','-.--')}")
                
                st.subheader("📋 Official Lineups")
                st.table(pd.DataFrame({g['away_name']: data['a_l'], g['home_name']: data['h_l']}))
            
