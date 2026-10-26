# Cursor Rules Setup - Windows
# Targets Windows PowerShell 5.1 (default `powershell.exe` from Install.bat)
# and PowerShell 7+ (`pwsh`). Avoid PS7-only APIs (e.g. 3-arg Join-Path).
$ErrorActionPreference = "Stop"
Set-Location $PSScriptRoot

Write-Host "=== Cursor Rules Setup ===" -ForegroundColor Cyan

function Get-VibeOpsPython {
    $cmd = Get-Command python3 -ErrorAction SilentlyContinue
    if (-not $cmd) { $cmd = Get-Command python -ErrorAction SilentlyContinue }
    if ($cmd) { return $cmd.Source }
    return $null
}

function Write-Utf8NoBom([string]$Path, [string]$Content) {
    # Windows PowerShell 5.1's `Set-Content -Encoding UTF8` writes a BOM
    # (EF BB BF). Cursor fails to parse mcp.json with a BOM, so the MCP
    # server never appears. Always write UTF-8 without BOM.
    $utf8 = New-Object System.Text.UTF8Encoding $false
    [System.IO.File]::WriteAllText($Path, $Content, $utf8)
}

function Refresh-PathFromMachine {
    $userPath = [System.Environment]::GetEnvironmentVariable("Path", "User")
    $machinePath = [System.Environment]::GetEnvironmentVariable("Path", "Machine")
    $extras = @(
        (Join-Path $env:USERPROFILE ".local\bin"),
        (Join-Path $env:USERPROFILE ".cargo\bin")
    )
    $env:Path = ($extras + @($userPath, $machinePath) | Where-Object { $_ }) -join ";"
}

if (-not (Get-Command specify -ErrorAction SilentlyContinue)) {
    if (-not (Get-Command uv -ErrorAction SilentlyContinue)) {
        Write-Host "Installing uv..."
        powershell -ExecutionPolicy ByPass -c "irm https://astral.sh/uv/install.ps1 | iex"
        Refresh-PathFromMachine
    }
    Write-Host "Installing Spec Kit..."
    uv tool install specify-cli --from git+https://github.com/github/spec-kit.git
    Refresh-PathFromMachine
}

# --- Ensure a stable per-machine Cursor client-id for MCP session identity ---
# The MCP server uses X-Cursor-Client-Id to recognise a reconnecting
# client so it can close the stale SSE session instead of accumulating
# zombies. Without this header, every Cursor reload stacks a new session
# against the per-project cap and eventually locks the user out with
# `too_many_sessions`. The ID is generated once per Windows user,
# stored at $env:USERPROFILE\.vibeops\cursor-client-id (ACL restricted
# to the current user), and never leaves this machine except as this
# header.
$vibeopsDir = Join-Path $env:USERPROFILE ".vibeops"
$cursorClientIdFile = Join-Path $vibeopsDir "cursor-client-id"
New-Item -ItemType Directory -Force -Path $vibeopsDir | Out-Null
if (-not (Test-Path $cursorClientIdFile) -or ((Get-Item $cursorClientIdFile).Length -eq 0)) {
    $newId = [guid]::NewGuid().ToString()
    Set-Content -Path $cursorClientIdFile -Value $newId -Encoding ASCII -NoNewline
    try {
        # Tighten ACL so other local users on a shared workstation can't
        # read the identifier (same threat model as the token file).
        $acl = New-Object System.Security.AccessControl.FileSecurity
        $acl.SetAccessRuleProtection($true, $false)
        $sysSid = New-Object System.Security.Principal.SecurityIdentifier "S-1-5-18"
        $admSid = New-Object System.Security.Principal.SecurityIdentifier "S-1-5-32-544"
        $userSid = ([System.Security.Principal.WindowsIdentity]::GetCurrent()).User
        foreach ($sid in @($sysSid, $admSid, $userSid)) {
            $rule = New-Object System.Security.AccessControl.FileSystemAccessRule(
                $sid, "FullControl", "Allow")
            $acl.AddAccessRule($rule)
        }
        Set-Acl -Path $cursorClientIdFile -AclObject $acl
    } catch {
        # Non-fatal - file is in a user-owned directory already.
    }
}
$cursorClientId = (Get-Content -Path $cursorClientIdFile -Raw).Trim()

# --- Auto-enable VibeOps MCP in Cursor (no manual toggle) ---
# Cursor loads servers from $HOME/.cursor/mcp.json at "user" scope, which
# bypasses the per-project "approve this MCP server?" prompt. We merge the
# VibeOps config carried in the ZIP (.cursor/mcp.install.json) into the
# user-global file. We deliberately do NOT ship a project-scope
# .cursor/mcp.json because Cursor shows scopes side-by-side and a duplicate
# entry causes "Disabled" / unknown_session failures.
$staleProjectMcp = ".cursor/mcp.json"
if ((Test-Path $staleProjectMcp) -and ((Get-Content $staleProjectMcp -Raw) -match '"vibeops"')) {
    Move-Item $staleProjectMcp "$staleProjectMcp.vibeops-backup" -Force
    Write-Host "  moved stale project-scope .cursor/mcp.json to .cursor/mcp.json.vibeops-backup"
}

