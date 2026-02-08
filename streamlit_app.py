import streamlit as st
import pandas as pd
import yfinance as yf
import requests
from ta.trend import EMAIndicator, ADXIndicator
from ta.volatility import AverageTrueRange
from streamlit_autorefresh import st_autorefresh
import datetime
import json
import os
import base64
from zoneinfo import ZoneInfo

# ─────────────────────────────────────────────
# PERSISTANCE : SYNC AUTOMATIQUE GITHUB
# ─────────────────────────────────────────────
def sync_to_github(file_path, data):
    try:
        if "GITHUB_TOKEN" not in st.secrets:
            return
        token = st.secrets["GITHUB_TOKEN"]
        repo = st.secrets["GITHUB_REPO"]
        url = f"https://api.github.com/repos/{repo}/contents/{file_path}"
        headers = {"Authorization": f"token {token}", "Accept": "application/vnd.github.v3+json"}
        
        res = requests.get(url, headers=headers)
        sha = res.json().get("sha") if res.status_code == 200 else None
        
        content = base64.b64encode(json.dumps(data, indent=4).encode()).decode()
        payload = {"message": f"Update {file_path} Sniper V19", "content": content}
        if sha: payload["sha"] = sha
        
        requests.put(url, headers=headers, json=payload)
    except:
        pass

# ─────────────────────────────────────────────
# GESTION DES FICHIERS JSON (AVEC SECURITE INITIALE)
# ─────────────────────────────────────────────
DB_FILE = "swing_active_trades.json"
HISTORY_FILE = "swing_history_trades.json"

def load_json(file):
    # Sécurité : Si le fichier n'existe pas, on le pré-crée pour éviter les erreurs de démarrage
    if not os.path.exists(file):
        initial_data = {} if file == DB_FILE else []
        with open(file, "w") as f:
            json.dump(initial_data, f)
        sync_to_github(file, initial_data)
        return initial_data
        
    try:
        with open(file, "r") as f:
            return json.load(f)
    except:
        return {} if file == DB_FILE else []

def save_json(file, data):
    with open(file, "w") as f:
        json.dump(data, f)
    sync_to_github(file, data)

# ─────────────────────────────────────────────
# TELEGRAM
# ─────────────────────────────────────────────
def send_telegram_msg(message):
    try:
        token = st.secrets.get("TELEGRAM_TOKEN", "8150058407:AAFg44ySihFKBO1UW69QZqi07otqeB2IK5s")
        chat_id = st.secrets.get("TELEGRAM_CHAT_ID", "1148025596")
        requests.get(f"https://api.telegram.org/bot{token}/sendMessage", params={"chat_id": chat_id, "text": message}, timeout=10)
    except:
        pass

# ─────────────────────────────────────────────
# FILTRE DE SESSION (SECURITE WEEK-END)
# ─────────────────────────────────────────────
def is_market_open(category):
    if category == "CRYPTO":
        return True
    
    now = datetime.datetime.now(ZoneInfo("Europe/Paris"))
    
    # Samedi (5) et Dimanche (6)
    if now.weekday() >= 5:
        # Réouverture Dimanche 23h
        if now.weekday() == 6 and now.hour >= 23:
            return True
        return False
    
    # Vendredi soir après fermeture
    if now.weekday() == 4 and now.hour >= 22:
        return False
        
    return True

# ─────────────────────────────────────────────
# CONFIGURATION APP & ASSETS
# ─────────────────────────────────────────────
st.set_page_config(page_title="Sniper V19 — Swing Trend Pro", layout="wide")
st_autorefresh(interval=300000, key="refresh") # Refresh toutes les 5 min

ASSETS = {
    "FOREX": [
        "EURUSD=X","GBPUSD=X","USDJPY=X","AUDUSD=X","USDCAD=X","USDCHF=X","NZDUSD=X",
        "EURGBP=X","EURJPY=X","GBPJPY=X","EURAUD=X","EURCAD=X","EURCHF=X","EURNZD=X",
        "GBPAUD=X","GBPCAD=X","GBPCHF=X","GBPNZD=X",
        "AUDJPY=X","AUDCAD=X","AUDCHF=X","AUDNZD=X",
        "CADJPY=X","CADCHF=X","CHFJPY=X",
        "NZDJPY=X","NZDCAD=X","NZDCHF=X"
    ],
    "CRYPTO": ["BTC-USD", "ETH-USD"]
}

