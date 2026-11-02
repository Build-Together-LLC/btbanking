"""ICICI's random-key hybrid format, independent of Frappe and connector state."""

import json
import secrets
import string
from base64 import b64decode, b64encode

from Crypto.Cipher import AES, PKCS1_v1_5
from Crypto.PublicKey import RSA
from Crypto.Util.Padding import pad, unpad


def encrypt_request(data, public_key):
	key = "".join(secrets.choice(string.digits) for _ in range(16)).encode("ascii")
	iv = "".join(secrets.choice(string.digits) for _ in range(16)).encode("ascii")
	plaintext = json.dumps(data).encode("utf-8")
	# ICICI's supplied steps explicitly encrypt RANDOMNO2 + JSON, not JSON alone.
	ciphertext = AES.new(key, AES.MODE_CBC, iv).encrypt(pad(iv + plaintext, AES.block_size))
	encrypted_key = PKCS1_v1_5.new(RSA.import_key(public_key)).encrypt(key)
	return {
		"requestId": secrets.token_hex(16),
		"service": "",
		"encryptedKey": b64encode(encrypted_key).decode("ascii"),
		"oaepHashingAlgorithm": "NONE",
		"iv": "",
		"encryptedData": b64encode(ciphertext).decode("ascii"),
		"clientInfo": "",
		"optionalParam": "",
	}


def decrypt_response(packet, private_key):
	if packet.get("oaepHashingAlgorithm", "NONE") != "NONE":
		raise ValueError("Unsupported ICICI response RSA padding")
	rsa_key = RSA.import_key(private_key)
	if not rsa_key.has_private():
		raise ValueError(
			"ICICI response decryption requires your client's private key; the configured file contains only a public key."
		)
	sentinel = secrets.token_bytes(32)
	key = PKCS1_v1_5.new(rsa_key).decrypt(b64decode(packet["encryptedKey"], validate=True), sentinel)
	if key == sentinel or len(key) not in (16, 24, 32):
		raise ValueError("Unable to decrypt ICICI response session key")
	ciphertext = b64decode(packet["encryptedData"], validate=True)
	minimum_length = 16 if packet.get("iv") else 32
	if len(ciphertext) < minimum_length or len(ciphertext) % AES.block_size:
		raise ValueError("Invalid ICICI encrypted response length")
	if packet.get("iv"):
		iv = b64decode(packet["iv"], validate=True)
		plaintext = unpad(AES.new(key, AES.MODE_CBC, iv).decrypt(ciphertext), AES.block_size)
	else:
		# Per ICICI: use the first decoded block as IV, decrypt, then discard the
		# first plaintext block. Works with their encrypted-prefix and raw-IV-prefix layouts.
		iv = ciphertext[:16]
		plaintext = unpad(AES.new(key, AES.MODE_CBC, iv).decrypt(ciphertext)[16:], AES.block_size)
	return json.loads(plaintext.decode("utf-8"))
