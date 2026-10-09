# `tw land` が submodule を持つ作業先の作業ツリーも、汚れが無いと確かめてから消す（振り返り: T-060）

- 観点: 赤 道具の経済
- 根拠: T-060 で `tw land t-060` は tsukumo の main への合流まで済んだが、`NOT_REMOVED`（`fatal: working trees containing submodules cannot be moved or removed`）で作業ツリーと枝が残り、人に預けた。tsukumo は submodule（tsukumo-plugins）を持つので、tsukumo が作業先のタスクでは毎回起きる
- 出し先: tsukumo-plugins の `tw land`（`tw_*.py` の land の口）を直すタスク。作業ツリーと各 submodule の `git status --porcelain` が空なら `git worktree remove --force` で消し、枝も消す。汚れがあれば今までどおり `NOT_REMOVED` で止まる。自己テストに submodule を持つ作業先の1行を足す
