import hashlib
import json
import os
import ssl
import urllib
from datetime import datetime, timedelta
from os.path import split
from time import sleep
import asyncio

import requests
import websockets
import re
import tkinter as tk
from PIL import Image, ImageTk


class MySession(requests.Session):
    def request(self, *args, **kwargs):
        kwargs.setdefault('verify', False)
        return super().request(*args, **kwargs)


class SchoolLive:
    ppt_list = []
    existing_ppt_urls = set()
    client = MySession()

    @staticmethod
    def extract_tenant_code_from_set_cookie(tenant_code_cookie_str: str):
        return tenant_code_cookie_str.split(';')[0].split('=')[1]

    @staticmethod
    def extract_tenant_code_from_cookie(tenant_code_cookie_str: str):
        return json.loads(tenant_code_cookie_str.split("=")[1])["tenant_id"]

    @staticmethod
    def extract_token_from_cookie(serialized_str: str):
        """
        This function extracts the token from a serialized string, where the token is stored in a format
        similar to: i:1;s:<length>:"<token>".

        Args:
            serialized_str (str): The serialized string containing the token.

        Returns:
            tuple: A tuple containing the token length and the extracted token, or None if no token is found.
        """
        # Step 1: Use regex to find the token part dynamically based on length
        match = re.search(r'i:1;s:(\d+):"([^"]+)"', serialized_str)

        # Step 2: Extract the length and token if found
        if match:
            token = match.group(2)  # The token itself
            return token
        else:
            return None

    def __init__(self, cookie_header: str):
        super().__init__()
        token, tenant_code = self.get_token_from_cookie_header(cookie_header)
        self.client.headers.update({
            'User-Agent': "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/135.0.0.0 Safari/537.36",
            'Accept': "application/json, text/plain, */*",
            'Accept-Encoding': "gzip, deflate, br, zstd",
            'sec-ch-ua-platform': "\"macOS\"",
            'authorization': f"Bearer {token}",
            'accept-language': "zh_cn",
            'sec-ch-ua': "\"Google Chrome\";v=\"135\", \"Not-A.Brand\";v=\"8\", \"Chromium\";v=\"135\"",
            'sec-ch-ua-mobile': "?0",
            'sec-fetch-site': "same-origin",
            'sec-fetch-mode': "cors",
            'sec-fetch-dest': "empty",
            'priority': "u=1, i",
            'Cookie': cookie_header,
        })


    def display_image(self, image_path, window, label):
        # Open the image using Pillow
        img = Image.open(image_path)
        img_width, img_height = img.size

        # Set the maximum dimensions of the window
        max_width = 800
        max_height = 600

        # Calculate the scaling factor while maintaining the aspect ratio
        width_ratio = max_width / img_width
        height_ratio = max_height / img_height
        scale_factor = min(width_ratio, height_ratio)

        # Calculate the new dimensions
        new_width = int(img_width * scale_factor)
        new_height = int(img_height * scale_factor)

        # Resize the image
        img = img.resize((new_width, new_height))

        # Convert image to a Tkinter-compatible format
        photo = ImageTk.PhotoImage(img)

        # Update the label to show the new image
        label.config(image=photo)
        label.image = photo
        window.update()  # Refresh the window to show the new image


    def save_new_ppt_images(self, ppt_data, index, window, label):
        """
        Save the images from the ppt_data (which contains the image URL)
        to disk only if the URL is new. The filename will include the index.
        """
        ppt_directory = "ppt_images"
        os.makedirs(ppt_directory, exist_ok=True)

        # Check if the URL is new
        image_url = ppt_data['pptimgurl']
        if image_url and image_url not in self.existing_ppt_urls:
            # Download and save the image with an index in the filename
            image_name = f"{index}_{hashlib.md5(image_url.encode()).hexdigest()}.jpg"
            image_path = os.path.join(ppt_directory, image_name)

            # Download the image
            img_data = self.client.get(image_url).content
            with open(image_path, 'wb') as img_file:
                img_file.write(img_data)

            print(f"New image saved at {image_path}")

            # Add the URL to the set of existing URLs
            self.existing_ppt_urls.add(image_url)
            self.display_image(image_path, window, label)
        else:
            print(f"Image URL {image_url} already exists")

    def get_list(self, course_id: int, course_real_id: int, window, label):
        url = f"https://classroom.guet.edu.cn/pptnote/v1/schedule/search-ppt?course_id={course_id}&sub_id={course_real_id}&page=1&per_page=100"
        response = self.client.get(url)
        data = response.json()

        new_ppt_found = False  # Flag to track if any new PPTs were found

        print("ppt list length:", len(data['list']))
        print(f"ppt: {data["list"]}")
        for i, item in enumerate(data["list"]):
            item_content = json.loads(item["content"])
            image_url = item_content.get('pptimgurl')

            # Check if the image URL is new and different
            if image_url and image_url not in self.existing_ppt_urls:
                self.save_new_ppt_images(item_content, i+1, window=window, label=label)
                new_ppt_found = True  # Mark as found a new PPT
            # No need to print here, we're collecting results

        if new_ppt_found:
            print("发现并保存了新的PPT。")
        else:
            print("未检测到新的PPT（无差异）。跳过保存。")

    # Rest of the class remains unchanged...


    def get_pong_reply(self):
        reply_bytes = bytearray([
            0x00, 0x00, 0x00, 0x10, 0x00, 0x10, 0x00, 0x01,
            0x00, 0x00, 0x00, 0x02, 0x00, 0x00, 0x00, 0x01
        ])
        return reply_bytes

    def get_week_schedules(self, token: str, start_date: str, end_date: str, tenant_id: str, user_real_id: int):
        url = f"https://classroom.guet.edu.cn/courseapi/v2/schedule/get-week-schedules?user_id={user_real_id}&tenant_id={tenant_id}&start_at={start_date}&end_at={end_date}&token={token}"
        response = self.client.get(url)
        data = response.json()
        return data

    def get_info_simple(self):
        url = f"https://classroom.guet.edu.cn/userapi/v1/infosimple"
        response = self.client.get(url)
        data = response.json()
        return data

    def get_token(self) -> (str, str):
        url = f"https://classroom.guet.edu.cn/casapi/index.php?r=auth/login&forward=https%3A%2F%2Fclassroom.guet.edu.cn%2Fcoursepage&code=OC469928w7HzCFx3aCAKBPvKsxcngL2CyDDcyhW"
        response = self.client.get(url, allow_redirects=False)
        cookies = response.headers.get("set-cookie")
        print(cookies)
        token = None
        tenant_code = None
        for cookie in cookies:
            decoded_cookie = urllib.parse.unquote(cookie)
            if "_token" in cookie:
                token = SchoolLive.extract_token_from_cookie(decoded_cookie)
            if "tenant_code" in cookie:
                tenant_code = SchoolLive.extract_tenant_code_from_cookie(decoded_cookie)

        return token, tenant_code

    def get_token_from_cookie_header(self, cookie_header: str) -> (str, str):
        cookies = cookie_header.split(";")

        token = None
        tenant_code = None
        for cookie in cookies:
            decoded_cookie = urllib.parse.unquote(cookie)
            print("value:", decoded_cookie)
            if "_token" in cookie:
                token = SchoolLive.extract_token_from_cookie(decoded_cookie)
            if "tenant" in cookie:
                tenant_code = SchoolLive.extract_tenant_code_from_cookie(decoded_cookie)

        return token, tenant_code

    def get_pong_reply(self):
        reply_bytes = bytearray([
            0x00, 0x00, 0x00, 0x10, 0x00, 0x10, 0x00, 0x01,
            0x00, 0x00, 0x00, 0x02, 0x00, 0x00, 0x00, 0x01
        ])
        return reply_bytes

    async def start_ppt_listener(self, user_id: int, course_real_id: int, cookie: str):
        headers = {
            'User-Agent': "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/135.0.0.0 Safari/537.36",
            'Pragma': "no-cache",
            'Cache-Control': "no-cache",
            'Cookie': cookie,
        }
        ssl_context = ssl._create_unverified_context()
        async with websockets.connect("wss://classroom.guet.edu.cn/ws", additional_headers=headers, ssl=ssl_context) as websocket:
            header = bytearray([
                0x00, 0x00, 0x00, 0x5D, 0x00, 0x10, 0x00, 0x01,
                0x00, 0x00, 0x00, 0x07, 0x00, 0x00, 0x00, 0x01
            ])
            message = {
                "mid": user_id,
                "room_id": f"live_ppt://{course_real_id}",
                "platform": "web",
                "accepts": [course_real_id],
            }
            json_message = json.dumps(message).replace(" ","")
            json_message_bytes = json_message.encode('utf-8')
            combined_packet = header + json_message_bytes
            print("{:x}", combined_packet)
            await websocket.send(combined_packet)

            greeting = await websocket.recv()
            print(f"Received from server: {greeting}")
            greeting_ok = bytearray([
                0x00, 0x00, 0x00, 0x10, 0x00, 0x10, 0x00, 0x01,
            ])
            if greeting.startswith(greeting_ok):
                print("start_ppt_listener success")

                reply_bytes = self.get_pong_reply()

                # Send a message to the server
                await websocket.send(reply_bytes)

                ping_response = bytearray([
                    0x00, 0x00, 0x00, 0x14, 0x00, 0x10, 0x00, 0x01,
                ])
                new_ppt_header = bytearray([
                    0x00, 0x00, 0x01, 0xF1, 0x00, 0x10, 0x00, 0x01,
                ])
                while True:
                    response = await websocket.recv()

                    if response.startswith(ping_response):
                        print("ping pong")
                        reply_bytes = self.get_pong_reply()
                        await websocket.send(reply_bytes)
                        sleep(5)
                        continue

                    if response.startswith(new_ppt_header):
                        ppt_data = json.loads(response[32:])
                        print("new ppt:", json.dumps(ppt_data, indent=4))
                        continue

                    print("解析响应失败：{:x}", response)


