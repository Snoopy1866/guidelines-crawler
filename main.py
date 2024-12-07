import pickle
from utils import GuidencePublishPage, Accessory, get_accessories

# with open("guidences.pickle", "rb") as f:
#     guidences = pickle.load(f)
#     print(guidences)

# a = Accessory(
#     content="　　1.人类免疫缺陷病毒检测试剂临床试验注册审查指导原则（2022年修订版 征求意见稿）（",
#     anchor_href="https://www.nmpa.gov.cn/directory/web/cmde/images/1677814167321040399.docx",
#     anchor_text="下载",
#     anchor_title="下载",
# )

# print(a.purified_title)


from selenium import webdriver

driver = webdriver.Firefox()
driver.implicitly_wait(60)

# Navigate to Url
url = "https://www.cmde.org.cn/flfg/zdyz/zqyjg/20210906163900523.html"

get_accessories(url, driver)
