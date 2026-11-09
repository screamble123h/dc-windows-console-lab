# Desktop Commander TZ4.10 — calibrated Windows laboratory

**Status: NOT READY FOR DEPLOYMENT.** This overlay adds tests; it does not install
or automatically fix Desktop Commander. It must never be used on a production
Windows computer.

## Target

Public test repository: https://github.com/screamble123h/dc-windows-console-lab

Apply these text files **only in a new experimental branch** derived from the
current `main`. Do not modify production repositories. The branch must already
contain the existing sanitized `lab/` and `ci/` tests from TZ4.8.

The new workflow is `.github/workflows/windows-v4_10-ci.yml`. It runs **only by
manual `workflow_dispatch`**, only on standard `windows-2022` hosted runners,
and retains evidence for **30 days**, if the repository retention policy permits.
No paid VM, cloud service, self-hosted runner or production connector is used.

## Preparation and permissions

1. Configure the existing GitHub App installation (ID `166887834`) to add ONLY
   `screamble123h/dc-windows-console-lab` to its selected repositories. Do not
   change other repository access. The user must approve this in GitHub UI.
2. Verify that the connector lists the test repository under that installation,
   and that a write action in a *new test branch* actually succeeds. If HTTP 403
   persists, stop; never retry destructive operations or write to `main`.
3. Upload this overlay through the approved GitHub connection to the new branch.
4. Manually start **Desktop Commander TZ4.10 - calibrated Windows evidence**
   from GitHub > Actions > Run workflow, selecting the test branch. The current
   ChatGPT GitHub connector lacks a workflow_dispatch mutation action.

## What the tests prove and do not prove

- A deliberately **visible** `cmd.exe` must be detected as a new console window
  with nonzero HWND and owning PID and a unique test title.
- A hidden `cmd.exe` must *not* be detected as a visible console with its unique
  test title.
- A Notepad foreground transition, when the session permits it, is tested
  separately. If Notepad cannot be activated, focus control is NOT PROVEN.
- The existing v4.6 matrix runs 100 baseline and 100 patched trials and the
  actual in-process Desktop Commander `startProcess` API smoke.
- The extra 15 CLIXML tests record **raw, unmodified stdout and stderr** as
  separate files and verify real error codes, markers and Russian text.
- Win32 `EnumDesktopsW` checks whether the experimental `FMDCLab_` desktop
  names remain in the runner window station; process snapshots detect residual
  broker PIDs. These are **candidates** only, not absolute leak certification.
- GitHub-hosted CI still does **not** establish human-workstation GUI behavior
  or real Remote MCP transport/reconnect behavior.

The strict verifier fails when a positive GUI control is not detected, a
negative control fails, focus cannot be demonstrated, 100+100 test counts are
missing, CLIXML preservation fails, or resource evidence is incomplete.
Artifacts are uploaded even on failure, so a red job can be informative.

**Never interpret all-green CI as deployment approval:** the verdict JSON
always says `ready_to_deploy: false` until separate GUI and Remote MCP
certification is actually performed on an authorized independent machine.

## Existing Windows evidence

These are *historical* and not runs of TZ4.10:

- https://github.com/screamble123h/dc-windows-console-lab/actions/runs/42498424953
- https://github.com/screamble123h/dc-windows-console-lab/actions/runs/42499070787

Both baseline and patched runs passed 100/100 functional cases. In each,
`CLIXML` appeared in `stderr` of 40 patched cases and zero baseline cases.
The prior observer had no positive control, so zero observed windows could
not confirm that it would detect an actual popup.

## No production deployment

The patch remains experimental. Do not modify the installed Desktop Commander,
remote integrations, Codex, Web-to-Print, or any workstation. No real accounts,
private files, customer orders or connection credentials may enter this public
repository.
