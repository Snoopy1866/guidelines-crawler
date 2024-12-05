import dataclasses
import datetime
import logging
import os
import re


from selenium.webdriver.common.by import By
from selenium.webdriver.chrome.webdriver import WebDriver
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC


@dataclasses.dataclass
class Accessory:
    accessory_text: str
    accessory_anchor_title: str
    accessory_anchor_text: str
    accessory_anchor_href: str

    def get_purify_title(self) -> str:
        pass


@dataclasses.dataclass
class GuidencePublishPage:
    publish_page_title: str
    publish_page_url: str
    publish_page_date: datetime.date
    publish_page_accessories: list[Accessory]

    def convert_accessories_to_md(self) -> str:
        accessories_md_list = [
            f'<li><a href="{accessory.accessory_anchor_href}">{accessory.accessory_anchor_title}</a></li>'
            for accessory in self.publish_page_accessories
        ]
        return "<ul>" + "".join(accessories_md_list) + "</ul>"


def wait_for_element(driver, by, value, timeout=10) -> EC.WebElement:
    return WebDriverWait(driver, timeout).until(EC.presence_of_element_located((by, value)))


def get_guidence_publish_pages(
    url: str, start_date: datetime.date, end_date: datetime.date, driver: WebDriver
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

    wait_for_element(driver, By.CSS_SELECTOR, selector_list_item)

    if elements := driver.find_elements(by=By.CSS_SELECTOR, value=selector_list_item):
        # 如果当前页的发布日期均不在目标日期范围内，提前返回
        oldest_date_in_current_page = datetime.datetime.strptime(
            elements[-1].find_element(by=By.TAG_NAME, value="span").text, "(%Y-%m-%d)"
        ).date()
        newest_date_in_current_page = datetime.datetime.strptime(
            elements[0].find_element(by=By.TAG_NAME, value="span").text, "(%Y-%m-%d)"
        ).date()
        if oldest_date_in_current_page > end_date or newest_date_in_current_page < start_date:
            logging.info(f"页面 {url} 中找不到 {start_date} ~ {end_date} 期间发布的指导原则。")
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
        logging.warning(f"页面 {url} 中找不到任何有效数据。")

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
    # 选择器：p:has(>a:only-of-type:where([href$='.doc'], [href$='.docx']))
    selector_type_1 = (
        "p:has(>a:only-of-type:where(" + ",".join(map(lambda x: f"a[href$='{x}']", file_extension_list)) + ")"
    )

    # 类型2
    # https://www.cmde.org.cn/flfg/zdyz/zqyjg/20150430164400462.html
    # <span>
    #   <span>附件xxx</span>
    #   <span>附件标题</span>
    # </span>
    # <a href="download_url">下载</a>
    # 选择器：span:has(+a[href$='.doc'], +a[href$='.docx'])
    selector_type_2 = "span:has(" + ",".join(map(lambda x: f"+a[href$='{x}']", file_extension_list)) + ")"

    # 类型3
    # https://www.cmde.org.cn/flfg/zdyz/fbg/fbgyy/20140723155501232.html
    # https://www.cmde.org.cn/flfg/zdyz/fbg/fbgyy/20211214162400496.html
    # <p>
    #   <img>
    #   <a href="download_url">通告2号 附件1.doc</a>
    #   ...
    # </p>
    # 选择器：p > img:nth-child(odd) + a:nth-child(even):where([href$='.doc'], [href$='.docx'])
    selector_type_3 = (
        "p > img:nth-child(odd) + a:nth-child(even):where("
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
    # https://www.cmde.org.cn/flfg/zdyz/zqyjg/20100212074430257.html
    # <a href="download_url">附件标题</a>
    # 选择器：a:where([href$='.doc'], [href$='.docx'])
    selector_type_5 = "a:where(" + ",".join(map(lambda x: f"[href$='{x}']", file_extension_list)) + ")"

    if elements := driver.find_elements(by=By.CSS_SELECTOR, value=selector_type_1):
        for element in elements:
            accessory_text = element.text
            accessory_anchor = element.find_element(by=By.TAG_NAME, value="a")
            accessory_anchor_title = accessory_anchor.get_attribute("title")
            accessory_anchor_href = accessory_anchor.get_attribute("href")
            accessory_anchor_text = accessory_anchor.text
            accessory_list.append(
                Accessory(accessory_text, accessory_anchor_title, accessory_anchor_text, accessory_anchor_href)
            )
    elif elements := driver.find_elements(by=By.CSS_SELECTOR, value=selector_type_2):
        for element in elements:
            accessory_text = element.text
            accessory_anchor = element.find_element(by=By.XPATH, value="following-sibling::a")
            accessory_anchor_title = accessory_anchor.get_attribute("title")
            accessory_anchor_href = accessory_anchor.get_attribute("href")
            accessory_anchor_text = accessory_anchor.text
            accessory_list.append(
                Accessory(accessory_text, accessory_anchor_title, accessory_anchor_text, accessory_anchor_href)
            )
    elif elements := driver.find_elements(by=By.CSS_SELECTOR, value=selector_type_3):
        for element in elements:
            accessory_text = ""
            accessory_anchor = element
            accessory_anchor_title = accessory_anchor.get_attribute("title")
            accessory_anchor_href = accessory_anchor.get_attribute("href")
            accessory_anchor_text = accessory_anchor.text
            accessory_list.append(
                Accessory(accessory_text, accessory_anchor_title, accessory_anchor_text, accessory_anchor_href)
            )
    elif elements := driver.find_elements(by=By.CSS_SELECTOR, value=selector_type_4):
        for element in elements:
            accessory_text = ""
            accessory_anchor = element
            accessory_anchor_title = accessory_anchor.find_element(by=By.TAG_NAME, value="font").text
            accessory_anchor_href = accessory_anchor.get_attribute("href")
            accessory_anchor_text = accessory_anchor.text
            accessory_list.append(
                Accessory(accessory_text, accessory_anchor_title, accessory_anchor_text, accessory_anchor_href)
            )
    elif elements := driver.find_elements(by=By.CSS_SELECTOR, value=selector_type_5):
        for element in elements:
            accessory_text = ""
            accessory_anchor = element
            accessory_anchor_title = accessory_anchor.get_attribute("title")
            accessory_anchor_href = accessory_anchor.get_attribute("href")
            accessory_anchor_text = accessory_anchor.text
            accessory_list.append(
                Accessory(accessory_text, accessory_anchor_title, accessory_anchor_text, accessory_anchor_href)
            )
    else:
        logging.info(f"页面 {url} 中找不到附件。")

    purify_accessories(accessory_list)

    return accessory_list


def purify_accessories(accessories: list[Accessory]) -> list[Accessory]:
    """
    附件后处理

    Args:
        accessories (list[Accessory]): 附件列表。
    """

    # 移除文件名匹配过滤列表的附件
    regex_filter_title_list = [
        re.compile(r"反馈意见表"),
        re.compile(r"征求意见表"),
        re.compile(r"意见反馈表"),
        re.compile(r"联系方式"),
    ]
    for i, accessory in enumerate(accessories):
        anchor_title = accessory.accessory_anchor_title
        anchor_href = accessory.accessory_anchor_href
        anchor_text = accessory.accessory_anchor_text
        text = accessory.accessory_text

        # 获取文件扩展名
        file_extension = os.path.splitext(anchor_href)[1]

        # 如果没有 title，则使用其他属性作为 title，优先级：anchor_title > anchor_text > text
        if not anchor_title:
            anchor_title = anchor_text or text

        # 检查 title 是否有扩展名，没有则添加
        if not anchor_title.endswith(file_extension):
            anchor_title += file_extension

        # 跳过不需要的文件
        if any([regex.search(anchor_title) for regex in regex_filter_title_list]):
            logging.info(f"过滤附件：{anchor_title}")
            accessories.pop(i)

        # 处理文件名中的多余字符
        anchor_title = re.sub(r"^(附件)?\d+\s*[-\.：．]?\s*", "", anchor_title)

        # 删除书名号
        anchor_title = re.sub(r"[《》]", "", anchor_title)

        # 将文件名中的非法字符替换为连字符
        anchor_title = re.sub(r"[\\/:*?\"<>|]", "-", anchor_title)

        # 更新附件属性
        accessory.accessory_anchor_title = anchor_title


def jinja_render(guidence_publish_page_list: list[GuidencePublishPage]) -> None:
    from jinja2 import Template

    template = Template(open("template.md", encoding="utf-8").read())
    rendered_markdown = template.render(gppl=guidence_publish_page_list)

    with open("guidence-list.md", "w", encoding="utf-8") as f:
        f.write(rendered_markdown)
