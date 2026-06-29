import os
import json
from fastapi import FastAPI, Depends, HTTPException, Security
from fastapi.middleware.cors import CORSMiddleware
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
import jwt
from nikkei_dict import NIKKEI_225_DICT

app = FastAPI(
    title="Whale Watch API",
    description="日股异动全球化警报系统 (Zero-Dollar Stack 本地过渡版)",
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

# ==========================================
# 📂 历史数据底座 (未来将迁移至 Supabase)
# ==========================================
DATA_PATH = os.path.join(os.path.dirname(os.path.dirname(__file__)), "data_pipeline", "mock_stock_data.json")

def load_local_data():
    """
    辅助函数：从本地加载 fetch_stocks.py 抓取的真实历史 K 线数据。
    TODO: 等 Supabase 数据库建好后，这个函数将替换为查询 Supabase 的 ticker_charts 表。
    """
    if not os.path.exists(DATA_PATH):
        print(f"⚠️ 警告: 找不到历史数据文件 {DATA_PATH}。请先运行 fetch_stocks.py")
        return {}
    with open(DATA_PATH, "r", encoding="utf-8") as f:
        return json.load(f)

# ==========================================
# 🔐 JWT 安全守卫 (Supabase Auth)
# ==========================================
security = HTTPBearer()

# TODO: 等配置好 Supabase 后，把 Project Settings -> API 里的 JWT Secret 填入环境变量
SUPABASE_JWT_SECRET = os.environ.get(
    "SUPABASE_JWT_SECRET", 
    "your-super-secret-jwt-token-with-at-least-32-characters-long" 
)

def get_current_user(credentials: HTTPAuthorizationCredentials = Security(security)):
    """
    核心鉴权依赖：解析前端通过 authFetch 传来的 Supabase JWT Token
    """
    token = credentials.credentials
    try:
        payload = jwt.decode(
            token, 
            SUPABASE_JWT_SECRET, 
            algorithms=["HS256"], 
            audience="authenticated"
        )
        return payload['sub'] # 返回用户的 UUID
    except jwt.ExpiredSignatureError:
        raise HTTPException(status_code=401, detail="登录已过期 (Token expired)")
    except jwt.InvalidTokenError:
        raise HTTPException(status_code=401, detail="无效的凭据 (Invalid token)")
    except Exception as e:
        raise HTTPException(status_code=401, detail=str(e))

# ==========================================
# 🟢 公开路由 (无需登录，供前端画图和列表使用)
# ==========================================

@app.get("/")
def root():
    return {
        "status": "healthy",
        "message": "Whale Watch 本地后端已成功启动！"
    }

@app.get("/api/v1/stocks")
def get_all_stocks_lightweight():
    """
    轻量级全量列表：供前端 Radar、搜索、首页轮播图使用。
    """
    stocks_db = load_local_data()
    all_stocks = []
    
    for ticker, data in stocks_db.items():
        if ticker not in NIKKEI_225_DICT:  
            continue
            
        daily = data.get("daily_data_1y", [])
        if len(daily) >= 2:
            latest_price = daily[-1]["close"]
            prev_price = daily[-2]["close"]
            is_up = latest_price >= prev_price
            change_val = latest_price - prev_price
            change_pct = (change_val / prev_price) * 100
            
            all_stocks.append({
                "ticker": ticker,
                "nameKey": ticker, 
                "price": latest_price,
                "prev_price": prev_price, 
                "isUp": is_up,
                "change": f"{'+' if latest_price >= prev_price else ''}{round(change_val, 2)} ({round(change_pct, 2)}%)",
                "volatility_score": abs(change_pct) 
            })
            
    return {
        "success": True,
        "count": len(all_stocks),
        "data": all_stocks
    }

@app.get("/api/v1/stocks/{ticker}")
def get_stock_detail(ticker: str):
    """
    单只股票详情：包含 1年日K 和 10年周K 庞大数组。
    """
    ticker_upper = ticker.upper()
    stocks_db = load_local_data()
    
    if ticker_upper in stocks_db:
        return {
            "success": True,
            "data": stocks_db[ticker_upper]
        }
    
    raise HTTPException(status_code=404, detail="Stock not found")

# ==========================================
# 🔴 私有路由 (必须携带 Token 才能访问)
# ==========================================

# 🌟 新增：前端初始化时拉取云端收藏夹
@app.get("/api/v1/user/favorites")
def get_user_favorites(user_id: str = Depends(get_current_user)):
    """
    获取用户的收藏夹列表
    """
    # TODO: 等 Supabase 建好，这里将替换为： SELECT ticker FROM user_favorites WHERE id = user_id
    print(f"✅ 安全验证通过！获取用户 UUID: {user_id} 的收藏夹数据")
    
    # 在数据库搭好前，安全降级返回测试数据供前端闭环联调
    return {
        "success": True, 
        "data": ["9983.T", "9984.T"] 
    }


@app.post("/api/v1/user/favorites")
def sync_user_favorites(
    favorites: list[str], 
    user_id: str = Depends(get_current_user) 
):
    """
    前端发生收藏操作时，同步覆盖到后端
    """
    # TODO: 等 Supabase 建好，这里将把 user_id 和 favorites 写进 Postgres 数据库
    print(f"✅ 安全验证通过！用户 UUID: {user_id} 正在云端同步收藏夹: {favorites}")
    
    return {"success": True, "message": "收藏夹云端同步成功"}