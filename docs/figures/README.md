# Pythonの関係図

[README](../../README.md) の説明を補足する図です。`.mmd` が編集元、`.svg` がGitHub表示用、`.png` が会議資料への貼り付け用です。

| 図 | 内容 | 画像 |
| --- | --- | --- |
| [python-environments.mmd](python-environments.mmd) | 各Python環境からパッケージを参照する関係 | [SVG](python-environments.svg) / [PNG](python-environments.png) |
| [colcon-python-flow.mmd](colcon-python-flow.mmd) | 問題が起こる構成と2方式の、ビルドからノード実行までの比較 | [SVG](colcon-python-flow.svg) / [PNG](colcon-python-flow.png) |

矢印は図ごとに意味が異なります。1枚目はパッケージの参照、2枚目は処理の順序です。`/ws` はワークスペースの絶対パスの例です。2枚目は今回検証した `ament_python` の `console_scripts` を対象にしています。

Mermaid CLI 11.12.0（Mermaid 11.17.2）と日本語フォント（IPAexゴシック）で生成しました。Node.js・Chromium・日本語フォントがある環境で、リポジトリのルートから再生成できます。

```bash
for name in python-environments colcon-python-flow; do
  npx --yes --package @mermaid-js/mermaid-cli@11.12.0 mmdc \
    -i "docs/figures/$name.mmd" -o "docs/figures/$name.svg" \
    -c docs/figures/mermaid-config.json -b white -w 2000
  npx --yes --package @mermaid-js/mermaid-cli@11.12.0 mmdc \
    -i "docs/figures/$name.mmd" -o "docs/figures/$name.png" \
    -c docs/figures/mermaid-config.json -b white -w 2000 -s 2
done
```

既存のChromiumを指定する場合は、Puppeteer設定ファイルに `executablePath` を記述し、`mmdc -p <設定ファイル>` で渡します。フォントやレンダラーを変更すると、改行位置や画像寸法が変わる場合があります。
