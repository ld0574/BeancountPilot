"""
double-entry-generator integration module
"""

import subprocess
import tempfile
from pathlib import Path
from typing import Optional, Dict, Any
import csv


class DoubleEntryGenerator:
    """double-entry-generator CLI integration"""

    def __init__(self, config_dir: Optional[Path] = None):
        """
        Initialize DEG integration

        Args:
            config_dir: Configuration file directory
        """
        self.config_dir = config_dir or Path.home() / ".beancountpilot" / "config"

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
        cmd = [
            "double-entry-generator",
            "translate",
            "--config", str(config_file),
            "--provider", provider,
            "--output", str(output_file),
            str(csv_file)
        ]

        try:
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=60,
            )

            if result.returncode == 0:
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
                    "message": f"CLI execution failed: {result.stderr}",
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
        if provider == "alipay":
            fieldnames = ["交易时间", "商品说明", "收/支", "金额", "交易对方", "交易状态"]
        elif provider == "wechat":
            fieldnames = ["交易时间", "商品", "收/支", "金额(元)", "交易类型", "交易对方", "当前状态"]
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
                writer.writerow(row)

    def _write_default_config(self, config_file: Path, provider: str) -> None:
        """Write default configuration file"""
        import yaml

        config = {
            "mapping": {
                "default": "Expenses:Misc",
            },
            "accounts": {
                "alipay": "Assets:Bank:Alipay",
                "wechat": "Assets:Bank:WeChat",
            },
        }

        with open(config_file, "w", encoding="utf-8") as f:
            yaml.dump(config, f, allow_unicode=True, sort_keys=False)

    def check_deg_installed(self) -> bool:
        """Check if double-entry-generator is installed"""
        try:
            result = subprocess.run(
                ["double-entry-generator", "--version"],
                capture_output=True,
                timeout=5,
            )
            return result.returncode == 0
        except (FileNotFoundError, subprocess.TimeoutExpired):
            return False
