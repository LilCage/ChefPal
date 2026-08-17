# 参与贡献

感谢你愿意给 ChefPal 添砖加瓦 🍳 这是一个个人学习 / 演示项目，欢迎任何形式的贡献：修 bug、加功能、补文档、提建议都行。

## 开发环境

### 后端（apps/server）

```bash
docker compose up -d postgres          # 本地 PostgreSQL（pgvector）
cd apps/server
python -m venv .venv && source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -e '.[dev]'
cp .env.example .env                    # 填入 DASHSCOPE_API_KEY 等
alembic upgrade head
pytest -q                               # 全部用例（mock 隔离 AI，无需真实密钥）
```

### 小程序（apps/miniapp）

```bash
cd apps/miniapp
npm install
cp .env.example .env
npm run dev:weapp                       # 用微信开发者工具打开 apps/miniapp/dist
```

注意：`apps/miniapp/project.config.json` 里是占位 AppID（`touristappid`），真机预览请在微信开发者工具里填你自己的 AppID。

## 代码风格

- **Python**：遵循 [ruff](https://docs.astral.sh/ruff/)（配置见 `apps/server/pyproject.toml`）。提交前跑一遍：

  ```bash
  cd apps/server
  ruff check . --fix
  ```

- **TypeScript**：保持现有风格，提交前确保 `tsc --noEmit` 与 `npm run build:weapp` 通过。
- **提交信息**：使用约定式提交（Conventional Commits），与本仓库历史一致：

  ```
  feat: 新增 XXX
  fix: 修复 XXX
  docs: 更新 README
  chore: 依赖升级 / 基础设施
  test: 补充用例
  ```

## 提 PR 流程

1. fork 仓库，从 `main` 切分支：`git checkout -b feat/your-feature`
2. 小步提交，提交信息见上；一个 PR 只做一件事
3. 跑通后端 `pytest` 和小程序 `npm run build:weapp`
4. 提 PR，按 [PR 模板](.github/PULL_REQUEST_TEMPLATE.md) 填写；CI 会同时跑后端测试和小程序构建

## 提问与讨论

- 使用类问题先看 [README](README.md) 和 [docs/](docs/)；找不到答案再到 [Issues](https://github.com/LilCage/ChefPal/issues) 提问。
- 安全问题不要公开提，走 [SECURITY.md](SECURITY.md) 里的流程。
