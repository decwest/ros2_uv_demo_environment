# P2の試験用パッチ

対象は `colcon-core` のPythonビルドタスクです。生成元はupstream commit
[`6bfb100bd8a9979e2903210f7a97724d6b8cf2c6`](https://github.com/colcon/colcon-core/commit/6bfb100bd8a9979e2903210f7a97724d6b8cf2c6)。
実際のデモでは各ディストリビューションのapt版モジュールをコピーし、同じパッチをfuzzなしで適用します。元のapt版と適用版のバージョンは同じです。

```bash
colcon build --python-shebang env
colcon build --symlink-install --python-shebang env
```

このオプションは実験用で、upstreamに採用されたAPIではありません。デフォルトの `--python-shebang default` またはオプション省略時は従来どおりです。

## 実装

- `PythonBuildTask.add_arguments()` がオプションを登録する。
- colconの共通のタスク引数収集機構がオプションを各パッケージへ渡す。
- `ament_python` アダプターが利用する `PythonBuildTask` にも同じ引数が届く。
- setuptoolsのinstall/develop処理が成功した後、**colconのビルド処理内で**そのパッケージの宣言済みconsole/gui entry pointの先頭行を `#!/usr/bin/env python3` に設定する。
- 既存の実行権限とスクリプト本文を維持する。

デモ実行スクリプトは生成後のshebangを修正しません。パッチを適用したcolcon自身の出力を観測します。両方のsetuptools経路を同じ処理で扱うため、setuptools内部のScriptWriterをmonkeypatchしない実装です。

## 実験の制約

- 対象はPOSIX上のsetuptoolsによるPython console/gui entry point。`ament_cmake`、CMakeの `install(PROGRAMS)`、任意の `scripts=`、Windowsランチャーは対象外。
- `setup.cfg` のinstall/developのスクリプト出力先と `$base` / `$platbase` をサポートする。出力先はinstall prefix内の絶対パスであること。
- 生成済みwrapperを対象とし、symlinkやPython以外のヘッダー、起動オプション付きshebang、shell trampolineはエラーにする。ソースのsymlinkをたどって書き換えたり、起動オプションを黙って捨てたりしない。
- ビルド・実行時に使うPythonを切り替える仕組みであり、ABI不整合や依存解決の競合を解消するものではない。
- 完成したinstall全体のrelocationは保証しない。

upstream提案に進める場合は、出力先の独自設定、Python起動オプション付きshebang、他のPythonビルドバックエンドを含めてAPIと適用範囲のレビューが必要です。

関連: [Discourse #14](https://discourse.openrobotics.org/t/57111/14)、[ros2/ros2#1094](https://github.com/ros2/ros2/issues/1094)、[PythonBuildTask](https://github.com/colcon/colcon-core/blob/master/colcon_core/task/python/build.py)。
