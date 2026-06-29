from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from nikkei_dict import NIKKEI_225_TICKERS
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

# 🚀 接口 1：轻量级全量列表 (供前端轮播图或雷达池使用)
@app.get("/api/v1/stocks")
def get_all_stocks_lightweight():
    """
    返回日经 225 所有股票的基础信息，剔除庞大的 K 线数组，秒开。
    """
    stocks_db = load_local_data()
    all_stocks = []
    
    for ticker, data in stocks_db.items():
        if ticker not in NIKKEI_225_TICKERS:  # 过滤非日经225股票
            continue
        # 计算最新价和涨跌幅（提取 daily_data_1y 的最后两天）
        daily = data.get("daily_data_1y", [])
        if len(daily) >= 2:
            latest_price = daily[-1]["close"]
            prev_price = daily[-2]["close"]
            is_up = latest_price >= prev_price
            change_val = latest_price - prev_price
            change_pct = (change_val / prev_price) * 100
            
            all_stocks.append({
                "ticker": ticker,
                "nameKey": ticker, # 暂时用 ticker 代替，后续可接字典
                "price": latest_price,
                "prev_price": prev_price,
                "isUp": is_up,
                "change": f"{'+' if latest_price >= prev_price else ''}{round(change_val, 2)} ({round(change_pct, 2)}%)",
                "volatility_score": abs(change_pct) # 传给前端，前端自己排序
            })
            
    return {
        "success": True,
        "count": len(all_stocks),
        "data": all_stocks
    }

# 🚀 接口 2：单只股票详情 (供前端 StockChart 渲染使用)
@app.get("/api/v1/stocks/{ticker}")
def get_stock_detail(ticker: str):
    """
    获取单只股票的完整动静分离图表数据（含 1年日K + 10年周K）
    """
    ticker_upper = ticker.upper()
    stocks_db = load_local_data()
    
    if ticker_upper in stocks_db:
        return {
            "success": True,
            "data": stocks_db[ticker_upper]
        }
    
    raise HTTPException(status_code=404, detail="Stock not found")