# Initialisation forcée
active_trades = load_json(DB_FILE)
history_trades = load_json(HISTORY_FILE)

def pip_factor(pair):
    if "BTC" in pair or "ETH" in pair: return 1
    return 100 if "JPY" in pair else 10000

# ─────────────────────────────────────────────
# MOTEUR DE STRATÉGIE SWING ELITE (1-4 JOURS)
# ─────────────────────────────────────────────
def run_engine():
    results = []
    tickers = [t for cat in ASSETS.values() for t in cat]
    
    # Téléchargement multi-TF
    data_d1 = yf.download(tickers, period="250d", interval="1d", group_by="ticker", progress=False, threads=False)
    data_h4 = yf.download(tickers, period="60d", interval="4h", group_by="ticker", progress=False, threads=False)
    data_h1 = yf.download(tickers, period="15d", interval="1h", group_by="ticker", progress=False, threads=False)

    for category, symbols in ASSETS.items():
        for ticker in symbols:
            try:
                name = ticker.replace("=X","").replace("-USD","USD")
                
                if not is_market_open(category):
                    continue

                # --- GESTION DES TRADES ACTIFS ---
                if name in active_trades:
                    trade = active_trades[name]
                    current_price = float(data_h1[ticker]["Close"].iloc[-1])
                    is_win, is_loss = False, False
                    if trade["type"] == "ACHAT 🚀":
                        if current_price >= trade["tp"]: is_win = True
                        elif current_price <= trade["sl"]: is_loss = True
                    else:
                        if current_price <= trade["tp"]: is_win = True
                        elif current_price >= trade["sl"]: is_loss = True
                    
                    if is_win or is_loss:
                        # Re-charger pour être sûr de ne rien écraser
                        current_h = load_json(HISTORY_FILE)
                        current_h.append({
                            "Date": datetime.datetime.now().strftime("%d/%m %H:%M"),
                            "Actif": name, "Type": trade["type"], "Résultat": "✅ WIN" if is_win else "❌ LOSS", "RR": trade["rr"] if is_win else -1.0
                        })
                        save_json(HISTORY_FILE, current_h)
                        del active_trades[name]
                        save_json(DB_FILE, active_trades)
                    continue

                # --- ANALYSE TECHNIQUE ---
                df_d1 = data_d1[ticker].dropna()
                df_h4 = data_h4[ticker].dropna()
                df_h1 = data_h1[ticker].dropna()
                
                ema200_d1 = EMAIndicator(df_d1["Close"], 200).ema_indicator().iloc[-1]
                ema50_h4 = EMAIndicator(df_h4["Close"], 50).ema_indicator().iloc[-1]
                ema200_h4 = EMAIndicator(df_h4["Close"], 200).ema_indicator().iloc[-1]
                adx_obj_h4 = ADXIndicator(df_h4["High"], df_h4["Low"], df_h4["Close"], 14)
                adx_h4 = adx_obj_h4.adx().iloc[-1]
                adx_prev_h4 = adx_obj_h4.adx().iloc[-5] 
                
                ema20_h1 = EMAIndicator(df_h1["Close"], 20).ema_indicator().iloc[-1]
                close_h1 = df_h1["Close"].iloc[-1]
                prev_close_h1 = df_h1["Close"].iloc[-2]
                atr_h1 = AverageTrueRange(df_h1["High"], df_h1["Low"], df_h1["Close"], 14).average_true_range().iloc[-1]
                
                is_trending = adx_h4 >= 25 and adx_h4 > adx_prev_h4
                trend_bull = close_h1 > ema200_d1 and ema50_h4 > ema200_h4 and is_trending
                trend_bear = close_h1 < ema200_d1 and ema50_h4 < ema200_h4 and is_trending
                
                signal, sl, tp, rr, comment = "ATTENDRE", None, None, 0, "Analyse en cours"

                if trend_bull:
                    if prev_close_h1 <= ema20_h1 and close_h1 > ema20_h1:
                        signal = "ACHAT 🚀"
                        low_h1 = df_h1["Low"].iloc[-10:].min()
                        sl = round(low_h1 - (atr_h1 * 1.5), 5)
                        tp = round(close_h1 + (abs(close_h1 - sl) * 2.0), 5)
                        comment = "Rejet Pullback confirmé"
                    else:
                        comment = "Tendance UP - Attente Rejet EMA20"

                elif trend_bear:
                    if prev_close_h1 >= ema20_h1 and close_h1 < ema20_h1:
                        signal = "VENTE 🔻"
                        high_h1 = df_h1["High"].iloc[-10:].max()
                        sl = round(high_h1 + (atr_h1 * 1.5), 5)
                        tp = round(close_h1 - (abs(sl - close_h1) * 2.0), 5)
                        comment = "Rejet Pullback confirmé"
                    else:
                        comment = "Tendance DOWN - Attente Rejet EMA20"
                
                else:
                    if adx_h4 < 25: comment = "ADX trop faible (Range)"
                    elif adx_h4 <= adx_prev_h4: comment = "Tendance s'essouffle (ADX baisse)"
                    else: comment = "Pas d'alignement Multi-TF"

                if signal != "ATTENDRE":
                    risk = abs(close_h1 - sl)
                    reward = abs(tp - close_h1)
                    rr = round(reward / risk, 2)
                    
                    if rr >= 1.5 and name not in active_trades:
                        active_trades[name] = {"type": signal, "entry": close_h1, "sl": sl, "tp": tp, "rr": rr}
                        save_json(DB_FILE, active_trades)
                        msg = f"🦅 SNIPER ELITE V19\n{name} | {signal}\n\n🎯 Objectif: SWING\n💰 Entrée: {round(close_h1, 5)}\n🛑 SL: {sl}\n✅ TP: {tp}\n📊 RR: {rr}"
                        send_telegram_msg(msg)

                results.append({"Actif": name, "Signal": signal, "Prix": round(close_h1, 5), "ADX H4": round(adx_h4, 1), "Commentaire": comment})
            except: continue
    return results

