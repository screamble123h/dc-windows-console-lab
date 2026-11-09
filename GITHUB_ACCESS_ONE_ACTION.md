# Exactly one necessary owner action

Open https://github.com/settings/installations/166887834 and choose
**Configure → Repository access → Select repositories**. Add the **single**
public repository `screamble123h/dc-windows-console-lab` and save.

The existing app installation currently lists eight selected private
repositories, not this public lab. Thus the integration can read public data
but does not have installation-scoped write access to the test repository.
This strongly explains GitHub HTTP 403 on branch/blob creation.

After saving, the next checks are:

- Does `list_repositories_by_installation(166887834)` now include the lab?
- Is `Contents: Read & write` permitted for the installed GitHub App? If not,
  a repository selection alone cannot grant an additional application scope.
- Does creating a branch from the current `main` SHA succeed (no edits to main)?

Do not add other FotoMag repositories, change production permissions, expose
secrets, or use a paid service. If the GitHub app cannot write even after the
repository is selected, upload this overlay to a test branch via the GitHub
website instead.