$projectMcp = ".cursor/mcp.install.json"
if (Test-Path $projectMcp) {
    # --- Step 1: redeem the enrollment token (if present) ---
    # New-style ZIPs carry a one-time `_vibeopsEnrollment` payload that
    # the helper exchanges for a long-lived per-install access token.
    # If the helper isn't shipped (older ZIP) or exits with FALLBACK,
    # we keep using the legacy bearer that's still in mcp.install.json.
    # Failure is never fatal - the user always ends up with a working
    # `mcp.json`, just possibly via the legacy single-shared-bearer path.
    $enrollHelper = ".vibeops-helpers/enroll-mcp.py"
    $py = Get-VibeOpsPython
    # NOTE: do NOT combine Test-Path / Get-Command with bare -and/-or -
    # PowerShell left-associativity made `X -and python -or Y -and python3`
    # require python3 even when `python` alone was available, so enrollment
    # was skipped on typical Windows installs.
    if ((Test-Path $enrollHelper) -and $py) {
        try {
            $enrollOut = & $py $enrollHelper --install-json $projectMcp 2>&1
            if ($LASTEXITCODE -eq 0) {
                Write-Host "  enrollment: $enrollOut"
            } else {
                Write-Host "  enrollment: $enrollOut (continuing with legacy bearer)" -ForegroundColor Yellow
            }
        } catch {
            Write-Host "  enrollment: helper error '$_' (continuing with legacy bearer)" -ForegroundColor Yellow
        }
    } elseif ((Test-Path $enrollHelper) -and -not $py) {
        Write-Host "  enrollment: Python not found; continuing with legacy bearer" -ForegroundColor Yellow
    }

    $globalDir = Join-Path $env:USERPROFILE ".cursor"
    $globalMcp = Join-Path $globalDir "mcp.json"
    New-Item -ItemType Directory -Force -Path $globalDir | Out-Null

    $mergedViaPython = $false
    if ($py) {
        # Prefer the same Python merge the macOS installer uses - correct
        # JSON, atomic replace, no BOM, no ConvertTo-Json quirks.
        $mergePy = Join-Path $env:TEMP ("vibeops-merge-mcp-" + [guid]::NewGuid().ToString() + ".py")
        @"
import json, sys, os, shutil
proj_path, global_path, client_id = sys.argv[1], sys.argv[2], sys.argv[3]
with open(proj_path, encoding="utf-8") as f:
    proj = json.load(f)
try:
    with open(global_path, encoding="utf-8") as f:
        glob = json.load(f)
except Exception:
    glob = {}
glob.setdefault("mcpServers", {})
servers = proj.get("mcpServers", {})
if not servers:
    sys.exit(0)
registered = []
for name, cfg in servers.items():
    if name == "vibeops" and isinstance(cfg, dict) and "url" in cfg:
        headers = cfg.setdefault("headers", {})
        if client_id:
            headers["X-Cursor-Client-Id"] = client_id
    glob["mcpServers"][name] = cfg
    registered.append(name)
if not registered:
    sys.exit(0)
if os.path.exists(global_path):
    shutil.copyfile(global_path, global_path + ".vibeops-backup")
tmp_path = global_path + ".vibeops-tmp"
with open(tmp_path, "w", encoding="utf-8") as f:
    json.dump(glob, f, indent=2)
    f.write("\n")
os.replace(tmp_path, global_path)
print("registered " + ", ".join(registered) + " in " + global_path)
"@ | Set-Content -Path $mergePy -Encoding ASCII
        try {
            $mergeOut = & $py $mergePy $projectMcp $globalMcp $cursorClientId 2>&1
            if ($LASTEXITCODE -eq 0) {
                $mergedViaPython = $true
                Write-Host "  $mergeOut"
            } else {
                Write-Host "  python merge failed ($mergeOut); falling back to PowerShell" -ForegroundColor Yellow
            }
        } catch {
            Write-Host "  python merge error '$_'; falling back to PowerShell" -ForegroundColor Yellow
        } finally {
            Remove-Item -Force $mergePy -ErrorAction SilentlyContinue
        }
    }

    if (-not $mergedViaPython) {
        try {
            $proj = Get-Content $projectMcp -Raw -Encoding UTF8 | ConvertFrom-Json
        } catch {
            $proj = $null
        }
        if ($proj -and $proj.mcpServers) {
            $vibeopsEntry = $proj.mcpServers.vibeops
            if ($vibeopsEntry -and $cursorClientId) {
                if (-not $vibeopsEntry.PSObject.Properties.Match('headers').Count) {
                    $vibeopsEntry | Add-Member -NotePropertyName headers -NotePropertyValue ([pscustomobject]@{})
                }
                if ($vibeopsEntry.headers.PSObject.Properties.Match('X-Cursor-Client-Id').Count) {
                    $vibeopsEntry.headers.'X-Cursor-Client-Id' = $cursorClientId
                } else {
                    $vibeopsEntry.headers | Add-Member -NotePropertyName 'X-Cursor-Client-Id' -NotePropertyValue $cursorClientId
                }
            }

            if (Test-Path $globalMcp) {
                try {
                    $glob = Get-Content $globalMcp -Raw -Encoding UTF8 | ConvertFrom-Json
                    Copy-Item $globalMcp "$globalMcp.vibeops-backup" -Force
                } catch {
                    $glob = [pscustomobject]@{ mcpServers = [pscustomobject]@{} }
                }
            } else {
                $glob = [pscustomobject]@{ mcpServers = [pscustomobject]@{} }
            }

            if (-not $glob.PSObject.Properties.Match('mcpServers').Count) {
                $glob | Add-Member -NotePropertyName mcpServers -NotePropertyValue ([pscustomobject]@{})
            }
            $registered = @()
            foreach ($prop in $proj.mcpServers.PSObject.Properties) {
                if ($glob.mcpServers.PSObject.Properties.Match($prop.Name).Count) {
                    $glob.mcpServers.($prop.Name) = $prop.Value
                } else {
                    $glob.mcpServers | Add-Member -NotePropertyName $prop.Name -NotePropertyValue $prop.Value
                }
                $registered += $prop.Name
            }

            Write-Utf8NoBom -Path $globalMcp -Content (($glob | ConvertTo-Json -Depth 10) + [Environment]::NewLine)
            Write-Host "  registered $($registered -join ', ') in $globalMcp"
        }
    }

    if (Test-Path $globalMcp) {
        # Tighten ACLs: this file contains a Bearer token granting the agent
        # access to this project's Key Vault credentials via the MCP server.
        # Default Windows ACLs grant Authenticated Users read access, which
        # on a shared workstation would let other local users read the token.
        # Replace the ACL with: SYSTEM Full, Administrators Full, current user
        # Full - and remove inherited entries.
        try {
            $acl = New-Object System.Security.AccessControl.FileSecurity
            $acl.SetAccessRuleProtection($true, $false)
            $sysSid = New-Object System.Security.Principal.SecurityIdentifier "S-1-5-18"
            $admSid = New-Object System.Security.Principal.SecurityIdentifier "S-1-5-32-544"
            $userSid = ([System.Security.Principal.WindowsIdentity]::GetCurrent()).User
            foreach ($sid in @($sysSid, $admSid, $userSid)) {
                $rule = New-Object System.Security.AccessControl.FileSystemAccessRule(
                    $sid, "FullControl", "Allow")
                $acl.AddAccessRule($rule)
            }
            Set-Acl -Path $globalMcp -AclObject $acl
            Write-Host "  ACL restricted to current user on $globalMcp"
        } catch {
            Write-Host "  could not tighten ACL on $globalMcp : $_" -ForegroundColor Yellow
        }
    }
}

