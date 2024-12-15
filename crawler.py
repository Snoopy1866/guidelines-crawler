import argparse
import concurrent.futures
import datetime
import logging
import os
import sys


from utils import (
    GuidencePublishPage,
    fetch_page,
    fetch_accessory,
    download_accessory,
    update_pickle_file,
    read_pickle_file,
    render_markdown,
)


# 配置 logging
logger = logging.getLogger()
logger.setLevel(logging.INFO)

console_handler = logging.StreamHandler()
console_handler.setLevel(logging.INFO)

formatter = logging.Formatter("%(asctime)s - %(levelname)s - %(message)s")
console_handler.setFormatter(formatter)

logger.addHandler(console_handler)

# 要爬取的网页地址
MAX_PAGE: int = 62
url_collection: list[str] = ["https://www.cmde.org.cn/flfg/zdyz/index.html"]
url_collection.extend(list(map(lambda x: f"https://www.cmde.org.cn/flfg/zdyz/index_{x}.html", range(1, MAX_PAGE + 1))))


def main():
    # 命令行参数
    parser = argparse.ArgumentParser(description="Crawl guidance publish pages.")
    parser.add_argument("--page", type=int, help="The page number to crawl.")
    args = parser.parse_args()

    TARGET_PAGE: int = args.page
    if 0 <= TARGET_PAGE < MAX_PAGE:
        target_urls = [url_collection[TARGET_PAGE]]
    else:
        logger.error(f"Invalid page number: {TARGET_PAGE}, it must >= 0 and <= {MAX_PAGE}.")
        sys.exit(1)

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

    logger.info("启动浏览器...")

    guidence_publish_pages: list[GuidencePublishPage] = []

    # 第一步：获取指导原则页面
    with concurrent.futures.ThreadPoolExecutor(max_workers=max_workers) as executor:
        logger.info("开始获取页面...")
        futures = {executor.submit(fetch_page, url, start_date, end_date): url for url in target_urls}

        try:
            for future in futures:
                url = futures[future]
                try:
                    result = future.result(timeout=timeout)
                    guidence_publish_pages.extend(result)
                except concurrent.futures.TimeoutError:
                    logger.error(f"Timeout occurred for fetching pages from {url}.")
                    future.cancel()
                except Exception as e:
                    logger.error(f"Failed to fetch pages from {url}: {e}.")
                else:
                    logging.info(f"成功从 {url} 获取页面")
        except Exception as e:
            logger.error(f"An error occurred: {e}.")

    if not guidence_publish_pages:
        logger.info("没有找到任何页面")
        sys.exit(1)
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
                except concurrent.futures.TimeoutError:
                    logger.error(f"Timeout occurred for fetching accessories from {url}.")
                    future.cancel()
                    sys.exit(1)
                except Exception as e:
                    logger.error(f"Failed to fetch accessories from {url}: {e}.")
                    sys.exit(1)
                else:
                    logging.info(f"成功从 {url} 获取附件信息")
        except Exception as e:
            logger.error(f"An error occurred: {e}.")

    # 第三步：下载附件
    with concurrent.futures.ThreadPoolExecutor(max_workers=max_workers) as executor:
        logger.info("开始下载附件...")
        futures = {
            executor.submit(download_accessory, guidence_publish_page, timeout): guidence_publish_page
            for guidence_publish_page in guidence_publish_pages
        }

        try:
            for future in futures:
                url = futures[future].url
                try:
                    future.result(timeout=timeout)
                except concurrent.futures.TimeoutError:
                    logger.error(f"Timeout occurred for downloading accessories from {url}.")
                    future.cancel()
                except Exception as e:
                    logger.error(f"Failed to download accessories from {url}: {e}.")
                else:
                    logging.info(f"成功从 {url} 下载附件")
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
