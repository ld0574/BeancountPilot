# BeancountPilot

<p align="center">
  <img src="docs/beanlogo.png" alt="BeancountPilot" width="360">
</p>

> AI 增强的智能交易分类和工作流增强工具，专为 Beancount 用户设计。

[English Documentation](README.md)

[![Python](https://img.shields.io/badge/Python-3.11+-blue.svg)](https://www.python.org/downloads/)
[![License](https://img.shields.io/badge/License-Apache--2.0-blue.svg)](LICENSE)
[![Version](https://img.shields.io/badge/Version-0.1.0-orange.svg)](https://github.com/ld0574/BeancountPilot)

## ✨ 特性

- 🤖 **AI 智能分类**：利用大语言模型自动将交易分类到正确的 Beancount 账户
- 📊 **交互式界面**：基于 Streamlit 的友好 Web 界面
- 🔄 **规则引擎**：支持基于规则的分类，可与 AI 分类结合使用
- 📚 **反馈学习**：通过用户反馈持续优化分类准确性
- 🔌 **无缝集成**：兼容现有的 `double-entry-generator` CLI 工作流
- 🔒 **本地优先**：确保敏感财务数据始终在用户控制下
- 🌐 **多 Provider 支持**：支持 OpenAI、DeepSeek、Ollama 等多种 AI 服务

## 🏗️ 架构

```
BeancountPilot/
├── src/                    # 后端源代码
│   ├── api/               # FastAPI 服务
│   ├── ai/                # AI 分类引擎
│   ├── core/              # 核心业务逻辑
│   ├── db/                # 数据库层
│   └── utils/             # 工具函数
├── frontend/              # Streamlit 前端
│   ├── components/        # UI 组件
│   ├── locales/           # i18n 语言文件
│   ├── views/             # 页面模块
│   ├── app.py             # 主应用入口
│   ├── config.py          # 前端配置
│   └── i18n.py            # 国际化支持
├── config/                # 配置文件
├── tests/                 # 测试
│   ├── unit/              # 单元测试
│   └── integration/       # 集成测试
└── docs/                  # 文档
```

详细的架构设计请参考 [docs/architecture.md](docs/architecture.md)。

## 🚀 快速开始

### 前置要求

- Python 3.11+
- pip 或 poetry

### 安装

1. 克隆仓库

```bash
git clone https://github.com/ld0574/BeancountPilot.git
cd BeancountPilot
```

2. 安装依赖

```bash
pip install -r requirements.txt
```

开发环境需要额外安装依赖：

```bash
pip install -r requirements-dev.txt
```

3. 初始化数据库

```bash
python -m src.db.init
```

该步骤还会在 `~/.beancountpilot/data/` 初始化默认 Beancount 模板文件：
`assets.bean`、`equity.bean`、`expenses.bean`、`income.bean`、`liabilities.bean`。

4. 配置 AI API Key

在应用设置中配置你的 AI Provider API Key：

- **DeepSeek**: [https://platform.deepseek.com/](https://platform.deepseek.com/)
- **OpenAI**: [https://platform.openai.com/](https://platform.openai.com/)
- **Ollama**: 本地部署，无需 API Key
- **自定义**: 任何兼容 OpenAI 格式的 API

### 运行

启动后端服务：

```bash
uvicorn src.api.main:app --reload --port 8000
```

启动前端（新终端）：

```bash
streamlit run frontend/app.py
```

访问 [http://localhost:8501](http://localhost:8501) 开始使用。

## 📖 使用指南

### 1. 配置账本模板文件（Workflow 第一步）

进入 `Settings -> Chart of Accounts -> Ledger Template Files`。

推荐流程：

1. 先编辑 `liabilities.bean`（或其他 `.bean` 文件），点击 `Save Ledger File`。
2. 确认上方 `Chart of Accounts` 已从账本文件同步。
3. 如需调整账户表，修改后点击 `Sync To Ledger Files` 回写到账本文件。

这样可以保持 `Chart of Accounts` 与五个账本模板文件始终一致：  
`assets.bean`、`equity.bean`、`expenses.bean`、`income.bean`、`liabilities.bean`。

### 2. 上传交易文件

支持支付宝、微信、建设银行等平台导出的 `CSV/XLS/XLSX` 文件。

DEG Provider 调用已对齐官方 CLI 语义（`translate -p <provider> -t beancount`），示例：

```bash
double-entry-generator translate -p ccb -t beancount ccb_records.xls
double-entry-generator translate -p alipay -t beancount alipay_records.csv
```

若你的数据源名称与 DEG provider 代码不一致，可在 `Settings -> DEG Mapping` 中配置映射：

1. 官方 provider 字典来自 `config/deg.yaml`（页面内只读），显示名称优先通过 `i18n_key` 从前端 locale 文案读取。
2. 尽量把来源标签映射到官方 target 代码。
3. 如果映射到非官方代码，除非你的 DEG 二进制/自定义解析器支持，否则可能转换失败。

### 3. AI 分类

系统会自动使用 AI 对交易进行分类，你也可以手动调整分类结果。
规则流程已改为 DEG 优先：先匹配已有 DEG 规则，unknown 再交给 AI，高置信度 AI 结果可自动沉淀为规则。
Settings 中的 Rule Management 现用于管理 DEG 风格规则（通用规则 + Provider 专属规则）。规则字段说明参考：
https://deb-sig.github.io/double-entry-generator/configuration/rules.html

另外，`Settings -> Rule Management` 已支持导入/导出完整 DEG YAML：

- 可直接导入 `import/alipay.yaml` 这种 Provider 全量配置。
- 可导出 Provider YAML，并按下面方式执行 DEG：

```bash
double-entry-generator translate --config ./alipay.yaml --provider alipay --output ./alipay.beancount alipay_records.csv
```

### 4. 生成 Beancount 文件

确认分类结果后，点击生成按钮导出 Beancount 格式文件。

### 5. 反馈学习

通过修正分类结果，系统会自动学习并优化后续分类。

## 🔧 配置

### AI 配置

在 `config/ai.yaml` 中配置 AI Provider：

```yaml
providers:
  deepseek:
    api_base: https://api.deepseek.com/v1
    api_key: ${DEEPSEEK_API_KEY}
    model: deepseek-chat
```

### 自定义 Provider

支持任何兼容 OpenAI API 格式的服务：

```yaml
providers:
  custom:
    api_base: https://your-custom-api.com/v1
    api_key: ${CUSTOM_API_KEY}
    model: your-model-name
```

### 账户表配置

在应用设置中配置你的 Beancount 账户表，例如：

```
Assets:Bank:Alipay
Assets:Bank:WeChat
Expenses:Food:Dining
Expenses:Transport:Taxi
...
```

## 🧪 测试

### 运行测试

运行所有测试：

```bash
pytest
```

仅运行单元测试：

```bash
pytest tests/unit/
```

仅运行集成测试：

```bash
pytest tests/integration/
```

运行测试并生成覆盖率报告：

```bash
pytest --cov=src --cov-report=html
```

### 测试覆盖率

项目具有全面的测试覆盖：

- **单元测试**：70+ 个测试，覆盖所有核心模块
- **集成测试**：8+ 个测试，用于 API 端点
- **总覆盖率**：80+ 个测试，涵盖数据库、AI、核心业务逻辑、API 和工具函数

### 测试结构

```
tests/
├── unit/                      # 单元测试
│   ├── test_db_models.py       # 数据库模型测试
│   ├── test_db_repositories.py  # 仓库层测试
│   ├── test_ai_base.py         # AI 提供者基类测试
│   ├── test_ai_prompt.py       # 提示词构建/解析测试
│   ├── test_ai_factory.py      # 提供者工厂测试
│   ├── test_core_rule_engine.py # 规则引擎测试
│   ├── test_utils_config.py    # 配置工具测试
│   └── test_api_schemas.py    # API 模式测试
└── integration/
    └── test_api_integration.py  # API 集成测试
```

## 🤝 贡献

欢迎贡献！请查看 [CONTRIBUTING.md](CONTRIBUTING.md) 了解详情。

## 📄 许可证

本项目采用 Apache-2.0 许可证 - 详见 [LICENSE](LICENSE) 文件。

## 🙏 致谢

- [Beancount](https://beancount.github.io/) - 复式记账系统
- [double-entry-generator](https://github.com/deb-sig/double-entry-generator) - 基于规则的复式记账导入器
- [Streamlit](https://streamlit.io/) - Web 应用框架
- [FastAPI](https://fastapi.tiangolo.com/) - Web 框架

## 📧 联系方式

如有问题或建议，请提交 [Issue](https://github.com/ld0574/BeancountPilot/issues)。
