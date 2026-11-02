"""ICICI Registration Status hybrid format for India Banking Connector v16."""

import json

import frappe
import requests
from frappe import _
from india_banking_connector.india_banking_connector.doctype.bank_request_log.bank_request_log import (
	create_api_log,
)

from btbanking.icici_crypto import decrypt_response, encrypt_request


class ICICIHybridMixin:
	@frappe.whitelist()
	def registration_inquiry(self):
		self.bulk_transaction = False
		self.update_client_details("registration_status")
		url = self.urls.registration_status
		payload = self.get_encrypted_payload(method="registration_status")
		with requests.Session() as session:
			session.headers.clear()
			response = session.post(
				url,
				headers={"content-type": "application/json", "apikey": self.client_key},
				data=payload,
				timeout=(10, 60),
			)
		log_id = create_api_log(
			response,
			action="Registration Status",
			account_config=self.get_account_config("registration_status"),
			ref_doctype=self.doc.doctype,
			ref_docname=self.doc.name,
			connector=self,
		)
		result = self.get_decrypted_response(response, method="registration_status", log_id=log_id)
		if result.status == "success":
			self.db_set("registration_status", "Registered")
		frappe.msgprint(result.message or _("Registration Status Fetched Failed"))

	def get_encrypted_payload(self, method):
		if method != "registration_status":
			return super().get_encrypted_payload(method)
		with open(self.get_file_relative_path(self.public_key), "rb") as key_file:
			return json.dumps(encrypt_request(self.get_account_config(method), key_file.read()))

	def get_decrypted_response(self, response, method, log_id=None):
		if method != "registration_status":
			return super().get_decrypted_response(response, method, log_id=log_id)
		result = frappe._dict({})
		if not response.ok:
			result.status = "Request Failure"
			result.message = response.text or response.status_code
			return result
		packet = response.json()
		if "encryptedKey" in packet and "encryptedData" in packet:
			with open(self.get_file_relative_path(self.private_key), "rb") as key_file:
				data = decrypt_response(packet, key_file.read())
			self.set_decrypted_response(log_id, data)
		else:
			# ICICI can return an unencrypted gateway error with HTTP 200.
			data = packet
		self.get_formated_response(data, result, method)
		return result

	def get_formated_response(self, data, res_dict, method):
		if method == "registration_status":
			data = json.loads(data) if isinstance(data, str) else dict(data)
			if str(data.get("RESPONSE", "")).upper() == "SUCCESS":
				# Upstream v16 recognizes this spelling only.
				data["RESPONSE"] = "Success"
		return super().get_formated_response(data, res_dict, method)
