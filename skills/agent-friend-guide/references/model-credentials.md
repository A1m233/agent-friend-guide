# 模型凭据

agent-friend 当前开放 DeepSeek 与 Kimi 两个模型调用渠道。使用某个渠道前，需要配置对应的 API Key，并确保账号有可用额度。OpenRouter 暂不维护，模型选择与凭据设置入口已隐藏。

初始默认对话模型是 Kimi 2.5，初始默认记忆模型是 DeepSeek Flash。已经在设置中主动选择过模型时，升级不会覆盖已有选择。

“新对话默认模型”只决定之后新建对话草稿的初始模型。修改并保存时不会重启服务，也不会改变当前会话或已经打开但尚未发送的草稿；当前会话可以在输入区单独切换模型。

保存或更换 DeepSeek、Kimi API Key 时，agent-friend 会先在线校验候选 Key，但不会生成模型回答。校验成功后才替换原配置，并自动应用到对话服务；明确校验失败时会保留原配置并显示失败原因。如果网络或渠道服务暂时不可用，页面会让你选择稍后重试，或确认“仍然保存”。确认保存的 Key 会显示“已配置”，可以之后点击“校验当前凭据”；校验成功时显示“已配置 · 已验证”。

## DeepSeek API Key

1. 登录 [DeepSeek 开放平台](https://platform.deepseek.com/)。
2. 打开 [API Keys](https://platform.deepseek.com/api_keys)。
3. 创建一个新 Key，并在页面只显示完整值时立即妥善保存。
4. 在 agent-friend 打开“设置 → 模型与凭据 → DeepSeek”，粘贴并保存。
5. 等待页面完成校验和应用。显示“已配置 · 已验证”后即可选择 DeepSeek 模型使用。

agent-friend 当前提供以下 DeepSeek 模型：

- DeepSeek V4 Flash：文本对话和工具调用；
- DeepSeek V4 Pro：文本对话和工具调用；
- DeepSeek V4 Flash Vision：文本、工具调用以及 JPEG、PNG、WebP 图片。

这三款模型都可在当前会话选择“关闭 / 低 / 高 / 最高”推理强度，默认关闭。切换模型时会先采用目标模型的默认档位，之后可以继续调整。

只有 DeepSeek V4 Flash Vision 可以添加图片。它不接受 PDF、TXT、GIF 或其它文件类型；单张图片最多 64 MiB，单轮最多 10 张且总计不超过 100 MiB。V4 Flash 与 V4 Pro 仍是纯文本模型。

官方文档：[DeepSeek API 文档](https://api-docs.deepseek.com/zh-cn/)。

## Kimi API Key

1. 登录 [Kimi 开放平台](https://platform.kimi.ai/)。
2. 打开 [API Keys](https://platform.kimi.ai/console/api-keys)。
3. 选择项目并创建 Key，保存页面展示的完整值。
4. 在 agent-friend 打开“设置 → 模型与凭据 → Kimi”，粘贴并保存。
5. 等待页面完成校验和应用。显示“已配置 · 已验证”后即可选择 Kimi 模型使用。

`platform.kimi.ai` 与其他 Kimi 平台的 Key 不一定通用，应从上面的开放平台创建。官方文档：[Kimi API 概览](https://platform.kimi.ai/docs/api/overview)。

Kimi K3（模型列表显示为 `kimi-k3`）支持文本对话和工具调用；当前会话可选择“低 / 高 / 最高”推理强度，默认“最高”，不提供关闭档位，暂不支持在 agent-friend 中添加附件。新增 K3 不会改变原有默认模型。

Kimi 2.6 与 Kimi 2.5 支持在当前会话关闭或开启推理，默认开启；Kimi 2.7 Code 与 Kimi 2.7 Code Highspeed 固定开启推理，不提供关闭或强度档位。

## OpenRouter 暂不维护

OpenRouter 模型和凭据设置不再向用户开放。隐藏入口不会主动删除以前保存的设置或凭据，也不会自动把旧会话切换到另一模型；这不代表旧渠道仍获得维护或保证可用。需要继续使用时，建议在当前会话和“新对话默认模型”中选择已配置的 DeepSeek 或 Kimi，不要为 agent-friend 新购 OpenRouter 额度。

如果已安装版本的模型列表与本文不同，以实际界面为准；旧版本可能没有 K3，或仍显示 OpenRouter 入口。

## 安全建议

- 不要把 Key 发到聊天、截图、Issue 或公开仓库。
- 为 agent-friend 单独创建 Key，便于撤销和查看用量。
- 怀疑泄露时立即到对应平台控制台撤销旧 Key 并创建新 Key。
