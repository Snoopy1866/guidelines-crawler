import dataclasses
import datetime
import os
import re
import requests

from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.common.exceptions import NoSuchElementException


@dataclasses.dataclass
class Accessory:
    accessory_title: str
    accessory_download_url: str


@dataclasses.dataclass
class GuidencePublishPage:
    publish_page_title: str
    publish_page_url: str
    publish_page_date: datetime.date
    publish_page_accessories: list[Accessory]

    def convert_accessories_to_md(self) -> str:
        accessories_md_list = [
            f'<li><a href="{accessory.accessory_download_url}">{accessory.accessory_title}</a></li>'
            for accessory in self.publish_page_accessories
        ]
        return "<ul>" + "".join(accessories_md_list) + "</ul>"


def get_guidence_publish_page_list(
    initial_page_url: str, start_date: datetime.date, end_date: datetime.date
) -> list[GuidencePublishPage]:
    """
    获取目标日期范围内的指导原则发布页列表。

    Args:
        initial_page_url (str): 初始爬取页面。
        start_date (datetime.date): 开始日期。
        end_date (datetime.date): 结束日期。
    Returns:
        list[GuidencePublishPage]: 指导原则发布页列表。
    """

    # 指导原则发布页列表
    guidence_publish_item_list: list[GuidencePublishPage] = []

    # 创建 WebDriver 实例
    driver: webdriver.Firefox = webdriver.Firefox()
    driver.implicitly_wait(10)

    # 定义选择器，选择列表中的每一项指导原则发布页面
    selector_list_item = ".list li:has(a[href$='.html'])"

    # 定义最大爬取的页面数
    max_page_try_limit = 10

    def get_guidence_publish_page_list_on_current_page(
        current_page_url: str, max_page_try_limit: int = max_page_try_limit
    ) -> None:
        driver.get(current_page_url)
        guidence_publish_page_elements = driver.find_elements(
            by=By.CSS_SELECTOR, value=selector_list_item
        )

        guidence_publish_item_list_in_current_page: list[GuidencePublishPage] = []

        print("正在获取页面...")
        for ele in guidence_publish_page_elements:
            ele_anchor = ele.find_element(by=By.TAG_NAME, value="a")

            publish_page_title = ele_anchor.get_attribute("title")
            publish_page_url = ele_anchor.get_attribute("href")
            publish_page_date = datetime.datetime.strptime(
                ele.find_element(by=By.CSS_SELECTOR, value="span").text, "(%Y-%m-%d)"
            ).date()
            publish_page_accessories = []

            guidence_publish_item_list_in_current_page.append(
                GuidencePublishPage(
                    publish_page_title,
                    publish_page_url,
                    publish_page_date,
                    publish_page_accessories,
                )
            )
            if start_date <= publish_page_date <= end_date:
                guidence_publish_item_list.append(
                    GuidencePublishPage(
                        publish_page_title,
                        publish_page_url,
                        publish_page_date,
                        publish_page_accessories,
                    )
                )

        data_list_in_current_page = map(
            lambda x: x.publish_page_date, guidence_publish_item_list_in_current_page
        )
        oldest_guidence_publish_date_in_current_page = min(data_list_in_current_page)
        # newest_guidence_publish_date_in_current_page = max(data_list_in_current_page)

        # 如果本页面的最早日期早于目标日期范围的最早日期，终止爬取
        if oldest_guidence_publish_date_in_current_page < start_date:
            driver.close()
            return
        else:
            if len(guidence_publish_item_list) == 0:
                max_page_try_limit -= 1
                if max_page_try_limit == 0:
                    print("已经到达最大爬取页面数，仍未找到符合条件的页面。")
                    driver.close()
                    return
            try:
                next_page_url = driver.find_element(
                    by=By.LINK_TEXT, value="下一页"
                ).get_attribute("href")
            except NoSuchElementException:
                next_page_url = None
            if next_page_url:
                get_guidence_publish_page_list_on_current_page(next_page_url)
            else:
                print("已经到达最后一页。")
                driver.close()
                return

    # 获取指导原则发布列表项
    get_guidence_publish_page_list_on_current_page(initial_page_url)
    return guidence_publish_item_list


