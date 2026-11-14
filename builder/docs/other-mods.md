# Living next to other stage mods

ACR has no mod support for adding stages. Stage mods (this project, ACR Extra Stages, Sando Rally, Thiérache, ...)
all use Unreal's pak patching, and that decides how they can coexist.

## Why stage mods collide

- The stage menu is built from a handful of **menu tables**, each one file: `DT_Levels`, `DT_Tracks`,
  `DT_TracksVariants`, `DT_TracksLocations` (the stage list) and `DT_TracksTextures`, `DT_TracksLocationsLogos`,
  `DT_TracksLocationsBackgrounds` (the images those rows point at, by row name).
- A pak cannot add a row to a table; it can only ship a **whole replacement file**.
- When several paks ship the same file, the game uses the one with the **highest pak order** and ignores the others.
  For files under `Content\Paks` (including `~mods`): a name ending `_<n>_P` has order `(n+1)*100`, a plain `_P`
  counts as n = 1. Equal orders have no defined winner.

So a mod that writes "vanilla tables + my stages" hides every other mod's stages, or is hidden by them.

## Stacking: copy what is installed, add ours

`scripts/install-ir-stages.ps1` builds our tables from what the game uses **right now**:

1. Find every non-vanilla pak (in `Paks\` and `Paks\~mods\`) that ships a menu table.
2. For each table, take the copy that currently wins. Tables can come from different mods: today Sando ships the logo
   and background tables, Thiérache the texture table, and both ship the stage list.
3. Add our rows to those copies and ship them as `<prefix>_registry_<n>_P`, with n above every other mod's.
4. Check that every row we copied is unchanged and only ours were added, before anything goes into `~mods`.

A copied table can carry a broken hard import: Thiérache's stage-list tables import `/Engine/UnknownPackage` where
vanilla imports the `ST_Track` string table (what `retoc to-legacy` writes when the imported package is not mounted
during conversion). The game tolerates it, but our build repairs such imports from the vanilla table
(`registry --repair-from`), so our tables import exactly what vanilla's do.

The game then reads our tables, which hold everyone's stages. Other mods' files are only read, never changed.

## The one rule: whoever installs last must include everyone

Our tables are a copy taken at install time. So:

| what happens later | effect | what to do |
|---|---|---|
| another mod installed or updated, and it stacks too (copies the installed tables, ours included) | everything shows | nothing |
| another mod installed or updated that does **not** stack, below our order | its new stages are hidden by our older copy | re-run our install |
| another mod that does not stack, **above** our order | our stages (and others) are hidden | that mod's problem; re-running ours puts ours on top again |
| another mod removed | its stages stay in our copy, without their files | re-run our install |
| game update | our copy hides vanilla changes | rebuild and re-run our install |

`install-ir-stages.ps1 -Check` compares the current winners with the ones we stacked on and says when to re-run.

## Removing ours

`-Uninstall` deletes only `<prefix>_*` files. If a mod installed after us stacked on our tables, its tables still
list our stages after we are gone (the menu would show stages without files); the uninstall finds and names such
mods so they can be re-installed. (Stripping our rows out of such a mod's tables is planned: back up, rewrite only
our rows, re-verify, restore on failure.)

## Notes on mods seen so far

- **Sando Rally** (Stage Manager): builds its tables on the user's PC, keeps them in `Paks\pakchunk99-SandoRegistry_2_P`
  (order 300), and ships its own logo / background images there. Its pace note editor stores edits in those tables, so
  re-run our install after editing notes there.
- **Thiérache**: `~mods\zz_acrxs_thierache_registry_9_P` (order 1000); ships a separate "Sando compatibility" registry
  that already contains Sando's rows, i.e. a fixed copy taken at its build time. Its files start with `zz_acrxs_`, so
  ACR Extra Stages' own uninstall (which removes `zz_acrxs_*`) removes Thiérache as well.
- **ACR Extra Stages** (upstream): builds its registry from vanilla only (`zz_acrxs_registry_P`, order 200) and removes
  every `zz_acrxs_*` file on uninstall. Use a different `-Prefix` (e.g. `zz_acrmg`) and content root for anything else.
