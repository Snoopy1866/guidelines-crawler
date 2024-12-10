#!/bin/bash

set -e # 在发生错误时退出脚本

# 获取上一个 tag 的名称
previous_tag=$(git describe --tags --abbrev=0 HEAD^)
echo "Previous tag: $previous_tag"

# 创建一个临时目录
temp_dir=$(mktemp -d)

# 在脚本结束时删除临时目录
trap "rm -rf $temp_dir" EXIT

# 切换到上一个 tag
git switch --detach $previous_tag

# 复制 guidences.pickle 文件到临时目录
cp guidences.pickle $temp_dir

# 返回最新的 commit
git switch -

# 将临时目录中的 guidences.pickle 文件复制到当前目录
cp $temp_dir/guidences.pickle ./old_guidences.pickle

# 比较差异，生成 diff.md 文件
python -m diff_tag
if [ $? -ne 0 ]; then
    echo "Error while running diff_tag.py."
    exit 1
fi

# 检查 diff.md 文件是否被成功创建
if [ -f diff.md ]; then
    # 创建一个新的 tag
    new_tag=$(date +"%Y%m%d.%H%M%S")
    echo "Creating a new tag: $new_tag"
    git tag $new_tag -m "Release $new_tag"

    # 推送新的 tag 到远端
    git push origin $new_tag

    # 创建新的 release
    gh release create $new_tag --title "Release $new_tag" --notes-file diff.md
else
    echo "Guidelines has not been changed since the last release."
    exit 0
fi
