import datetime
import os
import requests

from selenium import webdriver
from selenium.webdriver.common.by import By

driver = webdriver.Firefox()
driver.implicitly_wait(10)

# 指导原则页面 url
url = "https://www.cmde.org.cn/flfg/zdyz/index.html"

# 指导原则页面右侧列表元素的选择器
list_item = selector = ".list li:has(a[href$='.html'])"
list_item_url = "a"

# 开始爬取
driver.get(url)
elements = driver.find_elements(by=By.CSS_SELECTOR, value=selector)


# 建立右侧条目清单
class GuidenceItem:
    def __init__(self, title: str, url: str, date: datetime.date):
        self.title = title
        self.url = url
        self.date = date


guidenceItemList: list[GuidenceItem] = []

for ele in elements:
    anchor_ele = ele.find_element(by=By.CSS_SELECTOR, value=list_item_url)

    title = anchor_ele.get_attribute("title")
    url = anchor_ele.get_attribute("href")
    date = datetime.datetime.strptime(
        ele.find_element(by=By.CSS_SELECTOR, value="span").text, "(%Y-%m-%d)"
    ).date()

    guidenceItemList.append(
        GuidenceItem(
            title,
            url,
            date,
        )
    )

# 打开每个指导原则页面，获取内容
for item in guidenceItemList:
    driver.get(item.url)
    ele = driver.find_elements(
        by=By.CSS_SELECTOR, value="a[href$='.doc'], a[href$='.docx']"
    )

    # 建立文件夹
    dir = os.path.join("guidence", item.date.strftime("%Y-%m-%d"))
    os.makedirs(dir, exist_ok=True)

    # 下载每个文件到对应日期的文件夹中
    for e in ele:
        download_link = e.get_attribute("href")
        download_title = e.get_attribute("title")
        print(f"Downloading {download_title}")

        # 发送 HTTP GET 请求下载文件
        response = requests.get(download_link)

        # 确保请求成功
        if response.status_code == 200:
            # 提取文件名
            file_name = os.path.join(dir, download_title)

            # 将文件保存到本地
            with open(file_name, "wb") as f:
                f.write(response.content)
            print(f"Downloaded {file_name}")
        else:
            print(f"Failed to download {download_link}")


driver.close()
