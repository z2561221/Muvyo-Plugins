# Muvyo 插件分支、验收与发布

本仓库沿用 `z2561221/MoviePilot-Plugins` 的 GitHub 流程：固定业务分支直接 PR 到
main，两项门禁，merge commit 合并，main 自动建立 Tag、Release 和 ZIP。

## 固定分支

| 用途 | 分支 | 插件 ID | Release 前缀 |
|---|---|---|---|
| 正式索引与已验收产物 | main | 全部 | — |
| 克里斯蒂娜开发与测试 | worldlinefix/kurisu | z2561221.kurisu-mascot | KurisuMascot |
| 洛琪希开发与测试 | worldlinefix/roxy | z2561221.roxy-mascot | RoxyMascot |
| GitHub 门禁与发布机制 | worldlinefix/release-workflow | — | — |

`worldlinefix/<插件稳定标识>` 是长期保留的业务分支，插件中文显示名可修改，分支不随之更名。
映射保存在 `.github/plugin-catalog.json`。各业务分支直接提 PR 到 main，不经过共用 test 分支。
PR/commit 使用 `feat(...)`、`fix(...)`、`release(...)`、`chore(...)`、`docs(...)` 等前缀。

## 开发、测试、验收

1. 从最新 main 更新对应业务分支，在本地制作人物、动作与透明素材。
2. 递增插件版本，使用官方工具加密签名；保留索引中的全部现有插件及原仓库公钥。
   索引或包变化时 sequence 必须增加，并重新签署 index.json.sig。
3. 只向对应业务分支推送候选签名包，随后创建该分支到 main 的 PR。
4. `Plugin release gate` 检查分支归属、版本递增、索引与 manifest 一致性、包哈希、
   文件集合及纯形象权限。`Plugin test gate` 校验固定仓库公钥的索引签名、原版官方
   作者证书/包签名/素材检查，并执行门禁与归档回归测试。
5. 人物改动还须测试宿主 inspect/install、资源 HTTP 回读、启用与选中状态，
   并由用户验收外观、14 动作和聊天框遮挡。CI 不等同于实际页面验收。
   Chrome 默认由用户自行验收；服务重启、重载和安装源切换依任务授权执行。
6. 两项门禁通过、相关验收完成后，按任务授权以 merge commit 合入 main。
   不使用 squash/rebase，不直接写 main，不删除业务分支。
7. main 上 `Plugin Release` 自动验证签名包，生成 `PluginName_vVERSION` Tag 和
   `pluginnamelower_vVERSION.zip`，发布后回读 Tag 的目标提交、资产数、体积及 SHA-256。
   例如 `RoxyMascot_v1.0.0` / `roxymascot_v1.0.0.zip`。

## main 保护与正式发布

main ruleset 与 MP 相同：必须 PR、解决 review 对话、通过 `Plugin release gate` 和
`Plugin test gate`；禁止删除与强推。仅允许 merge commit；不设置管理员绕过、
不要求额外审批人数、不强制候选先更新到最新 main。合并前仍须核对并发索引变更。
自动合并关闭，合并后自动删分支关闭。

Release 仅从 main 发布，可以手动触发 main 工作流重试。首次启用时为现有正式版本
补建归档。已有完整 Release 必须保留；资产缺失、摘要不符或只存在 Tag 时报错，
不得删除、重建或覆盖历史发布。新修改必须递增版本并重新加密签名。

ZIP 是签名安装产物归档，不是宿主直接导入入口。安装仍通过仓库签名索引：

```text
https://gh-proxy.com/https://raw.githubusercontent.com/z2561221/Muvyo-Plugins/HEAD/index.json
```

测试候选使用对应业务分支 ref，例如洛琪希：

```text
https://gh-proxy.com/https://raw.githubusercontent.com/z2561221/Muvyo-Plugins/worldlinefix/roxy/index.json
```

建立分支和 PR 不会切换线上安装源。测试优先使用独立宿主；若使用现有宿主，先核对
仓库身份、repo_id、插件来源及 last_sequence 并备份。不要把相同 ID 从新仓库覆盖安装。
回切 main 时其 sequence 不得低于测试宿主已接受的序号；并发改动应合并条目后重签索引。

公开仓库只提交签名产物、流程文档与必要 CI 工具；原视频、人物源代码、生图配置、
提示词和私钥留在本地。官方验签工具固定版本及 SHA-256，保留证书过期检查。
本地历史 `publish_104.py` / `publish_roxy.py` 为已完成的单次发布记录，不作为新迭代入口。

仅修改流程时使用 `worldlinefix/release-workflow`，不修改插件签名包或签名索引，
也不因流程改动提升人物版本。

`.gitattributes` 禁止 Git 对签名索引、插件包和固定官方工具转换换行；Windows 检出
与 CI 必须保留原始字节。哈希不符时先核对检出规则，不重新签名来掩盖字节变化。
