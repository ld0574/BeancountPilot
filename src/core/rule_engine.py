"""
Rule engine - manages and executes rule-based classification
"""

import json
import uuid
from typing import Dict, Any, List, Optional

from sqlalchemy.orm import Session

from src.db.repositories import RuleRepository


class RuleEngine:
    """Rule engine"""

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

    def match_transaction(
        self, peer: str, item: str, category: str
    ) -> List[Dict[str, Any]]:
        """
        Match applicable rules for a transaction

        Args:
            peer: Payee
            item: Item
            category: Category

        Returns:
            List of matched rules
        """
        rules = RuleRepository.match_transaction(self.db, peer, item, category)

        return [
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

    def export_rules_to_deg_format(self) -> str:
        """
        Export rules to double-entry-generator configuration format

        Returns:
            YAML format rule configuration
        """
        rules = RuleRepository.list_all(self.db)

        # Build mapping
        mapping = {}

        for rule in rules:
            conditions = json.loads(rule.conditions)

            # Process peer conditions
            if "peer" in conditions:
                peer_conditions = conditions["peer"]
                if isinstance(peer_conditions, str):
                    peer_conditions = [peer_conditions]

                for peer in peer_conditions:
                    if peer not in mapping:
                        mapping[peer] = {}
                    mapping[peer]["account"] = rule.account

            # Process item conditions
            if "item" in conditions:
                item_conditions = conditions["item"]
                if isinstance(item_conditions, str):
                    item_conditions = [item_conditions]

                for item in item_conditions:
                    if item not in mapping:
                        mapping[item] = {}
                    mapping[item]["account"] = rule.account

        # Convert to YAML format
        import yaml

        return yaml.dump({"mapping": mapping}, allow_unicode=True, sort_keys=False)

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
