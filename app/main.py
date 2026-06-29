import os
from fastapi import FastAPI, Depends, HTTPException, Security
from fastapi.middleware.cors import CORSMiddleware
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
import jwt
from supabase import create_client, Client
from dotenv import load_dotenv, find_dotenv
from nikkei_dict import NIKKEI_225_DICT
from mangum import Mangum
import urllib.request
import json
from deep_translator import GoogleTranslator

# 加载环境变量
load_dotenv(find_dotenv())

app = FastAPI(
    title="Whale Watch API",
    description="日股异动全球化警报系统 (正式生产环境版)",
    version="1.0.0"
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ==========================================
# ☁️ 正式版数据库初始化 (Supabase PostgreSQL)
# ==========================================
SUPABASE_URL = os.environ.get("SUPABASE_URL", "")
SUPABASE_SERVICE_KEY = os.environ.get("SUPABASE_SERVICE_ROLE_KEY", "")

# 生产环境：如果没有配置 Key，后端会以 None 状态启动并返回 500，提醒你配置
db: Client | None = None
if SUPABASE_URL and SUPABASE_SERVICE_KEY:
    db = create_client(SUPABASE_URL, SUPABASE_SERVICE_KEY)

# ==========================================
# 🔐 JWT 安全守卫
# ==========================================
security = HTTPBearer()
SUPABASE_JWT_SECRET = os.environ.get("SUPABASE_JWT_SECRET", "")

def get_current_user(credentials: HTTPAuthorizationCredentials = Security(security)):
    token = credentials.credentials
    if not SUPABASE_JWT_SECRET:
        raise HTTPException(status_code=500, detail="JWT Secret not configured")
        
    try:
        payload = jwt.decode(token, SUPABASE_JWT_SECRET, algorithms=["HS256"], audience="authenticated")
        return payload['sub']
    except Exception:
        raise HTTPException(status_code=401, detail="Invalid token")

# ==========================================
# 🚀 生产级接口
# ==========================================

@app.get("/api/v1/stocks")
def get_all_stocks():
    """
    生产环境：直接读取 Supabase 数据库汇总表
    """
    if not db:
        raise HTTPException(status_code=503, detail="Database not connected")
    
    try:
        # 直接读取 stocks_summary 表，这是你的 Python 爬虫 (fetch_stocks.py) 应该存入的地方
        res = db.table("stocks_summary").select("*").execute()
        return {"success": True, "data": res.data}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/v1/stocks/{ticker}")
def get_stock_detail(ticker: str):
    """
    生产环境：直接读取 Supabase 数据库详细数据表
    """
    if not db:
        raise HTTPException(status_code=503, detail="Database not connected")
        
    try:
        # 读取 ticker_charts 表
        res = db.table("ticker_charts").select("*").eq("ticker", ticker.upper()).execute()
        if not res.data:
            raise HTTPException(status_code=404, detail="Stock not found")
        return {"success": True, "data": res.data[0]}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
    
@app.get("/api/v1/stocks/{ticker}/news")
def get_stock_news(ticker: str, lang: str = "ja"):
    """
    零成本多语言新闻引擎：拉取雅虎新闻，并实时批量翻译为前端指定的语言
    """
    try:
        url = f"https://query2.finance.yahoo.com/v1/finance/search?q={ticker.upper()}&newsCount=8"
        req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
        
        with urllib.request.urlopen(req) as response:
            data = json.loads(response.read().decode())
            
        news_items = data.get('news', [])
        
        # 1. 语言映射映射表 (前端缩写 -> Google Translate 支持的代码)
        lang_map = {
            "zh": "zh-CN",
            "en": "en",
            "ja": "ja",
            "ko": "ko"
        }
        target_lang = lang_map.get(lang[:2], "en") # 默认回退到英文

        clean_news = []
        
        # 2. 提取所有需要翻译的标题 (为批量翻译做准备，极大提升速度)
        titles = [item.get("title", "") for item in news_items]
        
        # 3. 免费批量翻译引擎 (如果目标语言本来就是日语，雅虎日文版就无需翻译，节省算力)
        translated_titles = titles
        if target_lang != "ja" and titles:
            try:
                # source='auto' 会自动识别雅虎返回的是英文还是日文
                translated_titles = GoogleTranslator(source='auto', target=target_lang).translate_batch(titles)
            except Exception as e:
                print("翻译服务暂时拥堵，回退到原文:", e)
                
        # 4. 组装翻译后的数据
        for idx, item in enumerate(news_items):
            # 防止翻译失败导致数组越界，做个安全兜底
            final_title = translated_titles[idx] if idx < len(translated_titles) and translated_titles[idx] else item.get("title", "")
            
            clean_news.append({
                "title": final_title,
                "publisher": item.get("publisher"), # 媒体来源一般是专有名词，不强求翻译
                "link": item.get("link"),
                "publishTime": item.get("providerPublishTime")
            })
            
        return {"success": True, "data": clean_news}
    except Exception as e:
        return {"success": False, "data": [], "error": str(e)}

# ==========================================
# 🔴 私有路由
# ==========================================

@app.get("/api/v1/user/favorites")
def get_user_favorites(user_id: str = Depends(get_current_user)):
    """
    从 Supabase 实时拉取用户收藏
    """
    if not db:
        raise HTTPException(status_code=503, detail="Database not connected")
        
    res = db.table("user_favorites").select("ticker").eq("user_id", user_id).execute()
    favorites_list = [item["ticker"] for item in res.data]
    return {"success": True, "data": favorites_list}

@app.post("/api/v1/user/favorites")
def sync_user_favorites(favorites: list[str], user_id: str = Depends(get_current_user)):
    """
    将用户收藏同步存入 Supabase
    """
    if not db:
        raise HTTPException(status_code=503, detail="Database not connected")
        
    # 执行原子性删除与插入
    db.table("user_favorites").delete().eq("user_id", user_id).execute()
    if favorites:
        insert_data = [{"user_id": user_id, "ticker": t} for t in favorites]
        db.table("user_favorites").insert(insert_data).execute()
            
    return {"success": True, "message": "云端同步成功"}

# ==========================================
# 🚀 AWS Lambda 终极入口
# ==========================================
# 🌟 新增：将 FastAPI 应用包裹进 Mangum，作为 Lambda 的触发入口
handler = Mangum(app)