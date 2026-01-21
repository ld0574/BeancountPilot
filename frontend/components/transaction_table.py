"""
Transaction table component
"""

import streamlit as st
import pandas as pd
from frontend.i18n import t


class TransactionTable:
    """Transaction table component"""

    def __init__(self, transactions=None, classifications=None):
        """
        Initialize transaction table

        Args:
            transactions: Transaction list
            classifications: Classification result list
        """
        self.transactions = transactions or []
        self.classifications = classifications or []

    def render(self, editable=True):
        """
        Render transaction table

        Args:
            editable: Whether the table is editable

        Returns:
            Edited DataFrame (if editable=True)
        """
        # Merge data
        df = self._merge_data()

        if df.empty:
            st.info(t("no_transaction_data"))
            return None

        # Configure columns
        column_config = {
            "peer": st.column_config.TextColumn(t("payee"), width="medium"),
            "item": st.column_config.TextColumn(t("item_label"), width="medium"),
            "category": st.column_config.TextColumn(t("category_label"), width="small"),
            "type": st.column_config.TextColumn(t("type_label"), width="small"),
            "time": st.column_config.TextColumn(t("time_label"), width="medium"),
            "amount": st.column_config.NumberColumn(t("amount"), format="%.2f", width="small"),
            "account": st.column_config.SelectboxColumn(
                t("account"),
                options=self._get_chart_of_accounts(),
                required=True,
                width="large",
            ),
            "confidence": st.column_config.ProgressColumn(
                t("confidence"),
                help=t("confidence_help"),
                format="%.2f",
                min_value=0,
                max_value=1,
                width="small",
            ),
            "source": st.column_config.TextColumn(t("source"), width="small"),
        }

        # Render table
        if editable:
            return st.data_editor(
                df,
                num_rows="dynamic",
                use_container_width=True,
                column_config=column_config,
                hide_index=True,
            )
        else:
            st.dataframe(
                df,
                use_container_width=True,
                column_config=column_config,
                hide_index=True,
            )
            return df

    def _merge_data(self):
        """Merge transactions and classification data"""
        if not self.transactions:
            return pd.DataFrame()

        # Create classification mapping
        classification_map = {}
        if self.classifications:
            classification_map = {
                c["transaction_id"]: c for c in self.classifications
            }

        # Merge data
        merged = []
        for tx in self.transactions:
            tx_id = tx.get("id", "")
            classification = classification_map.get(tx_id, {})

            merged.append({
                "id": tx_id,
                "peer": tx.get("peer", ""),
                "item": tx.get("item", ""),
                "category": tx.get("category", ""),
                "type": tx.get("type", ""),
                "time": tx.get("time", ""),
                "amount": tx.get("amount", 0),
                "account": classification.get("account", "Expenses:Misc"),
                "confidence": classification.get("confidence", 0),
                "reasoning": classification.get("reasoning", ""),
                "source": classification.get("source", "ai"),
            })

        return pd.DataFrame(merged)

    def _get_chart_of_accounts(self):
        """Get chart of accounts"""
        chart_of_accounts = st.session_state.get("chart_of_accounts", "")

        accounts = []
        for line in chart_of_accounts.split("\n"):
            line = line.strip()
            if line and not line.startswith("#"):
                accounts.append(line)

        return accounts if accounts else ["Expenses:Misc"]

    def get_statistics(self):
        """Get statistics"""
        if not self.transactions:
            return {}

        total_amount = sum(tx.get("amount", 0) for tx in self.transactions)
        avg_amount = total_amount / len(self.transactions) if self.transactions else 0

        ai_count = sum(
            1 for c in self.classifications if c.get("source") == "ai"
        )
        rule_count = sum(
            1 for c in self.classifications if c.get("source") == "rule"
        )

        avg_confidence = 0
        if self.classifications:
            avg_confidence = sum(
                c.get("confidence", 0) for c in self.classifications
            ) / len(self.classifications)

        return {
            "total_transactions": len(self.transactions),
            "total_amount": total_amount,
            "avg_amount": avg_amount,
            "ai_classified": ai_count,
            "rule_matched": rule_count,
            "avg_confidence": avg_confidence,
        }
