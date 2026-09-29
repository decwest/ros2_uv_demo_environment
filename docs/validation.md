# 検証結果 — 2026-09-29

[GitHub Actions run 36577298863](https://github.com/decwest/ros2_uv_demo_environment/actions/runs/36577298863) で、コミット [`f28337a`](https://github.com/decwest/ros2_uv_demo_environment/commit/f28337a350bb5d20707d620deba183e56bd7247a) を検証しました。Linux amd64のDocker環境です。

| 環境 | Python | colcon-core | colcon-ros | setuptools | uv |
| --- | --- | --- | --- | --- | --- |
| Jazzy / Ubuntu 24.04 | 3.12.3 | 0.21.3 | 0.5.0 | 68.1.2 | 0.11.28 |
| Lyrical / Ubuntu 26.04 | 3.14.4 | 0.21.3 | 0.5.0 | 78.1.1 | 0.11.28 |
| Rolling / Ubuntu 26.04 | 3.14.4 | 0.21.3 | 0.5.0 | 78.1.1 | 0.11.28 |

3環境とも以下の結果でした。各14条件、合計42条件です。

| 条件 | 通常install | symlink/develop |
| --- | --- | --- |
| 未修正 | 問題を再現 | 問題を再現 |
| setup.cfgによる回避策 | 成功 | 問題を再現 |
| venvからcolconを起動 | 成功 | 成功 |
| パッチ有効 | 成功 | 成功 |
| パッチ適用、オプション無効 | 問題を再現 | 問題を再現 |
| 未修正、venvなし | 成功 | 成功 |
| パッチ有効、venvなし | 成功 | 成功 |

- `ros2 run` と `ros2 launch` の両方で、子ノードのPythonと依存パッケージの読み込み元を確認。
- 全symlink条件で実際にdevelop経路を通り、ソース編集が再ビルドなしで反映された。フォールバックは0件。
- パッチ有効時は、同じinstall成果物を別のvenvから起動する検証も成功。
- 各環境で `PASS` 9件・`REPRODUCED` 5件。`FAIL`・`ERROR`・`NOT_COVERED` は0件。
- Python 3.12のcolcon統合テストと判定処理等の11テストも成功。

詳細なJSON、コマンドログ、apt一覧、イメージID、ファイルハッシュは上記runの `results-jazzy`・`results-lyrical`・`results-rolling` artifactsに保存しています。CI artifactsの保存期間は14日です。

なお、初回のRolling検証では、古いベースイメージから `rclpy` など一部だけを更新したことでC拡張の未解決シンボルが発生しました。Dockerfileでapt環境全体を更新し、C拡張のimportを先に検証するように修正した後の結果を上に記載しています。

これは記録したバージョンでの測定です。将来のapt更新や別アーキテクチャでの結果は、その環境で改めて確認してください。