# --- Activate the shipped pre-commit secret scanner ---
# Same rationale as the macOS script: don't force `git init`, but if a
# repo is already in place, wire the hook path to the folder we ship so
# .env / client_secret commits are blocked by default.
if ((Test-Path ".git") -and (Test-Path ".git-hooks")) {
    try {
        & git config core.hooksPath .git-hooks
        Write-Host "  activated pre-commit secret scanner (.git-hooks/pre-commit)"
    } catch {
        Write-Host "  could not activate pre-commit hook: $_" -ForegroundColor Yellow
    }
}

Write-Host "Opening Cursor..."
$prevEap = $ErrorActionPreference
$ErrorActionPreference = "Continue"
try {
    if (Get-Command cursor -ErrorAction SilentlyContinue) {
        & cursor .
    } else {
        Start-Process "cursor" -ArgumentList "." -ErrorAction SilentlyContinue
        if (-not $?) {
            Write-Host "Cursor CLI not found on PATH. Open this folder in Cursor manually." -ForegroundColor Yellow
        }
    }
} catch {
    Write-Host "Could not launch Cursor automatically. Open this folder in Cursor manually." -ForegroundColor Yellow
} finally {
    $ErrorActionPreference = $prevEap
}

if (Test-Path $projectMcp) {
    Write-Host ""
    Write-Host "=================================================================" -ForegroundColor Green
    Write-Host "  VibeOps MCP server is registered in Cursor (user-global scope)." -ForegroundColor Green
    Write-Host ""
    Write-Host "  If the agent can't find it, reload Cursor:"
    Write-Host "    Ctrl+Shift+P  ->  'Developer: Reload Window'"
    Write-Host ""
    Write-Host "  To rotate / revoke the token, use the project page on the"
    Write-Host "  VibeOps platform and re-download the ZIP."
    Write-Host "=================================================================" -ForegroundColor Green
    Write-Host ""
}

Write-Host "Done!" -ForegroundColor Green
