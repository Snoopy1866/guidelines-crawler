from __future__ import annotations

import dataclasses
import datetime
import logging
import os
import pickle
import re
import requests
import threading

from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.firefox.webdriver import WebDriver
from selenium.webdriver.firefox.options import Options

# 创建一个线程锁
lock = threading.Lock()

# 获取根日志记录器
logger = logging.getLogger()


@dataclasses.dataclass
class GuidencePublishPage:
    title: str
    url: str
    date: datetime.date
    accessories: list[Accessory]

    def __eq__(self, other: GuidencePublishPage) -> bool:
        return (
            self.title == other.title
            and self.url == other.url
            and self.date == other.date
            and self.accessories == other.accessories
        )


@dataclasses.dataclass
class Accessory:
    content: str = ""
    anchor_title: str = ""
    anchor_content: str = ""
    anchor_href: str = ""
    anchor_text_value: str = ""

    purified_title: str = ""
    is_valid: bool = True

    def __post_init__(self):
        self.content = self.content.strip()
        self.anchor_title = self.anchor_title.strip()
        self.anchor_content = self.anchor_content.strip()
        self.anchor_text_value = self.anchor_text_value.strip()
        self.purified_title = self.get_purified_title()
        self.check_valid()

    def __eq__(self, other: Accessory) -> bool:
        return (
            self.content == other.content
            and self.anchor_title == other.anchor_title
            and self.anchor_content == other.anchor_content
            and self.anchor_href == other.anchor_href
            and self.anchor_text_value == other.anchor_text_value
        )

    def check_valid(self) -> bool:
        """
        检查附件是否有效，无效附件将被过滤。
        """
        regex_filter_title_list = [
            re.compile(r"意见表"),
            re.compile(r"建议表"),
            re.compile(r"信息征集表"),
            re.compile(r"意见反馈表"),
            re.compile(r"联系方式"),
        ]

        if any([regex.search(self.purified_title) for regex in regex_filter_title_list]):
            logger.info(f"过滤附件：{self.purified_title}")
            self.is_valid = False

    def get_purified_title(self) -> str:
        """
        获取附件文件名处理的结果。
        """
        anchor_href = self.anchor_href

        content = self.content
        anchor_title = self.anchor_title
        anchor_content = self.anchor_content
        anchor_text_value = self.anchor_text_value

        # 定义预处理正则表达式
        regex_preprocess_list = [
            (re.compile(r"^(相关)?附件[：:]"), ""),
            (re.compile(r"^\d*[、]"), ""),
            (re.compile(r"\("), "（"),
            (re.compile(r"\)"), "）"),
        ]

        for pattern, repl in regex_preprocess_list:
            content = re.sub(pattern, repl, content)
            anchor_title = re.sub(pattern, repl, anchor_title)
            anchor_content = re.sub(pattern, repl, anchor_content)
            anchor_text_value = re.sub(pattern, repl, anchor_text_value)

        # 拆分文件名和扩展名
        _, file_extension = os.path.splitext(anchor_href)
        file_extension_without_dot = file_extension[1:]

        if re.search(r"通告(\d+号)?附件", anchor_title):
            # 如果 anchor_title 匹配 "通告\d+号附件"
            purified_title = content or anchor_text_value
        elif re.search(r"^附件\d+征求意见稿", anchor_title):
            # 如果 anchor_title 匹配 "^附件\d+征求意见稿"
            purified_title = content or anchor_text_value
        elif re.search(rf"^(附件)?\d*\.{file_extension_without_dot}$", anchor_title):
            # 如果 anchor_title 匹配 "^(附件)?\d+\.{file_extension_without_dot}$"
            purified_title = content or anchor_text_value
        elif anchor_title == "下载":
            # 如果 anchor_title 为 "下载"
            purified_title = content or anchor_text_value
        elif anchor_title == "":
            # 如果 anchor_title 为空
            purified_title = content or anchor_text_value

        if not purified_title:
            purified_title = anchor_content

        # 处理文件名中的多余字符
        # eg.
        # https://www.cmde.org.cn/flfg/zdyz/zqyjg/20230511105143123.html 附件3.7项体外诊断试剂修订指导原则.rar
        # https://www.cmde.org.cn/flfg/zdyz/fbg/fbgwy/20230814154949121.html 2023年通告32号 附件1牙科种植体系统同品种临床评价注册审查指导原则.doc
        # https://www.cmde.org.cn/flfg/zdyz/fbg/fbgwy/20230309105146187.html 附件1 牙科粘接剂产品注册审查指导原则.docx
        # https://www.cmde.org.cn/flfg/zdyz/fbg/fbgtwsj/20230302171913174.html \n特此通告。\n \n附件：\n1.新型冠状病毒（2019-nCoV）核酸检测试剂注册审查指导原则（下载）
        purified_title = re.sub(
            r"(.*(\n))*^(\d+年通告\d+号)?\s*(附件)?([-：．:\.\d\s]*)?(?!项)", "", purified_title, 0, re.M
        )

        # 删除“（下载）”
        purified_title = re.sub(r"（?下载）?", "", purified_title)

        # 删除开头的“（”或“）”
        purified_title = re.sub(r"^[（）]", "", purified_title)

        # 删除结尾的“（”或“）”
        if not re.search(r"（[^（）]+）$", purified_title):
            purified_title = re.sub(r"[（）]$", "", purified_title)

        # 删除书名号
        purified_title = re.sub(
            rf"^《(.+)》\s*(（征求意见稿）)?\s*(\.{file_extension_without_dot})?$", r"\1\2\3", purified_title
        )

        # 将文件名中的非法字符替换为连字符
        purified_title = re.sub(r"[\\/:*?\"<>|]", "-", purified_title)

        # 检查 title 是否有扩展名，没有则添加
        if not purified_title.endswith(file_extension):
            purified_title += file_extension

        # 如果最终的文件名为空，则使用 anchor_href 的最后一部分作为文件名
        if purified_title.replace(file_extension, "") == "":
            purified_title = anchor_href.split("/")[-1]

        return purified_title