def download_guidence(link: str, save_path: str) -> None:
    """
    从指导原则发布页面下载附件的文件。

    Args:
        link (str): 可供下载的文件链接。
        save_path (str): 文件保存路径。
    """

    retry_strategy = Retry(
        total=3,
        status_forcelist=[443, 500, 502, 503, 504],
        backoff_factor=1,
    )
    adapter = HTTPAdapter(max_retries=retry_strategy)
    session = requests.Session()
    session.mount("http://", adapter)
    session.mount("https://", adapter)

    try:
        response = session.get(link, timeout=5)
        with open(save_path, "wb") as f:
            f.write(response.content)
    except requests.exceptions.RequestException as e:
        print(f"Failed to download {link}")
        print(e)


def get_accessories_from_publish_page(
    publish_page: GuidencePublishPage,
    driver: webdriver.Firefox,
) -> None:
    """
    获取指导原则发布页面的内容。

    Args:
        publish_page (GuidencePublishPage): 一个 GuidencePublishPage 对象。
        driver (webdriver.Firefox): WebDriver 实例。
    """

    publish_page_title = publish_page.publish_page_title
    publish_page_url = publish_page.publish_page_url
    publish_page_date = publish_page.publish_page_date
    publish_page_accessories = publish_page.publish_page_accessories

    # 附件类型选择器列表
    selector_suffix_list = [
        "a[href$='.doc']",
        "a[href$='.docx']",
        "a[href$='.xls']",
        "a[href$='.xlsx']",
        "a[href$='.zip']",
        "a[href$='.rar']",
        "a[href$='.pdf']",
    ]
    selector_guidence_download_url = str.join(",", selector_suffix_list)

    # 附件过滤列表
    regex_filter_title_list = [
        re.compile(r"反馈意见表"),
        re.compile(r"征求意见表"),
        re.compile(r"意见反馈表"),
        re.compile(r"联系方式"),
    ]

    # 打开指导原则发布页面
    driver.get(publish_page_url)
    ele = driver.find_elements(by=By.CSS_SELECTOR, value=selector_guidence_download_url)

    # 根据发布日期建立文件夹
    dir = os.path.join("guidences", publish_page_date.strftime("%Y-%m-%d"))
    os.makedirs(dir, exist_ok=True)

    # 下载每个文件到对应日期的文件夹中
    for e in ele:
        accessory_download_url = e.get_attribute("href")
        accessory_title = e.get_attribute("title")
        accessory_text = e.text

        # 如果没有 title，使用 text 作为 title
        if not accessory_title:
            file_extension = os.path.splitext(accessory_download_url)[1]
            accessory_title = accessory_text + file_extension

        # 处理文件名
        # 删除前缀 "附件x" 等多余字符
        accessory_title = re.sub(r"^附件\d+\s*[-\.：]?\s*", "", accessory_title)

        # 将文件名中的非法字符替换为连字符
        accessory_title = re.sub(r"[\\/:*?\"<>|]", "-", accessory_title)

        # 跳过不需要的文件
        if any([regex.search(accessory_title) for regex in regex_filter_title_list]):
            continue

        # 添加到附件列表
        publish_page_accessories.append(
            Accessory(accessory_title, accessory_download_url)
        )

        # 跳过已下载的文件
        file_path = os.path.join(dir, accessory_title)
        if os.path.exists(file_path):
            print(f"文件 {accessory_title} 已存在，跳过下载。")
            continue

        # 下载文件
        print(f"Downloading {accessory_title}")
        download_guidence(accessory_download_url, file_path)


def jinja_render(guidence_publish_page_list: list[GuidencePublishPage]) -> None:
    from jinja2 import Template

    template = Template(open("template.md", encoding="utf-8").read())
    rendered_markdown = template.render(
        guidence_list=guidence_publish_page_list, enumerate=enumerate
    )

    with open("guidence-list.md", "w", encoding="utf-8") as f:
        f.write(rendered_markdown)
