# Phase 8.2 Recovery Notes

S15 restart coverage includes:

- C1 active contract saved
- C2 risk snapshot saved
- C3 auto decision saved
- C4 transition prepared before commit
- C5 replan saved before CAS apply
- C6 CAS applied before ACK
- C7 execution record saved before statistics
- C8 outbox claimed before ACK
- C9 checkpoint updated before next step

Each recovery event records the crash point plus command and plan progress. The acceptance guard checks that all nine points are present and that completed steps are not repeated after recovery.