def get_guidence_publish_pages(
    url: str,
    start_date: datetime.date,
    end_date: datetime.date,
    driver: WebDriver,
) -> list[GuidencePublishPage]:
    """
    获取目标日期范围内的指导原则发布页列表。

    Args:
        url (str): 目标 url。
        start_date (datetime.date): 目标起始日期。
        end_date (datetime.date): 目标结束日期。
        driver (WebDriver): WebDriver 实例。
    Returns:
        list[GuidencePublishPage]: 指导原则发布页列表。
    """

    driver.get(url)

    # 指导原则发布页列表
    guidence_publish_page_list: list[GuidencePublishPage] = []

    # 定义选择器
    selector_list_item = ".list li:has(a[href$='.html'])"

    if elements := driver.find_elements(by=By.CSS_SELECTOR, value=selector_list_item):
        # 如果当前页的发布日期均不在目标日期范围内，提前返回
        oldest_date_in_current_page = datetime.datetime.strptime(
            elements[-1].find_element(by=By.TAG_NAME, value="span").text, "(%Y-%m-%d)"
        ).date()
        newest_date_in_current_page = datetime.datetime.strptime(
            elements[0].find_element(by=By.TAG_NAME, value="span").text, "(%Y-%m-%d)"
        ).date()
        if oldest_date_in_current_page > end_date or newest_date_in_current_page < start_date:
            logger.info(f"页面 {url} 中找不到 {start_date} ~ {end_date} 期间发布的指导原则。")
        else:
            for element in elements:
                guidence_publish_page_anchor = element.find_element(by=By.TAG_NAME, value="a")

                guidence_publish_page_title = guidence_publish_page_anchor.get_attribute("title")
                guidence_publish_page_url = guidence_publish_page_anchor.get_attribute("href")
                guidence_publish_page_date = datetime.datetime.strptime(
                    element.find_element(by=By.TAG_NAME, value="span").text, "(%Y-%m-%d)"
                ).date()
                guidence_publish_page_accessories = []

                if start_date <= guidence_publish_page_date <= end_date:
                    guidence_publish_page_list.append(
                        GuidencePublishPage(
                            guidence_publish_page_title,
                            guidence_publish_page_url,
                            guidence_publish_page_date,
                            guidence_publish_page_accessories,
                        )
                    )
    else:
        logger.warning(f"页面 {url} 中找不到任何有效数据。")

    return guidence_publish_page_list


