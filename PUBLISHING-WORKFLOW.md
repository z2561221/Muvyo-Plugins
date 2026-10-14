# Muvyo 插件分支、验收与发布

插件内容遵循 Muvyo 官方发布格式。Git 分支、PR 检查和 main 保护沿用
`z2561221/MoviePilot-Plugins` 的工作习惯；它们不改变 Muvyo 的签名安装流程。

## 固定分支

| 用途 | 分支 | 插件 ID |
|---|---|---|
| 正式签名索引与已验收产物 | main | 全部 |
| 克里斯蒂娜 | worldlinefix/kurisu | z2561221.kurisu-mascot |
| 洛琪希撤回维护 | worldlinefix/roxy | z2561221.roxy-mascot（仅保留本地开发资料） |
| GitHub 门禁维护 | worldlinefix/release-workflow | — |

插件直接从固定业务分支 PR 到 main，不经过共用 test 分支。main 只允许 PR 通过
`Plugin release gate` 和 `Plugin test gate` 后以 merge commit 合并；保留业务分支，
禁止直接推送、强推和删除 main。PR/commit 可使用 `feat(...)`、`fix(...)`、
`release(...)`、`chore(...)`、`docs(...)` 等前缀。

## Muvyo 签名发布

Muvyo 正式仓库只发布 `index.json`、`index.json.sig` 和 `plugins/<插件ID>/` 下的
加密签名产物。这里没有 GitHub Release、Tag 或 ZIP 安装流程；安装与更新由 Muvyo
读取公开仓库索引完成。

1. 在本地 `src/<插件ID>/` 制作插件。`src/`、`mv_addon.py`、`muvyo-signing.json`
   和仓库私钥均不得提交。公开仓库不包含明文源码或入口 JS。
2. 用官方 `mv_addon.py` 生成加密包并验签。只把 `index.json`、`index.json.sig` 和
   对应 `plugins/` 产物提交到插件业务分支。
3. 每次索引变化都递增 `sequence`，并用同一把仓库 Ed25519 私钥重签最终索引。
   不更换仓库公钥，不直接编辑或重新打包已签名的插件文件。
4. 向用户展示待推送提交并获得同意后，推送业务分支、创建到 main 的 PR。
   CI 从官方指南固定提交临时取得 `mv_addon.py`，
   按 SHA-256 校验后调用官方验签；该脚本不会提交到插件仓库。
5. 人物新增或更新还须完成已授权的宿主 inspect/install、资源 HTTP 回读和启用、选中状态
   检查，并由用户验收外观、14 动作和聊天框遮挡。Chrome 默认由用户自行验收；代验、
   安装源切换、重启或重载按当前任务授权执行。CI 通过不等同于页面验收。
6. 两项门禁通过、相关验收完成后，按用户授权以 merge commit 合入 main。
   Muvyo 用户刷新仓库索引即可发现更新。撤回与纯流程修正按实际变更验收，
   不为验证流程重新安装已撤回的插件。

撤回插件时，从索引删除对应条目与 `plugins/<插件ID>/`，递增 sequence 并重签索引。
此操作阻止后续从仓库安装或更新该插件，但不会远程卸载其他用户已安装的插件；
已安装设备需由设备管理员自行卸载。
撤回合并后，将没有独立未合并工作的业务分支快进到已撤回的 main，避免旧分支索引
继续提供安装。业务分支名与 Git 历史保留；重新上线需要新的签名版本和用户授权。

## 本地提交检查

首次配置本地仓库时，启用 `.githooks/pre-commit`，并指定已核验的 Python 3 解释器：

```powershell
git config core.hooksPath .githooks
git config muvyo.pythonPath '<Python 3 解释器绝对路径>'
```

此钩子需要 PowerShell 7，Python 环境需要 `cryptography`。检查读取 Git 暂存区的
实际字节，阻止源码、签名凭据、私钥和 ZIP，校验索引签名、插件文件清单与哈希；
已签名的 PNG/WebP 正常放行。暂存区与工作区不同也不会误用未暂存的内容。
官方包验签与分支、版本门禁仍由 CI 执行。检查失败应修正暂存内容，不跳过钩子。

## GitHub 门禁

`Plugin release gate` 检查固定分支、索引与 manifest 一致性、sequence 和版本变化、
签名文件哈希及受保护文件范围。`Plugin test gate` 校验仓库索引签名、从官方固定提交
取得的官方插件验签结果、素材约束，以及撤回与签名失败用例。

main ruleset 只允许 merge commit，要求 PR 通过两项门禁并解决 review 对话，禁止删除
和强推 main，不设绕过角色。自动合并和合并后删分支均关闭。

纯流程维护使用 `worldlinefix/release-workflow`，不修改签名索引或人物包。

测试仓库源可以使用业务分支索引，例如：

```text
https://gh-proxy.com/https://raw.githubusercontent.com/z2561221/Muvyo-Plugins/worldlinefix/kurisu/index.json
```

建立分支不会切换现有宿主的仓库源。测试优先使用独立宿主；使用现有宿主前先核对
repo_id、插件来源和 last_sequence。测试安装接受的 sequence 不得高于随后回切的 main。

官方依据：[`muvyo-addon-guide` 发布指南](https://github.com/thsrite/muvyo-addon-guide/blob/dbf96b5ce1aba87fe73440091b4d513b9ccc4fae/docs/publishing.md)
和[发布 Skill](https://github.com/thsrite/muvyo-addon-guide/blob/dbf96b5ce1aba87fe73440091b4d513b9ccc4fae/template/.claude/skills/muvyo-addon-publish/SKILL.md)。
