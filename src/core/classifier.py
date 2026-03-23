"""
Classification coordinator - coordinates AI classification and rule engine
"""

import json
import ast
import re
from typing import Dict, Any, List, Optional, Callable

from sqlalchemy.orm import Session

from src.ai.base import BaseLLMProvider
from src.ai.factory import create_provider
from src.core.deg_integration import DoubleEntryGenerator
from src.db.repositories import (
    TransactionRepository,
    ClassificationRepository,
    RuleRepository,
    UserConfigRepository,
)
from src.core.rule_engine import RuleEngine
from src.utils.config import get_config, expand_path


class Classifier:
    """Classification coordinator"""

    def __init__(self, db: Session, provider_name: str = "deepseek"):
        """
        Initialize classifier

        Args:
            db: Database session
            provider_name: AI Provider name
        """
        self.db = db
        self.provider_name = provider_name
        self.provider: Optional[BaseLLMProvider] = None
        self.rule_engine = RuleEngine(db)

    @staticmethod
    def _first_text_value(value: Any) -> str:
        """Get first non-empty text from str/list values."""
        if isinstance(value, list):
            for item in value:
                text = str(item or "").strip()
                if text:
                    return text
            return ""
        return str(value or "").strip()

    @staticmethod
    def _is_empty_or_other_account(account: str) -> bool:
        """Treat empty/slash/leaf=Other as invalid classified account."""
        text = str(account or "").strip()
        if not text or text == "/":
            return True
        return text.split(":")[-1].strip().lower() == "other"

    @classmethod
    def _has_complete_accounts(cls, target_account: str, method_account: str) -> bool:
        """Require both target/method accounts to be non-empty and not Other."""
        return not cls._is_empty_or_other_account(target_account) and not cls._is_empty_or_other_account(method_account)

    @classmethod
    def _extract_rule_accounts(cls, rule: Any) -> tuple[str, str]:
        """Extract target/method account from stored rule model."""
        target_account = str(getattr(rule, "account", "") or "").strip()
        method_account = ""
        deg_has_target = True
        try:
            conditions = json.loads(getattr(rule, "conditions", "") or "{}")
        except Exception:
            conditions = {}
        if isinstance(conditions, dict):
            method_account = cls._first_text_value(conditions.get("methodAccount", ""))
            if conditions.get("_deg_has_target") is False:
                deg_has_target = False
            elif conditions.get("_deg_only") is True and "targetAccount" not in conditions:
                deg_has_target = False
            if not deg_has_target:
                target_account = cls._first_text_value(conditions.get("targetAccount", ""))
        if method_account == "/":
            method_account = ""
        return target_account, method_account

    def _select_rule_accounts(
        self,
        matched_rules: List[Any],
    ) -> tuple[str, str, float]:
        """
        Select best target/method accounts from matched rules.

        DEG configs often split target and method into separate rules.
        This helper first prefers a single complete rule; otherwise it
        merges target/method from the best matched rules by confidence.
        """
        if not matched_rules:
            return "", "", 0.0

        user_rules = [r for r in matched_rules if str(getattr(r, "source", "")).strip().lower() == "user"]
        candidate_rules = user_rules or matched_rules

        def _rule_specificity(rule: Any) -> int:
            """
            Heuristic specificity score for tie-breaking.

            Prefer rules with more explicit conditions (e.g., peer+method)
            over broad generic rules (e.g., method-only).
            """
            try:
                conditions = json.loads(getattr(rule, "conditions", "") or "{}")
            except Exception:
                conditions = {}
            if not isinstance(conditions, dict):
                return 0

            ignored = {
                "provider",
                "sep",
                "_deg_only",
                "_deg_has_target",
                "fullMatch",
                "description",
            }
            score = 0
            for key, value in conditions.items():
                if key in ignored or value in (None, "", []):
                    continue
                score += 1
                if isinstance(value, list):
                    score += min(len([v for v in value if str(v).strip()]), 3)
            return score

        complete_rules: List[tuple[float, int, str, str]] = []
        target_rules: List[tuple[float, int, str]] = []
        method_rules: List[tuple[float, int, str]] = []

        for rule in candidate_rules:
            target_account, method_account = self._extract_rule_accounts(rule)
            confidence = float(getattr(rule, "confidence", 0.0) or 0.0)
            specificity = _rule_specificity(rule)

            target_valid = not self._is_empty_or_other_account(target_account)
            method_valid = not self._is_empty_or_other_account(method_account)

            if target_valid and method_valid:
                complete_rules.append((confidence, specificity, target_account, method_account))
            if target_valid:
                target_rules.append((confidence, specificity, target_account))
            if method_valid:
                method_rules.append((confidence, specificity, method_account))

        if complete_rules:
            confidence, _, target_account, method_account = max(
                complete_rules,
                key=lambda item: (item[0], item[1]),
            )
            return target_account, method_account, confidence

        target_confidence, _, target_account = (
            max(target_rules, key=lambda item: (item[0], item[1]))
            if target_rules
            else (0.0, 0, "")
        )
        method_confidence, _, method_account = (
            max(method_rules, key=lambda item: (item[0], item[1]))
            if method_rules
            else (0.0, 0, "")
        )
        return target_account, method_account, max(target_confidence, method_confidence)

    @staticmethod
    def _extract_tx_fields(transaction: Dict[str, Any]) -> Dict[str, str]:
        """Extract provider-specific raw fields from transaction.raw_data."""
        raw_data = transaction.get("raw_data", "")
        parsed_dict: Dict[str, str] = {}
        if isinstance(raw_data, dict):
            parsed_dict = {str(k): str(v or "") for k, v in raw_data.items()}
        else:
            if not raw_data:
                return {}
            # Prefer JSON; fallback for legacy str(dict) records.
            parsed = None
            try:
                parsed = json.loads(raw_data)
            except Exception:
                try:
                    parsed = ast.literal_eval(raw_data)
                except Exception:
                    parsed = None
            if not isinstance(parsed, dict):
                return {}
            parsed_dict = {str(k): str(v or "") for k, v in parsed.items()}

        # Legacy malformed Alipay rows:
        # {"-----": "2025-..", "None": [交易分类, 交易对方, 对方账号, 商品说明, 收/支, 金额, 收/付款方式, 交易状态, ...]}
        raw_none = parsed_dict.get("None", "")
        legacy_values: list[str] = []
        if raw_none:
            try:
                maybe = ast.literal_eval(raw_none) if isinstance(raw_none, str) else raw_none
                if isinstance(maybe, list):
                    legacy_values = [str(v or "").strip() for v in maybe]
            except Exception:
                legacy_values = []
        if legacy_values:
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
                if legacy_values[idx]:
                    parsed_dict.setdefault(header, legacy_values[idx])

        # Normalize aliases for rule matching.
        method_value = (
            parsed_dict.get("method")
            or parsed_dict.get("收/付款方式")
            or parsed_dict.get("支付方式")
            or parsed_dict.get("付款方式")
            or parsed_dict.get("支付渠道")
            or ""
        )
        status_value = (
            parsed_dict.get("status")
            or parsed_dict.get("交易状态")
            or parsed_dict.get("当前状态")
            or parsed_dict.get("状态")
            or ""
        )
        tx_type_value = (
            parsed_dict.get("txType")
            or parsed_dict.get("transactionType")
            or parsed_dict.get("交易类型")
            or parsed_dict.get("交易分类")
            or parsed_dict.get("消费分类")
            or ""
        )
        if method_value:
            parsed_dict["method"] = str(method_value)
        if status_value:
            parsed_dict["status"] = str(status_value)
        if tx_type_value:
            parsed_dict["txType"] = str(tx_type_value)

        return parsed_dict

    @staticmethod
    def _extract_order_key(tx_fields: Dict[str, str]) -> str:
        """Extract stable merchant/order key for payment-refund pairing."""
        for key in ("商家订单号", "商户单号", "merchantId", "交易订单号", "交易单号", "orderId"):
            value = str(tx_fields.get(key, "")).strip()
            if value:
                # Refund rows may append suffix to the original order id.
                return value.split("_", 1)[0]
        return ""

    @staticmethod
    def _is_refund_like(transaction: Dict[str, Any], tx_fields: Dict[str, str]) -> bool:
        """Detect refund-like rows from category/item/type/status signals."""
        text = " ".join(
            [
                str(transaction.get("category", "") or ""),
                str(transaction.get("item", "") or ""),
                str(transaction.get("type", "") or ""),
                str(tx_fields.get("交易状态", "") or ""),
                str(tx_fields.get("status", "") or ""),
            ]
        )
        lowered = text.lower()
        return (
            "退款" in text
            or "退货" in text
            or "refund" in lowered
            or "退款成功" in text
        )

    @staticmethod
    def _is_payment_like(transaction: Dict[str, Any], tx_fields: Dict[str, str]) -> bool:
        """Detect payment-like rows that can be offset by refunds."""
        text = " ".join(
            [
                str(transaction.get("type", "") or ""),
                str(transaction.get("category", "") or ""),
                str(tx_fields.get("交易状态", "") or ""),
                str(tx_fields.get("status", "") or ""),
            ]
        )
        lowered = text.lower()
        if "支出" in text:
            return True
        # Some cancelled payments appear as closed but still represent payment side.
        if "交易关闭" in text:
            return True
        return "payment" in lowered and "refund" not in lowered

    def _detect_offset_pair_indices(self, transactions: List[Dict[str, Any]]) -> set[int]:
        """
        Detect transactions that form payment-refund offset pairs.

        We only pair rows when a stable order key exists and the absolute amount matches.
        """
        groups: Dict[tuple[str, str, float], List[tuple[int, bool, bool]]] = {}

        for idx, tx in enumerate(transactions):
            tx_fields = self._extract_tx_fields(tx)
            order_key = self._extract_order_key(tx_fields)
            if not order_key:
                continue

            try:
                amount = round(abs(float(tx.get("amount", 0.0) or 0.0)), 2)
            except Exception:
                amount = 0.0
            if amount <= 0:
                continue

            provider = str(tx.get("provider", "") or "").strip().lower()
            key = (provider, order_key, amount)
            is_refund = self._is_refund_like(tx, tx_fields)
            is_payment = self._is_payment_like(tx, tx_fields)
            groups.setdefault(key, []).append((idx, is_refund, is_payment))

        offset_indices: set[int] = set()
        for entries in groups.values():
            refund_idxs = [idx for idx, is_refund, _ in entries if is_refund]
            payment_idxs = [idx for idx, _, is_payment in entries if is_payment]
            if not refund_idxs or not payment_idxs:
                continue
            # Pair by count; mark the rows as offset and skip classification/generation.
            pair_count = min(len(refund_idxs), len(payment_idxs))
            offset_indices.update(refund_idxs[:pair_count])
            offset_indices.update(payment_idxs[:pair_count])
        return offset_indices

    def _get_auto_rule_confidence_threshold(self) -> float:
        """Confidence threshold for converting AI results into auto rules."""
        raw = UserConfigRepository.get(self.db, "deg_ai_auto_rule_min_confidence")
        if raw is None:
            return 0.90
        try:
            value = float(raw)
        except Exception:
            return 0.90
        return min(max(value, 0.0), 1.0)

    def _create_auto_rule_from_ai_result(
        self,
        transaction: Dict[str, Any],
        account: str,
        confidence: float,
    ) -> None:
        """Create provider-specific DEG-style auto rule from confident AI result."""
        if not account:
            return
        if confidence < self._get_auto_rule_confidence_threshold():
            return

        provider = str(transaction.get("provider", "")).strip().lower()
        peer = str(transaction.get("peer", "")).strip()
        item = str(transaction.get("item", "")).strip()
        category = str(transaction.get("category", "")).strip()

        # Build compact condition payload; keep it simple to avoid overfitting.
        # Previous behavior added peer+item+category together, which was too strict.
        conditions: Dict[str, Any] = {}
        if provider:
            conditions["provider"] = provider

        # De-duplicate identical peer/item text, then only keep one primary matcher.
        if peer and item and peer == item:
            item = ""

        if peer:
            conditions["peer"] = [peer]
        elif item:
            conditions["item"] = [item]
        elif category:
            conditions["category"] = [category]

        # Fallback regex when core fields are missing.
        if not any(k in conditions for k in ("peer", "item", "category")):
            tokens = []
            for key in ("peer", "item", "category"):
                value = str(transaction.get(key, "")).strip()
                if value:
                    tokens.append(value)
            if tokens:
                import re

                conditions["regexp"] = "|".join(re.escape(x) for x in sorted(set(tokens)))

        # De-dup against existing matching rules with same account.
        matched = RuleRepository.match_transaction(
            self.db,
            peer=peer,
            item=item,
            category=category,
            provider=provider,
            raw_data=transaction.get("raw_data", ""),
            tx_type=transaction.get("type", ""),
            tx_time=transaction.get("time", ""),
            tx_fields=self._extract_tx_fields(transaction),
        )
        for rule in matched:
            if str(rule.account).strip() == account:
                return

        name_base = (peer or item or category or provider or "ai").strip()[:20]
        self.rule_engine.create_rule(
            name=f"auto-{name_base}-{account.split(':')[-1][:12]}",
            conditions=conditions,
            account=account,
            confidence=min(max(confidence, 0.0), 1.0),
            source="auto",
        )

    def _get_deg_provider_aliases(self) -> Dict[str, str]:
        """Load DEG provider aliases from DB."""
        raw = UserConfigRepository.get(self.db, "deg_provider_aliases")
        if not raw:
            return {}
        try:
            parsed = json.loads(raw)
        except Exception:
            return {}
        if not isinstance(parsed, dict):
            return {}
        aliases: Dict[str, str] = {}
        for key, value in parsed.items():
            k = str(key).strip().lower()
            v = str(value).strip().lower()
            if k and v:
                aliases[k] = v
        return aliases

    def _create_deg(self) -> DoubleEntryGenerator:
        """Create DEG integration instance from app settings."""
        executable = get_config("application.deg.executable", "double-entry-generator")
        config_dir_raw = get_config("application.deg.config_dir")
        config_dir = expand_path(config_dir_raw) if config_dir_raw else None
        provider_aliases = self._get_deg_provider_aliases()
        return DoubleEntryGenerator(
            config_dir=config_dir,
            executable=executable,
            provider_aliases=provider_aliases,
        )

    @staticmethod
    def _parse_beancount_posting_accounts(beancount_text: str) -> list[list[str]]:
        """Parse posting accounts per transaction from Beancount text."""
        entries: list[list[str]] = []
        current: list[str] | None = None
        # Beancount account names look like Assets:Bank:Alipay (metadata like payTime: is invalid).
        account_pattern = re.compile(r"^[A-Z][A-Za-z0-9_-]*(?::[A-Z][A-Za-z0-9_-]*)+$")
        for raw_line in str(beancount_text or "").splitlines():
            line = raw_line.rstrip()
            if re.match(r"^\d{4}-\d{2}-\d{2}\s+\*", line):
                if current is not None:
                    entries.append(current)
                current = []
                continue

            if current is None:
                continue
            if not (line.startswith(" ") or line.startswith("\t")):
                continue

            stripped = line.strip()
            if not stripped or stripped.startswith(";"):
                continue
            account = stripped.split()[0]
            if account.endswith(":"):
                continue
            if account_pattern.match(account):
                current.append(account)

        if current is not None:
            entries.append(current)
        return entries

    @staticmethod
    def _pick_target_and_method(accounts: list[str]) -> tuple[str, str]:
        """Pick targetAccount and methodAccount from posting account list."""
        if not accounts:
            return "", ""
        method_candidates = [
            acc for acc in accounts if acc.startswith("Assets:") or acc.startswith("Liabilities:")
        ]
        target_candidates = [acc for acc in accounts if acc not in method_candidates]

        # Method-only rules can produce postings that contain only funding accounts.
        # In that case keep target empty and let AI fill target later.
        if not target_candidates and method_candidates:
            return "", method_candidates[0]

        target = target_candidates[0] if target_candidates else ""
        method = method_candidates[0] if method_candidates else ""
        if method and method == target and len(accounts) > 1:
            for acc in accounts:
                if acc != target and (acc.startswith("Assets:") or acc.startswith("Liabilities:")):
                    method = acc
                    break
        return str(target or "").strip(), str(method or "").strip()

    def _build_deg_prefill_map(self, transactions: List[Dict[str, Any]]) -> Dict[str, Dict[str, str]]:
        """
        Run DEG once on uploaded transactions and extract target/method prefill.
        """
        if not transactions:
            return {}
        provider = str(transactions[0].get("provider", "")).strip().lower() or "alipay"
        try:
            deg = self._create_deg()
            deg_config_yaml = self.rule_engine.export_deg_yaml(provider=provider)
            result = deg.generate_beancount_from_transactions(
                transactions=transactions,
                provider=provider,
                config_content=deg_config_yaml,
            )
            if not result.get("success"):
                return {}
            entries = self._parse_beancount_posting_accounts(result.get("beancount_file", ""))
            # DEG may skip malformed rows; index-based mapping would become unsafe.
            # In that case, disable this prefill batch and rely on rule/AI fallback.
            if len(entries) != len(transactions):
                return {}
            prefill: Dict[str, Dict[str, str]] = {}
            for idx, tx in enumerate(transactions):
                target_account, method_account = self._pick_target_and_method(entries[idx])
                key = str(tx.get("id", "")).strip() or f"idx:{idx}"
                prefill[key] = {
                    "targetAccount": target_account,
                    "methodAccount": method_account,
                }
            return prefill
        except Exception:
            return {}

    def _get_provider(self) -> BaseLLMProvider:
        """Get AI Provider instance"""
        if self.provider is None:
            # Get AI configuration from database
            ai_config = UserConfigRepository.get(self.db, "ai_config")
            if ai_config:
                config = json.loads(ai_config)
                provider_type, provider_config = self._resolve_provider_config(config)
            else:
                # Default configuration
                provider_type = "deepseek"
                provider_config = {
                    "api_base": "https://api.deepseek.com/v1",
                    "api_key": "",
                    "model": "deepseek-chat",
                    "temperature": 0.3,
                    "timeout": 30,
                }

            self.provider = create_provider(provider_type, provider_config)

        return self.provider

    def _resolve_provider_config(self, config: Dict[str, Any]) -> tuple[str, Dict[str, Any]]:
        """
        Resolve provider type and config.

        Supports both new profile-based format and legacy provider-map format.
        """
        # New profile-based format
        if isinstance(config.get("profiles"), list):
            profiles = config.get("profiles", [])
            default_ref = config.get("default_profile_id", "")

            selected = None
            # 1) Match by profile id
            for profile in profiles:
                if profile.get("id") == self.provider_name:
                    selected = profile
                    break
            # 2) Backward-compatible: match by provider type
            if selected is None:
                for profile in profiles:
                    if profile.get("provider") == self.provider_name:
                        selected = profile
                        break
            # 3) Match default profile id
            if selected is None and default_ref:
                for profile in profiles:
                    if profile.get("id") == default_ref:
                        selected = profile
                        break
            # 4) First available profile
            if selected is None and profiles:
                selected = profiles[0]

            if selected:
                provider_type = str(selected.get("provider", "deepseek")).lower()
                if provider_type not in {"deepseek", "openai", "ollama", "custom"}:
                    provider_type = "custom"
                return provider_type, dict(selected)

        # Legacy provider-map format
        provider_type = self.provider_name.lower()
        provider_config = config.get("providers", {}).get(provider_type, {})

        # Fallback to deepseek if requested provider missing in legacy map.
        if not provider_config:
            provider_type = "deepseek"
            provider_config = config.get("providers", {}).get(provider_type, {})

        return provider_type, provider_config

    def _get_chart_of_accounts(self) -> str:
        """Get chart of accounts"""
        config = UserConfigRepository.get(self.db, "chart_of_accounts")
        if config:
            return config

        # Default chart of accounts
        return """
Assets:Bank:Alipay
Assets:Bank:WeChat
Assets:Bank:Cash
Expenses:Food:Dining
Expenses:Food:Groceries
Expenses:Transport:Taxi
Expenses:Transport:Subway
Expenses:Shopping:Clothing
Expenses:Shopping:Electronics
Expenses:Entertainment:Movies
Expenses:Entertainment:Games
Expenses:Utilities:Phone
Expenses:Utilities:Internet
Expenses:Utilities:Electricity
Expenses:Health:Medicine
Expenses:Health:Insurance
Expenses:Education:Books
Expenses:Education:Courses
Expenses:Travel:Hotels
Expenses:Travel:Transport
Expenses:Other
Income:Salary
Income:Investment
Income:Other
"""

    def _get_historical_rules(self) -> str:
        """Get historical rules"""
        rules = RuleRepository.list_all(self.db, limit=50)

        if not rules:
            return "No historical rules"

        rule_strings = []
        for rule in rules:
            conditions = json.loads(rule.conditions)
            rule_strings.append(
                f"- {rule.name}: {conditions} -> {rule.account}"
            )

        return "\n".join(rule_strings)

    @staticmethod
    def _parse_accounts(chart_of_accounts: str) -> List[str]:
        """Parse chart-of-accounts text into account list."""
        accounts: List[str] = []
        seen = set()
        for raw in str(chart_of_accounts or "").splitlines():
            account = raw.strip()
            if not account or account.startswith("#"):
                continue
            if account in seen:
                continue
            seen.add(account)
            accounts.append(account)
        return accounts

    @staticmethod
    def _extract_hour(time_text: str) -> Optional[int]:
        """Extract hour from timestamp text."""
        text = str(time_text or "")
        match = re.search(r"(\d{1,2}):\d{2}", text)
        if not match:
            return None
        hour = int(match.group(1))
        if 0 <= hour <= 23:
            return hour
        return None

    @staticmethod
    def _find_accounts_by_keywords(accounts: List[str], keywords: List[str]) -> List[str]:
        """Find accounts whose names contain any keyword."""
        found = []
        lowered_keywords = [k.lower() for k in keywords]
        for account in accounts:
            text = account.lower()
            if any(k in text for k in lowered_keywords):
                found.append(account)
        return found

    def _suggest_food_account(self, transaction: Dict[str, Any], accounts: List[str]) -> Optional[str]:
        """
        Suggest food account for explicit meal/grocery signals.
        """
        if not accounts:
            return None
        peer = str(transaction.get("peer", "")).strip()
        item = str(transaction.get("item", "")).strip()
        category = str(transaction.get("category", "")).strip()
        text = f"{peer} {item} {category}".lower()

        food_category = any(token in category.lower() for token in ["餐饮", "美食", "food", "dining"])
        if not food_category and not any(token in text for token in ["餐", "饭", "包子", "小吃", "breakfast", "grocer"]):
            return None

        breakfast_accounts = self._find_accounts_by_keywords(
            accounts, ["breakfast", "早餐", "早饭", "morning"]
        )
        dining_accounts = self._find_accounts_by_keywords(
            accounts, ["dining", "餐饮", "外卖", "meal", "restaurant", "小吃"]
        )
        grocery_accounts = self._find_accounts_by_keywords(
            accounts, ["groceries", "grocery", "supermarket", "买菜", "菜场", "生鲜", "超市", "market"]
        )

        grocery_signal = any(
            token in text
            for token in ["超市", "生鲜", "菜场", "买菜", "market", "supermarket", "grocery", "grocer"]
        )
        if grocery_signal and grocery_accounts:
            return grocery_accounts[0]

        hour = self._extract_hour(str(transaction.get("time", "")))
        breakfast_signal = any(
            token in text
            for token in ["早餐", "早饭", "早点", "包子", "豆浆", "油条", "馒头", "粥", "breakfast"]
        )
        if (breakfast_signal or (hour is not None and 4 <= hour <= 10 and any(t in text for t in ["包子", "小吃", "早餐", "饭"]))) and breakfast_accounts:
            return breakfast_accounts[0]

        if dining_accounts:
            return dining_accounts[0]
        if grocery_accounts:
            return grocery_accounts[0]
        return None

    def _normalize_account_for_chart(
        self,
        transaction: Dict[str, Any],
        account: str,
        chart_accounts: List[str],
    ) -> str:
        """Ensure account is valid and apply local food heuristics."""
        selected = str(account or "").strip()
        if not chart_accounts:
            return selected or "Expenses:Other"

        # Food heuristic first for explicit scenarios (e.g., breakfast vendors).
        suggested_food = self._suggest_food_account(transaction, chart_accounts)
        if suggested_food:
            selected = suggested_food

        if selected in chart_accounts:
            return selected

        # Fallback by top-level account class.
        top = selected.split(":", 1)[0] if ":" in selected else ""
        if top:
            for account_item in chart_accounts:
                if account_item.startswith(f"{top}:"):
                    return account_item

        for fallback in ("Expenses:Other", "Income:Other"):
            if fallback in chart_accounts:
                return fallback
        return chart_accounts[0]

    async def classify_transaction(
        self,
        transaction: Dict[str, Any],
        chart_of_accounts: Optional[str] = None,
        language: str = "en",
    ) -> Dict[str, Any]:
        """
        Classify a single transaction

        Args:
            transaction: Transaction data

        Returns:
            Classification result
        """
        # 1. Check for user override rules
        matched_rules = RuleRepository.match_transaction(
            self.db,
            peer=transaction.get("peer", ""),
            item=transaction.get("item", ""),
            category=transaction.get("category", ""),
            provider=transaction.get("provider", ""),
            raw_data=transaction.get("raw_data", ""),
            tx_type=transaction.get("type", ""),
            tx_time=transaction.get("time", ""),
            tx_fields=self._extract_tx_fields(transaction),
        )

        # Provider/global DEG rules first: prefer user, fallback to auto.
        fallback_reason = ""
        fallback_method_account = ""
        if matched_rules:
            target_account, method_account, matched_confidence = self._select_rule_accounts(matched_rules)
            if self._has_complete_accounts(target_account, method_account):
                return {
                    "account": target_account,
                    "targetAccount": target_account,
                    "methodAccount": method_account,
                    "confidence": matched_confidence,
                    "reasoning": "Matched DEG rule",
                    "source": "rule",
                }
            fallback_method_account = method_account
            fallback_reason = "Matched DEG rule(s) but account fields were incomplete; used AI fallback"

        # 2. Use AI classification
        provider = self._get_provider()
        chart_of_accounts_text = chart_of_accounts or self._get_chart_of_accounts()
        chart_accounts = self._parse_accounts(chart_of_accounts_text)
        historical_rules = self._get_historical_rules()

        result = await provider.classify(
            transaction,
            chart_of_accounts_text,
            historical_rules,
            language=language,
        )
        normalized_target_account = self._normalize_account_for_chart(
            transaction,
            result.get("account", ""),
            chart_accounts,
        )
        result["account"] = normalized_target_account
        result["targetAccount"] = normalized_target_account
        ai_method_account = self._first_text_value(result.get("methodAccount", ""))
        if self._is_empty_or_other_account(ai_method_account):
            ai_method_account = ""
        if self._is_empty_or_other_account(fallback_method_account):
            fallback_method_account = ""
        # Prefer rule-derived funding account; only fallback to AI when missing.
        result["methodAccount"] = fallback_method_account or ai_method_account
        if fallback_reason:
            base_reasoning = str(result.get("reasoning", "")).strip()
            result["reasoning"] = f"{fallback_reason}. {base_reasoning}".strip()
        result["source"] = "ai"

        return result

    async def classify_transactions(
        self,
        transactions: List[Dict[str, Any]],
        chart_of_accounts: Optional[str] = None,
        language: str = "en",
        progress_callback: Optional[Callable[[int], None]] = None,
        deg_progress_callback: Optional[Callable[[int, int], None]] = None,
        ai_progress_callback: Optional[Callable[[int, int], None]] = None,
    ) -> List[Dict[str, Any]]:
        """
        Batch classify transactions

        Args:
            transactions: List of transactions

        Returns:
            List of classification results
        """
        results = []
        chart_of_accounts_text = chart_of_accounts or self._get_chart_of_accounts()
        chart_accounts = self._parse_accounts(chart_of_accounts_text)
        deg_prefill_map = self._build_deg_prefill_map(transactions)
        offset_skip_indices = self._detect_offset_pair_indices(transactions)
        total_transactions = len(transactions)
        deg_done = 0

        # First pass: DEG prefill -> local rule match -> AI.
        for tx_index, tx in enumerate(transactions):
            if tx_index in offset_skip_indices:
                results.append({
                    "transaction": tx,
                    "account": "",
                    "targetAccount": "",
                    "methodAccount": "",
                    "confidence": 1.0,
                    "reasoning": "Filtered offsetting payment/refund pair",
                    "source": "offset",
                    "skipGenerate": True,
                })
                if progress_callback:
                    progress_callback(1)
                deg_done += 1
                if deg_progress_callback:
                    deg_progress_callback(deg_done, total_transactions)
                continue

            tx_id_key = str(tx.get("id", "")).strip()
            if not tx_id_key:
                tx_id_key = f"idx:{len(results)}"

            prefill = deg_prefill_map.get(tx_id_key, {})
            prefill_target = str(prefill.get("targetAccount", "")).strip()
            prefill_method = str(prefill.get("methodAccount", "")).strip()
            if self._has_complete_accounts(prefill_target, prefill_method):
                normalized_target = self._normalize_account_for_chart(
                    tx,
                    prefill_target,
                    chart_accounts,
                )
                if self._has_complete_accounts(normalized_target, prefill_method):
                    results.append({
                        "transaction": tx,
                        "account": normalized_target,
                        "targetAccount": normalized_target,
                        "methodAccount": prefill_method,
                        "confidence": 1.0,
                        "reasoning": "Matched DEG prefill",
                        "source": "rule",
                    })
                    if progress_callback:
                        progress_callback(1)
                    deg_done += 1
                    if deg_progress_callback:
                        deg_progress_callback(deg_done, total_transactions)
                    continue

            # Check user rules
            matched_rules = RuleRepository.match_transaction(
                self.db,
                peer=tx.get("peer", ""),
                item=tx.get("item", ""),
                category=tx.get("category", ""),
                provider=tx.get("provider", ""),
                raw_data=tx.get("raw_data", ""),
                tx_type=tx.get("type", ""),
                tx_time=tx.get("time", ""),
                tx_fields=self._extract_tx_fields(tx),
            )

            if matched_rules:
                target_account, method_account, matched_confidence = self._select_rule_accounts(matched_rules)
                if self._has_complete_accounts(target_account, method_account):
                    results.append({
                        "transaction": tx,
                        "account": target_account,
                        "targetAccount": target_account,
                        "methodAccount": method_account,
                        "confidence": matched_confidence,
                        "reasoning": "Matched DEG rule",
                        "source": "rule",
                    })
                    if progress_callback:
                        progress_callback(1)
                    deg_done += 1
                    if deg_progress_callback:
                        deg_progress_callback(deg_done, total_transactions)
                    continue
                fallback_method = method_account
                if self._is_empty_or_other_account(fallback_method):
                    fallback_method = ""
                results.append({
                    "transaction": tx,
                    "source": "ai",
                    "rule_prefill_method": fallback_method,
                    "rule_fallback": bool(fallback_method),
                })
                deg_done += 1
                if deg_progress_callback:
                    deg_progress_callback(deg_done, total_transactions)
                continue

            # No matching rule, use AI
            results.append({"transaction": tx, "source": "ai"})
            deg_done += 1
            if deg_progress_callback:
                deg_progress_callback(deg_done, total_transactions)

        # Batch classify transactions that need AI
        ai_transactions = [r["transaction"] for r in results if r["source"] == "ai"]
        ai_total = len(ai_transactions)
        ai_done = 0
        if ai_progress_callback:
            ai_progress_callback(ai_done, ai_total)

        if ai_transactions:
            provider = self._get_provider()
            historical_rules = self._get_historical_rules()

            def _ai_progress(inc: int = 1) -> None:
                nonlocal ai_done
                inc_value = max(0, int(inc))
                ai_done = min(ai_total, ai_done + inc_value)
                if ai_progress_callback:
                    ai_progress_callback(ai_done, ai_total)
                if progress_callback and inc_value:
                    progress_callback(inc_value)

            ai_results = await provider.batch_classify(
                ai_transactions,
                chart_of_accounts_text,
                historical_rules,
                language=language,
                progress_callback=_ai_progress,
            )

            # Merge results
            ai_index = 0
            for i, result in enumerate(results):
                if result["source"] == "ai":
                    tx = result["transaction"]
                    tx_id_key = str(tx.get("id", "")).strip() or f"idx:{i}"
                    prefill = deg_prefill_map.get(tx_id_key, {})
                    prefill_method = str(prefill.get("methodAccount", "")).strip()
                    if self._is_empty_or_other_account(prefill_method):
                        prefill_method = ""
                    rule_prefill_method = str(result.get("rule_prefill_method", "")).strip()
                    if self._is_empty_or_other_account(rule_prefill_method):
                        rule_prefill_method = ""
                    ai_method = self._first_text_value(
                        ai_results[ai_index].get("methodAccount", "")
                    )
                    if self._is_empty_or_other_account(ai_method):
                        ai_method = ""
                    normalized_account = self._normalize_account_for_chart(
                        tx,
                        ai_results[ai_index].get("account", ""),
                        chart_accounts,
                    )
                    results[i].update({
                        "account": normalized_account,
                        "targetAccount": normalized_account,
                        # Prefer DEG/rule-derived funding account; fallback to AI only when missing.
                        "methodAccount": prefill_method or rule_prefill_method or ai_method,
                        "confidence": ai_results[ai_index]["confidence"],
                        "reasoning": ai_results[ai_index]["reasoning"],
                    })
                    ai_index += 1

        return results

    def save_classification(
        self, transaction_id: str, classification: Dict[str, Any]
    ) -> None:
        """
        Save classification result to database

        Args:
            transaction_id: Transaction ID
            classification: Classification result
        """
        ClassificationRepository.create(
            db=self.db,
            transaction_id=transaction_id,
            account=classification["account"],
            confidence=classification["confidence"],
            source=classification["source"],
            reasoning=classification.get("reasoning", ""),
        )