def get_accessories(url: str, driver: WebDriver) -> list[Accessory]:
    """
    获取单个页面的附件。

    Args:
        url (str): 单个页面的 url。
        driver (WebDriver): WebDriver 实例。
    """

    # 附件类型选择器列表
    file_extension_list = [
        ".doc",
        ".docx",
        ".xls",
        ".xlsx",
        ".zip",
        ".rar",
        ".pdf",
    ]

    # 打开指导原则发布页面
    driver.get(url)

    accessory_list: list[Accessory] = []

    # 类型1
    # https://www.cmde.org.cn/flfg/zdyz/zqyjg/20241128091030130.html
    # <p>
    #   xxx
    #   <a href="download_url" title="附件标题">下载</a>
    # </p>
    # 选择器：p:not(:has(span, img)):has(>a:only-of-type:where([href$='.doc'], [href$='.docx']))
    # 注意：<p> 标签内不包含 <span>, <img> 标签，以下页面不符合条件，不会被选中。
    # eg: https://www.cmde.org.cn/flfg/zdyz/fbg/fbgyy/20220429135956135.html
    # eg: https://www.cmde.org.cn/flfg/zdyz/fbg/fbgwy/20220118085047675.html
    selector_type_1 = (
        "p:not(:has(span)):has(>a:only-of-type:where("
        + ",".join(map(lambda x: f"a[href$='{x}']", file_extension_list))
        + ")"
    )

    # 类型2
    # https://www.cmde.org.cn/flfg/zdyz/zqyjg/20150430164400462.html
    # <span>
    #   <span>附件xxx</span>
    #   <span>附件标题</span>
    # </span>
    # <a href="download_url">下载</a>
    # 选择器：span:has(+a:where([href$='.doc'], [href$='.docx']))
    selector_type_2 = "span:has(+a:where(" + ",".join(map(lambda x: f"[href$='{x}']", file_extension_list)) + "))"

    # https://www.cmde.org.cn/flfg/zdyz/fbg/fbgyy/20140723155501232.html

    # 类型3
    # https://www.cmde.org.cn/flfg/zdyz/fbg/fbgyy/20211214162400496.html
    # https://www.cmde.org.cn/flfg/zdyz/fbg/fbgwy/20220118085047675.html
    # <p>
    #   <img>
    #   <a href="download_url">通告2号 附件1.doc</a>
    # </p>
    # 选择器：p:not(:has(span)) > img:only-of-type + a:only-of-type:where([href$='.docx'], [href$='.doc'])
    # 注意: <p> 标签内不包含 <span> 标签，以下页面不符合条件，不会被选中。
    # eg: https://www.cmde.org.cn/flfg/zdyz/fbg/fbgyy/20220429135956135.html
    selector_type_3 = (
        "p:not(:has(span)) > img:only-of-type + a:only-of-type:where("
        + ",".join(map(lambda x: f"[href$='{x}']", file_extension_list))
        + ")"
    )

    # 类型4
    # https://www.cmde.org.cn/flfg/zdyz/zqyjg/20120331134240363.html
    # <font></font>
    # <a href="download_url">
    #   <font>附件标题</font>
    # </a>
    # 选择器：a:where([href$='.doc'], [href$='.docx']):has(>font)
    selector_type_4 = "a:where(" + ",".join(map(lambda x: f"[href$='{x}']", file_extension_list)) + "):has(>font)"

    # 类型5
    # https://www.cmde.org.cn/flfg/zdyz/zqyjg/20221226164621102.html
    # <br>
    # 附件标题
    # <a href="download_url">下载</a>
    # 选择器：br:has(+a:where([href$='.doc'], [href$='.docx']))
    selector_type_5 = "br:has(+a:where(" + ",".join(map(lambda x: f"[href$='{x}']", file_extension_list)) + "))"

    # 类型6
    # https://www.cmde.org.cn/flfg/zdyz/fbg/fbgyy/20220429135956135.html
    # <span>附件标题</span>
    # <img>
    # <a href="download_url">下载</a>
    # 选择器：span:has(+img + a:where([href$='.doc'], [href$='.docx']))
    selector_type_6 = "span:has(+img + a:where(" + ",".join(map(lambda x: f"[href$='{x}']", file_extension_list)) + "))"

    # 类型7
    # https://www.cmde.org.cn/flfg/zdyz/zqyjg/20220623164120132.html
    # <br>
    # 附件标题
    # <img>
    # <a href="download_url">下载</a>
    # 选择器：br:has(+img + a:where([href$='.doc'], [href$='.docx']))
    selector_type_7 = "br:has(+img + a:where(" + ",".join(map(lambda x: f"[href$='{x}']", file_extension_list)) + "))"

    # 类型8
    # https://www.cmde.org.cn/flfg/zdyz/zqyjg/20100212074430257.html
    # <a href="download_url">附件标题</a>
    # 选择器：a:where([href$='.doc'], [href$='.docx'])
    selector_type_8 = "a:where(" + ",".join(map(lambda x: f"[href$='{x}']", file_extension_list)) + ")"

    if elements := driver.find_elements(by=By.CSS_SELECTOR, value=selector_type_1):
        for element in elements:
            content = element.text
            anchor = element.find_element(by=By.TAG_NAME, value="a")
            anchor_title = anchor.get_attribute("title")
            anchor_href = anchor.get_attribute("href")
            anchor_text_value = anchor.get_attribute("textvalue") or ""
            anchor_content = anchor.text
            accessory_list.append(Accessory(content, anchor_title, anchor_content, anchor_href, anchor_text_value))
    elif elements := driver.find_elements(by=By.CSS_SELECTOR, value=selector_type_2):
        for element in elements:
            content = element.text
            anchor = element.find_element(by=By.XPATH, value="following-sibling::a")
            anchor_title = anchor.get_attribute("title")
            anchor_href = anchor.get_attribute("href")
            anchor_text_value = anchor.get_attribute("textvalue") or ""
            anchor_content = anchor.text
            accessory_list.append(Accessory(content, anchor_title, anchor_content, anchor_href, anchor_text_value))
    elif elements := driver.find_elements(by=By.CSS_SELECTOR, value=selector_type_3):
        for element in elements:
            content = ""
            anchor = element
            anchor_title = anchor.get_attribute("title")
            anchor_href = anchor.get_attribute("href")
            anchor_text_value = anchor.get_attribute("textvalue") or ""
            anchor_content = anchor.text
            accessory_list.append(Accessory(content, anchor_title, anchor_content, anchor_href, anchor_text_value))
    elif elements := driver.find_elements(by=By.CSS_SELECTOR, value=selector_type_4):
        for element in elements:
            content = ""
            anchor = element
            anchor_title = anchor.find_element(by=By.TAG_NAME, value="font").text
            anchor_href = anchor.get_attribute("href")
            anchor_text_value = anchor.get_attribute("textvalue") or ""
            anchor_content = anchor.text
            accessory_list.append(Accessory(content, anchor_title, anchor_content, anchor_href, anchor_text_value))
    elif elements := driver.find_elements(by=By.CSS_SELECTOR, value=selector_type_5):
        for element in elements:
            content = driver.execute_script("return arguments[0].nextSibling.textContent", element)
            anchor = element.find_element(by=By.XPATH, value="following-sibling::a")
            anchor_title = anchor.get_attribute("title")
            anchor_href = anchor.get_attribute("href")
            anchor_text_value = anchor.get_attribute("textvalue") or ""
            anchor_content = anchor.text
            accessory_list.append(Accessory(content, anchor_title, anchor_content, anchor_href, anchor_text_value))
    elif elements := driver.find_elements(by=By.CSS_SELECTOR, value=selector_type_6):
        for element in elements:
            content = element.text
            anchor = element.find_element(by=By.XPATH, value="following-sibling::a")
            anchor_title = anchor.get_attribute("title")
            anchor_href = anchor.get_attribute("href")
            anchor_text_value = anchor.get_attribute("textvalue") or ""
            anchor_content = anchor.text
            accessory_list.append(Accessory(content, anchor_title, anchor_content, anchor_href, anchor_text_value))
    elif elements := driver.find_elements(by=By.CSS_SELECTOR, value=selector_type_7):
        for element in elements:
            content = driver.execute_script("return arguments[0].nextSibling.textContent", element)
            anchor = element.find_element(by=By.XPATH, value="following-sibling::a")
            anchor_title = anchor.get_attribute("title")
            anchor_href = anchor.get_attribute("href")
            anchor_text_value = anchor.get_attribute("textvalue") or ""
            anchor_content = anchor.text
            accessory_list.append(Accessory(content, anchor_title, anchor_content, anchor_href, anchor_text_value))
    elif elements := driver.find_elements(by=By.CSS_SELECTOR, value=selector_type_8):
        for element in elements:
            content = ""
            anchor = element
            anchor_title = anchor.get_attribute("title")
            anchor_href = anchor.get_attribute("href")
            anchor_text_value = anchor.get_attribute("textvalue") or ""
            anchor_content = anchor.text
            accessory_list.append(Accessory(content, anchor_title, anchor_content, anchor_href, anchor_text_value))
    else:
        logger.info(f"页面 {url} 中找不到附件。")

    return accessory_list


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
        total=5,
        status_forcelist=[443, 500, 502, 503, 504],
        backoff_factor=1,
    )
    adapter = HTTPAdapter(max_retries=retry_strategy)
    session = requests.Session()
    session.mount("http://", adapter)
    session.mount("https://", adapter)
    return session


