# 2つのvenv運用の比較 — 2026-10-26（JST）

Jazzyの同じDockerイメージで、以下の2方式を通常install・symlink-installの両方で検証しました。4条件とも成功し、この `ament_python` デモではシバンの問題を回避できました。試験用のシバン変更パッチは使っていません。

| 方式 | colconの起動方法 | 通常install | symlink-install |
| --- | --- | --- | --- |
| apt版をvenvのPythonで実行 | `.venv/bin/python -m colcon build` | PASS | PASS |
| venvにcolconを導入 | activate後に `colcon build` | PASS | PASS |

両方とも `/usr/bin/python3` を基に、`--system-site-packages` 付きでvenvを作っています。venvへのcolcon導入には `uv add --dev colcon-common-extensions` を使用しました。setuptoolsなどを手動で固定せず、uvが解決した結果を記録しています。

| 項目 | apt版を利用 | venvに導入 |
| --- | --- | --- |
| OS / ROS | Ubuntu 24.04 / Jazzy | 同左 |
| Python / uv | 3.12.3 / 0.11.28 | 同左 |
| colcon-core | 0.21.3 | 0.21.3 |
| colcon-ros | 0.5.0 | 0.5.0 |
| colcon-python-setup-py | 0.2.9 | 0.2.9 |
| setuptools | 68.1.2 | 79.0.1 |
| 上記モジュールの読み込み元 | `/usr/lib/python3/dist-packages/` | 各ワークスペースの `.venv/lib/python3.12/site-packages/` |
| ノードのシバン | `#!/work/<case>/.venv/bin/python` | `#!/work/<case>/.venv/bin/python3` |

`python` と `python3` の名前は異なりますが、どちらも各ワークスペースのvenvのPythonです。ノード自身の `sys.executable` と `sys.prefix` から確認しています。

各条件で次の7回、計28回のノード起動を検証しました。すべてで、選択したvenvのPython、venv内の依存 `venv_only_dep` の読み込み元、`rclpy` によるノード生成、子ノードの終了コードを確認しています。

- venvをactivateした状態で `ros2 run` と `ros2 launch`。
- ROSのsetupだけをsourceし、venvをactivateしない状態で同じ2種類の起動。
- ソースを編集し、再ビルドせず `ros2 run`。
- `uv sync --locked --offline` 後に同じ2種類の起動。

symlink-installの2条件は、どちらも実際に `setup.py develop` を通り、ソース編集が再ビルドなしで反映されました。通常installでは、編集前のインストール済みコードが動くことを確認しました。通常installへのフォールバックは0件です。

venv内のcolconは、`uv sync` 後も同じバージョン・読み込み元を維持し、通常の `colcon list` も成功しました。system Pythonから取得したパッケージ一覧・バージョン・場所も比較前後で変わっていません。既存の判定処理・実ビルド統合テスト11件も、同じJazzyイメージで成功しました。

再実行するには、このデモの構築済みイメージを指定します。

```bash
# イメージが未作成の場合
task build DISTRO=jazzy

DEMO_IMAGE=ros2-uv-demo:jazzy ./scripts/compare_venv_solutions.sh
```

準備用コンテナではPyPIへ接続し、venv版colconの依存を一度だけ解決します。そのlockfileとuvキャッシュを使い、比較用コンテナは `--network none` で実行します。各条件は新しいワークスペースとvenvを使用します。ホストのROSやPython環境へのインストールは行いません。

実行ごとに `output/<distro>/<run-id>/` へ、比較表、結果JSON、イメージ情報、apt一覧、ソースのハッシュ、各条件のログ、使用した `pyproject.toml` と `uv.lock` を保存します。次回実行時のPyPI解決結果は変わり得るため、同じバージョンでの再現が必要な場合は、今回のイメージ・lockfile・作業領域内のuvキャッシュを保存してください。

今回の実行IDは `20261025T153832Z-venv-solutions-8612` です。UTCでは10月25日、JSTでは10月26日の実行です。[比較レポート](../output/jazzy/20261025T153832Z-venv-solutions-8612/report.md) と [詳細JSON](../output/jazzy/20261025T153832Z-venv-solutions-8612/results.json) はローカルのGit管理外ディレクトリにあります。

