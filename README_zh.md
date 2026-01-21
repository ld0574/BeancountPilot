# BeancountPilot

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
├── config/                # 配置文件
├── tests/                 # 测试
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

3. 初始化数据库

```bash
python -m src.db.init
```

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

### 1. 上传交易文件

支持支付宝、微信等平台导出的 CSV 文件。

### 2. AI 分类

系统会自动使用 AI 对交易进行分类，你也可以手动调整分类结果。

### 3. 生成 Beancount 文件

确认分类结果后，点击生成按钮导出 Beancount 格式文件。

### 4. 反馈学习

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

## 🤝 贡献

欢迎贡献！请查看 [CONTRIBUTING.md](CONTRIBUTING.md) 了解详情。

## 📄 许可证

本项目采用 Apache-2.0 许可证 - 详见 [LICENSE](LICENSE) 文件。

## 🙏 致谢

- [Beancount](https://beancount.github.io/) - 复式记账系统
- [double-entry-generator](https://github.com/debrouwere/double-entry-generator) - 交易转换工具
- [Streamlit](https://streamlit.io/) - Web 应用框架
- [FastAPI](https://fastapi.tiangolo.com/) - Web 框架

## 📧 联系方式

如有问题或建议，请提交 [Issue](https://github.com/ld0574/BeancountPilot/issues)。
