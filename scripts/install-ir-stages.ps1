<#
.SYNOPSIS
  Installs the IR stages built by mods\additive\build.ps1 into the game's ~mods folder so that they sit next to every
  other installed stage mod (docs/other-mods.md), or checks / removes that install.

  ACR shows one stage list: each menu table (DT_Levels, DT_Tracks, ...) comes from the highest-priority pak that has it.
  Stage mods ship whole copies of these tables, so a mod that ignores the others hides them. This script stacks instead:

  1. Finds every non-vanilla pak in Paks\ and Paks\~mods\ (except this prefix's own) that carries a menu table.
  2. Per table, takes the copy that currently wins (highest pak order, see Get-PakOrder) as the base.
  3. Builds this prefix's registry from that base plus the IR stages, named <prefix>_registry_<n>_P with n above every
     other mod's, and verifies that every base row is unchanged and only the IR stages' rows were added.
  4. Links (or copies) the registry and the stage containers into ~mods and records what it stacked on
     (work\acr\install\state.json).

  Other mods' files are only read. Re-run after installing, updating or removing another stage mod, or after a game
  update: -Check tells whether the stacked-on tables changed since the last install.

.PARAMETER Stages     spec folder or files of the IR stages (default work\acr\specs-ir); their containers must be built
.PARAMETER Prefix     container file prefix (default $env:ACRXS_PREFIX, else zz_acrmg); only <prefix>_* files are written or removed
.PARAMETER Check      report whether the install is current (no changes)
.PARAMETER Uninstall  remove this prefix's files from ~mods, and report higher-priority menu tables that still list its stages
.PARAMETER DryRun     install into work\acr\install\dry-run-mods instead of the game's ~mods
#>
param(
    [string[]]$Stages,
    [string]$Prefix = $(if ($env:ACRXS_PREFIX) { $env:ACRXS_PREFIX } else { 'zz_acrmg' }),
    [string]$Game = $(if ($env:ACR_GAME_DIR) { $env:ACR_GAME_DIR } else { 'C:\Program Files (x86)\Steam\steamapps\common\Assetto Corsa Rally' }),
    [string]$Retoc,
    [switch]$Check,
    [switch]$Uninstall,
    [switch]$DryRun,
    [switch]$Copy
)
$ErrorActionPreference = 'Stop'
$root = Split-Path $PSScriptRoot
$workRoot = if ($env:ACRXS_WORK) { $env:ACRXS_WORK } else { Join-Path $root 'work' }   # ACRXS_WORK: work folder elsewhere (on the game's drive)
if ($Prefix -notmatch '^[a-z][a-z0-9_]*$') { throw "-Prefix must be lowercase letters, digits and _: $Prefix" }
if (-not $Retoc) { $Retoc = Join-Path $workRoot 'bin\bin\retoc.exe' }
if (-not (Test-Path $Retoc)) { throw "retoc not found at $Retoc" }
if (-not $Stages) { $Stages = @(Join-Path $workRoot 'acr\specs-ir') }
$Stages = @($Stages | % { $_ -split ',' } | ? { $_ })

$paksDir = Join-Path $Game 'acr\Content\Paks'
if (-not (Test-Path $paksDir)) { throw "no ACR install at $Game (set -Game or ACR_GAME_DIR)" }
$installDir = Join-Path $workRoot 'acr\install'
$mods = if ($DryRun) { Join-Path $installDir 'dry-run-mods' } else { Join-Path $paksDir '~mods' }
$statePath = Join-Path $installDir 'state.json'
$work = Join-Path $workRoot 'acr\additive'
$dist = Join-Path $work 'dist'
$tool = Join-Path $workRoot 'bin\acr-additive\acr-additive.exe'
New-Item -ItemType Directory -Force $installDir | Out-Null

function Run([string]$exe) {
    & $exe @args 2>&1 | Out-Host
    if ($LASTEXITCODE -ne 0) { throw "$exe failed ($LASTEXITCODE)" }
}

# The menu tables a stage registry overrides (acr-additive Registry.AllTables, the superset).
$Tables = @(
    'Common/DT_Levels', 'TrackSelection/DT_Tracks', 'TrackSelection/DT_TracksVariants', 'TrackSelection/DT_TracksLocations',
    'TrackSelection/DT_TracksTextures', 'TrackSelection/DT_TracksLocationsBackgrounds', 'TrackSelection/DT_TracksLocationsLogos'
)
function TablePath([string]$t) { "acr/Content/Data/Database/Main/$t.uasset" }

# UE's pak order for paks under the project's Content folder (FPakPlatformFile::GetPakOrderFromPakFilePath): a *_P patch
# gets +(n+1)*100 for *_<n>_P (n = 1 for a plain *_P); higher order wins. Equal orders have no defined winner.
function Get-PakNumber([string]$name) {
    if ($name -match '_(\d+)_P$') { return [int]$Matches[1] }
    if ($name -match '_P$') { return 1 }
    return -1
}
function Get-PakOrder([string]$name) { ((Get-PakNumber $name) + 1) * 100 }

function Test-Vanilla([string]$name) { $name -match '^(global|pakchunk\d+(optional)?-Windows)$' }

# Every non-vanilla container (except ours) with the menu tables it carries.
function Get-Registries {
    $found = @()
    foreach ($u in Get-ChildItem $paksDir -Recurse -File -Filter '*.utoc') {
        $name = $u.BaseName
        if ((Test-Vanilla $name) -or $name -like "${Prefix}_*") { continue }
        $list = & $Retoc list --path $u.FullName 2>$null
        $has = @($Tables | ? { $p = TablePath $_; $list | Select-String -SimpleMatch $p -Quiet })
        if (-not $has) { continue }
        $found += [pscustomobject]@{
            Name = $name; Utoc = $u.FullName; Number = Get-PakNumber $name; Order = Get-PakOrder $name; Tables = $has
            # ticks, not a date string: ConvertFrom-Json would turn an ISO string back into a DateTime and never compare equal
            Size = (Get-ChildItem ($u.FullName -replace '\.utoc$', '.ucas')).Length; Time = $u.LastWriteTimeUtc.Ticks
        }
    }
    return $found
}

# Per table: the container whose copy the game uses now (null = vanilla).
function Get-Winners($registries) {
    $w = [ordered]@{}
    foreach ($t in $Tables) {
        $c = @($registries | ? { $t -in $_.Tables } | Sort-Object Order, Name -Descending)
        if (-not $c) { $w[$t] = $null; continue }
        if ($c.Count -gt 1 -and $c[0].Order -eq $c[1].Order) {
            Write-Warning "$t is in $($c[0].Name) and $($c[1].Name) with the same pak order; the game's choice between them is not defined (using $($c[0].Name))"
        }
        $w[$t] = $c[0]
    }
    return $w
}

function Read-State { if (Test-Path $statePath) { Get-Content $statePath -Raw | ConvertFrom-Json } else { $null } }

function Show-Registries($registries, $winners) {
    if (-not $registries) { Write-Host '  no other stage mods with menu tables: stacking on vanilla'; return }
    foreach ($r in $registries | Sort-Object Order, Name) {
        $wins = @($Tables | ? { $winners[$_] -and $winners[$_].Name -eq $r.Name } | % { ($_ -split '/')[-1] })
        Write-Host ("  {0,-40} order {1,5}  tables {2}{3}" -f $r.Name, $r.Order, $r.Tables.Count, $(if ($wins) { "  (base for $($wins -join ', '))" } else { '' }))
    }
}

# Content root of the IR stages (/Game/<Root>/...), from the specs' Level.
function Get-Specs {
    $files = @($Stages | % { if (Test-Path $_ -PathType Container) { Get-ChildItem $_ -Filter *.json | % FullName } else { (Resolve-Path $_).Path } })
    if (-not $files) { throw "no stage specs in $($Stages -join ', ')" }
    return @($files | % { [pscustomobject]@{ File = $_; Spec = (Get-Content $_ -Raw | ConvertFrom-Json) } })
}

# Stage ids of ours listed in a container's DT_Levels (a mod that stacked on top of us copies our rows).
function Get-OurRowsIn($registry, [string[]]$roots) {
    $view = Join-Path $installDir "peek\$($registry.Name)"
    $vp = Join-Path $view 'acr\Content\Paks'
    Remove-Item -Recurse -Force $view -ErrorAction SilentlyContinue
    New-Item -ItemType Directory -Force $vp | Out-Null
    Get-ChildItem $paksDir -File | ? { Test-Vanilla $_.BaseName } | % { New-Item -ItemType HardLink -Path (Join-Path $vp $_.Name) -Target $_.FullName | Out-Null }
    Get-ChildItem (Split-Path $registry.Utoc) -File -Filter "$($registry.Name).*" | % { New-Item -ItemType HardLink -Path (Join-Path $vp $_.Name) -Target $_.FullName | Out-Null }
    $out = Join-Path $view 'levels.json'
    & $tool db-rows --table /Game/Data/Database/Main/Common/DT_Levels --out $out --game $view 2>&1 | Out-Null
    if ($LASTEXITCODE -ne 0) { Write-Warning "could not read DT_Levels of $($registry.Name)"; return @() }
    $rows = (Get-Content $out -Raw | ConvertFrom-Json -AsHashtable)
    if ($rows.ContainsKey('Rows')) { $rows = $rows['Rows'] }
    $hits = @(foreach ($k in $rows.Keys) {
        $path = [string]$rows[$k].AssetPathName
        if (@($roots | ? { $path.StartsWith("/Game/$_/", [StringComparison]::OrdinalIgnoreCase) })) { $k }
    })
    Remove-Item -Recurse -Force $view -ErrorAction SilentlyContinue
    return $hits
}

function Assert-GameClosed {
    if ($DryRun) { return }
    if (Get-Process -Name 'acr', 'acr-Win64-Shipping' -ErrorAction SilentlyContinue) { throw 'Assetto Corsa Rally is running: close it first' }
}

# ---------------------------------------------------------------- check
if ($Check) {
    $state = Read-State
    if (-not $state) { Write-Host "not installed with this script (no $statePath)"; return }
    $regs = @(Get-Registries)
    $winners = Get-Winners $regs
    Write-Host "installed $($state.installed_at): $($state.registry) + $(@($state.ids).Count) stage(s) ($($state.ids -join ', '))"
    Show-Registries $regs $winners
    $changes = @()
    foreach ($b in $state.base) {
        $now = $winners[$b.table]
        $was = $b.container
        if (-not $now -and -not $was) { continue }
        if (-not $now -or -not $was -or $now.Name -ne $was) { $changes += "$($b.table): base was $(if ($was) { $was } else { 'vanilla' }), now $(if ($now) { $now.Name } else { 'vanilla' })"; continue }
        if ($now.Size -ne [int64]$b.size -or $now.Time -ne [int64]$b.time) { $changes += "$($b.table): $was changed since the install" }
    }
    $above = @($regs | ? { $_.Number -ge $state.priority })
    foreach ($r in $above) { $changes += "$($r.Name) (pak number $($r.Number)) is at or above ours ($($state.priority)): its tables now win over ours" }
    $present = @(Get-ChildItem $mods -File -Filter "${Prefix}_*" -ErrorAction SilentlyContinue).Count
    if ($present -eq 0) { $changes += "no ${Prefix}_* files in $mods" }
    if ($changes) {
        Write-Host 'out of date:' -ForegroundColor Yellow
        $changes | % { Write-Host "  - $_" }
        Write-Host "re-run scripts\install-ir-stages.ps1 to rebuild the registry on the current state"
        exit 3
    }
    Write-Host 'up to date: the stacked-on menu tables are unchanged' -ForegroundColor Green
    return
}

# ---------------------------------------------------------------- uninstall
if ($Uninstall) {
    Assert-GameClosed
    $state = Read-State
    $ours = @(Get-ChildItem $mods -File -Filter "${Prefix}_*" -ErrorAction SilentlyContinue)
    $ours | Remove-Item -Force
    Write-Host "removed $($ours.Count) ${Prefix}_* file(s) from $mods"
    # a mod installed after us that stacked on our tables still lists our stages, whose containers are now gone
    $roots = @($(if ($state -and $state.roots) { $state.roots } else { Get-Specs | % { if ($_.Spec.Level -match '^/Game/([^/]+)/') { $Matches[1] } } }) | Sort-Object -Unique)
    $stale = @()
    foreach ($r in Get-Registries) {
        $hits = @(Get-OurRowsIn $r $roots)
        if ($hits) { $stale += "$($r.Name) still lists $($hits -join ', ')" }
    }
    if ($stale) {
        Write-Warning 'other stage mods copied these stages into their menu tables; the menu will still show them, without their files:'
        $stale | % { Write-Host "  - $_" }
        Write-Host '  re-install those mods so they rebuild their tables without these stages'
    }
    if (Test-Path $statePath) { Remove-Item $statePath }
    Write-Host 'uninstalled'
    return
}

# ---------------------------------------------------------------- install
Assert-GameClosed
if (-not $env:ACR_USMAP -and -not (Test-Path 'C:\Dumper-7\5.6.1-0+UE5-acr\Mappings\5.6.1-0+UE5-acr.usmap')) {
    $usmap = & (Join-Path $workRoot 'bin\bin\acr-mappings.exe') path --game $Game 2>$null
    if ($LASTEXITCODE -eq 0 -and $usmap) { $env:ACR_USMAP = ($usmap | Select-Object -Last 1).Trim() }
}
$env:ACR_GAME_DIR = $Game
$specs = Get-Specs
$roots = @($specs | % { if ($_.Spec.Level -match '^/Game/([^/]+)/') { $Matches[1] } } | Sort-Object -Unique)
foreach ($s in $specs) {
    $c = Join-Path $dist "${Prefix}_s_$($s.Spec.Id.ToLowerInvariant())_P.utoc"
    if (-not (Test-Path $c)) { throw "$($s.Spec.Id): no stage container $c - build it first (mods\additive\build.ps1 -Stages ... -Prefix $Prefix)" }
}

Write-Host "stage mods with menu tables in $paksDir"
$regs = @(Get-Registries)
$winners = Get-Winners $regs
Show-Registries $regs $winners
foreach ($r in $regs) {
    $hits = @(Get-OurRowsIn $r $roots)
    if ($hits) { throw "$($r.Name) already lists stages under /Game/$($roots -join ', /Game/') ($($hits -join ', ')): a mod stacked on an earlier install of ours. Uninstall it or reinstall it after removing ours." }
}
$priority = [math]::Max(1, ((@($regs | % Number) + 0) | Measure-Object -Maximum).Maximum + 1)
$regName = "${Prefix}_registry_${priority}_P"

# base tables: vanilla's, with each table some mod overrides replaced by the winning copy
$vanillaLegacy = Join-Path $work 'legacy'
if (-not (Test-Path (Join-Path $vanillaLegacy 'acr\Content\Data\Database\Main'))) { throw "no vanilla tables in $vanillaLegacy - run mods\additive\build.ps1 first" }
$base = Join-Path $installDir 'base'
Remove-Item -Recurse -Force $base -ErrorAction SilentlyContinue
& robocopy (Join-Path $vanillaLegacy 'acr\Content\Data\Database\Main') (Join-Path $base 'acr\Content\Data\Database\Main') /E /NFL /NDL /NJH /NJS /nc /ns /np | Out-Null
if ($LASTEXITCODE -ge 8) { throw 'copying the vanilla tables failed' }
foreach ($g in @($Tables | ? { $winners[$_] } | Group-Object { $winners[$_].Name })) {
    $r = $winners[$g.Group[0]]
    $tmp = Join-Path $installDir "extract\$($r.Name)"
    Remove-Item -Recurse -Force $tmp -ErrorAction SilentlyContinue
    New-Item -ItemType Directory -Force "$tmp\in" | Out-Null
    Get-ChildItem $paksDir -File -Filter 'global.*' | % { New-Item -ItemType HardLink -Path (Join-Path "$tmp\in" $_.Name) -Target $_.FullName | Out-Null }
    Get-ChildItem (Split-Path $r.Utoc) -File -Filter "$($r.Name).*" | % { New-Item -ItemType HardLink -Path (Join-Path "$tmp\in" $_.Name) -Target $_.FullName | Out-Null }
    Run $Retoc to-legacy --version UE5_6 --no-shaders @($g.Group | % { '--filter'; "Data/Database/Main/$_" }) "$tmp\in" "$tmp\out"
    foreach ($t in $g.Group) {
        foreach ($ext in '.uasset', '.uexp') {
            $src = Join-Path "$tmp\out" ("acr\Content\Data\Database\Main\$t$ext" -replace '/', '\')
            if (-not (Test-Path $src)) { throw "$($r.Name): $t$ext not extracted" }
            Copy-Item $src (Join-Path $base ("acr\Content\Data\Database\Main\$t$ext" -replace '/', '\')) -Force
        }
    }
    Remove-Item -Recurse -Force $tmp
}

# base view for -Verify: the vanilla paks plus one container with the base tables (exactly what our registry sits on)
$baseView = Join-Path $installDir 'base-view'
$bvPaks = Join-Path $baseView 'acr\Content\Paks'
Remove-Item -Recurse -Force $baseView -ErrorAction SilentlyContinue
New-Item -ItemType Directory -Force $bvPaks | Out-Null
Get-ChildItem $paksDir -File | ? { Test-Vanilla $_.BaseName } | % { New-Item -ItemType HardLink -Path (Join-Path $bvPaks $_.Name) -Target $_.FullName | Out-Null }
$baseTables = Join-Path $installDir 'base-tables'
Remove-Item -Recurse -Force $baseTables -ErrorAction SilentlyContinue
foreach ($t in $Tables) {
    foreach ($ext in '.uasset', '.uexp') {
        $rel = "acr\Content\Data\Database\Main\$t$ext" -replace '/', '\'
        New-Item -ItemType Directory -Force (Split-Path (Join-Path $baseTables $rel)) | Out-Null
        Copy-Item (Join-Path $base $rel) (Join-Path $baseTables $rel)
    }
}
Run $Retoc to-zen --version UE5_6 $baseTables (Join-Path $bvPaks 'pakchunk98-InstalledBase_P.utoc')

Write-Host "building $regName on that base"
$buildArgs = @('-NoProfile', '-File', (Join-Path $root 'mods\additive\build.ps1'), '-Stages', (($specs | % File) -join ','), '-RegistryOnly', '-SkipToolBuild',
    '-Prefix', $Prefix, '-RegistryBase', $base, '-RegistryPriority', $priority, '-VerifyBase', $baseView, '-Game', $Game, '-Verify')
& pwsh @buildArgs | Out-Host
if ($LASTEXITCODE -ne 0) { throw 'registry build / verify failed: nothing was installed' }

# install: drop our old files, link the registry and the specs' stage containers
New-Item -ItemType Directory -Force $mods | Out-Null
Get-ChildItem $mods -File -Filter "${Prefix}_*" | Remove-Item -Force
$files = @(Get-ChildItem $dist -File -Filter "$regName.*")
foreach ($s in $specs) { $files += Get-ChildItem $dist -File -Filter "${Prefix}_s_$($s.Spec.Id.ToLowerInvariant())_P.*" }
$sameVolume = (Split-Path -Qualifier (Resolve-Path $dist).Path) -eq (Split-Path -Qualifier (Resolve-Path $mods).Path)
$mode = 'copied'
if ($sameVolume -and -not $Copy) {
    $mode = 'hard-linked'
    try { foreach ($f in $files) { New-Item -ItemType HardLink -Path (Join-Path $mods $f.Name) -Target $f.FullName | Out-Null } }
    catch {
        Write-Warning "hard link failed ($($_.Exception.Message)); copying"
        $mode = 'copied'
        $files | % { Remove-Item (Join-Path $mods $_.Name) -Force -ErrorAction SilentlyContinue }
        $files | Copy-Item -Destination $mods -Force
    }
}
else { $files | Copy-Item -Destination $mods -Force }

[ordered]@{
    installed_at = (Get-Date).ToString('o'); game = $Game; mods = $mods; prefix = $Prefix; registry = $regName; priority = $priority
    roots = $roots; ids = @($specs | % { $_.Spec.Id })
    base = @($Tables | % { $w = $winners[$_]; [ordered]@{ table = $_; container = $(if ($w) { $w.Name } else { $null }); size = $(if ($w) { $w.Size } else { $null }); time = $(if ($w) { $w.Time } else { $null }) } })
} | ConvertTo-Json -Depth 5 | Set-Content $statePath -Encoding utf8

$mb = [math]::Round(($files | Measure-Object Length -Sum).Sum / 1MB)
Write-Host "installed ($mode) $regName + $(@($specs).Count) stage container(s), $mb MB, into $mods" -ForegroundColor Green
Write-Host "stages: $(($specs | % { $_.Spec.Id }) -join ', ')"
Write-Host 'Re-run this script after installing, updating or removing another stage mod, or after a game update (-Check tells when).'
Write-Host 'Remove: scripts\install-ir-stages.ps1 -Uninstall'
