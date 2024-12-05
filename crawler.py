import concurrent.futures
import datetime
import logging
import os
import requests

import colorlog

from requests.adapters import HTTPAdapter
from selenium.webdriver.firefox.webdriver import WebDriver
from urllib3.util.retry import Retry

from selenium import webdriver
from selenium.webdriver.firefox.options import Options

from utils import (
    GuidencePublishPage,
    get_guidence_publish_pages,
    get_accessories,
    jinja_render,
)

# 配置 colorlog
logger = logging.getLogger("my_logger")
logger.setLevel(logging.INFO)

handler = colorlog.StreamHandler()
handler.setFormatter(
    colorlog.ColoredFormatter(
        "%(log_color)s%(levelname)-8s%(reset)s %(blue)s%(message)s",  # 格式化日志输出
        datefmt=None,
        log_colors={
            "DEBUG": "blue",
            "INFO": "green",
            "WARNING": "yellow",
            "ERROR": "red",
            "CRITICAL": "bold_red",
        },
    )
)
logger.addHandler(handler)

# 要爬取的网页地址
MAX_PAGE = 63
url_collection = ["https://www.cmde.org.cn/flfg/zdyz/index.html"]
url_collection.extend(list(map(lambda x: f"https://www.cmde.org.cn/flfg/zdyz/index_{x}.html", range(1, MAX_PAGE))))
url_collection = url_collection[61:MAX_PAGE]

# 目标日期范围
start_date = datetime.date(2007, 1, 1)
end_date = datetime.date(2024, 12, 31)

# 线程池参数
max_workers = os.cpu_count()
timeout = 30

# 浏览器参数
options = Options()
options.add_argument("--headless")
options.add_argument("--disable-gpu")


# 浏览器实例的创建函数
def create_driver() -> WebDriver:
    driver = webdriver.Firefox(options=options)
    driver.implicitly_wait(5)
    return driver


# 重试策略
retry_strategy = Retry(
    total=3,
    status_forcelist=[443, 500, 502, 503, 504],
    backoff_factor=1,
)
adapter = HTTPAdapter(max_retries=retry_strategy)
# 会话
session = requests.Session()
session.mount("http://", adapter)
session.mount("https://", adapter)


# 获取指导原则发布页面
def fetch_page(url: str, driver: WebDriver) -> list[GuidencePublishPage]:
    driver = webdriver.Firefox(options=options)
    driver.implicitly_wait(5)
    try:
        logger.info(f"Fetching page: {url}")
        pages = get_guidence_publish_pages(url=url, start_date=start_date, end_date=end_date, driver=driver)
    except Exception as e:
        logger.error(f" Failed to fetch page {url}: {e}")
        pages = []
    finally:
        driver.close()
    return pages


# 打开每个指导原则发布页面，获取附件内容
def fetch_accessory(guidence_publish_page: GuidencePublishPage, driver: WebDriver) -> None:
    driver = webdriver.Firefox(options=options)
    driver.implicitly_wait(5)
    try:
        url = guidence_publish_page.publish_page_url
        logger.info(f"Fetching accessories from {url}")
        guidence_publish_page.publish_page_accessories = get_accessories(url=url, driver=driver)
    except Exception as e:
        logger.error(f"Failed to fetch accessories from {url}: {e}")
    finally:
        driver.close()


# 下载附件
def download_accessory(guidence_publish_page: GuidencePublishPage, session: requests.Session) -> None:
    save_dir = os.path.join("guidences", guidence_publish_page.publish_page_date.strftime("%Y-%m-%d"))
    os.makedirs(save_dir, exist_ok=True)

    for accessory in guidence_publish_page.publish_page_accessories:
        save_path = os.path.join(save_dir, accessory.accessory_anchor_title)
        logger.info(f"Saving {accessory.accessory_anchor_title} to {save_path}")
        if os.path.exists(save_path):
            logger.info(f"File {save_path} already exists.")
            return

        try:
            url = accessory.accessory_anchor_href
            logger.info(f"Downloading {url}")
            response = session.get(url, timeout=5)
            with open(save_dir, "wb") as f:
                f.write(response.content)
        except requests.exceptions.RequestException as e:
            logger.error(f"Failed to download {url}")
            logger.error(e)


def main():
    logger.info("正在启动浏览器...")

    guidence_publish_pages: list[GuidencePublishPage] = []

    with concurrent.futures.ThreadPoolExecutor(max_workers=max_workers) as executor:
        driver = create_driver()

        # 第一步：获取指导原则页面
        futures = {executor.submit(fetch_page, url, driver): url for url in url_collection}

        try:
            for future in concurrent.futures.as_completed(futures, timeout=timeout):
                url = futures[future]
                try:
                    guidence_publish_pages.extend(future.result())
                except Exception as e:
                    logger.error(f"Failed to fetch page {url}: {e}")
        except concurrent.futures.TimeoutError:
            for future, url in futures.items():
                if not future.done():
                    logger.error(f"Timeout occurred for fetching page {url}")

        # 排序
        guidence_publish_pages.sort(key=lambda x: x.publish_page_date, reverse=True)

        if not guidence_publish_pages:
            logger.info("没有找到页面。")
            exit()
        else:
            logger.info(f"找到 {len(guidence_publish_pages)} 个页面。")

        # 第二步：获取附件
        futures = {
            executor.submit(fetch_accessory, guidence_publish_page, driver): guidence_publish_page
            for guidence_publish_page in guidence_publish_pages
        }

        try:
            for future in concurrent.futures.as_completed(futures, timeout=timeout):
                guidence_publish_page = futures[future]
                try:
                    future.result()
                except Exception as e:
                    logger.error(f"Failed to fetch accessories from {guidence_publish_page.publish_page_url}: {e}")
        except concurrent.futures.TimeoutError:
            for future, guidence_publish_page in futures.items():
                if not future.done():
                    logger.error(f"Timeout occurred for fetching accessories {guidence_publish_page.publish_page_url}")

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
                    logger.error(f"Failed to download accessories from {guidence_publish_page.publish_page_url}: {e}")
        except concurrent.futures.TimeoutError:
            for future, guidence_publish_page in futures.items():
                if not future.done():
                    logger.error(
                        f"Timeout occurred for downloading accessories {guidence_publish_page.publish_page_url}"
                    )

    # 生成 Markdown 文件
    jinja_render(guidence_publish_pages)
    logger.info("已完成。")


if __name__ == "__main__":
    main()
