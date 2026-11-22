import streamlit as st
import yfinance as yf
import pandas as pd
import numpy as np
import plotly.graph_objects as go
import requests
import os
from datetime import datetime
import streamlit.components.v1 as components

# Page Setup
st.set_page_config(page_title="Janta AI - Pro Confluence & Risk Analyzer", layout="wide")

st.markdown("""
<style>
.main {background-color: #0b0e11; color: #eaecef;}
div[data-testid="stMetric"] {background: #161a1e; border: 1px solid #f0b90b; border-radius: 10px; padding: 12px;}
div[data-testid="stMetricValue"] {color: #f0b90b !important; font-weight: 800;}
.stButton>button {background: #f0b90b; color: #000; font-weight: 900; width: 100%; height: 55px; font-size: 18px; border-radius: 10px; border: none;}
.stButton>button:hover {background: #d9a406; color: #000;}
</style>
""", unsafe_allow_html=True)

st.title("⚡ JANTA AI - PRO CONFLUENCE & RISK SYSTEM")
st.caption("Multi-Timeframe SMC + Liquidity Sweep + SharkFunded Risk Guard")

# Pairs Configuration: (Yahoo_Symbol, TradingView_Symbol, Binance_Symbol, Pip_Multiplier, Contract_Size)
PAIRS = {
    "XAUUSD (Spot Gold)": ("GC=F", "OANDA:XAUUSD", None, 10, 100),
    "XAGUSD (Spot Silver)": ("SI=F", "OANDA:XAGUSD", None, 100, 5000),
    "EURUSD": ("EURUSD=X", "OANDA:EURUSD", None, 10000, 100000),
    "GBPUSD": ("GBPUSD=X", "OANDA:GBPUSD", None, 10000, 100000),
    "USDJPY": ("USDJPY=X", "OANDA:USDJPY", None, 100, 100000),
    "AUDUSD": ("AUDUSD=X", "OANDA:AUDUSD", None, 10000, 100000),
    "BTCUSD (Bitcoin)": ("BTC-USD", "BINANCE:BTCUSDT", "BTCUSDT", 1, 1),
    "ETHUSD (Ethereum)": ("ETH-USD", "BINANCE:ETHUSDT", "ETHUSDT", 1, 1),
    "SOLUSD (Solana)": ("SOL-USD", "BINANCE:SOLUSDT", "SOLUSDT", 10, 1),
    "XRPUSD (Ripple)": ("XRP-USD", "BINANCE:XRPUSDT", "XRPUSDT", 10000, 1),
}

TF_MAP = {"15m": "15", "1h": "60", "4h": "240", "1d": "D"}
HTF_MAP = {"15m": "1h", "1h": "4h", "4h": "1d", "1d": "1d"}

# 1. Real-time Live Price Fetcher
def get_live_price(pair_name, binance_sym, y_sym):
    headers = {"User-Agent": "Mozilla/5.0"}
    try:
        if "XAUUSD" in pair_name:
            r = requests.get("https://gold-api.com", timeout=5, headers=headers).json()
            return float(r['price'])
        elif "XAGUSD" in pair_name:
            r = requests.get("https://gold-api.com", timeout=5, headers=headers).json()
            return float(r['price'])
        elif binance_sym:
            r = requests.get(f"https://binance.com{binance_sym}", timeout=5, headers=headers).json()
            return float(r['price'])
        else:
            df = yf.download(y_sym, period="1d", interval="1m", progress=False)
            if isinstance(df.columns, pd.MultiIndex):
                df.columns = df.columns.get_level_values(0)
            if not df.empty:
                return float(df['Close'].iloc[-1])
    except Exception:
        return None
    return None

