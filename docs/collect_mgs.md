# MGSをタイトル別のフォルダにまとめる

`scripts/collect_mgs.py`は、検証用に生成したMGSをMSXのプレーヤーで
聴くためのコピー用スクリプトです。VGMの変換やMMLのコンパイルは行いません。
コピー元のファイルを残し、ファイル名と内容を維持します。

リポジトリのルートで実行してください。

## 使い方

まずコピー先を確認します。このコマンドではファイルやフォルダを作成しません。

```sh
python scripts/collect_mgs.py outputs/mgs/opll --outdir outputs/listening/opll --dry-run
```

実際にコピーする場合は`--dry-run`を外します。

```sh
python scripts/collect_mgs.py outputs/mgs/opll --outdir outputs/listening/opll
```

`--outdir`にはMSXへ転送するための任意のディレクトリも指定できます。
コピー元とコピー先は別のディレクトリツリーにしてください。
同一ディレクトリ、または一方が他方を含む指定はエラーになります。

## コピー先の構成

入力ディレクトリを再帰的に検索し、`.mgs`ファイルを集めます。
バッチ出力の曲別ディレクトリ（`.vgm`または`.vgz`）を取り除き、
その親ディレクトリ名をタイトルのフォルダ名として使います。

```text
outputs/mgs/opll/msxplay.com/grider/grider.vgm/grider.mgs
  → outputs/listening/opll/grider/grider.mgs

outputs/mgs/opll/vgmrips.net/ALESTE/ALESTE04.vgm/ALESTE04.mgs
  → outputs/listening/opll/ALESTE/ALESTE04.mgs
```

親ディレクトリが`.vgm`または`.vgz`ではない場合は、直近の親ディレクトリ名を
使います。GD3やMGSのタイトル文字列からフォルダ名を決める処理はありません。

## 再実行と上書き

コピー先に同じ内容のファイルがあればスキップします。
同名で内容が異なるファイルがある場合は、コピー開始前にエラーになります。
置き換えたい場合は`--overwrite`を指定します。

```sh
python scripts/collect_mgs.py outputs/mgs/opll --outdir outputs/listening/opll --overwrite
```

異なるコピー元が同じコピー先になる場合もエラーになります。
例えば別の配布元に同名のタイトルフォルダと同名のMGSがある場合です。
この衝突は`--overwrite`でも解消しないため、入力範囲または出力先を分けてください。
衝突判定ではフォルダ名とファイル名の大文字・小文字を区別しません。

終了時にはコピー件数、内容が同じためスキップした件数、タイトル数を表示します。
`--dry-run`では予定件数を表示します。
