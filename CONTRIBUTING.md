# Contributing to BeancountPilot

Thank you for your interest in contributing to BeancountPilot! This document provides guidelines and instructions for contributing to the project.

## Table of Contents

- [Code of Conduct](#code-of-conduct)
- [Getting Started](#getting-started)
- [Development Setup](#development-setup)
- [Adding a New Language](#adding-a-new-language)
- [Submitting Changes](#submitting-changes)
- [Coding Standards](#coding-standards)

## Code of Conduct

Be respectful and constructive. We aim to maintain a welcoming environment for all contributors.

## Getting Started

1. Fork the repository at https://github.com/ld0574/BeancountPilot
2. Clone your fork: `git clone https://github.com/your-username/BeancountPilot.git`
3. Create a new branch: `git checkout -b feature/your-feature-name`

## Development Setup

### Prerequisites

- Python 3.11+
- pip

### Install Dependencies

```bash
pip install -r requirements.txt
```

### Run the Backend

```bash
cd src/api
python main.py
```

The backend API will be available at `http://localhost:8000`.

### Run the Frontend

```bash
cd frontend
streamlit run app.py
```

The frontend will be available at `http://localhost:8501`.

## Adding a New Language

BeancountPilot supports internationalization (i18n) and you can easily add support for new languages.

### Step 1: Create a Translation File

Create a new JSON file in the `frontend/locales/` directory with the language code as the filename.

Example for French (`fr.json`):

```json
{
  "app_title": "BeancountPilot",
  "navigation": "Navigation",
  "upload_files": "📁 Upload Files",
  "transaction_classification": "🏷️ Transaction Classification",
  "settings": "⚙️ Settings",
  "language": "Language",
  "english": "English",
  "chinese": "中文",
  "french": "Français",
  ...
}
```

### Step 2: Translate All Keys

Copy all keys from [`frontend/locales/en.json`](frontend/locales/en.json) and translate the values to your target language.

**Important:**

- Keep the JSON structure exactly the same as the English version
- Do not modify the keys (they are used in the code)
- Only translate the values
- Keep placeholders like `{filename}`, `{count}`, `{error}` intact

### Step 3: Add Language Option

Update [`frontend/i18n.py`](frontend/i18n.py) to add your language to the options list:

```python
def get_language_options() -> list:
    """
    Get available language options

    Returns:
        List of (lang_code, lang_name) tuples
    """
    return [
        ("en", t("english")),
        ("zh", t("chinese")),
        ("fr", t("french")),  # Add your language here
    ]
```

### Step 4: Test

1. Restart the frontend application
2. Select your new language from the language dropdown in the sidebar
3. Verify all text is displayed correctly

### Step 5: Submit Your Contribution

1. Commit your changes: `git commit -m "Add French language support"`
2. Push to your fork: `git push origin feature/your-feature-name`
3. Create a pull request at https://github.com/ld0574/BeancountPilot/pulls

Include in your pull request:

- The new translation file in `frontend/locales/`
- The updated `frontend/i18n.py` file
- A screenshot showing the new language in action

### Language Code Standards

Use standard ISO 639-1 language codes:

- `en` - English
- `zh` - Chinese
- `fr` - French
- `de` - German
- `es` - Spanish
- `ja` - Japanese
- `ko` - Korean
- etc.

## Submitting Changes

1. Commit your changes: `git commit -m "Add French language support"`
2. Push to your fork: `git push origin feature/your-feature-name`
3. Create a pull request at https://github.com/ld0574/BeancountPilot/pulls

### Pull Request Guidelines

- Provide a clear description of your changes
- Reference any related issues
- Include screenshots for UI changes
- Ensure all tests pass
- Update documentation if needed

## Coding Standards

### Python

- Follow PEP 8 style guide
- Use type hints where appropriate
- Write docstrings for all functions and classes
- Keep functions focused and small

### Documentation

- All code comments and docstrings must be in English
- Update this CONTRIBUTING.md when making significant changes
- Update README.md for user-facing changes

### Testing

- Write tests for new features
- Ensure existing tests pass before submitting
- Test on both Windows and macOS/Linux if possible

## Questions?

If you have questions, please open an issue at https://github.com/ld0574/BeancountPilot/issues.

Thank you for contributing!
