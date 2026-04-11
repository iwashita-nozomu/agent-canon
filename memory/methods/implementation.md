# Implementation Method Memory

## Purpose

- 実装を設計と local precedent に従わせる
- low-risk slice と broad implementation を分ける

## Stable Methods

- implementer だけが repo source を編集する
- design trace が固定済みの狭い slice だけを Spark 系へ渡す
- 新しい pattern を増やす前に既存 code path を再利用する
