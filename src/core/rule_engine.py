"""
Rule engine - manages and executes rule-based classification
"""

import copy
import json
import re
import uuid
from typing import Dict, Any, List, Optional

from sqlalchemy.orm import Session
import yaml

from src.db.repositories import RuleRepository, UserConfigRepository


class RuleEngine:
    """Rule engine"""

    DEG_TEMPLATE_KEY_PREFIX = "deg_provider_template::"
    DEG_INTERNAL_CONDITION_KEYS = {
        "provider",
        "skip",
        "_deg_only",
        "_deg_has_target",
    }
    DEG_SPLITTABLE_KEYS = {
        "peer",
        "item",
        "category",
        "method",
        "status",
        "txType",
        "type",
        "transactionType",
    }
    DEFAULT_DEG_CONFIG = {
        "defaultMinusAccount": "Income:Other",
        "defaultPlusAccount": "Expenses:Other",
        "defaultCurrency": "CNY",
        "title": "BeancountPilot",
    }

    def __init__(self, db: Session):
        """
        Initialize rule engine

        Args:
            db: Database session
        """
        self.db = db

    def create_rule(
        self,
        name: str,
        conditions: Dict[str, Any],
        account: str,
        confidence: float = 1.0,
        source: str = "user",
    ) -> Dict[str, Any]:
        """
        Create rule

        Args:
            name: Rule name
            conditions: Condition dictionary containing peer, item, category, etc.
            account: Target account
            confidence: Confidence level
            source: Source (user or auto)

        Returns:
            Created rule
        """
        rule = RuleRepository.create(
            db=self.db,
            name=name,
            conditions=conditions,
            account=account,
            confidence=confidence,
            source=source,
        )

        return {
            "id": rule.id,
            "name": rule.name,
            "conditions": json.loads(rule.conditions),
            "account": rule.account,
            "confidence": rule.confidence,
            "source": rule.source,
            "created_at": rule.created_at,
        }

    def get_rule(self, rule_id: str) -> Optional[Dict[str, Any]]:
        """
        Get rule

        Args:
            rule_id: Rule ID

        Returns:
            Rule information
        """
        rule = RuleRepository.get_by_id(self.db, rule_id)
        if not rule:
            return None

        return {
            "id": rule.id,
            "name": rule.name,
            "conditions": json.loads(rule.conditions),
            "account": rule.account,
            "confidence": rule.confidence,
            "source": rule.source,
            "created_at": rule.created_at,
            "updated_at": rule.updated_at,
        }

    def list_rules(self, skip: int = 0, limit: int = 100) -> List[Dict[str, Any]]:
        """
        List all rules

        Args:
            skip: Number of records to skip
            limit: Number of records to limit

        Returns:
            List of rules
        """
        rules = RuleRepository.list_all(self.db, skip=skip, limit=limit)

        return [
            {
                "id": rule.id,
                "name": rule.name,
                "conditions": json.loads(rule.conditions),
                "account": rule.account,
                "confidence": rule.confidence,
                "source": rule.source,
                "created_at": rule.created_at,
                "updated_at": rule.updated_at,
            }
            for rule in rules
        ]

    def update_rule(
        self,
        rule_id: str,
        name: Optional[str] = None,
        conditions: Optional[Dict[str, Any]] = None,
        account: Optional[str] = None,
        confidence: Optional[float] = None,
        source: Optional[str] = None,
    ) -> Optional[Dict[str, Any]]:
        """
        Update rule

        Args:
            rule_id: Rule ID
            name: Rule name
            conditions: Condition dictionary
            account: Target account

        Returns:
            Updated rule
        """
        rule = RuleRepository.update(
            db=self.db,
            rule_id=rule_id,
            name=name,
            conditions=conditions,
            account=account,
            confidence=confidence,
            source=source,
        )

        if not rule:
            return None

        return {
            "id": rule.id,
            "name": rule.name,
            "conditions": json.loads(rule.conditions),
            "account": rule.account,
            "confidence": rule.confidence,
            "source": rule.source,
            "created_at": rule.created_at,
            "updated_at": rule.updated_at,
        }

    def delete_rule(self, rule_id: str) -> bool:
        """
        Delete rule

        Args:
            rule_id: Rule ID

        Returns:
            Whether deletion was successful
        """
        return RuleRepository.delete(self.db, rule_id)

    def delete_auto_rules(self, provider: str = "", scope: str = "all") -> Dict[str, Any]:
        """
        Delete auto-generated rules in one operation.

        Args:
            provider: Optional provider code filter
            scope: all | global | provider

        Returns:
            Cleanup summary
        """
        provider = self._normalize_provider(provider)
        scope = str(scope or "all").strip().lower()
        if scope not in {"all", "global", "provider"}:
            raise ValueError("Invalid scope. Use all/global/provider.")

        removed = 0
        for rule in RuleRepository.list_all(self.db):
            if str(rule.source or "").strip().lower() != "auto":
                continue

            try:
                conditions = json.loads(rule.conditions)
            except Exception:
                conditions = {}
            if not isinstance(conditions, dict):
                conditions = {}

            provider_values = self._extract_provider_values(conditions)
            is_provider_rule = bool(provider_values)

            if scope == "global" and is_provider_rule:
                continue
            if scope == "provider" and not is_provider_rule:
                continue
            if provider:
                if not is_provider_rule:
                    continue
                if provider not in provider_values:
                    continue

            if RuleRepository.delete(self.db, rule.id):
                removed += 1

        return {
            "deleted": removed,
            "provider": provider,
            "scope": scope,
            "source": "auto",
        }

    @staticmethod
    def _normalize_provider(provider: str) -> str:
        """Normalize provider code text."""
        return str(provider or "").strip().lower()

    @classmethod
    def _extract_provider_values(cls, conditions: Dict[str, Any]) -> list[str]:
        """Extract normalized provider values from rule conditions."""
        cond_provider = (conditions or {}).get("provider")
        values: list[str] = []
        seen: set[str] = set()

        raw_values: list[Any] = []
        if isinstance(cond_provider, str):
            raw_values = [cond_provider]
        elif isinstance(cond_provider, list):
            raw_values = cond_provider

        for value in raw_values:
            normalized = cls._normalize_provider(str(value))
            if normalized and normalized not in seen:
                seen.add(normalized)
                values.append(normalized)
        return values

    @classmethod
    def _template_key(cls, provider: str) -> str:
        """Build user config key for provider DEG template."""
        return f"{cls.DEG_TEMPLATE_KEY_PREFIX}{cls._normalize_provider(provider)}"

    def _get_stored_template(self, provider: str) -> dict[str, Any]:
        """Load provider DEG template from user config storage."""
        provider = self._normalize_provider(provider)
        if not provider:
            return {}
        raw = UserConfigRepository.get(self.db, self._template_key(provider))
        if not raw:
            return {}
        try:
            parsed = json.loads(raw)
        except Exception:
            return {}
        return parsed if isinstance(parsed, dict) else {}

    def _set_stored_template(self, provider: str, template: dict[str, Any]) -> None:
        """Persist provider DEG template to user config storage."""
        provider = self._normalize_provider(provider)
        if not provider:
            return
        UserConfigRepository.set(
            self.db,
            self._template_key(provider),
            json.dumps(template, ensure_ascii=False),
        )

    def _delete_provider_rules(self, provider: str) -> int:
        """Delete all provider-scoped rules for a provider."""
        provider = self._normalize_provider(provider)
        if not provider:
            return 0

        removed = 0
        for rule in RuleRepository.list_all(self.db):
            try:
                conditions = json.loads(rule.conditions)
            except Exception:
                continue

            provider_values = self._extract_provider_values(conditions)
            if provider in provider_values and RuleRepository.delete(self.db, rule.id):
                removed += 1
        return removed

    @staticmethod
    def _normalize_compare_value(value: Any) -> Any:
        """Normalize value for stable rule fingerprint comparison."""
        if isinstance(value, dict):
            normalized = {}
            for key in sorted(value.keys(), key=lambda x: str(x)):
                normalized[str(key)] = RuleEngine._normalize_compare_value(value.get(key))
            return normalized
        if isinstance(value, list):
            items = [RuleEngine._normalize_compare_value(v) for v in value]
            # Condition token order is not semantically important; compare as sorted set-like list.
            return sorted(items, key=lambda v: json.dumps(v, ensure_ascii=False, sort_keys=True))
        if isinstance(value, str):
            return value.strip()
        return value

    @classmethod
    def _rule_fingerprint(cls, conditions: Dict[str, Any]) -> str:
        """Build deterministic fingerprint for rule condition matching."""
        normalized = cls._normalize_compare_value(conditions or {})
        return json.dumps(normalized, ensure_ascii=False, sort_keys=True)

    def _provider_rule_fingerprint_index(self, provider: str) -> Dict[str, str]:
        """Return fingerprint -> rule_id index for one provider."""
        provider = self._normalize_provider(provider)
        if not provider:
            return {}

        index: Dict[str, str] = {}
        for rule in RuleRepository.list_all(self.db):
            try:
                conditions = json.loads(rule.conditions)
            except Exception:
                continue
            if not isinstance(conditions, dict):
                continue

            cond_provider = conditions.get("provider")
            provider_values = []
            if isinstance(cond_provider, str) and cond_provider.strip():
                provider_values = [cond_provider.strip().lower()]
            elif isinstance(cond_provider, list):
                provider_values = [
                    str(v).strip().lower()
                    for v in cond_provider
                    if str(v).strip()
                ]
            if provider not in provider_values:
                continue

            fingerprint = self._rule_fingerprint(conditions)
            if fingerprint and fingerprint not in index:
                index[fingerprint] = rule.id
        return index

    def _delete_global_rules(self) -> int:
        """Delete all global rules (rules without provider condition)."""
        removed = 0
        for rule in RuleRepository.list_all(self.db):
            try:
                conditions = json.loads(rule.conditions)
            except Exception:
                continue
            if conditions.get("provider"):
                continue
            if RuleRepository.delete(self.db, rule.id):
                removed += 1
        return removed

    def build_deg_config(self, provider: str) -> Dict[str, Any]:
        """Build complete DEG YAML dictionary for a provider."""
        provider = self._normalize_provider(provider) or "alipay"
        template = self._get_stored_template(provider)
        config: Dict[str, Any] = copy.deepcopy(template) if isinstance(template, dict) else {}
        if not config:
            config = dict(self.DEFAULT_DEG_CONFIG)
            config[provider] = {}

        for key, value in self.DEFAULT_DEG_CONFIG.items():
            if key not in config or config[key] in (None, ""):
                config[key] = value

        provider_block = config.get(provider)
        if not isinstance(provider_block, dict):
            provider_block = {}
        provider_block["rules"] = self.list_deg_rules(provider=provider)
        config[provider] = provider_block
        return config

    def export_deg_yaml(self, provider: str) -> str:
        """Export full DEG YAML config for a provider."""
        provider = self._normalize_provider(provider) or "alipay"
        config = self.build_deg_config(provider)
        return yaml.dump(config, allow_unicode=True, sort_keys=False)

    @classmethod
    def _split_condition_value(
        cls,
        key: str,
        value: Any,
        sep: str,
    ) -> Any:
        """Convert split-able DEG condition text into list for local matcher."""
        if key not in cls.DEG_SPLITTABLE_KEYS or not isinstance(value, str):
            return value
        text = value.strip()
        if not text:
            return ""
        if text == "/":
            return text
        if sep and sep in text:
            tokens = [item.strip() for item in text.split(sep) if item.strip()]
            if len(tokens) == 1:
                return tokens[0]
            return tokens
        return text

    @classmethod
    def _deg_entry_to_rule_payload(
        cls,
        entry: Dict[str, Any],
        provider: str,
        index: int,
    ) -> Optional[Dict[str, Any]]:
        """Convert one DEG rule entry to internal Rule payload."""
        if not isinstance(entry, dict):
            return None

        description = str(entry.get("description", "")).strip()
        name = description or f"{provider or 'global'}-rule-{index:03d}"
        target_account = str(entry.get("targetAccount", "")).strip()
        has_target_account = bool(target_account)

        conditions: Dict[str, Any] = {}
        provider = cls._normalize_provider(provider)
        if provider:
            conditions["provider"] = provider

        sep = str(entry.get("sep", "")).strip()
        if sep:
            conditions["sep"] = sep

        for key, raw_value in entry.items():
            if key in {"description", "targetAccount"}:
                continue
            if raw_value is None:
                continue
            value = cls._split_condition_value(key, raw_value, sep)

            if isinstance(value, str):
                value = value.strip()
                if not value:
                    continue

            conditions[key] = value

        if not has_target_account:
            # DEG allows rules with only methodAccount/commissionAccount etc.
            # Keep these rules for DEG export, but do not use them for local classification.
            conditions["_deg_only"] = True
            conditions["_deg_has_target"] = False

        account = (
            target_account
            or str(conditions.get("methodAccount", "")).strip()
            or str(conditions.get("commissionAccount", "")).strip()
            or str(conditions.get("pnlAccount", "")).strip()
            or "Expenses:Other"
        )

        return {
            "name": name,
            "conditions": conditions,
            "account": account,
            "confidence": 1.0,
            "source": "user",
        }

    def import_deg_yaml(
        self,
        yaml_text: str,
        provider: str = "",
        mode: str = "replace",
    ) -> Dict[str, Any]:
        """Import rules from complete DEG YAML config."""
        try:
            config = yaml.safe_load(yaml_text) or {}
        except Exception as e:
            raise ValueError(f"Invalid YAML: {str(e)}") from e
        if not isinstance(config, dict):
            raise ValueError("YAML root must be an object")

        provider = self._normalize_provider(provider)
        if not provider:
            for key, value in config.items():
                if isinstance(value, dict) and isinstance(value.get("rules"), list):
                    provider = self._normalize_provider(key)
                    break
        if not provider:
            raise ValueError("Provider is required or must exist as '<provider>.rules' in YAML")

        provider_key_in_yaml = None
        for key in config.keys():
            if isinstance(key, str) and self._normalize_provider(key) == provider:
                provider_key_in_yaml = key
                break
        if provider_key_in_yaml is None:
            provider_key_in_yaml = provider

        provider_rules = []
        provider_section = config.get(provider_key_in_yaml)
        if isinstance(provider_section, dict) and isinstance(provider_section.get("rules"), list):
            provider_rules = provider_section.get("rules", [])
        elif isinstance(config.get("rules"), list):
            provider_rules = config.get("rules", [])
        else:
            raise ValueError(f"No rules found for provider '{provider}'")

        normalized_mode = str(mode or "replace").strip().lower()
        if normalized_mode not in {"replace", "append"}:
            normalized_mode = "replace"

        deleted_provider_rules = 0
        if normalized_mode == "replace":
            deleted_provider_rules = self._delete_provider_rules(provider)

        existing_index: Dict[str, str] = {}
        if normalized_mode == "append":
            existing_index = self._provider_rule_fingerprint_index(provider)

        created = 0
        updated = 0
        skipped = 0
        for index, entry in enumerate(provider_rules, start=1):
            payload = self._deg_entry_to_rule_payload(entry, provider=provider, index=index)
            if not payload:
                skipped += 1
                continue

            fingerprint = self._rule_fingerprint(payload["conditions"])
            existing_rule_id = existing_index.get(fingerprint) if normalized_mode == "append" else None
            if existing_rule_id:
                RuleRepository.update(
                    db=self.db,
                    rule_id=existing_rule_id,
                    name=payload["name"],
                    conditions=payload["conditions"],
                    account=payload["account"],
                    confidence=payload["confidence"],
                    source=payload["source"],
                )
                updated += 1
                continue

            created_rule = RuleRepository.create(
                db=self.db,
                name=payload["name"],
                conditions=payload["conditions"],
                account=payload["account"],
                confidence=payload["confidence"],
                source=payload["source"],
            )
            created += 1
            if normalized_mode == "append" and fingerprint:
                existing_index[fingerprint] = created_rule.id

        # Keep imported top-level/default values and provider block metadata.
        template = copy.deepcopy(config)
        provider_block = template.get(provider_key_in_yaml)
        if not isinstance(provider_block, dict):
            provider_block = {}
        provider_block.pop("rules", None)
        if provider_key_in_yaml != provider:
            template.pop(provider_key_in_yaml, None)
        template[provider] = provider_block
        template.pop("rules", None)
        self._set_stored_template(provider, template)

        return {
            "provider": provider,
            "mode": normalized_mode,
            "created": created,
            "updated": updated,
            "skipped": skipped,
            "deleted_provider_rules": deleted_provider_rules,
            "template_saved": True,
        }

    def get_matching_rules(
        self,
        transaction: Dict[str, Any],
    ) -> List[Dict[str, Any]]:
        """Get all matching rules for one transaction (sorted by confidence desc)."""
        tx = transaction or {}
        provider = str(tx.get("provider", "") or "").strip().lower()
        raw_data = tx.get("raw_data", "")
        if isinstance(raw_data, dict):
            tx_fields = {str(k): v for k, v in raw_data.items()}
            raw_data_text = json.dumps(raw_data, ensure_ascii=False)
        else:
            raw_data_text = str(raw_data or "")
            tx_fields = {}
            if raw_data_text:
                try:
                    parsed = json.loads(raw_data_text)
                    if isinstance(parsed, dict):
                        tx_fields = {str(k): v for k, v in parsed.items()}
                except Exception:
                    tx_fields = {}

        rules = RuleRepository.match_transaction(
            self.db,
            peer=str(tx.get("peer", "") or ""),
            item=str(tx.get("item", "") or ""),
            category=str(tx.get("category", "") or ""),
            provider=provider,
            raw_data=raw_data_text,
            tx_type=str(tx.get("type", "") or ""),
            tx_time=str(tx.get("time", "") or ""),
            tx_fields=tx_fields,
        )

        results = [
            {
                "id": rule.id,
                "name": rule.name,
                "conditions": json.loads(rule.conditions),
                "account": rule.account,
                "confidence": rule.confidence,
                "source": rule.source,
            }
            for rule in rules
        ]
        return sorted(results, key=lambda r: float(r.get("confidence", 0.0)), reverse=True)

    def match_transaction(
        self,
        peer: Any,
        item: str = "",
        category: str = "",
        provider: str = "",
        raw_data: str = "",
        tx_type: str = "",
        tx_time: str = "",
        tx_fields: Optional[Dict[str, Any]] = None,
    ) -> Optional[Dict[str, Any]]:
        """
        Match the best rule for a transaction.

        Backward-compatible usage:
        - match_transaction(transaction_dict)
        - match_transaction(peer, item, category, ...)
        """
        if isinstance(peer, dict):
            matched = self.get_matching_rules(peer)
            return matched[0] if matched else None

        transaction = {
            "peer": peer,
            "item": item,
            "category": category,
            "provider": provider,
            "raw_data": raw_data,
            "type": tx_type,
            "time": tx_time,
        }
        if tx_fields:
            transaction["raw_data"] = tx_fields
        matched = self.get_matching_rules(transaction)
        return matched[0] if matched else None

    def export_rules_to_deg_format(self) -> str:
        """
        Export rules to double-entry-generator configuration format.

        Generates DEG-style `rules` entries with `regexp` and `targetAccount`.

        Returns:
            YAML format rule configuration
        """
        rules = RuleRepository.list_all(self.db)

        deg_rules = []
        for rule in rules:
            entry = self._to_deg_rule_entry(rule)
            if entry:
                deg_rules.append(entry)

        # Convert to YAML format
        import yaml

        return yaml.dump({"rules": deg_rules}, allow_unicode=True, sort_keys=False)

    def list_deg_rules(self, provider: str = "") -> List[Dict[str, Any]]:
        """Return DEG-style rule list used by generation."""
        rules = RuleRepository.list_all(self.db)
        deg_rules: List[Dict[str, Any]] = []
        provider = (provider or "").strip().lower()
        for rule in rules:
            conditions = json.loads(rule.conditions)
            cond_provider = conditions.get("provider")
            cond_provider_list = []
            if isinstance(cond_provider, str) and cond_provider.strip():
                cond_provider_list = [cond_provider.strip().lower()]
            elif isinstance(cond_provider, list):
                cond_provider_list = [
                    str(v).strip().lower()
                    for v in cond_provider
                    if str(v).strip()
                ]
            if provider and cond_provider_list and provider not in cond_provider_list:
                continue

            entry = self._to_deg_rule_entry(rule)
            if entry:
                deg_rules.append(entry)

        return deg_rules

    @staticmethod
    def _to_deg_rule_entry(rule: Any) -> Optional[Dict[str, Any]]:
        """Convert DB rule model to DEG-compatible rule object."""
        conditions = json.loads(rule.conditions)
        if conditions.get("skip") is True:
            return None

        entry: Dict[str, Any] = {"description": rule.name}
        if conditions.get("_deg_has_target", True):
            entry["targetAccount"] = rule.account

        regex_text = str(conditions.get("regexp", "")).strip()
        if not regex_text:
            keywords = []
            for key in ("peer", "item", "category"):
                value = conditions.get(key)
                if value is None:
                    continue
                if isinstance(value, str):
                    value = [value]
                for token in value:
                    token = str(token).strip()
                    if token:
                        keywords.append(re.escape(token))
            if keywords:
                regex_text = "|".join(sorted(set(keywords)))
        if regex_text:
            entry["regexp"] = regex_text

        sep = str(conditions.get("sep", "")).strip() or "|"
        for key, value in conditions.items():
            if key in {
                "provider",
                "skip",
                "_deg_only",
                "_deg_has_target",
                "regexp",
            }:
                continue
            if value is None:
                continue

            if isinstance(value, list):
                values = [str(v).strip() for v in value if str(v).strip()]
                if not values:
                    continue
                if len(values) == 1:
                    entry[key] = values[0]
                else:
                    entry[key] = sep.join(values)
                    if key != "sep":
                        entry["sep"] = sep
            elif isinstance(value, bool):
                entry[key] = value
            elif isinstance(value, (int, float)):
                entry[key] = value
            else:
                text = str(value).strip()
                if text:
                    entry[key] = text

        return entry

    def auto_generate_rule_from_feedback(
        self,
        peer: str,
        item: str,
        category: str,
        account: str,
    ) -> Dict[str, Any]:
        """
        Auto-generate rule from feedback

        Args:
            peer: Payee
            item: Item
            category: Category
            account: Target account

        Returns:
            Generated rule
        """
        # Build conditions
        conditions = {}

        if peer:
            conditions["peer"] = peer
        if item:
            conditions["item"] = item
        if category:
            conditions["category"] = category

        # Generate rule name
        name_parts = []
        if peer:
            name_parts.append(peer[:10])
        if item:
            name_parts.append(item[:10])
        if category:
            name_parts.append(category[:10])

        name = "-".join(name_parts) if name_parts else "auto-generated-rule"

        return self.create_rule(
            name=f"{name}-{uuid.uuid4().hex[:6]}",
            conditions=conditions,
            account=account,
            confidence=0.9,
            source="auto",
        )
