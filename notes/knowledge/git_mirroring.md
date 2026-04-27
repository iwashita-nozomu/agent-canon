# Git Mirroring
<!--
@dependency-start
upstream design README.md notes lifecycle index
@dependency-end
-->


この note は、template repo で Git mirror を組むときの確認観点をまとめたものです。
特定 repo の URL や bare path を正本にせず、再利用できる運用パターンだけを残します。

## 想定する構成

- 通常の push 先は `origin`
- 必要なら別 remote として `mirror` や `GitHub` を追加
- bare repo を経由する場合、bare repo 側の `post-receive` hook で mirror push を行う

つまり、通常は `main` から `origin` へ push し、必要なら bare repo か追加 remote が外部 mirror を担当する構成です。

## どこを見るか

- local repo の remote:
  - `git remote -v`
- bare repo の config:
  - `/mnt/git/<repo>.git/config`
- bare repo の hook:
  - `/mnt/git/<repo>.git/hooks/post-receive`
- SSH config:
  - `~/.ssh/config`
- mirror 用公開鍵:
  - `~/.ssh/<mirror-key>.pub`

## 典型的な失敗

- `origin` への push は通るが、mirror push だけ失敗する。
- bare repo の hook に認証情報が無い。
- HTTPS remote を使っているが、username / token が供給されない。
- `git credential fill` 自体が mirror 先の資格情報を返せない。

## 通すときの確認

- `git push origin main`
- `git rev-parse HEAD`
- `git rev-parse origin/main`
- bare repo の hook を確認
- 追加確認が必要な場合は `git push <mirror-remote> main` を直接試す

## 実際の確認手順

まず、local と `origin` が一致しているかを見ます。

```bash
git rev-parse HEAD
git rev-parse origin/main
```

次に、mirror 先の実際の先頭を見ます。fetch 済みの local tracking ref ではなく、remote 本体を見るのが安全です。

```bash
git ls-remote <mirror-remote> refs/heads/main
```

差分件数は、次で見られます。

```bash
git rev-list --count <mirror-remote>/main..origin/main
```

ただし、このコマンドは local の tracking ref を使うので、厳密に見たいときは先に `git fetch <mirror-remote>` するか、`ls-remote` の結果を優先します。

## mirror が遅れているときの通し方

### 1. remote 設定を確認する

```bash
git remote -v
git config --get-all remote.<mirror-remote>.pushurl
git --git-dir=/mnt/git/<repo>.git config --get remote.<mirror-remote>.url
```

少なくとも、local repo と bare repo の両方で mirror remote が正しい必要があります。

SSH を使うなら、どちらも次の形にそろえるのが分かりやすいです。

```text
git@<host>:<org>/<repo>.git
```

### 2. まずは direct push を試す

```bash
git push <mirror-remote> main
```

これで通れば、mirror 経路の問題ではなく bare repo hook 側の問題です。

### 3. bare repo mirror を確認する

```bash
sed -n '1,120p' /mnt/git/<repo>.git/hooks/post-receive
sed -n '1,120p' /mnt/git/<repo>.git/config
```

bare repo 側で `git push --mirror <mirror-remote>` を呼ぶ設計なら、hook と bare repo の remote 設定が一致している必要があります。

### 4. 認証方式を決める

この環境で一番詰まりやすいのは認証です。症状が

```text
fatal: could not read Username for 'https://<host>': terminal prompts disabled
```

であれば、HTTPS remote は見えていても資格情報が渡っていません。

対策は次のどちらかです。

- HTTPS token を credential helper 経由で渡す
- SSH remote に切り替えて、bare repo と local repo の両方で鍵を使う

SSH を使う場合は、次も確認します。

```bash
ssh -T git@<host>
```

ここで

```text
Permission denied (publickey)
```

が出るなら、鍵ファイルはあっても mirror 先への登録がまだです。

### 4.1 SSH 鍵を作る

```bash
ssh-keygen -t ed25519 -C "<email-or-label>" -f ~/.ssh/<mirror-key>
```

```bash
cat ~/.ssh/<mirror-key>.pub
```

この公開鍵を mirror 先に登録してから、再度 `ssh -T git@<host>` を試します。

### 4.2 SSH config をそろえる

```sshconfig
Host <host>
  HostName <host>
  User git
  IdentityFile ~/.ssh/<mirror-key>
  IdentitiesOnly yes
  StrictHostKeyChecking accept-new
```

この設定があると、local repo と bare repo の両方で同じ鍵を使いやすくなります。

### 5. 通ったあとに再確認する

```bash
git ls-remote <mirror-remote> refs/heads/main
git rev-parse HEAD
```

この 2 つが一致すれば、少なくとも `main` の mirror は完了です。