# 获取指导原则发布页面
def fetch_page(url: str, start_date: datetime.date, end_date: datetime.date) -> list[GuidencePublishPage]:
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
def download_accessory(guidence_publish_page: GuidencePublishPage, timeout: int) -> None:
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

        # 数据无变化，无需更新
        if old_data == new_data:
            logger.info("数据无变化，无需更新")
            return

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


def render_markdown(guidence_publish_page_list: list[GuidencePublishPage], file_path: str) -> None:
    """
    将 GuidencePublishPage 列表渲染为 Markdown 文件。
    """

    guidence_publish_page_list.sort(key=lambda x: (-x.date.toordinal(), x.title))

    markdown = "# List of Guidences\n\n"
    markdown += "| 发布日期 | 标题 | 附件链接 |\n"
    markdown += "| -------- | ---- | -------- |\n"

    current_row_date = None
    for page in guidence_publish_page_list:
        # 表格各列内容
        markdown_date = f"<a href='guidences/{page.date}'>{page.date}</a>"
        markdown_title = f"<a href='{page.url}' target='_blank'>{page.title}</a>"
        valid_accessories = [
            f'<li><a href="{accessory.anchor_href}">{accessory.purified_title}</a></li>'
            for accessory in page.accessories
            if accessory.is_valid
        ]
        markdown_accessories = f"<ul>{''.join(valid_accessories)}</ul>"

        # 如果当前行的日期与上一行的日期不同，则添加日期信息
        if current_row_date is None or page.date != current_row_date:
            markdown += f"| {markdown_date} | {markdown_title} | {markdown_accessories} \n"
            current_row_date = page.date
        else:
            markdown += f"| | {markdown_title} | {markdown_accessories} \n"

    with open(file_path, "w", encoding="utf-8") as f:
        f.write(markdown)
