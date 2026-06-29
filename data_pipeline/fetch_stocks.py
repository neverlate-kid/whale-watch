import os
import yfinance as yf
import pandas as pd
from dotenv import load_dotenv
from supabase import create_client, Client
from nikkei_dict import NIKKEI_225_DICT
import time

# 加载环境变量 (确保根目录有 .env 文件)
load_dotenv()

# 初始化 Supabase 客户端
SUPABASE_URL = os.environ.get("SUPABASE_URL")
SUPABASE_SERVICE_KEY = os.environ.get("SUPABASE_SERVICE_ROLE_KEY")
db: Client = create_client(SUPABASE_URL, SUPABASE_SERVICE_KEY)

def get_stock_data(ticker_symbol):
    """
    抓取并计算股票的完整数据
    """
    print(f"正在处理: {ticker_symbol}...")
    ticker = yf.Ticker(ticker_symbol)
    
    # 拉取历史数据
    df_daily = ticker.history(period="1y", interval="1d")
    df_weekly = ticker.history(period="10y", interval="1wk")
    
    if df_daily.empty or len(df_daily) < 2:
        return None
        
    # 计算基础指标
    latest_price = float(df_daily['Close'].iloc[-1])
    prev_price = float(df_daily['Close'].iloc[-2])
    change_val = latest_price - prev_price
    change_pct = (change_val / prev_price) * 100
    
    # 格式化前端需要的 K 线数组
    daily_list = [{"date": d.strftime('%Y-%m-%d'), "close": round(float(c), 2)} 
                  for d, c in df_daily['Close'].items()]
    weekly_list = [{"date": d.strftime('%Y-%m-%d'), "close": round(float(c), 2)} 
                   for d, c in df_weekly['Close'].items()]

    # 准备写入数据库的数据对象
    summary_data = {
        "ticker": ticker_symbol,
        "nameKey": ticker_symbol,
        "price": round(latest_price, 2),
        "prev_price": round(prev_price, 2),
        "isUp": latest_price >= prev_price,
        "change": f"{'+' if latest_price >= prev_price else ''}{round(change_val, 2)} ({round(change_pct, 2)}%)",
        "volatility_score": round(abs(change_pct), 2)
    }
    
    chart_data = {
        "ticker": ticker_symbol,
        "daily_data_1y": daily_list,
        "weekly_data_10y": weekly_list
    }
    
    return summary_data, chart_data

def main():
    tickers = list(NIKKEI_225_DICT.keys())
    print(f"开始同步 {len(tickers)} 只股票到云端数据库...")

    for ticker in tickers:
        try:
            data = get_stock_data(ticker)
            if data:
                summary, chart = data
                # 写入到数据库 (生产环境正式使用 upsert)
                db.table("stocks_summary").upsert(summary).execute()
                db.table("ticker_charts").upsert(chart).execute()
                print(f"✅ {ticker} 已同步")
            time.sleep(0.5) # 防封禁
        except Exception as e:
            print(f"❌ 同步 {ticker} 失败: {e}")

if __name__ == "__main__":
    main()