# BeancountPilot

> AI-powered intelligent transaction classification and workflow enhancement tool designed for Beancount users.

[中文文档](README_zh.md)

[![Python](https://img.shields.io/badge/Python-3.11+-blue.svg)](https://www.python.org/downloads/)
[![License](https://img.shields.io/badge/License-Apache--2.0-blue.svg)](LICENSE)
[![Version](https://img.shields.io/badge/Version-0.1.0-orange.svg)](https://github.com/ld0574/BeancountPilot)

## ✨ Features

- 🤖 **AI-Powered Classification**: Automatically classify transactions to correct Beancount accounts using LLM
- 📊 **Interactive UI**: User-friendly web interface built with Streamlit
- 🔄 **Rule Engine**: Rule-based classification that works alongside AI classification
- 📚 **Feedback Learning**: Continuously improve classification accuracy through user feedback
- 🔌 **Seamless Integration**: Compatible with existing `double-entry-generator` CLI workflow
- 🔒 **Local-First**: Ensure sensitive financial data stays under user control
- 🌐 **Multi-Provider Support**: Support for OpenAI, DeepSeek, Ollama, and custom OpenAI-compatible APIs

## 🏗️ Architecture

```
BeancountPilot/
├── src/                    # Backend source code
│   ├── api/               # FastAPI service
│   ├── ai/                # AI classification engine
│   ├── core/              # Core business logic
│   ├── db/                # Database layer
│   └── utils/             # Utility functions
├── frontend/              # Streamlit frontend
│   ├── components/        # UI components
│   ├── locales/           # i18n language files
│   ├── pages/             # Page modules
│   ├── app.py             # Main app entry
│   ├── config.py          # Frontend config
│   └── i18n.py            # Internationalization
├── config/                # Configuration files
├── tests/                 # Tests
└── docs/                  # Documentation
```

For detailed architecture design, please refer to [docs/architecture.md](docs/architecture.md).

## 🚀 Quick Start

### Prerequisites

- Python 3.11+
- pip or poetry

### Installation

1. Clone the repository

```bash
git clone https://github.com/ld0574/BeancountPilot.git
cd BeancountPilot
```

2. Install dependencies

```bash
pip install -r requirements.txt
```

3. Initialize database

```bash
python -m src.db.init
```

4. Configure AI API Key

Configure your AI Provider API Key in the application settings:

- **DeepSeek**: [https://platform.deepseek.com/](https://platform.deepseek.com/)
- **OpenAI**: [https://platform.openai.com/](https://platform.openai.com/)
- **Ollama**: Local deployment, no API Key required
- **Custom**: Any OpenAI-compatible API

### Running

Start backend service:

```bash
uvicorn src.api.main:app --reload --port 8000
```

Start frontend (new terminal):

```bash
streamlit run frontend/app.py
```

Visit [http://localhost:8501](http://localhost:8501) to get started.

## 📖 Usage Guide

### 1. Upload Transaction Files

Support CSV files exported from platforms like Alipay, WeChat, etc.

### 2. AI Classification

The system automatically uses AI to classify transactions, and you can manually adjust classification results.

### 3. Generate Beancount File

After confirming classification results, click the generate button to export Beancount format file.

### 4. Feedback Learning

By correcting classification results, the system automatically learns and optimizes future classifications.

## 🔧 Configuration

### AI Configuration

Configure AI Provider in `config/ai.yaml`:

```yaml
providers:
  deepseek:
    api_base: https://api.deepseek.com/v1
    api_key: ${DEEPSEEK_API_KEY}
    model: deepseek-chat
```

### Custom Provider

Support any OpenAI-compatible service:

```yaml
providers:
  custom:
    api_base: https://your-custom-api.com/v1
    api_key: ${CUSTOM_API_KEY}
    model: your-model-name
```

### Chart of Accounts Configuration

Configure your Beancount chart of accounts in application settings, for example:

```
Assets:Bank:Alipay
Assets:Bank:WeChat
Expenses:Food:Dining
Expenses:Transport:Taxi
...
```

## 🤝 Contributing

Contributions are welcome! Please see [CONTRIBUTING.md](CONTRIBUTING.md) for details.

## 📄 License

This project is licensed under Apache-2.0 License - see [LICENSE](LICENSE) file for details.

## 🙏 Acknowledgments

- [Beancount](https://beancount.github.io/) - Double-entry bookkeeping system
- [double-entry-generator](https://github.com/debrouwere/double-entry-generator) - Transaction conversion tool
- [Streamlit](https://streamlit.io/) - Web application framework
- [FastAPI](https://fastapi.tiangolo.com/) - Web framework

## 📧 Contact

For questions or suggestions, please submit an [Issue](https://github.com/ld0574/BeancountPilot/issues).
