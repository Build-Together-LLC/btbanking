import json
from base64 import b64decode, b64encode
from unittest import TestCase
from unittest.mock import patch

from Crypto.Cipher import AES, PKCS1_v1_5
from Crypto.PublicKey import RSA
from Crypto.Util.Padding import pad, unpad

from btbanking.icici_crypto import decrypt_response, encrypt_request


class TestICICIHybrid(TestCase):
	@classmethod
	def setUpClass(cls):
		cls.rsa_key = RSA.generate(2048)
		cls.private_key = cls.rsa_key.export_key()
		cls.public_key = cls.rsa_key.public_key().export_key()
		cls.data = {"CORPID": "TEST", "USERID": "USER1", "URN": "TESTING123"}

	def test_request_matches_the_banks_seven_steps(self):
		with patch("btbanking.icici_crypto.secrets.choice", side_effect=list("1" * 16 + "2" * 16)):
			packet = encrypt_request(self.data, self.public_key)
		key = PKCS1_v1_5.new(self.rsa_key).decrypt(b64decode(packet["encryptedKey"]), b"invalid")
		self.assertEqual(key, b"1" * 16)
		iv = b"2" * 16
		plaintext = unpad(AES.new(key, AES.MODE_CBC, iv).decrypt(b64decode(packet["encryptedData"])), 16)
		self.assertEqual(plaintext[:16], iv)
		self.assertEqual(json.loads(plaintext[16:]), self.data)
		self.assertEqual(packet["oaepHashingAlgorithm"], "NONE")
		self.assertEqual(packet["iv"], "")

	def test_requests_use_fresh_session_keys(self):
		packets = [encrypt_request(self.data, self.public_key) for _ in range(2)]
		keys = [
			PKCS1_v1_5.new(self.rsa_key).decrypt(b64decode(p["encryptedKey"]), b"invalid") for p in packets
		]
		self.assertNotEqual(keys[0], keys[1])
		for key in keys:
			self.assertEqual(len(key), 16)
			self.assertTrue(key.isdigit())

	def response(self, layout):
		key, iv = b"1234567890123456", b"6543210987654321"
		plaintext = json.dumps(self.data).encode()
		if layout == "encrypted-prefix":
			plaintext = iv + plaintext
		ciphertext = AES.new(key, AES.MODE_CBC, iv).encrypt(pad(plaintext, 16))
		if layout == "raw-prefix":
			ciphertext = iv + ciphertext
		return {
			"encryptedKey": b64encode(PKCS1_v1_5.new(self.rsa_key.public_key()).encrypt(key)).decode(),
			"encryptedData": b64encode(ciphertext).decode(),
			"iv": b64encode(iv).decode() if layout == "separate-iv" else "",
			"oaepHashingAlgorithm": "NONE",
		}

	def test_response_uses_received_iv_and_clients_private_key(self):
		for layout in ["encrypted-prefix", "raw-prefix", "separate-iv"]:
			with self.subTest(layout=layout):
				self.assertEqual(decrypt_response(self.response(layout), self.private_key), self.data)

	def test_rejects_invalid_ciphertext(self):
		packet = self.response("raw-prefix")
		packet["encryptedData"] = b64encode(b"truncated").decode()
		with self.assertRaisesRegex(ValueError, "response length"):
			decrypt_response(packet, self.private_key)

	def test_rejects_wrong_rsa_padding(self):
		packet = self.response("raw-prefix")
		packet["oaepHashingAlgorithm"] = "SHA1"
		with self.assertRaisesRegex(ValueError, "RSA padding"):
			decrypt_response(packet, self.private_key)

	def test_reports_a_public_key_configured_as_the_private_key(self):
		with self.assertRaisesRegex(ValueError, "contains only a public key"):
			decrypt_response(self.response("raw-prefix"), self.public_key)
