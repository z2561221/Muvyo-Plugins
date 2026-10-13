# Official verifier

`mv_addon.py` and `LICENSE` are copied without changes from [thsrite/muvyo-addon-guide](https://github.com/thsrite/muvyo-addon-guide)
at commit `dbf96b5ce1aba87fe73440091b4d513b9ccc4fae`.

Verifier SHA-256: `ae0187203f68fb2e97b9ebbaf3d7f19f4e879a5a9ef5841ef953aa52f7fbb4de`.

CI uses only `verify`: no author credentials, repository private key or decrypted
plugin source is required. Official certificate expiry, signature, icon and
mascot image checks remain enabled. The package author must renew an expired
certificate and publish a new signed version; CI does not bypass expiry.
