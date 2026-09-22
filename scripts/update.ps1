<#
YouTube Chushutu - updater (Windows). Launched by update.bat.

Brings an existing install up to the latest release:
  1. downloads the current source ZIP from GitHub and overlays it on this
     folder (the virtual environment, backend\.env and your downloads are
     left alone),
  2. upgrades yt-dlp together with its challenge-solver script and installs
     the Deno JavaScript runtime into the virtual environment,
  3. says what to do next.

Keep every message ASCII: the console this runs in is not guaranteed to
render anything else.
#>
param(
    [string]$ProjectDir = "",
    [string]$Branch = "main"
)

$ErrorActionPreference = "Stop"
$Repo = "zunovia/youtube_chushutu-01"

function Step($msg) { Write-Host ""; Write-Host "==> $msg" -ForegroundColor Cyan }
function Ok($msg)   { Write-Host "[OK] $msg" -ForegroundColor Green }
function Warn($msg) { Write-Host "[WARN] $msg" -ForegroundColor Yellow }
function Fail($msg) {
    Write-Host ""
    Write-Host "[ERROR] $msg" -ForegroundColor Red
    Write-Host ""
    Read-Host "Press Enter to close" | Out-Null
    exit 1
}

try {
    # --- Locate the install --------------------------------------------------
    if (-not $ProjectDir) {
        # Running as <install>\scripts\update.ps1; a copy in %TEMP% has no such parent.
        $candidate = Split-Path -Parent $PSScriptRoot
        if (Test-Path (Join-Path $candidate "start.bat")) { $ProjectDir = $candidate }
        else { $ProjectDir = (Get-Location).Path }
    }
    # GetFullPath folds the trailing \. that update.bat passes (it avoids a
    # trailing backslash escaping the closing quote) so the venv path below
    # compares equal to what a running python.exe reports.
    $ProjectDir = [System.IO.Path]::GetFullPath((Resolve-Path $ProjectDir).Path).TrimEnd('\')
    if (-not (Test-Path (Join-Path $ProjectDir "backend\pyproject.toml"))) {
        Fail "This does not look like a YouTube Chushutu folder:`n  $ProjectDir`nPut update.bat next to start.bat and run it from there."
    }
    $Backend    = Join-Path $ProjectDir "backend"
    $Venv       = Join-Path $Backend ".venv"
    $VenvPython = Join-Path $Venv "Scripts\python.exe"

    Write-Host ""
    Write-Host "========================================="
    Write-Host "  YouTube Chushutu Updater"
    Write-Host "========================================="
    Write-Host "  Folder: $ProjectDir"

    # --- Refuse while the server runs ----------------------------------------
    # pip cannot replace files Windows has open, and a half-replaced yt-dlp is
    # worse than an old one.
    $running = Get-Process -Name python, pythonw -ErrorAction SilentlyContinue |
        Where-Object { $_.Path -and $_.Path.StartsWith($Venv, [System.StringComparison]::OrdinalIgnoreCase) }
    if ($running) {
        Fail "The server is still running (the start.bat window).`nClose that window first, then run update.bat again."
    }

    # --- Download the latest source -----------------------------------------
    Step "Downloading the latest version ($Branch)"
    [Net.ServicePointManager]::SecurityProtocol = [Net.ServicePointManager]::SecurityProtocol -bor [Net.SecurityProtocolType]::Tls12
    $Work = Join-Path $env:TEMP ("ytc-update-" + [guid]::NewGuid().ToString("N"))
    New-Item -ItemType Directory -Path $Work | Out-Null
    $Zip = Join-Path $Work "src.zip"
    $Url = "https://github.com/$Repo/archive/refs/heads/$Branch.zip"
    try {
        Invoke-WebRequest -UseBasicParsing -Uri $Url -OutFile $Zip
    } catch {
        Fail "Download failed: $Url`n$($_.Exception.Message)`nCheck the internet connection and try again."
    }
    Expand-Archive -Path $Zip -DestinationPath $Work -Force
    $SrcDir = Get-ChildItem -Path $Work -Directory | Where-Object { $_.Name -ne "__MACOSX" } | Select-Object -First 1
    if (-not $SrcDir) { Fail "The downloaded archive was empty." }
    $Src = $SrcDir.FullName
    Ok "Downloaded"

    # --- Overlay the files ---------------------------------------------------
    Step "Updating program files (settings and downloaded videos are untouched)"
    # These hold only program code, so they are replaced wholesale: a stale
    # file left behind (an old extension script, a removed module) can break
    # things in ways that are hard to see.
    foreach ($dir in @("backend\app", "backend\tests", "extension", "scripts")) {
        $dest = Join-Path $ProjectDir $dir
        $from = Join-Path $Src $dir
        if (-not (Test-Path $from)) { continue }
        if (Test-Path $dest) { Remove-Item -Recurse -Force $dest }
        Copy-Item -Recurse -Force $from $dest
    }
    foreach ($file in @("start.bat", "start.sh", "update.sh", "README.md", ".gitattributes", ".gitignore",
                        "backend\run.py", "backend\pyproject.toml")) {
        $from = Join-Path $Src $file
        if (Test-Path $from) { Copy-Item -Force $from (Join-Path $ProjectDir $file) }
    }
    # update.bat is the file that launched us. CMD reads a batch file as it
    # runs, so touch it only when it really changed - and compare without
    # line endings: a copy downloaded on its own is LF, the ZIP's is CRLF, and
    # replacing one with the other shifts CMD's read offset into garbage.
    $newBat = Join-Path $Src "update.bat"
    $oldBat = Join-Path $ProjectDir "update.bat"
    if (Test-Path $newBat) {
        $same = $false
        if (Test-Path $oldBat) {
            $a = (Get-Content -Raw $newBat) -replace "`r", ""
            $b = (Get-Content -Raw $oldBat) -replace "`r", ""
            $same = ($a -eq $b)
        }
        if (-not $same) { Copy-Item -Force $newBat $oldBat }
    }
    Remove-Item -Recurse -Force $Work -ErrorAction SilentlyContinue
    Ok "Files updated"

    # --- Python packages -----------------------------------------------------
    # A venv is only a pointer to the Python that created it. Uninstalling or
    # upgrading that Python leaves python.exe in place but unable to start
    # ("did not find executable at C:\Python3xx\python.exe"), so existence is
    # not enough: run it.
    $venvOk = $false
    if (Test-Path $VenvPython) {
        try {
            # --version needs no quoting. Start-Process joins -ArgumentList with
            # spaces and no quotes, so '-c "import sys"' arrived as -c import sys,
            # failed with a SyntaxError, and rebuilt a healthy venv on every run.
            $probe = Start-Process -FilePath $VenvPython -ArgumentList "--version" -Wait -PassThru -NoNewWindow
            $venvOk = ($probe.ExitCode -eq 0)
        } catch { $venvOk = $false }
        if (-not $venvOk) {
            Warn "The virtual environment cannot start (the Python it was built with was removed or moved)."
            Warn "Rebuilding it - this takes a little longer than a normal update."
            Remove-Item -Recurse -Force $Venv
        }
    }
    if (-not $venvOk) {
        Step "Creating the virtual environment"
        # 'py' first: on Windows a bare 'python' may be the Microsoft Store
        # stub, which exists on PATH but only opens the Store. Prove each
        # candidate by running it.
        $py = $null
        foreach ($name in @("py", "python", "python3")) {
            $cmd = Get-Command $name -ErrorAction SilentlyContinue
            if (-not $cmd) { continue }
            try {
                $v = Start-Process -FilePath $cmd.Source -ArgumentList "--version" -Wait -PassThru -NoNewWindow
                if ($v.ExitCode -eq 0) { $py = $cmd.Source; break }
            } catch { }
        }
        if (-not $py) {
            Fail "Python was not found on this PC (it may have been uninstalled).`nInstall it from https://www.python.org/downloads/ - tick 'Add Python to PATH' -`nthen run update.bat again."
        }
        Write-Host "  using $py"
        & $py -m venv $Venv
        if (-not (Test-Path $VenvPython)) { Fail "Could not create the virtual environment." }
    }

    Step "Upgrading yt-dlp and installing the Deno runtime (a few minutes; Deno is about 40 MB)"
    & $VenvPython -m pip install --upgrade pip --quiet --disable-pip-version-check
    & $VenvPython -m pip install --upgrade -e $Backend --quiet --disable-pip-version-check
    if ($LASTEXITCODE -ne 0) { Fail "pip failed while installing the backend. Scroll up for the error." }
    # [default] carries yt-dlp-ejs, the solver script that must match yt-dlp.
    & $VenvPython -m pip install --upgrade "yt-dlp[default]" --quiet --disable-pip-version-check
    if ($LASTEXITCODE -ne 0) { Fail "pip failed while upgrading yt-dlp. Scroll up for the error." }
    # Best effort: the wheel exists only for 64-bit machines.
    & $VenvPython -m pip install --upgrade deno --quiet --disable-pip-version-check
    if ($LASTEXITCODE -ne 0) {
        Warn "Deno could not be installed by pip (no build for this machine?)."
        Warn "Installing Node.js 22 or newer from https://nodejs.org works as an alternative."
    }
    Ok "Packages updated"

    # --- Report --------------------------------------------------------------
    Step "Installed versions"
    Push-Location $Backend
    & $VenvPython -c "import sys, shutil; sys.path.insert(0, '.'); import yt_dlp; from app.services.extractor import detect_js_runtime; rt = detect_js_runtime(); print('  yt-dlp : ' + yt_dlp.version.__version__); print('  Deno   : ' + (rt.summary if rt else 'NOT FOUND - YouTube downloads will fail')); print('  ffmpeg : ' + (shutil.which('ffmpeg') or 'NOT FOUND - MP3 and 1080p+ unavailable'))"
    Pop-Location

    Write-Host ""
    Write-Host "========================================="
    Write-Host "  Update complete" -ForegroundColor Green
    Write-Host "========================================="
    Write-Host ""
    Write-Host "Next:"
    Write-Host "  1. Start the server:  $ProjectDir\start.bat"
    Write-Host "  2. Reload the Chrome extension: open chrome://extensions and click the"
    Write-Host "     reload button (circular arrow) on the 'YouTube Chushutu' card."
    Write-Host "  3. Press F5 on the YouTube page."
    Write-Host ""
    Read-Host "Press Enter to close" | Out-Null
    exit 0
} catch {
    Fail "Unexpected error: $($_.Exception.Message)`n$($_.ScriptStackTrace)"
}
