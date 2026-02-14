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

        def get_strength_metrics(side, team_name):
            t_info = get_team_info(team_name)
            
            batters = box[side].get('batters', [])[:9]
            l_score = sum([float(get_advanced_stats(b, "hitting").get('war', 0.1)) for b in batters])
            
            pitchers = box[side].get('pitchers', [])
            bp_score = sum([float(get_advanced_stats(p, "pitching").get('war', 0.05)) for p in pitchers[1:4]]) if len(pitchers) > 1 else 0.1
            
            sp_id = box[side].get('pitchers', [None])[0]
            sp_data = statsapi.player_stat_data(sp_id, group="pitching", type="season")['stats'][0]['stats'] if sp_id else {}
            
            # ERA vs FIP Balance:
            # We take the average of ERA and FIP to ensure "Run Suppression" is valued as much as "Pure Skill"
            p_era = float(sp_data.get('era', 4.00))
            p_fip = float(sp_data.get('fip', 4.20))
            pitching_skill = (p_era + p_fip) / 2
            
            # WEIGHTING: 45% Standings, 15% Starter (heavily influenced by ERA/FIP), 12% Bullpen, 28% Lineup
            adj_wpct = (t_info['wpct'] * 0.45) + (l_score * 0.028) + (bp_score * 0.12) + ((4.1/pitching_skill) * 0.15)
            
            return {"name": game_info.get(f'{side}_probable_pitcher', "TBD"), "stats": sp_data, "wpct": max(0.1, min(0.9, adj_wpct)), "div_id": t_info['div_id']}

        a, h = get_strength_metrics('away', game_info['away_name']), get_strength_metrics('home', game_info['home_name'])
        
        pa, pb = a['wpct'], h['wpct']
        prob_h = (pb - (pa * pb)) / (pa + pb - (2 * pa * pb))
        prob_h += 0.04 # Home Field
        
        note = "Divisional battle." if a['div_id'] == h['div_id'] and a['div_id'] is not None else "Inter-divisional matchup."
            
        return {"a_l": build_lineup('away'), "h_l": build_lineup('home'), "prob_h": max(0.1, min(0.9, prob_h)), "box": box, "a_sp": a, "h_sp": h, "note": note}
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
                
                st.subheader("🏟️ Starters")
                c1, c2 = st.columns(2)
                for col, team, key in zip([c1, c2], [g['away_name'], g['home_name']], ['a_sp', 'h_sp']):
                    s = data[key]
                    col.write(f"**{s['name']}**")
                    col.caption(f"ERA: {s['stats'].get('era','-.--')} | FIP: {s['stats'].get('fip','-.--')}")
                
                st.subheader("📋 Lineups")
                st.table(pd.DataFrame({g['away_name']: data['a_l'], g['home_name']: data['h_l']}))

                st.subheader("📝 Scoreboard")
                b, status = data['box'], g.get('status', '')
                aw_r, hm_r = b['away']['teamStats']['batting'].get('runs', 0), b['home']['teamStats']['batting'].get('runs', 0)
                df = pd.DataFrame({"Team": [g['away_name'], g['home_name']], "R": [aw_r, hm_r], "H": [b['away']['teamStats']['batting'].get('hits', 0), b['home']['teamStats']['batting'].get('hits', 0)]})
                
                def highlight_winner(row):
                    if "Final" in status:
                        winner = g['away_name'] if aw_r > hm_r else g['home_name']
                        if row.Team == winner:
                            return ['background-color: #1b5e20; color: white'] * len(row)
                    return [''] * len(row)
                st.table(df.style.apply(highlight_winner, axis=1))
            
