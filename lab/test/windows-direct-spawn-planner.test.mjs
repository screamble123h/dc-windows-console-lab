import test from 'node:test';
import assert from 'node:assert/strict';
import { planWindowsDirectSpawn, parseLiteralWindowsInvocation } from '../dist/utils/windows-direct-spawn.js';
import { getShellSpawnArgs } from '../dist/utils/shell.js';

const ps = 'C:\\Windows\\System32\\WindowsPowerShell\\v1.0\\powershell.exe';
const cmd = 'C:\\Windows\\System32\\cmd.exe';
const pwsh = 'C:\\Program Files\\PowerShell\\7\\pwsh.exe';
const git = 'C:\\Program Files\\Git\\cmd\\git.exe';
const exe = 'C:\\Program Files\\nodejs\\node.exe';
const locations = new Map([
  ['powershell', ps], ['powershell.exe', ps],
  ['cmd', cmd], ['cmd.exe', cmd],
  ['pwsh', pwsh], ['pwsh.exe', pwsh],
  ['git.exe', git], ['node.exe', exe],
  [ps.toLowerCase(), ps], [cmd.toLowerCase(), cmd],
  [pwsh.toLowerCase(), pwsh], [git.toLowerCase(), git],
  [exe.toLowerCase(), exe],
]);
const resolve = name => locations.get(name.toLowerCase()) || null;
const plan = (command, configured=ps, resolver=resolve, isWindows=true) =>
  planWindowsDirectSpawn(command, configured, resolver, isWindows);

test('direct native same-shell PowerShell preserves switches without a wrapper', () => {
  assert.deepEqual(plan('powershell -NoProfile -NoLogo'), {
    executable: ps, args: ['-NoProfile', '-NoLogo'], windowsVerbatim: false, reason: 'same-shell'
  });
  assert.deepEqual(plan('powershell.exe -NoProfile').args, ['-NoProfile']);
  assert.deepEqual(plan('PowerShell -NoProfile -NonInteractive -WindowStyle Hidden').args,
    ['-NoProfile', '-NonInteractive', '-WindowStyle', 'Hidden']);
});

test('CMD uses Windows verbatim argument mode only when directly spawning CMD', () => {
  assert.deepEqual(plan('cmd /Q', cmd), {
    executable: cmd, args: ['/Q'], windowsVerbatim: true, reason: 'same-shell'
  });
  assert.equal(plan('cmd.exe /c echo', ps).windowsVerbatim, true);
});

test('pwsh direct same-shell without a quoted executable path', () => {
  assert.deepEqual(plan('pwsh -NoLogo -NoProfile', pwsh), {
    executable: pwsh, args: ['-NoLogo', '-NoProfile'], windowsVerbatim: false, reason: 'same-shell'
  });
});

test('explicit native .exe avoids extra PowerShell wrapper', () => {
  assert.deepEqual(plan('git.exe --version'), {
    executable: git, args: ['--version'], windowsVerbatim: false, reason: 'explicit-native-exe'
  });
  assert.equal(plan('"C:\\Program Files\\Git\\cmd\\git.exe" -C D:\\Test rev-parse HEAD'), null,
    'quoted executable paths stay on the established shell validator path');
  assert.deepEqual(plan('node.exe --version').executable, exe);
});

test('bare unknown programs and PowerShell cmdlets preserve existing shell behavior', () => {
  for (const command of ['git status', 'node --version', 'Get-Date', 'Write-Output hello', 'dir', 'curl https://example.com', 'not_a_binary.exe']) {
    assert.equal(plan(command), null, command);
  }
});

test('quoted arguments and multiline scripts stay on original wrapper path', () => {
  const commands = [
    'powershell -Command "Write-Output hello"',
    'cmd.exe /c "echo hello"',
    'git.exe -C "D:\\Project Folder" status',
    'powershell\n-NoProfile',
    'powershell\r\n-NoProfile',
    '$git -C . status',
    'powershell; whoami',
    'powershell | Write-Output foo',
    'powershell && cmd.exe',
    'powershell > output.txt',
    'powershell & {Get-Date}',
    'powershell (Get-Date)',
    'powershell `Get-Date`',
    'powershell -Command {Get-Date}',
    'powershell -Command $(Get-Date)',
    'powershell "',
    '"powershell"evil -NoLogo',
    '"powershell" "-NoLogo"',
    '"C:\\Program Files\\PowerShell\\7\\pwsh.exe"\n-NoLogo',
    'powershell.exe -Command "a;b"',
    'powershell.exe -Command "a&b"',
  ];
  for (const command of commands) assert.equal(plan(command), null, JSON.stringify(command));
});

test('rejects mismatched executable resolution and unsupported platforms', () => {
  assert.equal(plan('powershell -NoLogo', ps, () => cmd), null);
  assert.equal(plan('powershell -NoLogo', ps, () => 'powershell.exe'), null);
  assert.equal(plan('powershell -NoLogo', ps, () => null), null);
  assert.equal(plan('powershell -NoLogo', ps, () => { throw Error('missing'); }), null);
  assert.equal(plan('powershell -NoLogo', ps, resolve, false), null);
  assert.equal(plan('git.exe --version', 'C:\\Tools\\bash.exe'), null);
  assert.equal(plan('cmd /Q', 'C:\\Tools\\bash.exe'), null);
  assert.equal(plan('"C:\\other\\powershell.exe" -NoLogo', ps, () => 'C:\\other\\powershell.exe'), null);
  assert.equal(plan('git.exe status', ps, () => 'C:\\Fake\\git.cmd'), null);
});

test('the literal parser handles empty and malformed commands without throwing', () => {
  for(const command of ['', '   ', '""', '"path', '"path"other', '\n', 'foo\u0000']) {
    assert.equal(parseLiteralWindowsInvocation(command), null, JSON.stringify(command));
  }
  assert.deepEqual(parseLiteralWindowsInvocation('git.exe --version'), {executable:'git.exe', args:['--version']});
  assert.equal(parseLiteralWindowsInvocation('"C:\\Program Files\\Git\\git.exe" --version'), null);
});

test('no Linux behavior change to getShellSpawnArgs', () => {
  assert.deepEqual(getShellSpawnArgs(process.execPath, 'hello there').useShellOption, process.execPath);
  assert.deepEqual(getShellSpawnArgs('bash', 'printf example').args, ['-l', '-c', 'printf example']);
});

test('512 deterministic malformed variants never take the optimized path', () => {
  const bad = [';', '|', '&', '$', '"', "'", '\n', '\r', '>', '<', '`', '(', ')', '{', '}', '[', ']', '!', '%', '\u0000'];
  for(let i=0;i<512;i++) {
    const marker=bad[i%bad.length];
    const command=`powershell -NoProfile ${marker}${String(i)}`;
    assert.equal(plan(command),null,JSON.stringify(command));
  }
});
