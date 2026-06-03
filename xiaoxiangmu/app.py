from fastapi import FastAPI
from fastapi.responses import HTMLResponse
import pydantic
import requests
import math

app = FastAPI(title="体感温度计算器")

# ==================== 配置区域 ====================
# 替换为你刚申请的【Web服务】类型的 Key
AMAP_KEY = "baded245384adbd8ff635bdfcdb19dd9"


# ==================================================

# 定义前端传过来的数据格式
class LocationData(pydantic.BaseModel):
    longitude: float
    latitude: float


def calculate_apparent_temp(T: float, RH: float, V: float) -> float:
    """Steadman 体感温度公式"""
    e = (RH / 100.0) * 6.105 * math.exp((17.27 * T) / (237.7 + T))
    return round(T + 0.33 * e - 0.7 * V - 4.0, 1)


def get_comfort_level(AT: float) -> str:
    if AT < 0:
        return "极寒，极不舒适！请注意防冻。"
    elif 0 <= AT < 15:
        return "凉爽/寒冷，体感偏凉。建议穿厚外套。"
    elif 15 <= AT < 27:
        return "舒适。温度适宜，人体感觉最为清爽。"
    elif 27 <= AT < 32:
        return "闷热，稍有不适。请注意防暑多喝水。"
    elif 32 <= AT < 41:
        return "炎热，很不舒适！尽量避免长时间户外活动。"
    else:
        return "酷热，危险！有极高几率发生热射病！"


# 接口：接收经纬度，调用天气API并计算
@app.post("/api/weather")
def get_weather_and_apparent(data: LocationData):
    try:
        # 高德 Web 服务：通过经纬度抓取实时天气
        # 转换坐标格式为高德要求的 "经度,纬度"
        location_str = f"{round(data.longitude, 6)},{round(data.latitude, 6)}"

        # 1. 逆地理编码获取城市 adcode
        geo_url = f"https://restapi.amap.com/v3/geocode/regeo?key={AMAP_KEY}&location={location_str}"
        geo_res = requests.get(geo_url, timeout=5).json()
        if geo_res.get("status") != "1":
            return {"success": False, "msg": "逆地理编码失败"}

        address_component = geo_res["regeocode"]["addressComponent"]
        adcode = address_component["adcode"]
        province = address_component.get("province", "")
        city = address_component.get("city", "")
        if isinstance(city, list): city = ""  # 有些直辖市city为空列表

        # 2. 根据 adcode 获取天气
        weather_url = f"https://restapi.amap.com/v3/weather/weatherInfo?key={AMAP_KEY}&city={adcode}&extensions=base"
        w_res = requests.get(weather_url, timeout=5).json()

        if w_res.get("status") != "1" or not w_res.get("lives"):
            return {"success": False, "msg": "获取天气数据失败"}

        live = w_res["lives"][0]
        T = float(live["temperature"])
        RH = float(live["humidity"])

        # 风力转换
        wind_power_str = live.get("windpower", "0")
        V = float(wind_power_str.replace("≤", "")) if wind_power_str.isdigit() else 2.0

        # 3. 计算体感温度
        AT = calculate_apparent_temp(T, RH, V)
        desc = get_comfort_level(AT)

        return {
            "success": True,
            "location": f"{province}{city}",
            "temp": T,
            "humidity": RH,
            "wind": V,
            "apparent_temp": AT,
            "desc": desc
        }
    except Exception as e:
        return {"success": False, "msg": str(e)}


# 根路由：直接返回一个漂亮的、适配手机和电脑的前端单页面
@app.get("/", response_class=HTMLResponse)
def index():
    return """
    <!DOCTYPE html>
    <html>
    <head>
        <meta charset="UTF-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <title>智能体感温度计算器</title>
        <style>
            body { font-family: -apple-system, sans-serif; background: #f4f6f9; display: flex; justify-content: center; align-items: center; height: 100vh; margin: 0; }
            .card { background: white; padding: 30px; border-radius: 16px; box-shadow: 0 4px 20px rgba(0,0,0,0.08); width: 90%; max-width: 400px; text-align: center; }
            h2 { color: #333; margin-top: 0; }
            button { background: #007aff; color: white; border: none; padding: 12px 24px; font-size: 16px; border-radius: 8px; cursor: pointer; width: 100%; transition: background 0.2s; }
            button:hover { background: #0056b3; }
            #result { margin-top: 25px; display: none; text-align: left; background: #f8fafc; padding: 15px; border-radius: 8px; }
            .at-val { font-size: 32px; font-weight: bold; color: #ff3b30; text-align: center; margin: 10px 0; }
        </style>
    </head>
    <body>
        <div class="card">
            <h2>🌦️ 体感温度分析系统</h2>
            <p style="color:#666; font-size:14px;">本应用将申请您的浏览器定位权限，用以计算当前位置的体感温度。</p>
            <button onclick="getLocation()">获取当前位置体感</button>
            <div id="result">
                <div style="color:#666; font-size:14px;">当前位置: <span id="loc" style="color:#333;font-weight:bold;"></span></div>
                <div class="at-val" id="at">-- °C</div>
                <div style="font-size:14px; color:#555; text-align:center; margin-bottom:10px;" id="desc"></div>
                <hr style="border:0; border-top:1px solid #e2e8f0;">
                <div style="font-size:13px; color:#888;">实际气温: <span id="t"></span>°C | 湿度: <span id="rh"></span>%</div>
            </div>
        </div>
        <script>
            function getLocation() {
                if (navigator.geolocation) {
                    navigator.geolocation.getCurrentPosition(showPosition, showError);
                } else { alert("您的浏览器不支持地理定位。"); }
            }
            function showPosition(position) {
                const coords = { longitude: position.coords.longitude, latitude: position.coords.latitude };
                fetch('/api/weather', {
                    method: 'POST',
                    headers: {'Content-Type': 'application/json'},
                    body: JSON.stringify(coords)
                })
                .then(res => res.json())
                .then(data => {
                    if(data.success) {
                        document.getElementById('result').style.display = 'block';
                        document.getElementById('loc').innerText = data.location;
                        document.getElementById('at').innerText = data.apparent_temp + " °C";
                        document.getElementById('desc').innerText = data.desc;
                        document.getElementById('t').innerText = data.temp;
                        document.getElementById('rh').innerText = data.humidity;
                    } else { alert("出错了: " + data.msg); }
                });
            }
            function showError(error) { alert("定位失败，请确保您允许了网页获取位置权限。"); }
        </script>
    </body>
    </html>
    """