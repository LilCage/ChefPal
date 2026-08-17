# v0.1.0

ChefPal 首个公开版本：一个根据你手头食材实时生成菜谱的微信小程序（Taro 4 + React 18 + FastAPI + PostgreSQL/pgvector + DeepSeek）。

## 核心能力

- **对话式首页**：多轮问答、AI 联网搜索 + 结构化回答、SSE 流式打字机、问答历史/收藏
- **菜谱知识库（RAG）**：pgvector 向量检索，HowToCook 386 条种子 + AI 沉淀，未收录菜名现生成入库
- **食材魔方**：文字 / 拍照 / 语音输入 → 生成 TOP3 菜谱（匹配度 / 时间 / 难度 / 缺料提示）
- **发现 · 社区广场**：作品发布、瀑布流、点赞 / 评论、话题、关注、分享卡片
- **我的厨房**：微信一键登录、口味记忆、收藏、我的作品
- **膳食规划**：3 / 7 天计划 + 营养分析 + 购物清单
- 另有：时令食材日历、黑暗料理拯救、家庭投票、烹饪挑战、菜谱进化树、多智能体协作、语音助手、冰箱管家、链接 / 文档解析

## 工程与质量

- 后端 371 个 pytest 用例（mock 隔离 AI，无需真实密钥）
- CI（GitHub Actions）：后端测试（pgvector 服务）+ 小程序构建双门禁
- 全套开源配套：MIT 协议、CONTRIBUTING / SECURITY / CODE_OF_CONDUCT、Issue / PR 模板

## 快速开始

见根目录 [README](../README.md)「快速开始」：`docker compose up -d postgres` → 启动后端 → 运行小程序。
