import os
import yfinance as yf
import pandas as pd
from dotenv import load_dotenv, find_dotenv
from supabase import create_client, Client
from nikkei_dict import NIKKEI_225_DICT
import time

# 加载环境变量 (确保根目录有 .env 文件)
load_dotenv(find_dotenv())

# 初始化 Supabase 客户端
SUPABASE_URL = os.environ.get("SUPABASE_URL")
SUPABASE_SERVICE_KEY = os.environ.get("SUPABASE_SERVICE_ROLE_KEY")

# 生产环境预警保护
if not SUPABASE_URL or not SUPABASE_SERVICE_KEY:
    print("⚠️ 致命错误: 未检测到 Supabase 环境变量，脚本停止运行。")
    exit(1)

db: Client = create_client(SUPABASE_URL, SUPABASE_SERVICE_KEY)

def get_stock_data(ticker_symbol):
    """
    抓取、清洗并计算股票的完整数据
    """
    print(f"正在处理: {ticker_symbol}...")
    ticker = yf.Ticker(ticker_symbol)
    
    # 拉取历史数据
    df_daily = ticker.history(period="1y", interval="1d")
    df_weekly = ticker.history(period="10y", interval="1wk")
    
    # 🚨 安全卫士 1：暴力清洗脏数据，彻底剔除含有 NaN 的行，防止数据库报错
    df_daily = df_daily.dropna(subset=['Close', 'Volume'])
    df_weekly = df_weekly.dropna(subset=['Close', 'Volume'])
    
    if df_daily.empty or len(df_daily) < 2:
        print(f"⚠️ {ticker_symbol} 数据不足，跳过")
        return None
        
    # 计算基础指标
    latest_price = float(df_daily['Close'].iloc[-1])
    prev_price = float(df_daily['Close'].iloc[-2])
    
    # 🚨 安全卫士 2：防止除数为 0 的极端崩溃情况
    if prev_price == 0:
        return None
        
    change_val = latest_price - prev_price
    change_pct = (change_val / prev_price) * 100
    
    # 🌟 核心修复：使用 iterrows 确保 date, close, volume 三个字段一个不少！
    daily_list = []
    for d, row in df_daily.iterrows():
        daily_list.append({
            "date": d.strftime('%Y-%m-%d'),
            "close": round(float(row['Close']), 2),
            "volume": int(row['Volume'])
        })
        
    weekly_list = []
    for d, row in df_weekly.iterrows():
        weekly_list.append({
            "date": d.strftime('%Y-%m-%d'),
            "close": round(float(row['Close']), 2),
            "volume": int(row['Volume'])
        })

    # 准备写入数据库的摘要对象
    summary_data = {
        "ticker": ticker_symbol,
        "nameKey": ticker_symbol,
        "price": round(latest_price, 2),
        "prev_price": round(prev_price, 2),
        "isUp": latest_price >= prev_price,
        "change": f"{'+' if latest_price >= prev_price else ''}{round(change_val, 2)} ({round(change_pct, 2)}%)",
        "volatility_score": round(abs(change_pct), 2)
    }
    
    # 准备写入数据库的图表对象
    chart_data = {
        "ticker": ticker_symbol,
        "daily_data_1y": daily_list,
        "weekly_data_10y": weekly_list
    }
    
    return summary_data, chart_data

def main():
    tickers = list(NIKKEI_225_DICT.keys())
    print(f"🚀 开始同步 {len(tickers)} 只股票到 Supabase 云端数据库...")

    success_count = 0
    for ticker in tickers:
        try:
            data = get_stock_data(ticker)
            if data:
                summary, chart = data
                # 使用 upsert (存在则更新，不存在则插入)
                db.table("stocks_summary").upsert(summary).execute()
                db.table("ticker_charts").upsert(chart).execute()
                print(f"✅ [{success_count+1}] {ticker} 已同步")
                success_count += 1
                
            # 必须休眠防封禁
            time.sleep(0.5) 
        except Exception as e:
            print(f"❌ 同步 {ticker} 失败: {e}")

    print(f"🎉 同步任务结束！成功同步: {success_count}/{len(tickers)}")

if __name__ == "__main__":
    main()