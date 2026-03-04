"""
Classification coordinator - coordinates AI classification and rule engine
"""

import json
import ast
import re
from typing import Dict, Any, List, Optional

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
        try:
            conditions = json.loads(getattr(rule, "conditions", "") or "{}")
        except Exception:
            conditions = {}
        if isinstance(conditions, dict):
            method_account = cls._first_text_value(conditions.get("methodAccount", ""))
        if method_account == "/":
            method_account = ""
        return target_account, method_account

    @staticmethod
    def _extract_tx_fields(transaction: Dict[str, Any]) -> Dict[str, str]:
        """Extract provider-specific raw fields from transaction.raw_data."""
        raw_data = transaction.get("raw_data", "")
        if isinstance(raw_data, dict):
            return {str(k): str(v or "") for k, v in raw_data.items()}
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

        if isinstance(parsed, dict):
            return {str(k): str(v or "") for k, v in parsed.items()}
        return {}

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
            prefill: Dict[str, Dict[str, str]] = {}
            for idx, tx in enumerate(transactions):
                if idx >= len(entries):
                    break
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
Expenses:Misc
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
            return selected or "Expenses:Misc"

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

        for fallback in ("Expenses:Misc", "Income:Other"):
            if fallback in chart_accounts:
                return fallback
        return chart_accounts[0]

    async def classify_transaction(
        self,
        transaction: Dict[str, Any],
        chart_of_accounts: Optional[str] = None,
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
        if matched_rules:
            user_rules = [r for r in matched_rules if r.source == "user"]
            candidate_rules = user_rules or matched_rules
            rule = max(candidate_rules, key=lambda r: r.confidence)
            target_account, method_account = self._extract_rule_accounts(rule)
            if self._has_complete_accounts(target_account or rule.account, method_account):
                return {
                    "account": target_account or rule.account,
                    "targetAccount": target_account or rule.account,
                    "methodAccount": method_account,
                    "confidence": rule.confidence,
                    "reasoning": "Matched DEG rule",
                    "source": "rule",
                }
            fallback_reason = "Matched DEG rule but account fields were incomplete; used AI fallback"

        # 2. Use AI classification
        provider = self._get_provider()
        chart_of_accounts_text = chart_of_accounts or self._get_chart_of_accounts()
        chart_accounts = self._parse_accounts(chart_of_accounts_text)
        historical_rules = self._get_historical_rules()

        result = await provider.classify(
            transaction, chart_of_accounts_text, historical_rules
        )
        normalized_target_account = self._normalize_account_for_chart(
            transaction,
            result.get("account", ""),
            chart_accounts,
        )
        result["account"] = normalized_target_account
        result["targetAccount"] = normalized_target_account
        result["methodAccount"] = self._first_text_value(result.get("methodAccount", ""))
        if fallback_reason:
            base_reasoning = str(result.get("reasoning", "")).strip()
            result["reasoning"] = f"{fallback_reason}. {base_reasoning}".strip()
        result["source"] = "ai"

        return result

    async def classify_transactions(
        self,
        transactions: List[Dict[str, Any]],
        chart_of_accounts: Optional[str] = None,
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

        # First pass: DEG prefill -> local rule match -> AI.
        for tx in transactions:
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
                user_rules = [r for r in matched_rules if r.source == "user"]
                candidate_rules = user_rules or matched_rules
                rule = max(candidate_rules, key=lambda r: r.confidence)
                target_account, method_account = self._extract_rule_accounts(rule)
                if self._has_complete_accounts(target_account or rule.account, method_account):
                    results.append({
                        "transaction": tx,
                        "account": target_account or rule.account,
                        "targetAccount": target_account or rule.account,
                        "methodAccount": method_account,
                        "confidence": rule.confidence,
                        "reasoning": "Matched DEG rule",
                        "source": "rule",
                    })
                    continue

            # No matching rule, use AI
            results.append({"transaction": tx, "source": "ai"})

        # Batch classify transactions that need AI
        ai_transactions = [r["transaction"] for r in results if r["source"] == "ai"]

        if ai_transactions:
            provider = self._get_provider()
            historical_rules = self._get_historical_rules()

            ai_results = await provider.batch_classify(
                ai_transactions, chart_of_accounts_text, historical_rules
            )

            # Merge results
            ai_index = 0
            for i, result in enumerate(results):
                if result["source"] == "ai":
                    tx = result["transaction"]
                    tx_id_key = str(tx.get("id", "")).strip() or f"idx:{i}"
                    prefill = deg_prefill_map.get(tx_id_key, {})
                    prefill_method = str(prefill.get("methodAccount", "")).strip()
                    ai_method = self._first_text_value(
                        ai_results[ai_index].get("methodAccount", "")
                    )
                    normalized_account = self._normalize_account_for_chart(
                        tx,
                        ai_results[ai_index].get("account", ""),
                        chart_accounts,
                    )
                    results[i].update({
                        "account": normalized_account,
                        "targetAccount": normalized_account,
                        "methodAccount": ai_method or prefill_method,
                        "confidence": ai_results[ai_index]["confidence"],
                        "reasoning": ai_results[ai_index]["reasoning"],
                    })
                    self._create_auto_rule_from_ai_result(
                        result["transaction"],
                        normalized_account,
                        float(ai_results[ai_index].get("confidence", 0.0)),
                    )
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
