# Android biometric login 1.0.34

Base: b4d3f1c. No server code, schema, production DB, photos or photo queue changes.

## Operation
- Password sign-in remains the first step. On supported APKs the user can opt into "이 기기에서 생체 로그인 사용" and authenticate with the Android system prompt.
- Android 11/API30+ with an enrolled Class 3 biometric is supported; other devices/APKs and browsers keep password sign-in. Weak face recognition is not accepted. All qualifying fingerprints enrolled in the device may authorize this vault; use a personal device.
- Username/password JSON is encrypted with an AndroidKeyStore AES-GCM key requiring strong biometric authentication for every operation. Server origin is authenticated additional data. Preferences contain only ciphertext, IV, key alias and server origin. Android backup is disabled. No biometric templates are handled by this app.
- Successful decryption performs an HTTPS POST to the existing /api/login from native code, with redirects disabled, finite timeouts and bounded response size. Only the server-issued session token crosses back to JavaScript. Offline login is not granted. Normal server password checks, rate limiting, account active checks and current permissions remain authoritative. Password change/deactivation rejects the saved credential on next sign-in.
- Key invalidation, fingerprint/security changes, cancellation and lockout fall back to password login. Native work is cancelled on Activity stop and server-address change clears enrollment. Password sign-in clears previous enrollment before optionally enrolling the current account.
- Normal logout revokes the current server session but keeps the optional biometric vault, allowing subsequent biometric sign-in. The login page provides "생체 로그인 해제" to remove it. This feature does not add a separate lock to an already authenticated session on every app resume. Sessions retain the server's existing 12-hour expiry.
- Existing VIN system camera capture, photo upload queue, insets and server trust checks remain intact.

## Verification
- tests/biometric_browser.py: actual isolated server/Chromium; old-APK browser fallback, password login, mocked native cancellation/success, invalid token denied without offline cache fallback, enrollment cancellation keeps successful password login, no password in browser persistent storage.
- tests/vin_rear_browser.py: existing system camera bridge/file-capture regression passed.
- Gradle assembleRelease and release lint passed after correction of a platform-vs-AndroidX constant. Existing SDK XML/deprecated API warnings remain.
- Signed APK verified with apksigner; package com.hakom.warehouse.photos unchanged, versionCode 34/versionName 1.0.34. Certificate SHA256 matches the prior locally released APK in android-safe-area-20261024/release. Password/key material was not printed or committed. Artifact: C:/Users/CCS/ScooterWarehouse-deployment/android-biometric-1.0.34/스쿠터창고.apk; verification.json alongside it.
- Real Galaxy Z Fold8 fingerprint prompt, hardware-bound encryption/decryption, enrollment changes/lockout, update installation, camera/keyboard/fold transitions on this APK are **unverified**. Browser native callbacks are mocks, not device authentication evidence.

## Deploy/recovery
Web patch plus new APK required. Old APKs remain compatible with password login. Fast-forward this reviewed commit; no server restart or data migration required. Install the APK as an update, not by deleting the existing app (pending original photos must remain). A web-only rollback to b4d3f1c disables the biometric UI while retaining password login; production DB must not be restored/replaced. Keep signed artifacts and keys outside Git. GitHub push is not part of this change.

Reference: https://developer.android.com/identity/sign-in/biometric-auth and Android KeyGenParameterSpec setUserAuthenticationParameters.
