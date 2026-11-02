# ICICI Registration Status extension

BT Banking extends the installed India Banking Connector v16 ICICI Connector through
Frappe's `extend_doctype_class` hook. It does not replace the original app or its DocTypes.

## Changes

- Generate a fresh cryptographically random 16-digit AES key and IV for every Registration Status request.
- Encrypt the AES key using ICICI's public certificate with RSA PKCS#1 v1.5 padding.
- Encrypt `IV + JSON payload` using AES-CBC with PKCS padding, per ICICI's supplied steps.
- Send a JSON envelope with `encryptedKey`, `encryptedData`, `oaepHashingAlgorithm: NONE`, and metadata.
- Use `content-type: application/json` and `apikey` as application headers, clearing Requests session defaults and setting connection/read timeouts. HTTP transport headers are generated automatically.
- Decrypt hybrid responses with the client's private key and response IV layout.
- Report an actionable error when a public key is configured as the client private key.
- Preserve plain JSON gateway errors and normalize successful status capitalization.
- Log the response before attempting decryption.

URLs continue to come from the ICICI Connector's **API Endpoints** tab. No shared
**Bank API Endpoint** record, migration or copied customer configuration is required.
Other operations delegate to the installed connector's implementation.

## Install and activate

Install `india_banking_connector` version 16 first, then this app on the same site:

```sh
bench get-app https://github.com/Build-Together-LLC/btbanking --branch Bt
bench --site your-site install-app btbanking
bench --site your-site migrate
bench restart
```

Configure the ICICI Connector's sandbox Registration Status endpoint, API key,
ICICI request-encryption public certificate and client response-decryption private key.
The client private key must match the public certificate previously shared with ICICI.
Refresh the browser before testing. Test against the sandbox before production use.

If the earlier local ICICI customization is installed, restore the original connector
code after preserving any unrelated changes. This extension owns the customization;
no patch to India Banking Connector source is needed.

## Validation and limitations

Run with the bench Python environment from this app directory:

```sh
python -m unittest discover -s btbanking/tests -v
```

Tests cover the bank's request format, fresh keys, response IV formats, invalid keys,
request headers/logging, errors, success handling, and delegation to the upstream class.

The equivalent local connector implementation returned HTTP 200 with an encrypted
response from ICICI's sandbox. Decryption was blocked because the configured client
Private Key file contained only a public key. HTTP 200 alone does not establish successful
registration; the decrypted response is required. This packaged extension still needs
installation and UAT on the target site.

No credentials, certificates, private keys, account data or request logs are committed.
