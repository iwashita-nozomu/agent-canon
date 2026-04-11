# Requirements Method Memory

## Purpose

- requirements を source bucket ごとに分離する
- accumulated context から解ける曖昧さを先に潰す

## Stable Methods

- current request、durable user preference、repo/code precedent、domain/external constraint、unknown/open question を混ぜない
- durable user preference は current request か repo evidence があるときだけ task requirement に昇格する
- active clause に `unknown_or_open_question` を残さない
