# Push Notification — Manual Device Checklist (T-09)

**Purpose:** verify what cannot be proven in-process — that the notification is
actually *displayed* correctly and contains nothing but the generic wake-up
text on real Android/iOS browsers. Run on one physical device per release.

The automated counterpart lives in `tests/test_push_contract.py` (wire-payload
shape, provider-rejection handling, schedule lifecycle).

## Preconditions

- [ ] Relay reachable from the device (VPN or LAN as configured)
- [ ] PWA installed to home screen (Web Push requires it on iOS ≥ 16.4)
- [ ] `push_enabled=true` and VAPID keys set server-side
- [ ] Browser granted notification permission

## Steps

1. Open the PWA, sign in, enable notifications when prompted.
2. From a second device (or curl), create a push subscription and a due
   schedule for this profile.
3. Wait ≤ 60 s (worker tick) for the notification.

## Pass criteria

- [ ] Notification appears within ~90 s.
- [ ] Body text is exactly the generic message ("You have a health reminder."
      / localized equivalent) — **no** name, symptom, severity, diagnosis,
      instruction, clinic, or contact detail anywhere on the lock screen,
      banner, or notification shade.
- [ ] Tapping opens the app; no PHI is visible before unlock on a locked
      device (lock-screen content hidden).
- [ ] No sound/vibration pattern that could signal urgency (generic only).

## Fail action

Any leak of clinical context: file as a privacy incident against PS-01,
disable `push_enabled` at the relay, and re-run
`tests/test_privacy_surface.py` plus this checklist before re-enabling.

Last executed: never yet (preclinical) · Executed by: ______ · Date: ______
