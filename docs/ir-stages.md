# IR stages: building stages from non-DR2 Stage IRs

How to turn a Stage IR v2 folder made by another producer (e.g. ACRMapGenerator, built from open elevation and map
data) into an ACR stage with its own menu entry, without any DR2 data. The IR contract (which `stage.json` keys are
read) is in docs/stage-ir.md, "IRs from other producers". Living next to other stage mods is in docs/other-mods.md.

The DR2 path (`config/stages.toml`, `scripts/gen-stage-specs.ps1`, the launcher) is unchanged by any of this.

## One-time setup

- .NET 10 SDK, PowerShell 7, Rust (rustup) and git, as in CONTRIBUTING.md.
- The work folder must be **on the game's drive**: the vanilla view is built from hard links to the game's paks. It is
  `work\` in the checkout unless `$env:ACRXS_WORK` points elsewhere (e.g. `E:\acr_work` when the checkout is on C:).
  Every path below written as `work\...` is under that folder.
- retoc and the mappings tool into `work\bin\bin`:

  ```powershell
  cargo install --git https://github.com/trumank/retoc retoc_cli --root work\bin
  cargo install --path tools\acr-mappings --root work\bin --locked
  ```

- The usmap for the installed game build (starts ACR, reads it, closes it; read-only):

  ```powershell
  work\bin\bin\acr-mappings.exe dump --game "<ACR dir>"
  work\bin\bin\acr-mappings.exe validate --game "<ACR dir>" --tool work\bin\acr-additive\acr-additive.exe
  ```

  It writes `work\mappings\<build>.usmap`. Point `ACR_USMAP` at it for `mods\additive\build.ps1`.
- `mods\stage\build.ps1 -ExtractOnly` once (texture templates in `work\acr\legacy-vanilla`).

Environment for the commands below:

```powershell
$env:ACR_GAME_DIR = '<ACR dir>'
$env:ACR_USMAP    = "$PWD\work\mappings\<build>.usmap"
# optional: own file prefix and package root, so nothing collides with ACR Extra Stages' zz_acrxs_* / /Game/AcrXs
$env:ACRXS_PREFIX       = 'zz_acrmg'
$env:ACRXS_CONTENT_ROOT = 'AcrMg'
```

## 1. Spec from the IR

```powershell
pwsh -File scripts\gen-ir-spec.ps1 -Ir <IR folder> -Id AmgMurNoc01
```

Writes `work\acr\specs-ir\<id>.json`. `-Id` is the stage's row and package name (letters and digits). Everything else
comes from `stage.json` and can be overridden:

| option | default |
|---|---|
| `-ContentRoot` | `$env:ACRXS_CONTENT_ROOT`, else `AcrXs`: packages under `/Game/<ContentRoot>/Stages/<Id>/` |
| `-LocationName`, `-LocationRow` | `location.name` up to the first comma; the row is its PascalCase |
| `-Country` | from `location.country` (ISO code or English name) -> a vanilla `DT_Countries` row |
| `-Surface` | longest `surface_segments[].surface` -> Gravel / Tarmac / Snow |
| `-Template` | the vanilla location of that surface: Wales / Alsace / Livigno (its tile and info-box data) |
| `-Description` | "<location.name>. Built from <sources.attribution>." |
| `-Tile`, `-Logo` | a vanilla tile / logo row; default: the template's tile and a generated "RALLY <location>" plate |
| `-LogoColors` | plate colours, `"<plate>,<stripe>,..."` |
| `-SkySection` | a `config/sky.toml` section; default: the host sky as shipped |
| `-GroundOffset` | metres added to the computed placement height |
| `-NoMenuImages` | keep the template's track map / route map / height profile |

Stages of the same location share its row: give them the same location name (or `-LocationRow`).

## 2. Build

```powershell
pwsh -File mods\additive\build.ps1 -Stages work\acr\specs-ir -Verify
```

For each spec with `IrDir`, `stage-build` runs without the DR2-only options (no DR2 render ground, canopies or
default sky) and adds what the IR carries: the vista ring when `render/vista.glb` exists, pace notes when
`pacenotes.tokens` is non-empty, object collision when `objects` is set. Then the usual overlay, relocate, menu images
and registry. `-Verify` re-reads everything with CUE4Parse (`work\acr\additive\check\verify.txt`).

Output: `work\acr\additive\dist\<prefix>_s_<id>_P.*` per stage and `<prefix>_registry_P.*`.
`-Prefix` overrides `$env:ACRXS_PREFIX` (default `zz_acrxs`).

## 3. Install

```powershell
pwsh -File scripts\install-ir-stages.ps1             # build the registry on what is installed, then link into ~mods
pwsh -File scripts\install-ir-stages.ps1 -DryRun     # same, into work\acr\install\dry-run-mods
pwsh -File scripts\install-ir-stages.ps1 -Check      # is the install still current?
pwsh -File scripts\install-ir-stages.ps1 -Uninstall  # remove <prefix>_* from ~mods
```

The game must be closed. Install rebuilds the registry on top of the menu tables of every other installed stage mod
(docs/other-mods.md), names it `<prefix>_registry_<n>_P` above all of them, verifies that their rows are unchanged
and only ours were added, and only then touches `~mods`. It writes `work\acr\install\state.json`.

**Re-run the install** after installing, updating or removing another stage mod, or after a game update. `-Check`
says when (exit code 3 = out of date).

Play offline: these are added stages, not part of online play or leaderboards.

## Files

| path | what |
|---|---|
| `scripts/gen-ir-spec.ps1` | spec from an IR |
| `mods/additive/build.ps1` | stage containers and registry (`IrDir` specs, `-Prefix`, `-RegistryBase`, `-RegistryPriority`, `-VerifyBase`) |
| `scripts/install-ir-stages.ps1` | stacked install / check / uninstall |
| `work/acr/specs-ir/` | generated specs |
| `work/acr/install/` | base tables, base view and state of the last install |
