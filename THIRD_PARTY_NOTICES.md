# 第三方组件与许可声明

ChefPal 遵循 MIT 协议开源，但仓库内包含 / 运行时使用的部分第三方内容遵循各自的许可，特此声明。

## 仓库内分发的资源

| 组件 | 来源 | 许可 |
|------|------|------|
| `apps/miniapp/scripts/zcool-kuaile.ttf`（站酷快乐体） | [站酷字体](https://www.zcool.com.cn/) | 站酷字体授权：允许免费商用与传播，不可单独出售字体文件；详见站酷字体官网授权说明 |
| 知识库种子数据（HowToCook 菜谱文本，运行时从 GitHub 拉取，不入库） | [Anduin2017/HowToCook](https://github.com/Anduin2017/HowToCook) | [Unlicense](https://unlicense.org/)（公有领域），拉取与再加工均在许可范围内 |

## 运行时依赖

- **Python 后端**：FastAPI、SQLAlchemy、Alembic、LangChain、pgvector 等，完整清单见 [`apps/server/pyproject.toml`](apps/server/pyproject.toml)。
- **小程序前端**：Taro、React、NutUI-React、Zustand 等，完整清单见 [`apps/miniapp/package.json`](apps/miniapp/package.json)。

以上依赖均通过官方包管理器安装，遵循各自开源许可（以 MIT / Apache-2.0 / BSD 为主）。

## 使用第三方内容时的义务

- **站酷快乐体**：可用于本项目及其衍生作品的界面展示与宣传；如将字体文件单独再分发，请遵守站酷官方授权条款。
- **HowToCook 数据**：Unlicense 允许任意使用；本项目在运行时拉取并按需结构化入库，不随代码仓库分发原始数据。

如有遗漏或疑问，欢迎提 Issue 指出。
