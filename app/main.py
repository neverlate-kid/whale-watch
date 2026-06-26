from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
import json
import os

app = FastAPI(
    title="Whale Watch API",
    description="日股异动全球化警报系统的本地测试接口",
    version="1.0.0"
)

# 允许跨域（未来 React Native 模拟器联调必不可少）
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# 获取本地 JSON 数据的绝对路径
DATA_PATH = os.path.join(os.path.dirname(os.path.dirname(__file__)), "data_pipeline", "mock_stock_data.json")

def load_local_data():
    """辅助函数：从本地加载洗好的股票 JSON"""
    if not os.path.exists(DATA_PATH):
        return {}
    with open(DATA_PATH, "r", encoding="utf-8") as f:
        return json.load(f)

@app.get("/")
def root():
    return {
        "status": "healthy",
        "message": "Whale Watch 本地后端已成功启动！"
    }

@app.get("/api/v1/stocks/{ticker}")
def get_stock_chart(ticker: str):
    """
    获取单只股票的动静分离图表数据（1年日K + 10年周K）
    """
    # 统一转成大写，比如把 nintendo 变成 7974.T
    ticker_upper = ticker.upper()
    
    # 动态读取刚刚生成的 json 文件
    stocks_db = load_local_data()
    
    if ticker_upper in stocks_db:
        return {
            "success": True,
            "data": stocks_db[ticker_upper]
        }
    
    # 如果输入的股票代码不在 8 只白名单里，返回 404
    raise HTTPException(
        status_code=404, 
        detail=f"Stock {ticker_upper} not found in whitelist. Please check your config."
    )