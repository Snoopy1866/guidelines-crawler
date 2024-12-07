import argparse
import concurrent.futures
import datetime
import logging
import os
import pickle
import requests
import sys
import threading

from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

from selenium import webdriver
from selenium.webdriver.firefox.webdriver import WebDriver
from selenium.webdriver.firefox.options import Options

from utils import GuidencePublishPage, get_guidence_publish_pages, get_accessories, render_markdown

# 创建一个线程锁
lock = threading.Lock()

# 配置 logging
logger = logging.getLogger()
logger.setLevel(logging.INFO)

console_handler = logging.StreamHandler()
console_handler.setLevel(logging.INFO)

formatter = logging.Formatter("%(asctime)s - %(levelname)s - %(message)s")
console_handler.setFormatter(formatter)

# logger.addHandler(file_handler)
logger.addHandler(console_handler)

# 要爬取的网页地址
MAX_PAGE: int = 62
url_collection: list[str] = ["https://www.cmde.org.cn/flfg/zdyz/index.html"]
url_collection.extend(list(map(lambda x: f"https://www.cmde.org.cn/flfg/zdyz/index_{x}.html", range(1, MAX_PAGE + 1))))

# 命令行参数
parser = argparse.ArgumentParser(description="Crawl guidance publish pages.")
parser.add_argument("--page", type=int, help="The page number to crawl.")
args = parser.parse_args()

TARGET_PAGE: int = args.page
if 0 <= TARGET_PAGE < MAX_PAGE:
    url_collection = [url_collection[TARGET_PAGE]]
else:
    logger.error(f"Invalid page number: {TARGET_PAGE}, it must >= 0 or <= {MAX_PAGE}.")
    sys.exit()

# 目标日期范围
start_date: datetime.date = datetime.date(2007, 1, 1)
end_date: datetime.date = datetime.date(2024, 12, 31)

# 线程池参数
max_workers: int = os.cpu_count() * 10
timeout: int = 60

# pickle 文件路径
guidence_pickle_path: str = "guidences.pickle"

# guidence-list.md 文件路径
guidence_list_path: str = "guidences-list.md"


# 创建 driver
def create_driver() -> WebDriver:
    options = Options()
    options.add_argument("--headless")
    options.add_argument("--disable-gpu")
    driver = webdriver.Firefox(options=options)
    driver.implicitly_wait(30)
    return driver


# 创建 session
def create_session() -> requests.Session:
    retry_strategy = Retry(
        total=10,
        status_forcelist=[443, 500, 502, 503, 504],
        backoff_factor=1,
    )
    adapter = HTTPAdapter(max_retries=retry_strategy)
    session = requests.Session()
    session.mount("http://", adapter)
    session.mount("https://", adapter)
    return session


# 获取指导原则发布页面
def fetch_page(url: str) -> list[GuidencePublishPage]:
    driver = create_driver()
    try:
        logger.info(f"正在从 {url} 获取页面")
        pages = get_guidence_publish_pages(url=url, start_date=start_date, end_date=end_date, driver=driver)
    except Exception as e:
        logger.error(f"Failed to fetch pages from {url}: {e}.")
        pages = []
    finally:
        driver.quit()
    return pages


# 打开每个指导原则发布页面，获取附件内容
def fetch_accessory(guidence_publish_page: GuidencePublishPage) -> None:
    driver = create_driver()
    try:
        url = guidence_publish_page.url
        logger.info(f"正在从 {url} 获取附件信息")
        guidence_publish_page.accessories = get_accessories(url=url, driver=driver)
    except Exception as e:
        logger.error(f"Failed to fetch accessories from {url}: {e}.")
    finally:
        driver.quit()


# 删除重复的文件
def remove_duplicate_files(save_path: str) -> None:
    with lock:
        if os.path.exists(save_path):
            save_dir = os.path.dirname(save_path)
            items = os.listdir(save_dir)
            for item in items:
                file_path = os.path.join(save_dir, item)
                if file_path != save_path and os.path.getsize(file_path) == os.path.getsize(save_path):
                    os.remove(file_path)
                    logger.info(f"删除重复文件 {file_path}")


# 下载附件
def download_accessory(guidence_publish_page: GuidencePublishPage) -> None:
    save_dir = os.path.join("guidences", guidence_publish_page.date.strftime("%Y-%m-%d"))
    os.makedirs(save_dir, exist_ok=True)

    for accessory in guidence_publish_page.accessories:
        if not accessory.is_valid:
            continue
        save_path = os.path.join(save_dir, accessory.purified_title)
        if os.path.exists(save_path):
            logger.info(f"File {save_path} already exists.")
            remove_duplicate_files(save_path)
            continue

        try:
            session = create_session()
            url = accessory.anchor_href
            logger.info(f"正在从 {url} 下载附件并保存至 {save_path}")
            with session.get(url, timeout=timeout, stream=True) as response:
                if response.status_code == 200:
                    with open(save_path, "wb") as f:
                        for chunk in response.iter_content(chunk_size=8192):
                            f.write(chunk)
                else:
                    logger.error(f"Failed to download {url}, status code: {response.status_code}.")
        except requests.exceptions.RequestException as e:
            logger.error(f"Failed to download {url}.")
            logger.error(e)
        finally:
            session.close()
            remove_duplicate_files(save_path)


