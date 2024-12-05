import concurrent.futures
import datetime
import logging
import os
import sys
import requests

from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

from selenium import webdriver
from selenium.webdriver.firefox.options import Options
from selenium.webdriver.firefox.webdriver import WebDriver

from utils import (
    GuidencePublishPage,
    get_guidence_publish_pages,
    get_accessories,
    jinja_render,
)

# 配置 logging
logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")

# 要爬取的网页地址
MAX_PAGE = 63
url_collection = ["https://www.cmde.org.cn/flfg/zdyz/index.html"]
url_collection.extend(list(map(lambda x: f"https://www.cmde.org.cn/flfg/zdyz/index_{x}.html", range(1, MAX_PAGE))))
url_collection = url_collection

# 目标日期范围
start_date = datetime.date(2007, 1, 1)
end_date = datetime.date(2024, 12, 31)

# 线程池参数
max_workers = os.cpu_count()
timeout = 60

# 浏览器参数
options = Options()
options.add_argument("--headless")
options.add_argument("--disable-gpu")

driver = webdriver.Firefox(options=options)
driver.implicitly_wait(10)


# 重试策略
retry_strategy = Retry(
    total=5,
    status_forcelist=[443, 500, 502, 503, 504],
    backoff_factor=1,
)
adapter = HTTPAdapter(max_retries=retry_strategy, pool_connections=50, pool_maxsize=50)
# 会话
session = requests.Session()
session.mount("http://", adapter)
session.mount("https://", adapter)


# 获取指导原则发布页面
def fetch_page(url: str) -> list[GuidencePublishPage]:
    try:
        logging.info(f"Fetching page: {url}")
        pages = get_guidence_publish_pages(url=url, start_date=start_date, end_date=end_date, driver=driver)
    except Exception as e:
        logging.error(f"Failed to fetch page {url}: {e}")
        pages = []
    return pages


# 打开每个指导原则发布页面，获取附件内容
def fetch_accessory(guidence_publish_page: GuidencePublishPage) -> None:
    try:
        url = guidence_publish_page.publish_page_url
        logging.info(f"Fetching accessories from {url}")
        guidence_publish_page.publish_page_accessories = get_accessories(url=url, driver=driver)
    except Exception as e:
        logging.error(f"Failed to fetch accessories from {url}: {e}")


# 下载附件
def download_accessory(guidence_publish_page: GuidencePublishPage, session: requests.Session) -> None:
    save_dir = os.path.join("guidences", guidence_publish_page.publish_page_date.strftime("%Y-%m-%d"))
    os.makedirs(save_dir, exist_ok=True)

    for accessory in guidence_publish_page.publish_page_accessories:
        save_path = os.path.join(save_dir, accessory.accessory_anchor_title)
        logging.info(f"Saving {accessory.accessory_anchor_title} to {save_path}")
        if os.path.exists(save_path):
            logging.info(f"File {save_path} already exists.")
            continue

        try:
            url = accessory.accessory_anchor_href
            logging.info(f"Downloading {url}")
            response = session.get(url, timeout=10)
            if response.status_code == 200:
                with open(save_path, "wb") as f:
                    f.write(response.content)
            else:
                logging.error(f"Failed to download {url}, status code: {response.status_code}")
        except requests.exceptions.RequestException as e:
            logging.error(f"Failed to download {url}")
            logging.error(e)


def main():
    logging.info("正在启动浏览器...")

    guidence_publish_pages: list[GuidencePublishPage] = []

    with concurrent.futures.ThreadPoolExecutor(max_workers=max_workers) as executor:
        # 第一步：获取指导原则页面
        futures = {executor.submit(fetch_page, url): url for url in url_collection}

        try:
            for future in concurrent.futures.as_completed(futures, timeout=timeout):
                url = futures[future]
                try:
                    guidence_publish_pages.extend(future.result())
                except Exception as e:
                    logging.error(f"Failed to fetch page {url}: {e}")
        except concurrent.futures.TimeoutError:
            for future, url in futures.items():
                if not future.done():
                    logging.error(f"Timeout occurred for fetching page {url}")

        # 排序
        guidence_publish_pages.sort(key=lambda x: x.publish_page_date, reverse=True)

        if not guidence_publish_pages:
            logging.info("没有找到页面。")
            sys.exit()
        else:
            logging.info(f"找到 {len(guidence_publish_pages)} 个页面。")

        # 第二步：获取附件
        futures = {
            executor.submit(fetch_accessory, guidence_publish_page): guidence_publish_page
            for guidence_publish_page in guidence_publish_pages
        }

        try:
            for future in concurrent.futures.as_completed(futures, timeout=timeout):
                guidence_publish_page = futures[future]
                try:
                    future.result()
                except Exception as e:
                    logging.error(f"Failed to fetch accessories from {guidence_publish_page.publish_page_url}: {e}")
        except concurrent.futures.TimeoutError:
            for future, guidence_publish_page in futures.items():
                if not future.done():
                    logging.error(f"Timeout occurred for fetching accessories {guidence_publish_page.publish_page_url}")

        # 第三步：下载附件
        futures = {
            executor.submit(download_accessory, guidence_publish_page, session): guidence_publish_page
            for guidence_publish_page in guidence_publish_pages
        }

        try:
            for future in concurrent.futures.as_completed(futures, timeout=timeout):
                guidence_publish_page = futures[future]
                try:
                    future.result()
                except Exception as e:
                    logging.error(f"Failed to download accessories from {guidence_publish_page.publish_page_url}: {e}")
        except concurrent.futures.TimeoutError:
            for future, guidence_publish_page in futures.items():
                if not future.done():
                    logging.error(
                        f"Timeout occurred for downloading accessories {guidence_publish_page.publish_page_url}"
                    )

    guidence_publish_pages

    # 生成 Markdown 文件
    jinja_render(guidence_publish_pages)
    logging.info("已完成。")


if __name__ == "__main__":
    main()
