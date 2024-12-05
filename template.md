# List of Guidences

| 发布日期 | 标题 | 原始页面 | 附件链接 |
| -------- | ---- | -------- | -------- |

{%- for g in gppl %}
| {{g.publish_page_date}} | {{g.publish_page_title}} | {{g.publish_page_url}} | {{g.convert_accessories_to_md()}} |
{%- endfor %}
