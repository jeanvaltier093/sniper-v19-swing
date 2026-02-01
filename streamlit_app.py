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
# GESTION DES FICHIERS JSON
# ─────────────────────────────────────────────
DB_FILE = "swing_active_trades.json"
HISTORY_FILE = "swing_history_trades.json"

def load_json(file):
    if os.path.exists(file):
        try:
            with open(file, "r") as f: return json.load(f)
        except: return {} if file == DB_FILE else []
    return {} if file == DB_FILE else []

def save_json(file, data):
    with open(file, "w") as f: json.dump(data, f)
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

active_trades = load_json(DB_FILE)
history_trades = load_json(HISTORY_FILE)

def pip_factor(pair):
    if "BTC" in pair or "ETH" in pair: return 1
    return 100 if "JPY" in pair else 10000

# ─────────────────────────────────────────────
# MOTEUR DE STRATÉGIE SWING (1-4 JOURS)
# ─────────────────────────────────────────────
def run_engine():
    results = []
    tickers = [t for cat in ASSETS.values() for t in cat]
    
    # Téléchargement multi-TF (Correction threads=False pour stabilité Streamlit Cloud)
    data_d1 = yf.download(tickers, period="250d", interval="1d", group_by="ticker", progress=False, threads=False)
    data_h4 = yf.download(tickers, period="60d", interval="4h", group_by="ticker", progress=False, threads=False)
    data_h1 = yf.download(tickers, period="15d", interval="1h", group_by="ticker", progress=False, threads=False)

    for category, symbols in ASSETS.items():
        for ticker in symbols:
            try:
                name = ticker.replace("=X","").replace("-USD","USD")
                
                # SECURITE : Si le marché est fermé, on saute l'analyse pour cet actif
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
                        history_trades.append({
                            "Date": datetime.datetime.now().strftime("%d/%m %H:%M"),
                            "Actif": name, "Type": trade["type"], "Résultat": "✅ WIN" if is_win else "❌ LOSS", "RR": trade["rr"] if is_win else -1.0
                        })
                        save_json(HISTORY_FILE, history_trades)
                        del active_trades[name]
                        save_json(DB_FILE, active_trades)
                    continue

                # --- ANALYSE TECHNIQUE ---
                df_d1 = data_d1[ticker].dropna()
                df_h4 = data_h4[ticker].dropna()
                df_h1 = data_h1[ticker].dropna()
                
                # 1. TIME FRAME D1 : Direction Majeure
                ema200_d1 = EMAIndicator(df_d1["Close"], 200).ema_indicator().iloc[-1]
                close_d1 = df_d1["Close"].iloc[-1]
                
                # 2. TIME FRAME H4 : Structure + Force (ADX)
                ema50_h4 = EMAIndicator(df_h4["Close"], 50).ema_indicator().iloc[-1]
                ema200_h4 = EMAIndicator(df_h4["Close"], 200).ema_indicator().iloc[-1]
                adx_h4_obj = ADXIndicator(df_h4["High"], df_h4["Low"], df_h4["Close"], 14)
                adx_h4 = adx_h4_obj.adx().iloc[-1]
                
                # 3. TIME FRAME H1 : Timing + Pullback
                ema20_h1 = EMAIndicator(df_h1["Close"], 20).ema_indicator().iloc[-1]
                ema50_h1 = EMAIndicator(df_h1["Close"], 50).ema_indicator().iloc[-1]
                close_h1 = df_h1["Close"].iloc[-1]
                atr_h1 = AverageTrueRange(df_h1["High"], df_h1["Low"], df_h1["Close"], 14).average_true_range().iloc[-1]
                
                # --- LOGIQUE DE TENDANCE FORTE ---
                trend_bull = close_d1 > ema200_d1 and ema50_h4 > ema200_h4 and close_h1 > ema50_h4 and adx_h4 >= 25
                trend_bear = close_d1 < ema200_d1 and ema50_h4 < ema200_h4 and close_h1 < ema50_h4 and adx_h4 >= 25
                
                signal = "ATTENDRE"
                sl, tp, rr = None, None, 0
                comment = "Analyse en cours"

                # --- DÉTECTION PULLBACK H1 (Achat) ---
                if trend_bull:
                    if df_h1["Low"].iloc[-1] <= ema20_h1 * 1.001:
                        signal = "ACHAT 🚀"
                        low_h1 = df_h1["Low"].iloc[-5:].min()
                        sl = round(low_h1 - (atr_h1 * 0.6), 5)
                        tp = round(close_h1 + (abs(close_h1 - sl) * 1.8), 5)
                        comment = "Pullback haussier confirmé"
                    else:
                        comment = "Tendance UP - En attente de repli"

                # --- DÉTECTION PULLBACK H1 (Vente) ---
                elif trend_bear:
                    if df_h1["High"].iloc[-1] >= ema20_h1 * 0.999:
                        signal = "VENTE 🔻"
                        high_h1 = df_h1["High"].iloc[-5:].max()
                        sl = round(high_h1 + (atr_h1 * 0.6), 5)
                        tp = round(close_h1 - (abs(sl - close_h1) * 1.8), 5)
                        comment = "Pullback baissier confirmé"
                    else:
                        comment = "Tendance DOWN - En attente de repli"
                
                else:
                    if adx_h4 < 25: comment = "ADX trop faible (Range)"
                    elif close_d1 > ema200_d1 and close_h1 < ema50_h4: comment = "Correction H4 en cours"
                    else: comment = "Pas d'alignement Daily/H4"

                # --- VALIDATION RR ET ENREGISTREMENT ---
                if signal != "ATTENDRE":
                    risk = abs(close_h1 - sl)
                    reward = abs(tp - close_h1)
                    rr = round(reward / risk, 2)
                    
                    if rr >= 1.5 and name not in active_trades:
                        active_trades[name] = {"type": signal, "entry": close_h1, "sl": sl, "tp": tp, "rr": rr}
                        save_json(DB_FILE, active_trades)
                        
                        msg = f"🦅 SNIPER SWING V19\n{name} | {signal}\n\n🎯 Objectif: 1-4 jours\n💰 Entrée: {round(close_h1, 5)}\n🛑 SL: {sl}\n✅ TP: {tp}\n📊 RR: {rr}\n📈 ADX H4: {round(adx_h4,1)}"
                        send_telegram_msg(msg)

                results.append({
                    "Actif": name, "Signal": signal, "Prix": round(close_h1, 5),
                    "ADX H4": round(adx_h4, 1), "Commentaire": comment
                })

            except: continue
    return results