def update_pickle_file(new_data: list[GuidencePublishPage], file_path: str) -> None:
    if os.path.exists(file_path):
        # 读取 pickle 文件
        with open(file_path, "rb") as f:
            old_data: list[GuidencePublishPage] = pickle.load(f)
        # 合并数据
        old_gpp_urls = [gpp.url for gpp in old_data]
        for new_gpp in new_data:
            if new_gpp.url not in old_gpp_urls:
                old_data.append(new_gpp)
            else:
                old_acc = old_data[old_gpp_urls.index(new_gpp.url)].accessories
                old_acc_urls = [acc.anchor_href for acc in old_acc]
                for new_acc in new_gpp.accessories:
                    if new_acc.anchor_href not in old_acc_urls:
                        old_acc.append(new_acc)
                    else:
                        old_acc[old_acc_urls.index(new_acc.anchor_href)] = new_acc
    else:
        old_data = new_data

    # 排序
    old_data.sort(key=lambda x: (-x.date.toordinal(), x.title))

    # 写入 pickle 文件
    with open(file_path, "wb") as f:
        pickle.dump(old_data, f)


def read_pickle_file(file_path: str) -> list[GuidencePublishPage]:
    if os.path.exists(file_path):
        with open(file_path, "rb") as f:
            return pickle.load(f)
    else:
        return []


def main():
    logger.info("启动浏览器...")

    guidence_publish_pages: list[GuidencePublishPage] = []

    # 第一步：获取指导原则页面
    with concurrent.futures.ThreadPoolExecutor(max_workers=max_workers) as executor:
        logger.info("开始获取页面...")
        futures = {executor.submit(fetch_page, url): url for url in url_collection}

        try:
            for future in futures:
                url = futures[future]
                try:
                    result = future.result(timeout=timeout)
                    guidence_publish_pages.extend(result)
                    logging.info(f"成功从 {url} 获取页面")
                except concurrent.futures.TimeoutError:
                    logger.error(f"Timeout occurred for fetching pages from {url}.")
                    future.cancel()
                except Exception as e:
                    logger.error(f"Failed to fetch pages from {url}: {e}.")
        except Exception as e:
            logger.error(f"An error occurred: {e}.")

    if not guidence_publish_pages:
        logger.info("没有找到任何页面")
        sys.exit()
    else:
        logger.info(f"找到 {len(guidence_publish_pages)} 个页面")

    # 第二步：获取附件
    with concurrent.futures.ThreadPoolExecutor(max_workers=max_workers) as executor:
        logger.info("开始获取附件信息...")
        futures = {
            executor.submit(fetch_accessory, guidence_publish_page): guidence_publish_page
            for guidence_publish_page in guidence_publish_pages
        }

        try:
            for future in futures:
                url = futures[future].url
                try:
                    future.result(timeout=timeout)
                    logging.info(f"成功从 {url} 获取附件信息")
                except concurrent.futures.TimeoutError:
                    logger.error(f"Timeout occurred for fetching accessories from {url}.")
                    future.cancel()
                except Exception as e:
                    logger.error(f"Failed to fetch accessories from {url}: {e}.")
        except Exception as e:
            logger.error(f"An error occurred: {e}.")

    # 第三步：下载附件
    with concurrent.futures.ThreadPoolExecutor(max_workers=max_workers) as executor:
        logger.info("开始下载附件...")
        futures = {
            executor.submit(download_accessory, guidence_publish_page): guidence_publish_page
            for guidence_publish_page in guidence_publish_pages
        }

        try:
            for future in futures:
                url = futures[future].url
                try:
                    future.result(timeout=timeout)
                    logging.info(f"成功从 {url} 下载附件")
                except concurrent.futures.TimeoutError:
                    logger.error(f"Timeout occurred for downloading accessories from {url}.")
                    future.cancel()
                except Exception as e:
                    logger.error(f"Failed to download accessories from {url}: {e}.")
        except Exception as e:
            logger.error(f"An error occurred: {e}.")

    # 更新 pickle 文件
    logger.info("更新 pickle 文件...")
    update_pickle_file(guidence_publish_pages, guidence_pickle_path)

    # 生成 Markdown 文件
    logger.info("生成 Markdown 文件...")
    render_markdown(read_pickle_file(guidence_pickle_path), guidence_list_path)

    logger.info("完成")


if __name__ == "__main__":
    main()