この2026-10-26の結果が確認しているのは、記録した環境での `ament_python`、console entry point、`ros2 run` / `ros2 launch` の動作です。この時点ではLyrical・Rolling、`ament_cmake`、NumPyなどのABI互換性、大規模な依存構成、venvやinstallの移設は検証していません。Lyrical・Rollingの追加結果は以下に記載します。

## Lyrical・Rollingの追加検証 — 2026-10-27（JST）

案1「venvにcolconを導入する」を、Lyrical・Rollingでも検証しました。同じ比較スクリプトで案2「apt版colconをvenvのPythonで実行する」も再確認し、2環境・2方式・2ビルド方式の計8条件すべてが成功しました。シバン変更パッチは使用していません。

| 環境 | 方式 | 通常install | symlink-install |
| --- | --- | --- | --- |
| Lyrical | 案1：venvにcolconを導入 | PASS | PASS（実際にdevelop） |
| Lyrical | 案2：apt版をvenvのPythonで実行 | PASS | PASS（実際にdevelop） |
| Rolling | 案1：venvにcolconを導入 | PASS | PASS（実際にdevelop） |
| Rolling | 案2：apt版をvenvのPythonで実行 | PASS | PASS（実際にdevelop） |

両環境ともLinux amd64のDockerで、Ubuntu 26.04.1 LTS / Python 3.14.4 / uv 0.11.28を使用しました。公式の `ros:lyrical-ros-base-resolute` と `ros:rolling-ros-base-resolute` から検証用イメージを構築しています。

| ビルドツール | 案1：venvに導入 | 案2：apt版を利用 |
| --- | --- | --- |
| colcon-core | 0.21.3 | 0.21.3 |
| colcon-ros | 0.5.0 | 0.5.0 |
| colcon-python-setup-py | 0.2.9 | 0.2.9 |
| setuptools | 79.0.1 | 78.1.1 |

案1では `/usr/bin/python3` を基に `--system-site-packages` 付きのvenvを作り、`uv add --dev colcon-common-extensions` を実行しました。colcon・setuptoolsのバージョンを手動では固定せず、uvの解決結果をlockfileに保存しています。activate後の通常の `colcon build` が `.venv/bin/colcon` を使い、生成されたノードのシバンが各venvの `bin/python3` を指すことを確認しました。

各条件で前述の7回のノード起動を行い、案1だけで4条件・28回、案2も含めて8条件・56回すべてが成功しました。`ros2 run` / `ros2 launch`、activateなしの起動、ソース編集の反映、`uv sync --locked --offline` 後の起動とビルドツールの維持を確認しています。symlink-installの全4条件でdevelop経路を通り、通常installへのフォールバックは0件でした。両環境ともsystem Pythonのパッケージ一覧・バージョン・配置は比較前後で変わっていません。

通常installでは `byte-compiling is disabled, skipping` という警告が出ました。検証用イメージでは `PYTHONDONTWRITEBYTECODE=1` を設定しています。ビルドとノード起動は成功しており、シバンや依存の読み込みに関するエラーはありませんでした。

再実行コマンドは以下です。既に検証用イメージがあれば、各 `build` 行を省略できます。依存解決を行う準備段階はオンライン、ビルドとノード起動はネットワークを無効にしたコンテナで実行します。

```bash
./scripts/demo.sh build lyrical
DEMO_IMAGE=ros2-uv-demo:lyrical ./scripts/compare_venv_solutions.sh

./scripts/demo.sh build rolling
DEMO_IMAGE=ros2-uv-demo:rolling ./scripts/compare_venv_solutions.sh
```

今回のログ・結果JSON・lockfile・使用イメージと入力ファイルの記録は、以下のローカルのGit管理外ディレクトリにあります。

- [Lyricalの結果](../output/lyrical/20261027T090435Z-venv-solutions-9636/report.md)：`output/lyrical/20261027T090435Z-venv-solutions-9636/`
- [Rollingの結果](../output/rolling/20261027T090435Z-venv-solutions-27391/report.md)：`output/rolling/20261027T090435Z-venv-solutions-27391/`
- [両環境の集計](../output/builds/20261027-venv-solutions/summary.json) とイメージ構築ログ：`output/builds/20261027-venv-solutions/`

今回の追加検証も最小の `ament_python` パッケージが対象です。`ament_cmake` 混在、NumPyなどのABI互換性、大規模な依存構成、venvやinstallの移設は引き続き未検証です。
