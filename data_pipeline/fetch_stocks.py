import os
import time
import requests
import yfinance as yf
import pandas as pd
from dotenv import load_dotenv
from supabase import create_client, Client
from nikkei_dict import NIKKEI_225_DICT, get_name

# 加载环境变量 (确保根目录有 .env 文件)
if os.environ.get("AWS_EXECUTION_ENV") is None: load_dotenv()

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

def send_daily_push_notifications():
    """
    双轨制每日推送：
    1. 所有用户：大盘异动 Top 5
    2. 会员用户：其自选股内的异动 Top 5 (不足5个则全推)
    """
    print("🔔 正在准备双轨制每日收盘推送...")
    
    # 🌟 1. 抓取大盘异动 Top 5 (面向全员)
    res_global = db.table("stocks_summary").select("*").order("volatility_score", desc=True).limit(5).execute()
    global_top_movers = res_global.data
    if not global_top_movers: return

    # 🌟 2. 获取当天所有 225 只股票的最新数据作为“底层字典”，方便给会员算自选股
    res_all = db.table("stocks_summary").select("*").execute()
    all_stocks_dict = {s["ticker"]: s for s in res_all.data}

    # 🌟 3. 拉取全量用户的设备信息 (Token, 语言, 是否是Premium)
    users_res = db.table("user_devices").select("*").execute()
    if not users_res.data: return

    # 🌟 4. 拉取全量用户的自选股清单，并在内存中按用户分组
    fav_res = db.table("user_favorites").select("*").execute()
    user_favs = {}
    for row in fav_res.data:
        uid = row["user_id"]
        ticker = row["ticker"]
        # 只保留今天在底座库里有的股票
        if ticker in all_stocks_dict:
            if uid not in user_favs: user_favs[uid] = []
            user_favs[uid].append(all_stocks_dict[ticker])

    # 🌟 5. 多语言模板配置 (拆分大盘和自选两种模板)
    templates = {
        "zh": {
            "global_title": "大盘异动 Top 5 📊", "global_body": "今日波动最大：{tickers}。点击进入雷达榜！",
            "fav_title": "自选股异动警报 💎", "fav_body": "你的自选股中波动最大：{tickers}。点击查看详情！"
        },
        "en": {
            "global_title": "Market Top 5 Movers 📊", "global_body": "Highest volatility today: {tickers}. Tap to open Radar!",
            "fav_title": "Watchlist Alert 💎", "fav_body": "Biggest movers in your watchlist: {tickers}. Tap to view!"
        },
        "ja": {
            "global_title": "市場変動トップ 5 📊", "global_body": "本日の変動率上位：{tickers}。レーダーで確認！",
            "fav_title": "お気に入り変動アラート 💎", "fav_body": "お気に入り内の変動上位：{tickers}。タップして確認！"
        },
        "ko": {
            "global_title": "시장 변동성 Top 5 📊", "global_body": "오늘의 변동성 상위: {tickers}. 레이더에서 확인하세요!",
            "fav_title": "관심종목 변동 알림 💎", "fav_body": "관심종목 내 변동성 상위: {tickers}. 클릭하여 확인!"
        }
    }

    expo_messages = []
    
    # 🌟 6. 为每一位用户定制生成推送
    for user in users_res.data:
        token = user.get("push_token")
        if not token or not token.startswith("ExponentPushToken"): continue
            
        lang = user.get("language", "en")
        if lang not in templates: lang = "en"
        
        is_premium = user.get("is_premium", False)
        uid = user.get("user_id")
        
        # ----------------------------------------------------
        # 轨道 A: 生成面向【所有用户】的大盘推送
        # ----------------------------------------------------
        global_strs = []
        for stock in global_top_movers:
            company_name = get_name(stock["ticker"], lang)
            pct = stock["change"].split(" ")[-1]
            global_strs.append(f"{company_name}{pct}")
            
        expo_messages.append({
            "to": token, "sound": "default",
            "title": templates[lang]["global_title"],
            "body": templates[lang]["global_body"].format(tickers=", ".join(global_strs)),
            "data": {"url": "/radar"} # 点击进入雷达榜
        })

        # ----------------------------------------------------
        # 轨道 B: 生成面向【会员用户】的专属自选股推送
        # ----------------------------------------------------
        # 条件：是高级会员 + 用户有收藏记录
        if is_premium and uid in user_favs and len(user_favs[uid]) > 0:
            # 取出该用户的自选股，按当天的波动率(volatility_score)降序排列，并只截取前 5 名
            sorted_favs = sorted(user_favs[uid], key=lambda x: x['volatility_score'], reverse=True)[:5]
            
            fav_strs = []
            for stock in sorted_favs:
                company_name = get_name(stock["ticker"], lang)
                pct = stock["change"].split(" ")[-1]
                fav_strs.append(f"{company_name}{pct}")
                
            expo_messages.append({
                "to": token, "sound": "default",
                "title": templates[lang]["fav_title"],
                "body": templates[lang]["fav_body"].format(tickers=", ".join(fav_strs)),
                "data": {"url": "/favorites"} # 点击进入收藏页
            })

    # 🌟 7. 调用 Expo 接口批量发射
    if not expo_messages: return
    headers = {"Accept": "application/json", "Accept-encoding": "gzip, deflate", "Content-Type": "application/json"}
    
    for i in range(0, len(expo_messages), 100):
        batch = expo_messages[i:i+100]
        try:
            resp = requests.post("https://exp.host/--/api/v2/push/send", json=batch, headers=headers)
            print(f"✅ 推送批次 {i//100 + 1} 发送完毕 (共 {len(batch)} 条消息)")
        except Exception as e:
            print(f"❌ 推送失败: {e}")

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
    send_daily_push_notifications()

# ==========================================
# AWS Lambda 触发入口
# ==========================================
def lambda_handler(event, context):
    print("收到 Lambda 触发事件，开始执行每日同步任务...")
    main() # 调用主函数
    return {
        "statusCode": 200, 
        "body": "Daily Sync Complete"
    }

# ==========================================
# 本地测试触发入口
# ==========================================
if __name__ == "__main__":
    main()

