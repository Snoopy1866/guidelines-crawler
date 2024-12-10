import os
import sys

from utils import GuidencePublishPage, read_pickle_file


old_pickle_path: str = "old_guidences.pickle"
new_pickle_path: str = "guidences.pickle"


def render_diff_markdown(diff_guidences: list[GuidencePublishPage]):
    with open("diff.md", "w", encoding="utf-8") as f:
        f.write("# New guidelines\n")
        for guidence in diff_guidences:
            f.write(f"- [{guidence.title}]({guidence.url})\n")


if os.path.exists(old_pickle_path) and os.path.exists(new_pickle_path):
    old_guidences: list[GuidencePublishPage] = read_pickle_file(old_pickle_path)
    new_guidences: list[GuidencePublishPage] = read_pickle_file(new_pickle_path)

    old_page_urls = set([guidence.url for guidence in old_guidences])
    new_page_urls = set([guidence.url for guidence in new_guidences])

    diff_urls = new_page_urls - old_page_urls

    if diff_urls:
        diff_guideces = [guidence for guidence in new_guidences if guidence.url in diff_urls]
        render_diff_markdown(diff_guideces)
else:
    print("pickle 文件不存在")
    sys.exit(1)
