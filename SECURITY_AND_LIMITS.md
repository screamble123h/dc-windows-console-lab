# TZ4.10 safety and limits

- GitHub public Actions standard windows-2022 runner only.
- Manual workflow_dispatch only, no trigger on source push.
- No paid resources; minimum public-repository permission scope, checkout
  with persist-credentials disabled.
- No production process execution. This overlay contains no production
  hostname, paths, credentials, personal information or customer data.
- Tests can deliberately open a visible CMD **only on the isolated runner**.
- Positive control with nonce and Win32 HWND+PID is required before claiming
  zero visible consoles in this runner. It is not proof of a physical GUI.
- Negative control uses CREATE_NO_WINDOW. It is not a guarantee against
  millisecond flashes below the sampling interval.
- Actual foreground transition is only PASS if Notepad was demonstrably in
  the foreground and an independently observed transfer occurred.
- CLIXML diagnostic deliberately preserves raw byte streams. It does not
  silently strip progress, warning or error records from Desktop Commander.
- Resource snapshots enumerate only the runner's window station and candidate
  process names; not proof of zero leaks in every interactive environment.
- No full Remote MCP transport + reconnect test is supplied by this workflow.
- All evidence retains `ready_to_deploy=false` regardless of CI color.
