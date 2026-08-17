# 安全说明

ChefPal 是个人学习 / 演示项目，代码按 MIT 协议开源。**不建议直接在生产环境使用**，如要部署请自行评估并加固。

## 已知的安全边界

- **默认密钥仅用于本地开发**：`apps/server/.env.example` 与 `apps/server/app/core/config.py` 中的 `JWT_SECRET` 是占位值，部署到公网前必须替换为强随机值（例如 `openssl rand -hex 32`）。
- **AI 内容不构成专业建议**：AI 生成的菜谱与回答为通用烹饪建议，不构成医疗 / 营养处方。
- **依赖与数据**：知识库种子数据（HowToCook）运行时从 GitHub 拉取，请留意其来源的可信度；第三方依赖请定期更新。

## 报告漏洞

如果你发现了安全漏洞（如密钥泄漏、越权访问、注入等）：

1. **不要公开**：请勿在 Issues / PR 中直接贴出漏洞细节。
2. 通过 GitHub 的 **Private vulnerability reporting** 功能提交（仓库 → Security → Report a vulnerability），或私信维护者。
3. 若包含截图 / 复现步骤，请脱敏后再提供。

维护者会尽快确认并修复。修复前请勿公开披露。

## 密钥自查

给仓库提任何改动前，请确认没有把以下内容提交进 git：

- `DASHSCOPE_API_KEY` / `ZHIPU_API_KEY` / `WECHAT_SECRET` / `COS_SECRET_KEY` 等真实密钥
- 任何 `.env` 文件（仓库只跟踪 `.env.example`）
- 私钥、token、密码

> 一旦真实密钥进入过 git 历史，**修改代码无法抹除历史**——请立即视为已泄漏并到对应平台轮换该密钥。
