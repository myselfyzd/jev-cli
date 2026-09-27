#!/usr/bin/env bash
# 把 bin/jev 软链到 ~/.local/bin/jev，之后任何目录直接敲 jev 就能用。
set -euo pipefail
here="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
target="${HOME}/.local/bin/jev"

mkdir -p "$(dirname "$target")"
chmod +x "$here/bin/jev"
ln -sf "$here/bin/jev" "$target"

echo "已安装：$target -> $here/bin/jev"
case ":$PATH:" in
  *":$HOME/.local/bin:"*) ;;
  *) echo "注意：~/.local/bin 不在 PATH 里，把它加进 shell 配置。" ;;
esac

echo
echo "自检："
"$target" --version
echo "跑测试（不打网络、不花钱）："
python3.11 -m unittest discover -s "$here/tests" -t "$here" 2>&1 | tail -3