# ─────────────────────────────────────────────
# INTERFACE UTILISATEUR
# ─────────────────────────────────────────────
st.title("🦅 Sniper V19 — Swing Trend Following")

# SECTION STATISTIQUES (RELIT LE FICHIER À CHAQUE REFRESH)
history_to_show = load_json(HISTORY_FILE)
if history_to_show:
    df_h = pd.DataFrame(history_to_show)
    c1, c2, c3 = st.columns(3)
    winrate = (len(df_h[df_h["Résultat"] == "✅ WIN"]) / len(df_h)) * 100 if len(df_h) > 0 else 0
    c1.metric("Winrate Global", f"{round(winrate, 1)}%")
    c2.metric("Profit Cumulé", f"{round(df_h['RR'].sum(), 2)}R")
    c3.metric("Nombre de Trades", len(df_h))
    with st.expander("Voir l'historique détaillé", expanded=True):
        st.table(df_h.tail(20))
else:
    st.info("📊 Historique : En attente de clôture du premier trade.")

# TABLEAU DES SIGNAUX
st.header("🎯 Radar de Tendance (Triple Alignement Elite)")
data_results = run_engine()
if data_results:
    st.dataframe(pd.DataFrame(data_results), use_container_width=True)

with st.sidebar:
    st.info("Stratégie : Daily Trend + H4 ADX Accel + H1 Candle Rejection")
    if st.button("🗑 Réinitialiser Verrous"):
        if os.path.exists(DB_FILE): os.remove(DB_FILE)
        st.success("Verrous supprimés")
    if st.button("🔴 Effacer Historique"):
        if os.path.exists(HISTORY_FILE):
            os.remove(HISTORY_FILE)
            save_json(HISTORY_FILE, [])
        st.success("Historique vidé")
    if st.button("📩 Test Telegram"):
        send_telegram_msg("✅ Sniper V19 ELITE opérationnel")
        st.toast("Message envoyé")
