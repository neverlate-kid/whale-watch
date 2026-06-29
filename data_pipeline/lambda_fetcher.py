import json
import os
import boto3
import yfinance as yf
import requests
from datetime import datetime

# 假设你的 nikkei_dict.py 在同一级目录下
# 如果报错，请确保你已经正确导入了你的日经 225 字典
from nikkei_dict import nikkei225_dict 

# 环境变量读取 S3 桶名，默认使用你的桶名，请在 AWS Lambda 环境变量中配置 S3_BUCKET_NAME
BUCKET_NAME = os.environ.get('S3_BUCKET_NAME', '你的S3桶名称') 
s3 = boto3.client('s3')

def lambda_handler(event, context):
    try:
        # 1. 获取所有225只股票的代码
        tickers = list(nikkei225_dict.keys())
        # yfinance 要求代码之间用空格隔开，例如 "7203.T 9984.T"
        tickers_str = " ".join(tickers)

        # 2. 伪装请求头防封禁
        session = requests.Session()
        session.headers.update({
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            "Accept": "*/*",
        })

        print(f"开始批量抓取 {len(tickers)} 只股票最新数据...")
        
        # 3. 核心：批量拉取 (period="1d", interval="1m" 保证数据量最小，速度最快)
        data = yf.download(
            tickers_str, 
            period="1d", 
            interval="1m", 
            session=session, 
            group_by="ticker", 
            threads=True
        )

        # 4. 构建要存入 S3 的 JSON 结构
        market_data = {
            "last_updated": datetime.utcnow().isoformat() + "Z", # 记录 UTC 更新时间
            "stocks": {}
        }

        for ticker in tickers:
            try:
                # 检查 yfinance 是否成功返回了该股票的数据，并且数据不为空
                if ticker in data and not data[ticker].empty:
                    # 拿到今天最后一条 1 分钟线数据（即最新价）
                    latest_row = data[ticker].dropna().iloc[-1]
                    
                    market_data["stocks"][ticker] = {
                        "price": float(latest_row['Close']),
                        "volume": int(latest_row['Volume']),
                        "timestamp": str(latest_row.name)
                    }
            except Exception as e:
                # 某一只股票解析失败不影响全局
                print(f"解析 {ticker} 失败: {e}")

        # 5. 将结果转换为 JSON 字符串并推送到 AWS S3
        json_body = json.dumps(market_data)
        
        s3.put_object(
            Bucket=BUCKET_NAME,
            Key='latest_market_prices.json',
            Body=json_body,
            ContentType='application/json',
            CacheControl='max-age=60', # 允许 CDN / 前端缓存 60 秒
            # 如果你的 S3 没有开启强制 Object Writer ACLs disabled，可能需要开启 ACL:
            # ACL='public-read' 
        )

        print("成功推送到 S3！")
        return {
            'statusCode': 200,
            'headers': {'Content-Type': 'application/json'},
            'body': json.dumps({'message': 'Successfully updated market data.', 'count': len(market_data['stocks'])})
        }

    except Exception as e:
        print(f"发生致命错误: {e}")
        return {
            'statusCode': 500,
            'body': json.dumps(f"Error: {str(e)}")
        }

# 如果你想在本地直接跑 python lambda_function.py 测试并上传 S3，取消下面的注释：
# if __name__ == "__main__":
#     os.environ['AWS_PROFILE'] = 'default' # 确保本地配好了 aws cli 凭证
#     lambda_handler(None, None)