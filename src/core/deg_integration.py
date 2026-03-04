"""
double-entry-generator integration module
"""

import subprocess
import tempfile
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

            # Write CSV file
            csv_file = temp_path / "transactions.csv"
            self._write_csv(csv_file, transactions, provider)

            # Write configuration file
            config_file = temp_path / "config.yaml"
            if config_content:
                with open(config_file, "w", encoding="utf-8") as f:
                    f.write(config_content)
            else:
                # Use default configuration
                self._write_default_config(config_file, provider)

            # Output file
            output_file = temp_path / "output.beancount"

            # Call DEG
            return self.call_double_entry_generator(
                csv_file, config_file, output_file, provider
            )

    def _write_csv(
        self, csv_file: Path, transactions: list[Dict[str, Any]], provider: str
    ) -> None:
        """Write CSV file"""
        # Determine CSV format based on provider
        provider = self._normalize_provider(provider)
        if provider == "alipay":
            fieldnames = ["交易时间", "商品说明", "收/支", "金额", "交易对方", "交易状态"]
        elif provider == "wechat":
            fieldnames = ["交易时间", "商品", "收/支", "金额(元)", "交易类型", "交易对方", "当前状态"]
        elif provider in self.bank_style_providers:
            fieldnames = ["交易日期", "摘要", "借贷标志", "收入金额", "支出金额", "对方户名"]
        else:
            # 通用格式
            fieldnames = ["time", "item", "type", "amount", "peer", "status"]

        with open(csv_file, "w", encoding="utf-8", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=fieldnames)
            writer.writeheader()

            for tx in transactions:
                row = {}
                for field in fieldnames:
                    # Map field names
                    if field == "交易时间" or field == "time":
                        row[field] = tx.get("time", "")
                    elif field == "商品说明" or field == "商品" or field == "item":
                        row[field] = tx.get("item", "")
                    elif field == "收/支" or field == "type":
                        row[field] = tx.get("type", "")
                    elif field == "金额" or field == "金额(元)" or field == "amount":
                        row[field] = tx.get("amount", "")
                    elif field == "交易对方" or field == "peer":
                        row[field] = tx.get("peer", "")
                    elif field == "交易状态" or field == "当前状态" or field == "status":
                        row[field] = tx.get("status", "交易成功")
                    elif field == "交易日期":
                        row[field] = tx.get("time", "")
                    elif field == "摘要":
                        row[field] = tx.get("item", "") or tx.get("category", "")
                    elif field == "借贷标志":
                        tx_type = str(tx.get("type", ""))
                        row[field] = "贷" if any(k in tx_type for k in ("收", "入", "贷")) else "借"
                    elif field == "收入金额":
                        amount = self._to_float(tx.get("amount", 0) or 0)
                        tx_type = str(tx.get("type", ""))
                        is_income = amount > 0 and any(k in tx_type for k in ("收", "入", "贷"))
                        row[field] = f"{amount:.2f}" if is_income else ""
                    elif field == "支出金额":
                        amount = self._to_float(tx.get("amount", 0) or 0)
                        tx_type = str(tx.get("type", ""))
                        is_income = amount > 0 and any(k in tx_type for k in ("收", "入", "贷"))
                        row[field] = "" if is_income else f"{abs(amount):.2f}"
                    elif field == "对方户名":
                        row[field] = tx.get("peer", "")
                writer.writerow(row)

    def _write_default_config(self, config_file: Path, provider: str) -> None:
        """Write default configuration file"""
        import yaml

        provider = self._normalize_provider(provider)
        config = {
            "defaultMinusAccount": "Income:Other",
            "defaultPlusAccount": "Expenses:Misc",
            "defaultCurrency": "CNY",
            "title": "BeancountPilot",
            provider: {
                "rules": [],
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
