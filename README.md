# JPBL PowerPro Importer

パワプロの試合成績スクリーンショットから、JPBL 成績入力 GAS 用の GameJSON を作る Windows 向けローカルツールです。

現段階は **野手・投手OCR確認GUI** です。NameList v1/v2 の読み込み、成績画面OCR、NameList照合、手動確認GUI、内部モデル、入力検証、QS/HQS 算出、GameJSON v1 の出力を提供します。

## 必要環境

- Python 3.11 以上
- PaddleOCR（初回解析時に日本語対応の認識モデルを取得）
- PySide6-Fluent-Widgets（上部の設定UIに使用。`requirements.txt` で導入）

セットアップ（プロジェクト専用の仮想環境を使用）：

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
```

PaddleOCRは外部のTesseract実行ファイルやPATH設定を必要としません。初回の
「画像を解析」時だけ、PaddleOCRの日本語対応モデルをダウンロードします。
以後は `runtime/paddlex/` 内のローカルモデルを再利用します。

## 将来の配布版でのPaddleOCR同梱

配布版ではPaddleOCR本体と初回取得した認識モデルをPyInstallerへ同梱します。
利用者にTesseractの別途インストールやPATH設定を要求しない構成にできます。
同梱するPaddlePaddle・PaddleOCR・モデルのバージョンとライセンスは配布フェーズで
固定して確認します。

### EXEビルド

PaddleXが動的に参照する `python-bidi` の配布情報も含める必要があるため、手入力の
PyInstallerコマンドではなく、次のスクリプトでビルドします。

```powershell
.\build_exe.ps1
```

完成品は `dist\JPBL PowerPro Importer\JPBL PowerPro Importer.exe` です。`build\` 内の
EXEはPyInstallerの中間生成物のため起動しません。

## GUIの起動

```powershell
.\.venv\Scripts\python.exe main.py
```

NameList、球団、成績種別、成績画像を選択してから「画像を解析」を押します。
野手と投手を同じ球団で順に解析すると、両方の確認済み行をまとめて出力できます。
野手・投手とも成績画像は1～2枚選択でき、スクロール画面を使う場合は上側→下側の順で
選択します。重複して表示された選手行はNameList照合結果を使って統合します。
ドラッグ＆ドロップした画像は現在の選択へ追加されるため、1枚目を選択後に2枚目だけを
ドロップできます。「画像をリセット」で画像選択だけを消去して選び直せます。

独立した `ユーザー設定` カードの `ユーザー名` には3文字の識別子を設定します。設定は次回以降も保持され、
Game IDは `ユーザー名-球団コード-YYYYMMDD-通し番号`（例: `ABC-BT-20261005-001`）として
球団・試合日の変更時に自動更新されます。通し番号はGame ID欄の末尾を直接編集できます。
ユーザー名が未入力の場合は、先頭3文字に `UKN` を使用します。

出力前に上部の `Game ID` と `試合日` を確認し、各選手行の `備考` を必要に
応じて入力してください。「GameJSONを書き出す」を押して保存先を指定すると、
各行の備考が対応する選手の `adds.備考` に出力されます。空欄は空文字列です。

上部は NameList、試合情報、成績画像の3カードです。NameListと画像はファイル名だけを
表示し、フルパスはツールチップで確認できます。

画像座標は `config/batter_screen_regions.json` と
`config/pitcher_screen_regions.json` に集約されています。実機画像でずれがあれば、
該当ファイルだけを校正します。

## テスト

```powershell
.\.venv\Scripts\python.exe -m unittest discover -s tests -v
```
