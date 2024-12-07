import re

# purified_title = "1.人类免疫缺陷病毒检测试剂临床试验注册审查指导原则（2022年修订版 征求意见稿）（"
# if not re.search(r"（[^（）]+）$", purified_title):
#     purified_title = re.sub(r"(^[（）]|[（）]$)", "", purified_title)
# print(purified_title)

# purified_title = "《血液透析浓缩物《注册审查指导原则（2023年修订版）》.doc"
# file_extension_without_dot = "doc"
# purified_title = re.sub(rf"^《(.+)》(\.{file_extension_without_dot})?$", r"\1\2", purified_title)
# print(purified_title)

import os

# anchor_href = "附件1血液透析浓缩物注册审查指导原则（2023年修订版）.doc"
# file_name, file_extension = os.path.splitext(anchor_href)
# print(file_name)
# print(file_extension)

# print(os.listdir(r"C:\Users\17531\Documents\GitHub\Snoopy1866\guidelines\guidences\2024-11-28"))

from crawler import remove_duplicate_files

# remove_duplicate_files(
#     r"C:\Users\17531\Documents\GitHub\Snoopy1866\guidelines\guidences\2022-12-02\一次性使用硬膜外麻醉导管注册审查指导原则.docx"
# )