# 2. Accurate Historical Candles Loader (Binance Direct for Crypto, Adjusted Yahoo for Forex/Metals)
@st.cache_data(ttl=30)
def fetch_candles(pair_name, tf):
    y_sym, _, binance_sym, _, _ = PAIRS[pair_name]
    
    # Direct Binance Klines for accurate Crypto charts
    if binance_sym:
        try:
            url = f"https://binance.com{binance_sym}&interval={tf}&limit=200"
            data = requests.get(url, timeout=6).json()
            df = pd.DataFrame(data, columns=[
                'OpenTime', 'Open', 'High', 'Low', 'Close', 'Volume',
                'CloseTime', 'QuoteAssetVol', 'Trades', 'TakerBuyBase', 'TakerBuyQuote', 'Ignore'
            ])
            df['Date'] = pd.to_datetime(df['OpenTime'], unit='ms')
            df.set_index('Date', inplace=True)
            for col in ['Open', 'High', 'Low', 'Close', 'Volume']:
                df[col] = df[col].astype(float)
            return df[['Open', 'High', 'Low', 'Close', 'Volume']]
        except Exception:
            pass

    # Yahoo Finance for Metals & Forex
    try:
        period = "15d" if tf in ["15m", "1h"] else "90d"
        df = yf.download(y_sym, period=period, interval=tf, auto_adjust=True, progress=False)
        if isinstance(df.columns, pd.MultiIndex):
            df.columns = df.columns.get_level_values(0)
        return df.dropna()
    except Exception:
        return pd.DataFrame()

# 3. Save History
def save_trade_log(pair, tf, mp, sl, tp1, tp2, bias, conf_pct, lot_size):
    file = "janta_ai_logs.csv"
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    row = pd.DataFrame([{
        "Time": now, "Pair": pair, "TF": tf, "Price": round(mp, 4),
        "Bias": bias, "Confluence%": conf_pct, "SL": round(sl, 4),
        "TP1": round(tp1, 4), "TP2": round(tp2, 4), "Safe_Lot": lot_size
    }])
    if os.path.exists(file):
        try:
            old = pd.read_csv(file)
            row = pd.concat([old, row], ignore_index=True)
        except Exception:
            pass
    row.to_csv(file, index=False)

# Sidebar: Risk Management Settings (Default tailored for $5,000 Account & $50 Max Floating Rule)
with st.sidebar:
    st.header("🛡️ Prop Account Risk Guard")
    acc_balance = st.number_input("Account Balance ($)", value=5000, step=500)
    max_risk_usd = st.number_input("Max Risk Per Trade ($)", value=25, min_value=5, max_value=50, help="SharkFunded 1% Floating Limit is $50. Keep risk at $20-$25 for safety.")
    rr_ratio = st.selectbox("Target Risk:Reward", [2.0, 2.5, 3.0], index=0)
    st.info("⚠️ **Rule Reminder:** 1% Max Floating Rule ($50) se bachne ke liye hamesha calculated Safe Lot Size hi use karein.")

# Main Controls
col1, col2 = st.columns(2)
with col1:
    pair = st.selectbox("1. Trading Pair Chunein", list(PAIRS.keys()), index=0)
with col2:
    tf = st.selectbox("2. Timeframe Chunein (1h Recommended)", ["15m", "1h", "4h", "1d"], index=1)

y_sym, tv_sym, binance_sym, pip_mult, contract_size = PAIRS[pair]

