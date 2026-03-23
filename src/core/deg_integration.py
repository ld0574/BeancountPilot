"""
double-entry-generator integration module
"""

import subprocess
import tempfile
import json
import ast
import re
from pathlib import Path
from typing import Optional, Dict, Any
import csv

from src.core.deg_catalog import (
    get_official_provider_catalog,
    get_official_provider_codes,
    get_default_provider_aliases,
    get_bank_style_providers,
)


class DoubleEntryGenerator:
    """double-entry-generator CLI integration"""

    OFFICIAL_PROVIDER_CATALOG = get_official_provider_catalog()
    OFFICIAL_PROVIDER_CODES = get_official_provider_codes()
    DEFAULT_PROVIDER_ALIASES = get_default_provider_aliases()
    BANK_STYLE_PROVIDERS = get_bank_style_providers()

    def __init__(
        self,
        config_dir: Optional[Path] = None,
        executable: str = "double-entry-generator",
        provider_aliases: Optional[Dict[str, str]] = None,
    ):
        """
        Initialize DEG integration

        Args:
            config_dir: Configuration file directory
            executable: DEG executable command
            provider_aliases: Optional aliases mapping input provider -> DEG provider code
        """
        self.config_dir = config_dir or Path.home() / ".beancountpilot" / "config"
        self.executable = executable
        self.official_provider_catalog = get_official_provider_catalog()
        self.official_provider_codes = {item["code"] for item in self.official_provider_catalog}
        self.default_provider_aliases = get_default_provider_aliases()
        self.bank_style_providers = get_bank_style_providers()

        aliases = dict(self.default_provider_aliases)
        if provider_aliases:
            aliases.update({str(k).strip().lower(): str(v).strip().lower() for k, v in provider_aliases.items()})
        self.provider_aliases = aliases

    def _normalize_provider(self, provider: str) -> str:
        """Normalize app-side data source names to DEG provider names."""
        provider = (provider or "").strip().lower()
        return self.provider_aliases.get(provider, provider or "alipay")

    @staticmethod
    def _to_float(value: Any) -> float:
        """Best-effort conversion to float."""
        try:
            return float(value)
        except (TypeError, ValueError):
            return 0.0

    @staticmethod
    def _extract_raw_fields(transaction: Dict[str, Any]) -> Dict[str, str]:
        """Extract transaction raw_data to a normalized text dictionary."""
        raw_data = transaction.get("raw_data")
        parsed: Any = {}

        if isinstance(raw_data, dict):
            parsed = raw_data
        elif isinstance(raw_data, str) and raw_data.strip():
            try:
                parsed = json.loads(raw_data)
            except Exception:
                try:
                    parsed = ast.literal_eval(raw_data)
                except Exception:
                    parsed = {}

        if not isinstance(parsed, dict):
            return {}

        normalized: Dict[str, str] = {}
        for key, value in parsed.items():
            normalized[str(key).strip()] = "" if value is None else str(value).strip()

        # Legacy malformed Alipay rows from early parser versions:
        # {"-----": "2025-..", "None": [交易分类, 交易对方, ..., 收/付款方式, ...]}
        legacy_values = parsed.get("None")
        if isinstance(legacy_values, str):
            try:
                maybe_list = ast.literal_eval(legacy_values)
                if isinstance(maybe_list, list):
                    legacy_values = maybe_list
            except Exception:
                legacy_values = None
        if isinstance(legacy_values, list):
            legacy_headers = [
                "交易分类",
                "交易对方",
                "对方账号",
                "商品说明",
                "收/支",
                "金额",
                "收/付款方式",
                "交易状态",
                "交易订单号",
                "商家订单号",
                "备注",
            ]
            for idx, header in enumerate(legacy_headers):
                if idx >= len(legacy_values):
                    break
                text = str(legacy_values[idx] or "").strip()
                if text:
                    normalized.setdefault(header, text)

            for key, value in parsed.items():
                key_text = str(key or "").strip()
                value_text = str(value or "").strip()
                if key_text == "None" or not value_text:
                    continue
                if re.search(r"\d{4}[-/]\d{1,2}[-/]\d{1,2}", value_text):
                    normalized.setdefault("交易时间", value_text)
                    break

        return normalized

    @classmethod
    def _pick_value(
        cls,
        tx: Dict[str, Any],
        raw_fields: Dict[str, str],
        keys: list[str],
        default: str = "",
    ) -> str:
        """Pick first non-empty value from top-level tx and raw_data fields."""
        for key in keys:
            top = tx.get(key)
            if top is not None:
                text = str(top).strip()
                if text:
                    return text
            raw = raw_fields.get(key)
            if raw is not None:
                text = str(raw).strip()
                if text:
                    return text
        return default

    def call_double_entry_generator(
        self,
        csv_file: Path,
        config_file: Path,
        output_file: Path,
        provider: str = "alipay",
    ) -> Dict[str, Any]:
        """
        Call double-entry-generator CLI

        Args:
            csv_file: Input CSV file path
            config_file: Configuration file path
            output_file: Output file path
            provider: Data provider (alipay, wechat, etc.)

        Returns:
            Execution result
        """
        provider = self._normalize_provider(provider)
        command_variants = [
            # Preferred syntax for modern DEG versions.
            [
                self.executable,
                "translate",
                "--config", str(config_file),
                "-p", provider,
                "-t", "beancount",
                "-o", str(output_file),
                str(csv_file),
            ],
            # Backward-compatible syntax for older DEG versions.
            [
                self.executable,
                "translate",
                "--config", str(config_file),
                "--provider", provider,
                "--output", str(output_file),
                str(csv_file),
            ],
        ]

        try:
            result = None
            for cmd in command_variants:
                result = subprocess.run(
                    cmd,
                    capture_output=True,
                    text=True,
                    timeout=60,
                )

                # Success.
                if result.returncode == 0:
                    break

                # Retry with fallback flags only when CLI flags are not recognized.
                stderr = (result.stderr or "").lower()
                if "unknown flag" in stderr or "unknown shorthand flag" in stderr:
                    continue

                # Other failures should stop retrying.
                break

            if result and result.returncode == 0:
                # Read output file
                if output_file.exists():
                    with open(output_file, "r", encoding="utf-8") as f:
                        beancount_content = f.read()

                    return {
                        "success": True,
                        "beancount_file": beancount_content,
                        "message": "Generation successful",
                    }
                else:
                    return {
                        "success": False,
                        "message": "Output file not generated",
                    }
            else:
                return {
                    "success": False,
                    "message": f"CLI execution failed: {result.stderr if result else 'unknown error'}",
                }

        except subprocess.TimeoutExpired:
            return {
                "success": False,
                "message": "CLI execution timeout",
            }
        except FileNotFoundError:
            return {
                "success": False,
                "message": "double-entry-generator not installed or not in PATH",
            }
        except Exception as e:
            return {
                "success": False,
                "message": f"Unknown error: {str(e)}",
            }

    def generate_beancount_from_transactions(
        self,
        transactions: list[Dict[str, Any]],
        provider: str = "alipay",
        config_content: Optional[str] = None,
        deg_rules: Optional[list[Dict[str, Any]]] = None,
    ) -> Dict[str, Any]:
        """
        Generate Beancount file from transaction list

        Args:
            transactions: List of transactions
            provider: Data provider
            config_content: Configuration content (optional)

        Returns:
            Generation result
        """
        # Create temporary files
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)

            provider = self._normalize_provider(provider)

            # Write CSV file
            csv_file = temp_path / "transactions.csv"

            # Write configuration file
            config_file = temp_path / "config.yaml"
            if config_content:
                with open(config_file, "w", encoding="utf-8") as f:
                    f.write(config_content)
            else:
                # Use default configuration
                self._write_default_config(config_file, provider, deg_rules=deg_rules)

            # Output file
            output_file = temp_path / "output.beancount"

            # Call DEG with encoding fallback.
            # Alipay/WeChat/bank-style exports are commonly GB18030-encoded.
            encodings_to_try = self._csv_encodings_for_provider(provider)
            last_result: Dict[str, Any] = {
                "success": False,
                "message": "Generation failed before DEG execution",
            }

            for csv_encoding in encodings_to_try:
                self._write_csv(csv_file, transactions, provider, encoding=csv_encoding)
                if output_file.exists():
                    output_file.unlink()

                last_result = self.call_double_entry_generator(
                    csv_file, config_file, output_file, provider
                )
                if last_result.get("success"):
                    return last_result

            attempted = ", ".join(encodings_to_try)
            return {
                **last_result,
                "message": (
                    f"{last_result.get('message', 'Generation failed')} "
                    f"(tried CSV encodings: {attempted})"
                ).strip(),
            }

    def generate_beancount_from_csv_file(
        self,
        csv_file: Path | str,
        provider: str = "alipay",
        config_content: Optional[str] = None,
        deg_rules: Optional[list[Dict[str, Any]]] = None,
    ) -> Dict[str, Any]:
        """
        Generate Beancount directly from an existing raw CSV file.

        This bypasses transaction re-serialization and preserves original export shape.
        """
        csv_path = Path(csv_file)
        if not csv_path.exists():
            return {
                "success": False,
                "message": f"CSV file not found: {csv_path}",
            }

        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            provider = self._normalize_provider(provider)

            config_file = temp_path / "config.yaml"
            if config_content:
                with open(config_file, "w", encoding="utf-8") as f:
                    f.write(config_content)
            else:
                self._write_default_config(config_file, provider, deg_rules=deg_rules)

            output_file = temp_path / "output.beancount"
            return self.call_double_entry_generator(
                csv_file=csv_path,
                config_file=config_file,
                output_file=output_file,
                provider=provider,
            )

    def _csv_encodings_for_provider(self, provider: str) -> list[str]:
        """Return encoding candidates for provider-specific CSV compatibility."""
        provider = self._normalize_provider(provider)
        if provider in {"alipay", "wechat"} or provider in self.bank_style_providers:
            return ["gb18030", "utf-8-sig", "utf-8"]
        return ["utf-8-sig", "utf-8", "gb18030"]

    def _write_csv(
        self,
        csv_file: Path,
        transactions: list[Dict[str, Any]],
        provider: str,
        encoding: str = "utf-8",
    ) -> None:
        """Write CSV file"""
        # Determine CSV format based on provider
        provider = self._normalize_provider(provider)
        if provider == "alipay":
            # Match official Alipay export column order to keep DEG parser compatible.
            fieldnames = [
                "交易时间",
                "交易分类",
                "交易对方",
                "对方账号",
                "商品说明",
                "收/支",
                "金额",
                "收/付款方式",
                "交易状态",
                "交易订单号",
                "商家订单号",
                "备注",
            ]
        elif provider == "wechat":
            fieldnames = ["交易时间", "商品", "收/支", "金额(元)", "交易类型", "交易对方", "当前状态"]
        elif provider in self.bank_style_providers:
            fieldnames = ["交易日期", "摘要", "借贷标志", "收入金额", "支出金额", "对方户名"]
        else:
            # 通用格式
            fieldnames = ["time", "item", "type", "amount", "peer", "status"]

        with open(csv_file, "w", encoding=encoding, newline="") as f:
            writer = csv.DictWriter(f, fieldnames=fieldnames)
            writer.writeheader()

            for tx in transactions:
                raw_fields = self._extract_raw_fields(tx if isinstance(tx, dict) else {})
                row = {}
                for field in fieldnames:
                    # Map field names
                    if field == "交易时间" or field == "time":
                        row[field] = self._pick_value(
                            tx, raw_fields, ["time", "交易时间", "交易日期", "记账日期", "日期"], default=""
                        )
                    elif field == "交易分类":
                        row[field] = self._pick_value(
                            tx,
                            raw_fields,
                            ["category", "交易分类", "消费分类", "分类", "类型", "item", "商品说明"],
                            default="",
                        )
                    elif field == "商品说明" or field == "商品" or field == "item":
                        row[field] = self._pick_value(
                            tx,
                            raw_fields,
                            ["item", "商品说明", "商品", "摘要", "备注", "交易描述"],
                            default="",
                        )
                    elif field == "收/支" or field == "type":
                        row[field] = self._pick_value(
                            tx, raw_fields, ["type", "收/支", "交易类型", "借贷标志", "借贷方向"], default=""
                        )
                    elif field == "金额" or field == "金额(元)" or field == "amount":
                        row[field] = self._pick_value(
                            tx,
                            raw_fields,
                            ["amount", "金额", "金额(元)", "交易金额", "支出金额", "收入金额"],
                            default="",
                        )
                    elif field == "交易对方" or field == "peer":
                        row[field] = self._pick_value(
                            tx, raw_fields, ["peer", "交易对方", "对方户名", "商户名称", "收款方", "付款方"], default=""
                        )
                    elif field == "交易状态" or field == "当前状态" or field == "status":
                        row[field] = self._pick_value(
                            tx, raw_fields, ["status", "交易状态", "当前状态", "状态"], default="交易成功"
                        )
                    elif field == "对方账号":
                        row[field] = self._pick_value(
                            tx, raw_fields, ["peer_account", "对方账号", "对方账户"], default="/"
                        ) or "/"
                    elif field == "收/付款方式":
                        row[field] = self._pick_value(
                            tx,
                            raw_fields,
                            ["method", "收/付款方式", "支付方式", "付款方式", "支付渠道"],
                            default="",
                        )
                    elif field == "交易订单号":
                        row[field] = self._pick_value(
                            tx,
                            raw_fields,
                            ["transaction_id", "交易订单号", "order_id", "订单号"],
                            default="",
                        )
                    elif field == "商家订单号":
                        row[field] = self._pick_value(
                            tx,
                            raw_fields,
                            ["merchant_order_id", "商家订单号"],
                            default="",
                        )
                    elif field == "备注":
                        row[field] = self._pick_value(tx, raw_fields, ["note", "备注"], default="")
                    elif field == "交易日期":
                        row[field] = self._pick_value(
                            tx, raw_fields, ["time", "交易日期", "交易时间", "记账日期"], default=""
                        )
                    elif field == "摘要":
                        row[field] = self._pick_value(
                            tx, raw_fields, ["item", "摘要", "交易摘要", "category", "交易分类", "消费分类"], default=""
                        )
                    elif field == "借贷标志":
                        tx_type = self._pick_value(
                            tx, raw_fields, ["type", "收/支", "交易类型", "借贷标志"], default=""
                        )
                        row[field] = "贷" if any(k in tx_type for k in ("收", "入", "贷")) else "借"
                    elif field == "收入金额":
                        amount = self._to_float(
                            self._pick_value(tx, raw_fields, ["amount", "收入金额", "金额", "交易金额"], default="0")
                        )
                        tx_type = self._pick_value(
                            tx, raw_fields, ["type", "收/支", "交易类型", "借贷标志"], default=""
                        )
                        is_income = amount > 0 and any(k in tx_type for k in ("收", "入", "贷"))
                        row[field] = f"{amount:.2f}" if is_income else ""
                    elif field == "支出金额":
                        amount = self._to_float(
                            self._pick_value(tx, raw_fields, ["amount", "支出金额", "金额", "交易金额"], default="0")
                        )
                        tx_type = self._pick_value(
                            tx, raw_fields, ["type", "收/支", "交易类型", "借贷标志"], default=""
                        )
                        is_income = amount > 0 and any(k in tx_type for k in ("收", "入", "贷"))
                        row[field] = "" if is_income else f"{abs(amount):.2f}"
                    elif field == "对方户名":
                        row[field] = self._pick_value(
                            tx, raw_fields, ["peer", "对方户名", "交易对方", "收款人", "付款人"], default=""
                        )
                writer.writerow(row)

    def _write_default_config(
        self,
        config_file: Path,
        provider: str,
        deg_rules: Optional[list[Dict[str, Any]]] = None,
    ) -> None:
        """Write default configuration file"""
        import yaml

        provider = self._normalize_provider(provider)
        config = {
            "defaultMinusAccount": "Income:Other",
            "defaultPlusAccount": "Expenses:Other",
            "defaultCurrency": "CNY",
            "title": "BeancountPilot",
            provider: {
                "rules": deg_rules or [],
            },
        }

        with open(config_file, "w", encoding="utf-8") as f:
            yaml.dump(config, f, allow_unicode=True, sort_keys=False)

    def check_deg_installed(self) -> bool:
        """Check if double-entry-generator is installed"""
        return self.get_deg_status()["installed"]

    def get_deg_status(self) -> Dict[str, Any]:
        """Get DEG installation status and version text if available."""
        # Newer DEG versions use `version` subcommand; some builds may still support `--version`.
        version_checks = [
            [self.executable, "version"],
            [self.executable, "--version"],
        ]

        for cmd in version_checks:
            try:
                result = subprocess.run(
                    cmd,
                    capture_output=True,
                    text=True,
                    timeout=5,
                )
                if result.returncode == 0:
                    output = (result.stdout or result.stderr or "").strip()
                    version = output.splitlines()[0] if output else ""
                    return {
                        "installed": True,
                        "version": version,
                    }
            except (FileNotFoundError, subprocess.TimeoutExpired):
                continue

        return {
            "installed": False,
            "version": "",
        }
