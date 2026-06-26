import yfinance as yf
import pandas as pd
import json
import os
from config import TOKENS_WHITELIST

def clean_and_compress_data(ticker_symbol):
    print(f"正在处理股票: {ticker_symbol}...")
    ticker = yf.Ticker(ticker_symbol)
    
    # 1. 拉取1年日K (Daily Data for 1 Year)
    df_daily = ticker.history(period="1y", interval="1d")
    if df_daily.empty:
        return None
        
    # 只保留前端图表关心的字段：日期、收盘价、成交量
    # yfinance 的 index 是 Datetime，我们把它转成字符串
    df_daily = df_daily.reset_index()
    daily_list = []
    for _, row in df_daily.iterrows():
        daily_list.append({
            "date": row['Date'].strftime('%Y-%m-%d'),
            "close": round(float(row['Close']), 2),
            "volume": int(row['Volume'])
        })

    # 2. 拉取10年周K (Weekly Data for 10 Years)
    df_weekly = ticker.history(period="10y", interval="1wk")
    df_weekly = df_weekly.reset_index()
    weekly_list = []
    for _, row in df_weekly.iterrows():
        # 周K线有时候会有空值，做个简单判断
        if pd.isna(row['Date']) or pd.isna(row['Close']):
            continue
        weekly_list.append({
            "date": row['Date'].strftime('%Y-%m-%d'),
            "close": round(float(row['Close']), 2),
            "volume": int(row['Volume'])
        })

    # 3. 拼接成计划书中的“双周期高压缩 JSON”结构
    stock_json = {
        "ticker": ticker_symbol,
        "last_updated": pd.Timestamp.now().strftime('%Y-%m-%d %H:%M:%S'),
        "daily_data_1y": daily_list,
        "weekly_data_10y": weekly_list
    }
    return stock_json

def main():
    all_data = {}
    for ticker in TOKENS_WHITELIST:
        try:
            stock_data = clean_and_compress_data(ticker)
            if stock_data:
                all_data[ticker] = stock_data
        except Exception as e:
            print(f"处理 {ticker} 时发生错误: {e}")
            
    # 先把结果保存在本地的一个 json 文件里，方便后面 FastAPI 直接读取
    output_path = os.path.join(os.path.dirname(__file__), "mock_stock_data.json")
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(all_data, f, ensure_ascii=False, indent=4)
    print(f"🎉 成功！所有洗好的数据已保存在: {output_path}")

if __name__ == "__main__":
    main()