if st.button("🔍 START MULTI-TIMEFRAME ANALYSIS"):
    with st.spinner("Live Price aur Smart Money Levels check ho rahe hain..."):
        live_mp = get_live_price(pair, binance_sym, y_sym)
        df = fetch_candles(pair, tf)
        htf = HTF_MAP[tf]
        df_htf = fetch_candles(pair, htf)

        if df.empty or len(df) < 30:
            st.error("Chart data load nahi ho paya. Kripya 5 second baad dobara koshish karein.")
            st.stop()

        # Sync Spot Price accurately with Futures/Yahoo candles
        chart_last = float(df['Close'].iloc[-1])
        mp = live_mp if (live_mp and live_mp > 0) else chart_last
        offset = mp - chart_last
        for col in ['Open', 'High', 'Low', 'Close']:
            df[col] = df[col] + offset

        c, h, l, o = df['Close'], df['High'], df['Low'], df['Open']
        last = float(c.iloc[-1])

        # Core Indicators (ATR, EMA, RSI)
        ema20 = c.ewm(span=20, adjust=False).mean()
        ema50 = c.ewm(span=50, adjust=False).mean()
        tr = pd.concat([h - l, (h - c.shift(1)).abs(), (l - c.shift(1)).abs()], axis=1).max(axis=1)
        atr = tr.ewm(alpha=1/14, adjust=False, min_periods=14).mean()
        atr_v = float(atr.iloc[-1]) if not pd.isna(atr.iloc[-1]) else float((h.iloc[-14:].max() - l.iloc[-14:].min()) / 14)

        delta = c.diff()
        gain = delta.clip(lower=0).ewm(alpha=1/14, adjust=False).mean()
        loss = (-delta.clip(upper=0)).ewm(alpha=1/14, adjust=False).mean()
        rsi = 100 - (100 / (1 + np.where(loss == 0, 100, gain / loss)))
        rsi_v = float(rsi[-1])

        # Higher Timeframe (HTF) Trend Check
        htf_bull, htf_bear = False, False
        if not df_htf.empty and len(df_htf) > 20:
            htf_c = df_htf['Close']
            htf_e20 = float(htf_c.ewm(span=20, adjust=False).mean().iloc[-1])
            htf_e50 = float(htf_c.ewm(span=50, adjust=False).mean().iloc[-1])
            if float(htf_c.iloc[-1]) > htf_e20 > htf_e50:
                htf_bull = True
            elif float(htf_c.iloc[-1]) < htf_e20 < htf_e50:
                htf_bear = True

        # Key Support & Resistance (Swing Highs/Lows)
        swing_high = float(h.iloc[-25:-2].max())
        swing_low = float(l.iloc[-25:-2].min())

        # Liquidity Sweep Detection (Stop Hunt)
        liq_bull, liq_bear = False, False
        prev_low_min = float(l.iloc[-20:-3].min())
        prev_high_max = float(h.iloc[-20:-3].max())
        # Price swept below previous low and closed back above it
        if (l.iloc[-2] < prev_low_min or l.iloc[-1] < prev_low_min) and last > prev_low_min:
            liq_bull = True
        # Price swept above previous high and closed back below it
        if (h.iloc[-2] > prev_high_max or h.iloc[-1] > prev_high_max) and last < prev_high_max:
            liq_bear = True

        # Unmitigated Fair Value Gaps (FVG)
        bull_fvgs, bear_fvgs = [], []
        for i in range(len(df) - 30, len(df) - 2):
            if i < 1: continue
            if h.iloc[i-1] < l.iloc[i+1] and (l.iloc[i+1] - h.iloc[i-1]) > atr_v * 0.4:
                if last > h.iloc[i-1]:
                    bull_fvgs.append((float(h.iloc[i-1]), float(l.iloc[i+1])))
            if l.iloc[i-1] > h.iloc[i+1] and (l.iloc[i-1] - h.iloc[i+1]) > atr_v * 0.4:
                if last < l.iloc[i-1]:
                    bear_fvgs.append((float(h.iloc[i+1]), float(l.iloc[i-1])))

        # Order Block (Last opposing candle before strong move)
        bull_ob, bear_ob = None, None
        for i in range(len(df) - 15, len(df) - 2):
            if c.iloc[i] < o.iloc[i] and c.iloc[i+1] > o.iloc[i+1] and c.iloc[i+2] > h.iloc[i]:
                bull_ob = (float(l.iloc[i]), float(h.iloc[i]))
            if c.iloc[i] > o.iloc[i] and c.iloc[i+1] < o.iloc[i+1] and c.iloc[i+2] < l.iloc[i]:
                bear_ob = (float(l.iloc[i]), float(h.iloc[i]))

        # Confluence Scoring System (Weighted towards Reversal/SMC rather than lagging EMAs)
        bull_pts, bear_pts = 0, 0
        reasons = []

        if htf_bull:
  
