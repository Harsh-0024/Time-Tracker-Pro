from __future__ import annotations

import json
import logging
import os
import requests
from typing import Optional, Tuple, Dict, Any, List

from ..db import get_db_connection
from ..repositories.sheety_accounts import (
    get_active_api_account,
    set_active_account,
    update_account_test_result,
    get_user_api_accounts,
)
from ..repositories.settings import get_user_settings
from ..repositories.users import get_user_count
from ..core.rows import row_value


logger = logging.getLogger(__name__)

SHEETY_ENV_ACCOUNTS_ENV = "SHEETY_API_ACCOUNTS"
SHEETY_ENV_TOKENS_ENV = "SHEETY_API_TOKENS"
SHEETY_ENDPOINT_ENV = "SHEETY_ENDPOINT"


class SheetyFailoverService:
    """Service for handling Sheety API requests with automatic failover."""
    
    def __init__(self, db_name: str, user_id: int):
        self.db_name = db_name
        self.user_id = user_id
        self.max_retries = 3
        self.switched_account = False
        self.switched_from = None
        self.switched_to = None

    def _account_id(self, account) -> Optional[int]:
        try:
            value = account["id"] if hasattr(account, "keys") and "id" in account.keys() else None
        except Exception:
            value = None
        if value is None:
            return None
        try:
            return int(value)
        except (TypeError, ValueError):
            return None

    def _account_label(self, account) -> str:
        label = row_value(account, "account_email") or row_value(account, "email")
        if label:
            return str(label)
        account_id = self._account_id(account)
        if account_id is not None:
            return f"Account {account_id}"
        return "Env Token"

    def _account_key(self, account) -> tuple:
        account_id = self._account_id(account)
        if account_id is not None:
            return ("db", account_id)
        return (
            "env",
            row_value(account, "api_token"),
            row_value(account, "api_base_url"),
        )

    def _is_env_account(self, account) -> bool:
        try:
            if hasattr(account, "keys") and "is_env" in account.keys():
                return bool(account["is_env"])
        except Exception:
            pass
        return False

    def _allow_env_fallback(self) -> bool:
        try:
            return get_user_count(self.db_name) <= 1
        except Exception:
            return False

    def _resolve_env_base_url(self, active_account=None) -> str:
        settings = get_user_settings(self.db_name, int(self.user_id))
        base_url = (settings.get("sheety_endpoint") or "").strip() if settings else ""
        if not base_url:
            base_url = (os.getenv(SHEETY_ENDPOINT_ENV) or "").strip()
        if not base_url and active_account is not None:
            base_url = (row_value(active_account, "api_base_url") or "").strip()
        return base_url

    def _parse_env_accounts(self, base_url: Optional[str] = None) -> List[Dict[str, Any]]:
        if not self._allow_env_fallback():
            return []
        resolved_base_url = (base_url or "").strip() or self._resolve_env_base_url()
        if not resolved_base_url:
            return []

        accounts: List[Dict[str, Any]] = []
        seen_tokens = set()

        raw_accounts = (os.getenv(SHEETY_ENV_ACCOUNTS_ENV) or "").strip()
        if raw_accounts:
            try:
                payload = json.loads(raw_accounts)
            except Exception as exc:
                logger.warning("Failed to parse %s: %s", SHEETY_ENV_ACCOUNTS_ENV, exc)
                payload = []
            if isinstance(payload, dict):
                payload = [payload]
            if isinstance(payload, list):
                for item in payload:
                    token = ""
                    account_url = ""
                    account_email = ""
                    if isinstance(item, str):
                        token = item.strip()
                    elif isinstance(item, dict):
                        token = (item.get("api_token") or item.get("token") or "").strip()
                        account_url = (
                            item.get("api_base_url")
                            or item.get("api_url")
                            or item.get("endpoint")
                            or ""
                        ).strip()
                        account_email = (
                            item.get("account_email") or item.get("email") or ""
                        ).strip()
                    if not token:
                        continue
                    if token in seen_tokens:
                        continue
                    seen_tokens.add(token)
                    accounts.append(
                        {
                            "id": None,
                            "user_id": int(self.user_id),
                            "account_email": account_email or f"Env Token {len(accounts) + 1}",
                            "api_base_url": account_url or resolved_base_url,
                            "api_token": token,
                            "priority": 1000 + len(accounts),
                            "is_active": 0,
                            "is_env": True,
                        }
                    )

        raw_tokens = (os.getenv(SHEETY_ENV_TOKENS_ENV) or "").strip()
        if raw_tokens:
            for raw_token in raw_tokens.replace(";", ",").replace("\n", ",").split(","):
                token = raw_token.strip()
                if not token:
                    continue
                if token in seen_tokens:
                    continue
                seen_tokens.add(token)
                accounts.append(
                    {
                        "id": None,
                        "user_id": int(self.user_id),
                        "account_email": f"Env Token {len(accounts) + 1}",
                        "api_base_url": resolved_base_url,
                        "api_token": token,
                        "priority": 1000 + len(accounts),
                        "is_active": 0,
                        "is_env": True,
                    }
                )

        return accounts

    def _get_all_accounts(self, active_account=None) -> List[Any]:
        accounts = list(get_user_api_accounts(self.db_name, self.user_id) or [])
        accounts.extend(self._parse_env_accounts(self._resolve_env_base_url(active_account)))
        return accounts

    def has_available_accounts(self) -> bool:
        return bool(self._get_all_accounts())

    def get_env_accounts(self) -> List[Dict[str, Any]]:
        return self._parse_env_accounts()
    
    def _build_headers(self, api_token: Optional[str]) -> Dict[str, str]:
        """Build request headers with optional auth token."""
        headers = {'Content-Type': 'application/json'}
        if api_token:
            headers['Authorization'] = api_token if api_token.startswith('Bearer ') else f'Bearer {api_token}'
        return headers
    
    def _test_api_account(self, account) -> Tuple[bool, Optional[int], Optional[str]]:
        """Test if an API account is working. Returns (success, row_count, error_message)."""
        try:
            api_base_url = account['api_base_url']
            headers = self._build_headers(row_value(account, 'api_token'))
            account_label = self._account_label(account)
            
            response = requests.get(api_base_url, headers=headers, timeout=10)
            
            if response.status_code == 200:
                try:
                    data = response.json()
                except ValueError:
                    return False, None, "Sheety returned a non-JSON response"
                # Sheety returns data in format: {"sheet1": [{...}, {...}]}
                # Get the first key's value which should be the array of rows
                sheet_data = next(iter(data.values())) if data else []
                row_count = len(sheet_data) if isinstance(sheet_data, list) else 0
                return True, row_count, None
            else:
                preview = (response.text or "").strip().replace("\n", " ")
                if len(preview) > 200:
                    preview = preview[:200] + "..."
                logger.warning(
                    "API test failed for account %s: HTTP %s",
                    account_label,
                    response.status_code,
                )
                detail = f"HTTP {response.status_code}"
                if preview:
                    detail = f"{detail} - {preview}"
                return False, None, detail
        except Exception as e:
            logger.error("API test error for account %s: %s", self._account_label(account), e)
            return False, None, str(e)
    
    def _try_request(
        self,
        account,
        method: str,
        endpoint: str = "",
        json_data: Optional[Dict] = None,
    ) -> Tuple[bool, Optional[Any], Optional[str]]:
        """Try a request with a specific account. Returns (success, response_data, error_message)."""
        try:
            api_base_url = account['api_base_url']
            url = f"{api_base_url.rstrip('/')}/{endpoint.lstrip('/')}" if endpoint else api_base_url
            headers = self._build_headers(row_value(account, 'api_token'))
            account_id = self._account_id(account)
            account_label = self._account_label(account)
            
            method_upper = str(method or "").upper()
            if method_upper == 'GET':
                response = requests.get(url, headers=headers, timeout=15)
            elif method_upper == 'POST':
                response = requests.post(url, headers=headers, json=json_data, timeout=15)
            elif method_upper == 'PUT':
                response = requests.put(url, headers=headers, json=json_data, timeout=15)
            elif method_upper == 'DELETE':
                response = requests.delete(url, headers=headers, timeout=15)
            else:
                return False, None, f"Unsupported method {method_upper}"
            
            if response.status_code in (200, 201, 204):
                if account_id is not None:
                    update_account_test_result(self.db_name, account_id, True, self.user_id)
                try:
                    return True, response.json() if response.content else {}, None
                except Exception:
                    return True, {}, None
            else:
                preview = (response.text or "").strip().replace("\n", " ")
                if len(preview) > 200:
                    preview = preview[:200] + "..."
                detail = f"HTTP {response.status_code}"
                if preview:
                    detail = f"{detail} - {preview}"
                logger.warning("Request failed for account %s: %s", account_label, detail)
                if account_id is not None:
                    update_account_test_result(self.db_name, account_id, False, self.user_id)
                return False, None, detail
        except Exception as e:
            logger.error("Request error for account %s: %s", self._account_label(account), e)
            account_id = self._account_id(account)
            if account_id is not None:
                update_account_test_result(self.db_name, account_id, False, self.user_id)
            return False, None, str(e)

    def _strip_internal_meta(self, json_data: Optional[Dict]) -> tuple[Optional[Dict], Optional[Dict[str, Any]]]:
        if not isinstance(json_data, dict):
            return json_data, None
        meta = json_data.get("__ttpro_meta")
        if meta is None and "__ttpro_bypass_outbox" not in json_data:
            return json_data, None
        cleaned: Dict[str, Any] = {}
        for key, value in json_data.items():
            if key in {"__ttpro_meta", "__ttpro_bypass_outbox"}:
                continue
            cleaned[key] = value
        return cleaned, (meta if isinstance(meta, dict) else None)

    def _infer_sheet_key(self, json_data: Optional[Dict]) -> Optional[str]:
        if not isinstance(json_data, dict):
            return None
        for key in json_data.keys():
            if key in {"__ttpro_meta", "__ttpro_bypass_outbox"}:
                continue
            return str(key)
        return None

    def make_request(self, method: str, endpoint: str = '', json_data: Optional[Dict] = None) -> Tuple[bool, Optional[Any], Optional[str]]:
        """
        Make a Sheety API request with automatic failover.
        Returns (success, response_data, error_message).
        """
        method_upper = str(method or "").upper()
        cleaned_json, _ = self._strip_internal_meta(json_data)

        if method_upper in {"POST", "PUT", "DELETE"}:
            try:
                from ..repositories.sheety_outbox import (
                    enqueue_outbox_operation,
                    is_rewrite_in_progress,
                )

                bypass_outbox = bool(
                    isinstance(json_data, dict) and bool(json_data.get("__ttpro_bypass_outbox"))
                )
                if not bypass_outbox and is_rewrite_in_progress(self.db_name, int(self.user_id)):
                    conn = get_db_connection(self.db_name)
                    try:
                        outbox_id = enqueue_outbox_operation(
                            conn,
                            int(self.user_id),
                            method_upper,
                            str(endpoint or ""),
                            self._infer_sheet_key(json_data),
                            (json_data if isinstance(json_data, dict) else {}),
                            True,
                        )
                        conn.commit()
                    finally:
                        conn.close()
                    return True, {"__queued": True, "outbox_id": int(outbox_id)}, None
            except Exception as exc:
                logger.warning("Failed to enqueue Sheety outbox operation: %s", exc)

        # Get active account
        active_account = get_active_api_account(self.db_name, self.user_id)
        accounts = self._get_all_accounts(active_account)

        if not active_account:
            if not accounts:
                # No accounts configured
                return False, None, "No Sheety API accounts configured"
            for account in accounts:
                success, _, _ = self._test_api_account(account)
                account_id = self._account_id(account)
                if account_id is not None:
                    update_account_test_result(self.db_name, account_id, success, self.user_id)
                if success:
                    if account_id is not None:
                        set_active_account(self.db_name, account_id, self.user_id)
                    active_account = account
                    break
            if not active_account:
                return False, None, "No working Sheety API account found"
        
        # Try the active account
        success, data, last_error = self._try_request(active_account, method_upper, endpoint, cleaned_json)
        
        if success:
            return True, data, None
        
        # Active account failed, try every fallback account
        logger.info("Active account %s failed, trying failover...", self._account_label(active_account))

        accounts = self._get_all_accounts(active_account)
        if not accounts:
            return False, None, "No Sheety API accounts configured"
        active_key = self._account_key(active_account)

        attempts = 0
        for account in accounts:
            if self._account_key(account) == active_key:
                continue
            attempts += 1
            logger.info("Trying fallback account %s (attempt %s)", self._account_label(account), attempts)
            success, data, error = self._try_request(account, method_upper, endpoint, cleaned_json)
            if success:
                # Failover successful! Switch to this account
                account_id = self._account_id(account)
                if account_id is not None:
                    set_active_account(self.db_name, account_id, self.user_id)
                self.switched_account = True
                self.switched_from = self._account_label(active_account)
                self.switched_to = self._account_label(account)

                logger.info(
                    "Failover successful: switched from %s to %s",
                    self.switched_from,
                    self.switched_to,
                )

                return True, data, None
            if error:
                last_error = error

        # All accounts failed
        return False, None, last_error or "All API accounts failed"

    def make_request_bypass_outbox(
        self, method: str, endpoint: str = "", json_data: Optional[Dict] = None
    ) -> Tuple[bool, Optional[Any], Optional[str]]:
        payload = json_data if isinstance(json_data, dict) else ({} if json_data is None else None)
        if isinstance(payload, dict):
            payload = dict(payload)
            payload["__ttpro_bypass_outbox"] = True
        return self.make_request(method, endpoint, payload)
    
    def get_failover_notification(self) -> Optional[Dict[str, str]]:
        """Get notification data if account was switched."""
        if self.switched_account:
            return {
                'from': self.switched_from,
                'to': self.switched_to
            }
        return None
    
    def test_connection(self, account_id: Optional[int] = None) -> Tuple[bool, Optional[int], Optional[str]]:
        """
        Test connection for a specific account or the active one.
        Returns (success, row_count, error_message).
        """
        if account_id:
            from ..repositories.sheety_accounts import get_api_account_by_id
            account = get_api_account_by_id(self.db_name, account_id, self.user_id)
        else:
            account = get_active_api_account(self.db_name, self.user_id)
        
        if not account:
            return False, None, "Account not found"
        
        success, row_count, error = self._test_api_account(account)
        account_pk = self._account_id(account)
        if account_pk is not None:
            update_account_test_result(self.db_name, account_pk, success, self.user_id)
        
        if success:
            return True, row_count, None
        else:
            return False, None, error or "Connection test failed"