def get_week_start_end():
    # Get today's date
    today = datetime.today()

    # Get the current week's Monday and Sunday
    monday = today - timedelta(days=today.weekday())  # Monday of this week
    sunday = monday + timedelta(days=6)  # Sunday of this week

    # Format the dates in 'yyyy-MM-dd' format
    monday_str = monday.strftime('%Y-%m-%d')
    sunday_str = sunday.strftime('%Y-%m-%d')

    return monday_str, sunday_str

def get_weekday_int():
    # Get today's date
    today = datetime.now().weekday()
    # Get the weekday (0 = Monday, 6 = Sunday)
    weekday_int = today
    return weekday_int

def get_course_id(week_schedules) -> (str, str):
    # Print week schedule details
    day = get_weekday_int() - 1
    day_schedule = week_schedules['result']['list'][day]
    for j, course in enumerate(day_schedule['course']):
        print(f"  Course {j+1}:")
        print(f"    Title: {course['course_title']}")
        print(f"    Teacher: {course['teacher_name']}")
        print(f"    Room: {course['room_name']}")
        print(f"    Start Time: {course['start_at']}")
        print(f"    End Time: {course['end_at']}")
        print()

    # Get user input for course selection
    course_index = int(input("输入课程索引（从1开始）："))

    # Retrieve the course_real_id and course_id based on input
    selected_course = week_schedules['result']['list'][day]['course'][course_index - 1]
    course_real_id = selected_course['id']
    course_id = selected_course['course_id']

    return int(course_id), int(course_real_id)

# Example usage
monday, sunday = get_week_start_end()
print("Monday:", monday)
print("Sunday:", sunday)

cookie = input("请从浏览器拷贝 cookie header 的值过来：").strip()
live = SchoolLive(cookie)
token, tenant_code = live.get_token_from_cookie_header(cookie)

print("token:", token)
print("tenant_code:", tenant_code)

user_info = live.get_info_simple()
user_id = int(user_info['params']['id'])

print("user_id:", user_id)

week_schedules = live.get_week_schedules(user_real_id=user_id, tenant_id=tenant_code, start_date=monday,
                                         end_date=sunday,
                                         token=token)

course_id, course_real_id = get_course_id(week_schedules)

# async def main():
#     await liveve.start_ppt_listener(user_id=user_id, course_real_id=course_real_id, cookie=live.client.headers.get("cookie"))

window = tk.Tk()
window.title("Latest PPT Viewer")
window.geometry("800x450")
# Label to show the PPT image
label = tk.Label(window)
label.pack()
while True:
    print("正在搜索ppt")
    live.get_list(course_id=course_id, course_real_id=course_real_id, window=window, label=label)
    sleep(1)

# asyncio.run(main())