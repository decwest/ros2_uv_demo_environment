# ros2_uv_demo_environment

ROS 2のapt環境にワークスペース単位のuv環境を組み合わせたときの、Pythonノードのshebang問題を比較するデモです。

[Discourseの議論（投稿14）](https://discourse.openrobotics.org/t/57111/14) のP2を対象に、Jazzy・Lyrical・Rollingで、未修正版・既存の回避策・試験用パッチを同じノードで比較します。GPUは不要です。

[2026-09-29の実測結果](docs/validation.md): 3環境・42条件で期待する動作を確認済みです。

## 使い方

必要なのは、LinuxまたはWSL上のDocker Engine、Python 3、[Task](https://taskfile.dev/)です。ホストへのROS・uvのインストールは不要です。

```bash
git clone https://github.com/decwest/ros2_uv_demo_environment.git
cd ros2_uv_demo_environment
task doctor
task jazzy
```

初回はDockerイメージをビルドします。以後もDockerのビルドキャッシュを使い、リポジトリ内の変更を反映します。各実験は新しいワークスペースで実行します。

```bash
task lyrical
task rolling
task matrix                          # 3種類を順に実行。途中で失敗しても残りを試す
task demo DISTRO=jazzy                # task jazzy と同じ
task demo DISTRO=jazzy CASE=patched BUILD_MODE=symlink
task shell DISTRO=jazzy MODE=patched # 検証後のワークスペースに入る
task build DISTRO=rolling            # イメージの準備のみ
```

Taskがない場合は `./scripts/demo.sh run jazzy all all` でも実行できます。

Dockerに接続できない場合、WSLではDocker Desktopを起動し、Settings → Resources → WSL integrationで対象のディストリビューションを有効にしてください。

## 比較する条件

各条件で通常インストール・`--symlink-install`、`ros2 run`・`ros2 launch`を試します。

| CASE | colconの実装・起動方法 | 検証する点 |
| --- | --- | --- |
| `stock` | apt版をsystem Pythonから起動 | venvが有効でもノードがsystem Pythonを使う問題 |
| `setup-cfg` | apt版 + `[build_scripts] executable` | 通常インストールで効く既存の回避策と、develop経路との差 |
| `venv-build` | apt版を `.venv/bin/python -m colcon` で起動 | venvの絶対パスをshebangに記録する回避策 |
| `patched` | apt版と同じコードにパッチを適用 + `--python-shebang env` | 両経路で実行時のPATHからPythonを選べるか |
| `patched-off` | 修正版、オプションなし | 未修正版の挙動を維持するか |
| `system` | apt版、venvなし | 通常のROS環境が動くか |
| `patched-system` | 修正版、オプションあり、venvなし | このコンテナのPATHでsystem Pythonに解決されるか |

`stock` などの問題ケースでは、**venv専用依存が見えないことを、正常に起動したROSノードから確認できた場合**を再現成功とします。ビルド失敗、`rclpy`の失敗、タイムアウトは再現成功になりません。

ノードはJSONで、Pythonの実行ファイル、prefix、依存パッケージの読み込み元、`rclpy`によるノード生成結果を出力します。launchの親プロセスの終了コードだけで成功とは判定しません。

`patched` では、**再ビルドせず別のvenvに切り替えて**両方の起動方法を再検証します。これは実行時のPython選択を確認するもので、ROSのinstallディレクトリ全体の移設可能性を保証するものではありません。

## 結果の見方

```text
output/<distro>/<実行ID>/
├── report.md              # 比較表
├── results.json           # 全条件の測定結果
├── environment.json       # OS、Python、uv、colcon、setuptools、パッチ情報
├── image.json             # 実行したDockerイメージID等
├── apt-packages.tsv       # インストール済みaptパッケージ
├── sources.json           # 実際に使ったファイルのSHA-256
├── applied.patch
└── <case>-<build-mode>/
    ├── result.json
    ├── builder.log        # ビルドに使ったPythonとcolconの読み込み元
    ├── build.log
    ├── run.log
    ├── launch.log
    ├── source-edit.log
    └── colcon-log/
```

| 結果 | 意味 |
| --- | --- |
| `PASS` | その条件で期待する動作を確認 |
| `REPRODUCED` | system Pythonが選ばれ、venv専用依存が見えない問題を確認 |
| `NOT_COVERED` | symlinkを要求したが通常インストールにフォールバック。develop経路は未検証 |
| `FAIL` | ビルド後の観測結果が期待と異なる |
| `ERROR` | 環境準備・ビルド・証拠取得の失敗 |

colconはsetuptoolsの機能によって通常インストールにフォールバックします。そのため、指定フラグだけでなく `command.log` にある実際のビルド経路を確認し、さらにソース編集が再ビルドなしで反映されるか検証します。

終了コードは、期待どおりなら `0`、FAIL/ERRORなら `1`、フォールバックによる未検証が残れば `2` です。フォールバックをレポートで確認しながら処理を続ける場合は `ALLOW_FALLBACK=1 task rolling` を使えます。結果の `NOT_COVERED` 表示は残ります。

GitHub Actionsでも3ディストリビューションを実行し、レポートをArtifactsに保存します。CIではフォールバックを警告として扱い、確認できた動作の失敗を検出します。**CIが成功しても、`NOT_COVERED` の経路を検証済みとは扱いません。**

## 対話的に調べる

```bash
task shell DISTRO=jazzy MODE=patched

# コンテナ内。ROSとvenvはセットアップ済み。
colcon build --symlink-install --python-shebang env
ros2 run uv_shebang_demo probe
ros2 launch uv_shebang_demo probe.launch.py
head -n 1 install/uv_shebang_demo/lib/uv_shebang_demo/probe
```

修正版のシェルでは、`colcon` 関数がビルド時だけ修正版モジュールを選び、`/usr/bin/python3 -m colcon` を実行します。`venv-build` のシェルではvenvのPythonから起動します。検証のため `revision.py` は編集済みの状態です。

`.work/<distro>/<実行ID>/` にコンテナの作業領域を保存します。コンテナ内の絶対パスを含むので、ホストから直接実行したり、別の場所へ移したりするための環境ではありません。

## 環境と再現性

ベースイメージは [config/distros.json](config/distros.json) で指定します。

| ROS | 初期設定のベースイメージ |
| --- | --- |
| Jazzy | `ros:jazzy-ros-base-noble` |
| Lyrical | `ros:lyrical-ros-base-resolute` |
| Rolling | `ros:rolling-ros-base-resolute` |

uvは `0.11.28`。venvには各コンテナの `/usr/bin/python3` を明示し、`--system-site-packages` を付けます。Pythonの自動ダウンロードは禁止しています。`uv sync --frozen --offline` と同梱の小さなwheelだけで依存を導入し、実験用コンテナは `--network none` で起動します。

colconとsetuptoolsはapt版を使います。イメージ構築時にaptパッケージ全体を更新し、ROSのC拡張を読み込めることを確認します。これは特にRollingで、古いベースイメージの一部のROSパッケージだけを更新してABIが不整合になるのを避けるためです。未修正版のモジュールは変更せず、そのコピーを `/opt/colcon-patched` に置いてパッチを適用します。適用に失敗するとイメージのビルドを停止し、パッチが効かない状態で検証を続けません。

タグとaptリポジトリは更新されるため、Dockerfileだけでは過去の環境を完全には再現できません。結果を共有するときは、**依存導入済みデモイメージとレポートを一緒に保存**してください。

```bash
task build DISTRO=jazzy
docker save ros2-uv-demo:jazzy -o jazzy-demo.tar

# 保存したイメージで再実行する。ビルドはスキップ。
docker load -i jazzy-demo.tar
DEMO_IMAGE=ros2-uv-demo:jazzy task jazzy

# 自分のレジストリに保存したdigest指定のデモイメージでも実行可能。
# DEMO_IMAGE=registry.example/demo@sha256:... task jazzy
```

`DEMO_IMAGE` は完成済みのこのデモのイメージを指定します。公式ROSイメージをそのまま指定するものではありません。ビルドの入力は `BASE_IMAGE` と `UV_IMAGE` で変更できます。各実行はイメージIDを確定してから起動します。

## パッチを変更する

[patches/README.md](patches/README.md) に実装範囲と制約を記載しています。`--python-shebang env` はこのリポジトリの試験用オプションで、標準colconのオプションではありません。

1. `patches/colcon-core-env-shebang.patch` を変更する。
2. `task jazzy` または `task demo DISTRO=jazzy CASE=patched` を実行する。
3. 比較表と実測されたPython・shebang・ソース編集の反映を確認する。

オプション無効時の回帰を含めて調べる場合は、CASEを省略して全条件を実行してください。

## Dockerなしのテスト

```bash
task test
```

標準ライブラリだけで、判定処理と同梱wheelを検証します。colconがなければcolcon統合テストは明示的にskipします。統合テストも実行する場合は、例えば次のように分離したツール環境を使います。

```bash
uv venv --python 3.12 .work/test-tools
uv pip install --python .work/test-tools/bin/python -r tests/requirements.txt
.work/test-tools/bin/python -m unittest discover -s tests -v
```

統合テストは実際の `ament_python` ビルド、生成スクリプト、ソース編集を確認します。ROSランタイムの検証はDocker側で行います。ツール環境のsetuptools固定はテスト用で、デモイメージのapt版には適用しません。

依存fixtureを変更した場合は `python3 scripts/build_fixture.py demos/shebang` でwheelを再生成し、uv 0.11.28で `uv lock --directory demos/shebang` を更新してください。

## 今回の範囲

P2とその回避策の比較が対象です。venvの自動有効化（P3）、NumPy ABI、uv管理PythonのABI、PyTorch/CUDAのデモは今後の追加対象です。`.venv` が通常の再帰探索で除外される点は [投稿6の訂正](https://discourse.openrobotics.org/t/57111/6) に従い、未解決問題として扱っていません。

`env python3` は実行時のPATHに従います。venvを有効にすればそのPythonが選ばれますが、一般の環境で「venvなしなら必ず `/usr/bin/python3`」とは限りません。

License: Apache-2.0.
