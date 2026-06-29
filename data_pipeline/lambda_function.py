import json
import os
import boto3
import yfinance as yf
import requests
from datetime import datetime, timedelta, timezone
from nikkei_dict import NIKKEI_225_DICT

BUCKET_NAME = os.environ.get('S3_BUCKET_NAME', '你的S3桶名称') 
s3 = boto3.client('s3')

# 定义日本标准时间 (JST = UTC+9)
JST = timezone(timedelta(hours=9))

def is_market_open():
    """判断当前时间日本股市是否开盘 (或处于需要抓取收盘数据的缓冲期)"""
    now_jst = datetime.now(JST)
    
    # 1. 过滤周末 (5=周六, 6=周日)
    if now_jst.weekday() >= 5:
        return False
        
    # 2. 东京证券交易所交易时间：09:00 - 15:30
    # 我们将抓取时间放宽到 09:00 - 15:35，以确保能抓取到 15:30 最后一秒的最终收盘价
    market_start = now_jst.replace(hour=9, minute=0, second=0, microsecond=0)
    market_end = now_jst.replace(hour=15, minute=35, second=0, microsecond=0)
    
    if market_start <= now_jst <= market_end:
        # 注: 日股在 11:30-12:30 是午休，为了代码简洁及应对盘中小幅波动修正，午休期间保持抓取也无妨
        return True
        
    return False

def lambda_handler(event, context):
    try:
        # 🌟 核心优化：休市期间直接终止执行，零资源消耗
        if not is_market_open():
            print("当前为非交易时段，跳过抓取任务。")
            return {
                'statusCode': 200,
                'body': json.dumps({'message': 'Market is closed, skipping.'})
            }

        tickers = list(NIKKEI_225_DICT.keys())
        tickers_str = " ".join(tickers)

        session = requests.Session()
        session.headers.update({
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            "Accept": "*/*",
        })

        print(f"市场处于交易中，开始抓取 {len(tickers)} 只股票...")
        
        data = yf.download(
            tickers_str, 
            period="1d", 
            interval="1m", 
            session=session, 
            group_by="ticker", 
            threads=True
        )

        market_data = {
            "last_updated": datetime.utcnow().isoformat() + "Z",
            "stocks": {}
        }

        for ticker in tickers:
            try:
                if ticker in data and not data[ticker].empty:
                    latest_row = data[ticker].dropna().iloc[-1]
                    market_data["stocks"][ticker] = {
                        "price": float(latest_row['Close']),
                        "volume": int(latest_row['Volume']),
                        "timestamp": str(latest_row.name)
                    }
            except Exception as e:
                pass # 忽略单只股票解析错误

        json_body = json.dumps(market_data)
        
        s3.put_object(
            Bucket=BUCKET_NAME,
            Key='latest_market_prices.json',
            Body=json_body,
            ContentType='application/json',
            CacheControl='max-age=60'
        )

        print("收盘价/实时价 成功推送到 S3！")
        return {
            'statusCode': 200,
            'body': json.dumps({'message': 'Success'})
        }

    except Exception as e:
        print(f"Error: {e}")
        return {
            'statusCode': 500,
            'body': json.dumps(f"Error: {str(e)}")
        }