# ─────────────────────────────────────────────
# INTERFACE UTILISATEUR
# ─────────────────────────────────────────────
st.title("🦅 Sniper V19 — Swing Trend Following (1-4 Jours)")

# Bloc Statistiques
if history_trades:
    df_h = pd.DataFrame(history_trades)
    c1, c2, c3 = st.columns(3)
    winrate = (len(df_h[df_h["Résultat"] == "✅ WIN"]) / len(df_h)) * 100 if len(df_h) > 0 else 0
    c1.metric("Winrate Global", f"{round(winrate, 1)}%")
    c2.metric("Profit Cumulé", f"{round(df_h['RR'].sum(), 2)}R")
    c3.metric("Nombre de Trades", len(df_h))
    with st.expander("Voir l'historique détaillé"):
        st.table(df_h.tail(15))

# Tableau des signaux
st.header("🎯 Radar de Tendance (Triple Alignement)")
data_results = run_engine()
if data_results:
    st.dataframe(pd.DataFrame(data_results), use_container_width=True)
else:
    st.warning("Marché Forex fermé ou analyse en attente de données.")

# Barre latérale
with st.sidebar:
    st.info("Stratégie : Daily Trend + H4 ADX + H1 Pullback")
    if st.button("🗑 Réinitialiser Verrous"):
        if os.path.exists(DB_FILE): os.remove(DB_FILE)
        st.success("Verrous supprimés")
    if st.button("🔴 Effacer Historique"):
        if os.path.exists(HISTORY_FILE): os.remove(HISTORY_FILE)
        st.success("Historique vidé")
    if st.button("📩 Test Telegram"):
        send_telegram_msg("✅ Sniper V19 opérationnel")
        st.toast("Message envoyé")
