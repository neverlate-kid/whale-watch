import yfinance as yf
import pandas as pd
import json
import os
import time

# 动态获取日经225名单
def get_nikkei225_tickers():
    print("正在从维基百科抓取日经225最新成分股名单...")
    try:
        url = "https://en.wikipedia.org/wiki/Nikkei_225"
        # 提取页面中的所有表格
        tables = pd.read_html(url)
        # 通常成分股名单在第3个表格（索引为2）
        df = tables[2] 
        # 提取 Ticker 列，并加上 .T 后缀
        tickers = df['Ticker'].astype(str) + '.T'
        return tickers.tolist()
    except Exception as e:
        print(f"获取名单失败，请检查网络: {e}")
        # 如果失败，提供一个基础的备用列表保证流程不中断
        return ["7203.T", "9984.T", "8306.T", "6861.T", "9983.T"]

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

    nikkei_225_list = get_nikkei225_tickers()
    print(f"成功获取 {len(nikkei_225_list)} 只股票代码，开始拉取数据...")

    for i, ticker in enumerate(nikkei_225_list):
        print(f"[{i+1}/{len(nikkei_225_list)}] ", end="")
        try:
            stock_data = clean_and_compress_data(ticker)
            if stock_data:
                all_data[ticker] = stock_data
                
            # 关键防封禁：每次请求后强制休眠 0.5 到 1 秒
            # 如果没有这个，雅虎金融会立刻拉黑你正在运行脚本的 IP
            time.sleep(0.5) 
            
        except Exception as e:
            print(f"处理 {ticker} 时发生错误: {e}")
            time.sleep(2) # 报错的话多停一会儿
            
    # 保存结果
    output_path = os.path.join(os.path.dirname(__file__), "mock_stock_data.json")
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(all_data, f, ensure_ascii=False, indent=0) # indent=0 减小文件体积
    print(f"🎉 日经225全量数据处理完毕！保存在: {output_path}")

if __name__ == "__main__":
    main()