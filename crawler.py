import datetime

from selenium import webdriver

from utils import (
    GuidencePublishPage,
    get_guidence_publish_page_list,
    get_accessories_from_publish_page,
    jinja_render,
)


# 首页
homepage_url = "https://www.cmde.org.cn/flfg/zdyz/index.html"

# 目标日期范围
start_date = datetime.date(2007, 1, 1)
end_date = datetime.date(2024, 12, 31)

# 目标日期范围内的指导原则发布页列表
print("正在启动浏览器...")
guidence_publish_page_list: list[GuidencePublishPage] = get_guidence_publish_page_list(
    initial_page_url=homepage_url,
    start_date=start_date,
    end_date=end_date,
)
if not guidence_publish_page_list:
    print("未获取到页面。")
    exit(0)
else:
    print(f"找到 {len(guidence_publish_page_list)} 个页面。")
guidence_publish_page_list.sort(key=lambda x: x.publish_page_date, reverse=True)

# 打开每个指导原则发布页面，获取内容
print("等待重新启动浏览器...")
driver: webdriver.Firefox = webdriver.Firefox()
driver.implicitly_wait(10)

for guidence_publish_page in guidence_publish_page_list:
    get_accessories_from_publish_page(guidence_publish_page, driver)

driver.close()

# 生成 Markdown 文件
jinja_render(guidence_publish_page_list)
print("已完成。")
