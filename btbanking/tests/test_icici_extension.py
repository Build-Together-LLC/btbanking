import ast
import json
from pathlib import Path
from types import SimpleNamespace
from unittest import TestCase
from unittest.mock import Mock, PropertyMock, mock_open, patch

import frappe
from india_banking_connector.connectors.doctype.icici_connector.icici_connector import ICICIConnector

from btbanking.overrides import icici_connector as module


class ExtendedICICI(module.ICICIHybridMixin, ICICIConnector):
	pass


class TestICICIExtension(TestCase):
	def setUp(self):
		self.connector = object.__new__(ExtendedICICI)
		self.connector.public_key = "public.crt"
		self.connector.private_key = "client.key"
		self.connector.bulk_transaction = False
		self.connector.client_key = "dummy-key"
		self.connector.doc = frappe._dict(doctype="ICICI Connector", name="test")
		self.enterContext(patch.object(module, "_", lambda message: message))

	def test_hook_declares_dependency_and_mixin(self):
		tree = ast.parse((Path(__file__).parents[1] / "hooks.py").read_text())
		values = {
			node.targets[0].id: ast.literal_eval(node.value)
			for node in tree.body
			if isinstance(node, ast.Assign)
			and isinstance(node.targets[0], ast.Name)
			and node.targets[0].id in ("required_apps", "extend_doctype_class")
		}
		self.assertIn("india_banking_connector", values["required_apps"])
		self.assertEqual(
			values["extend_doctype_class"]["ICICI Connector"],
			["btbanking.overrides.icici_connector.ICICIHybridMixin"],
		)
		self.assertIn(module.ICICIHybridMixin.registration_inquiry, frappe.whitelisted)

	def test_frappe_constructs_the_extended_controller(self):
		from frappe.model.base_document import _get_extended_class

		with (
			patch.object(
				frappe,
				"get_hooks",
				return_value={"ICICI Connector": ["btbanking.overrides.icici_connector.ICICIHybridMixin"]},
			),
			patch.object(frappe, "get_attr", return_value=module.ICICIHybridMixin),
		):
			extended = _get_extended_class(ICICIConnector, "ICICI Connector")
			self.assertTrue(issubclass(extended, ICICIConnector))
			self.assertIs(extended.registration_inquiry, module.ICICIHybridMixin.registration_inquiry)

	def test_other_operations_delegate_to_installed_connector(self):
		with patch.object(ICICIConnector, "get_encrypted_payload", return_value="upstream") as original:
			self.assertEqual(self.connector.get_encrypted_payload("make_payment"), "upstream")
			original.assert_called_once_with("make_payment")
		with patch.object(ICICIConnector, "get_decrypted_response", return_value="upstream") as original:
			self.assertEqual(
				self.connector.get_decrypted_response("response", "bank_balance", log_id="log"), "upstream"
			)
			original.assert_called_once_with("response", "bank_balance", log_id="log")

	def test_connector_endpoint_lookup_is_inherited(self):
		self.assertIs(ExtendedICICI.urls, ICICIConnector.urls)
		self.assertNotIn("urls", module.ICICIHybridMixin.__dict__)

	def test_payload_uses_hybrid_helper_and_configured_public_key(self):
		data = {"CORPID": "TEST"}
		with (
			patch.object(self.connector, "get_file_relative_path", return_value="public.crt"),
			patch.object(self.connector, "get_account_config", return_value=data),
			patch("builtins.open", mock_open(read_data=b"public-key")),
			patch.object(module, "encrypt_request", return_value={"encryptedKey": "test"}) as encrypt,
		):
			self.assertEqual(
				json.loads(self.connector.get_encrypted_payload("registration_status")),
				{"encryptedKey": "test"},
			)
			encrypt.assert_called_once_with(data, b"public-key")

	def test_registration_headers_and_logging_precede_decryption(self):
		calls = []
		url = "https://sandbox.example.test/RegistrationStatus"
		with (
			patch.object(
				ExtendedICICI,
				"urls",
				new_callable=PropertyMock,
				return_value=SimpleNamespace(registration_status=url),
			),
			patch.object(self.connector, "update_client_details"),
			patch.object(self.connector, "get_encrypted_payload", return_value="hybrid-json"),
			patch.object(self.connector, "get_account_config", return_value={}),
			patch.object(module.requests, "Session") as factory,
			patch.object(
				module, "create_api_log", side_effect=lambda *a, **k: calls.append("log") or "log-id"
			),
			patch.object(
				self.connector,
				"get_decrypted_response",
				side_effect=lambda *a, **k: (
					calls.append("decrypt") or frappe._dict(status="success", message="ok")
				),
			),
			patch.object(self.connector, "db_set") as db_set,
			patch.object(module.frappe, "msgprint"),
		):
			self.connector.registration_inquiry()
			session = factory.return_value.__enter__.return_value
			session.headers.clear.assert_called_once_with()
			session.post.assert_called_once_with(
				url,
				headers={"content-type": "application/json", "apikey": "dummy-key"},
				data="hybrid-json",
				timeout=(10, 60),
			)
			db_set.assert_called_once_with("registration_status", "Registered")
		self.assertEqual(calls, ["log", "decrypt"])

	def test_plain_gateway_errors_are_not_decrypted(self):
		response = Mock(ok=True)
		response.json.return_value = {"success": False, "errormessage": "Unauthorized"}
		with patch.object(module, "decrypt_response") as decrypt:
			result = self.connector.get_decrypted_response(response, "registration_status")
			self.assertEqual(result.status, "Failed")
			self.assertEqual(result.message, "Unauthorized")
			decrypt.assert_not_called()

	def test_http_errors_preserve_bank_response(self):
		result = self.connector.get_decrypted_response(
			Mock(ok=False, text="bank error", status_code=400), "registration_status"
		)
		self.assertEqual(result.status, "Request Failure")
		self.assertEqual(result.message, "bank error")

	def test_encrypted_response_uses_client_key_and_persists_plaintext(self):
		response = Mock(ok=True)
		response.json.return_value = {"encryptedKey": "key", "encryptedData": "data"}
		data = {"RESPONSE": "SUCCESS", "MESSAGE": "Registered"}
		with (
			patch.object(self.connector, "get_file_relative_path", return_value="client.key"),
			patch("builtins.open", mock_open(read_data=b"private-key")),
			patch.object(module, "decrypt_response", return_value=data) as decrypt,
			patch.object(self.connector, "set_decrypted_response") as save,
		):
			result = self.connector.get_decrypted_response(response, "registration_status", log_id="log-id")
			decrypt.assert_called_once_with(response.json.return_value, b"private-key")
			save.assert_called_once_with("log-id", data)
			self.assertEqual(result.status, "success")

	def test_success_normalization_does_not_modify_input(self):
		data = {"RESPONSE": "SUCCESS"}
		result = frappe._dict()
		self.connector.get_formated_response(data, result, "registration_status")
		self.assertEqual(data["RESPONSE"], "SUCCESS")
		self.assertEqual(result.status, "success")
