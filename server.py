# GPS 协议分析
# http://www.techbulo.com/2508.html
# https://blog.csdn.net/lzyzuixin/article/details/6161507
# https://www.cnblogs.com/happykoukou/p/5502517.html

# 错误解决：WARNING:  Unsupported upgrade request.
# http://www.04007.cn/article/977.html
import asyncio, serial, logging, time, os, random
import threading
from typing import Dict
from decimal import Decimal
from threading import Thread
from fastapi import FastAPI, WebSocket
from starlette.websockets import WebSocketState

if os.name == "nt":
    SERIAL_PORT = "COM18"
elif os.name == "posix":
    SERIAL_PORT = "/dev/ttyUSB0"
    os.system(f'sudo chmod 777 {SERIAL_PORT}')

logging.basicConfig(
    level=logging.NOTSET,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

clients = {}
gpsdata = {}
last_gpsdata = {}
ser = serial.Serial(port=SERIAL_PORT, baudrate=38400)
if not ser.is_open:
    ser.open()


def convert_coord(value):
    """将GPS值转换为度分秒形式
    Args:
        value(str): GPS读取的经度或纬度
    Returns:
        list: 度分秒列表
    """
    v1, v2 = value.split('.')
    v2_dec = Decimal(f'0.{v2}') * 60  # + Decimal(random.random())
    return [v1[:-2], v1[-2:], v2_dec.to_eng_string()]


def login(client_info: Dict[str, WebSocket]):
    if client_info.get("id") in clients.keys():
        try:
            clients.get(client_info.get("id")).close()
        except:
            pass
    clients.update(client_info)
    print('客户端数量：', len(clients.items()))


def get_coord():
    flag = 0
    while True:
        try:
            if ser.inWaiting():
                bin_data = ser.read_until()
                # print(bin_data)
                data = bin_data.decode().split(',')
                if data[0] == "$GNRMC":
                    cn_time = f"{int(data[1][:2])+8}{data[1][2:6]}".rjust(
                        6, '0')
                    cn_time = f"{cn_time[:2]}:{cn_time[2:4]}:{cn_time[4:]}"
                    date = data[9]
                    date = f"{date[4:]}-{date[2:4]}-{date[:2]}"
                    gpsdata.update({
                        "时间":
                        cn_time,
                        "纬度": [*convert_coord(data[3]), data[4]],
                        "经度": [*convert_coord(data[5]), data[6]],
                        "速度":
                        (Decimal(data[7]) * Decimal("1.85")).to_eng_string(),
                        "方位角":
                        data[8],
                        "日期":
                        date,
                    })
                    flag = flag | 0b1
                elif data[0] in ["$GPGGA", "$GNGGA"]:  # GPS定位或GPS与北斗混合定位
                    gpsdata.update({
                        "GPS状态": {
                            "0": "未定位",
                            "1": "非差分定位",
                            "2": "差分定位",
                            "3": "无效PPS",
                            "6": "正在估算"
                        }.get(data[6], "错误"),
                        "卫里数量": data[7],
                        "海拔": data[9],
                    })
                    flag = flag | 0b10
                elif data[0] == "$GPGSA":
                    gpsdata.update({
                        "PDOP综合位置精度因子":
                        data[15],
                        "HDOP水平精度因子":
                        data[16],
                        "VDOP垂直精度因子":
                        data[17].split('*')[0] if '*' in data[17] else '',
                    })
                    flag = flag | 0b100
                if flag == 0b111:
                    flag = 0
            else:
                time.sleep(0.3)
        except:
            pass


Thread(target=get_coord).start()

app = FastAPI()


@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    logging.disable(logging.DEBUG)
    await websocket.accept()

    async def send_coord():
        global last_gpsdata
        while True:
            try:
                asyncio.sleep(0.1)
                if gpsdata == last_gpsdata:
                    continue
                await websocket.send_json(gpsdata)
                last_gpsdata = gpsdata.copy()
                print(threading.current_thread)
            except Exception as ex:
                if websocket.client_state == WebSocketState.DISCONNECTED:
                    logger.info(f"websocket缓存子线程退出:{str(ex)}")
                    break
                logger.info(f"websocket缓存子线程出错:{str(ex)}")

    try:
        while True:
            # 监听前端传递的信息
            client_info = await websocket.receive_json()
            logger.info(('收到websocket客户端指令：', client_info))

            if client_info.get("cmd") == "login":
                login({client_info.get("id"): websocket})

            elif client_info.get("cmd") == "ping":
                await websocket.send_json({"ping": "pong"})

            elif client_info.get("cmd") == "startupdate":
                Thread(target=asyncio.run, args=(send_coord(), )).start()

    except Exception as ex:
        logger.error(f"websocket断开:{str(ex)}")
