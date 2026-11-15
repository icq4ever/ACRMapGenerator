<#
.SYNOPSIS
  Writes a stage spec (work/acr/specs-ir/<id>.json by default) for a Stage IR v2 folder made by another producer
  (no DR2 data, e.g. ACRMapGenerator), for mods/additive/build.ps1. Menu entries come from the IR's stage.json:

  - stage name      : `name` (resolved by acr-additive from the IR at registry time, not stored in the spec)
  - location name   : `location.name` up to the first comma ("Corsica, FR" -> "Corsica")
  - country / flag  : `location.country` (ISO 3166 code, or a country name) -> the vanilla DT_Countries row
  - surface         : the longest surface in `surface_segments` (asphalt / concrete -> Tarmac, snow / ice -> Snow, else Gravel)
  - length          : `length_m`
  - menu images     : route map, track map and elevation profile drawn from the IR (elevations are absolute, ElevationOffset 0)

  The new location copies a vanilla location of the same surface (Tarmac: Alsace, Gravel: Wales, Snow: Livigno) and keeps
  its main-menu tile; the logo is a generated rally plate (scripts/menu-location-logos.ps1). Every value can be overridden.

.EXAMPLE
  pwsh -File scripts\gen-ir-spec.ps1 -Ir ..\ACRMapGenerator\data\...\stage_ir\corsica_muracciole_noceta_5150_15950 -Id AmgMurNoc01
#>
param(
    [Parameter(Mandatory)][string]$Ir,          # Stage IR folder (holds stage.json)
    [Parameter(Mandatory)][string]$Id,          # ACR row / package name of the stage: letters and digits, e.g. AmgMurNoc01
    [string]$OutDir = (Join-Path $(if ($env:ACRXS_WORK) { $env:ACRXS_WORK } else { Join-Path (Split-Path $PSScriptRoot) 'work' }) 'acr\specs-ir'),
    # content root of the stage's packages, /Game/<ContentRoot>/Stages/<Id>/... (default AcrXs, or $env:ACRXS_CONTENT_ROOT)
    [string]$ContentRoot = $(if ($env:ACRXS_CONTENT_ROOT) { $env:ACRXS_CONTENT_ROOT } else { 'AcrXs' }),
    [string]$LocationRow,                       # DT_TracksLocations row (default: the location name in PascalCase)
    [string]$LocationName,                      # menu text (default: location.name up to the first comma)
    [string]$Description,                       # location info box (default: "<location.name>. Built from <attribution>.")
    [string]$Country,                           # DT_Countries row (default: from location.country)
    [ValidateSet('Gravel', 'Tarmac', 'Snow')][string]$Surface,
    [string]$Template,                          # vanilla DT_TracksLocations row to copy (default: by surface)
    [string]$Tile,                              # vanilla DT_TracksLocationsBackgrounds row (default: the template's)
    [string]$Logo,                              # vanilla DT_TracksLocationsLogos row (default: a generated plate)
    [string]$LogoPng,                           # own logo image, any size (default: <IR>/menu/logo.png when it exists); fitted by scripts/location-logo-png.ps1
    [string]$LogoColors = '#1F3A93,#FFFFFF',    # generated plate: "<plate>,<stripe>,..."
    [string]$SkySection,                        # config/sky.toml section (default: the host sky as shipped)
    [double]$GroundOffset = 0,
    [switch]$NoMenuImages
)
$ErrorActionPreference = 'Stop'
if ($Id -notmatch '^[A-Za-z][A-Za-z0-9]*$') { throw "-Id must be letters and digits, starting with a letter: $Id" }
if ($ContentRoot -notmatch '^[A-Za-z][A-Za-z0-9]*$') { throw "-ContentRoot must be letters and digits, starting with a letter: $ContentRoot" }
$irDir = (Resolve-Path $Ir).Path
$stageJson = Join-Path $irDir 'stage.json'
if (-not (Test-Path $stageJson)) { throw "no stage.json in $irDir" }
$irJson = Get-Content $stageJson -Raw | ConvertFrom-Json -Depth 100
if ($irJson.schema -ne 'acrxs/stage-ir' -or [int]$irJson.version -lt 2) { throw "$stageJson is not a Stage IR v2 (schema '$($irJson.schema)', version '$($irJson.version)')" }
if (-not $irJson.name) { throw "$stageJson has no name" }

function PascalCase([string]$s) {
    $t = $s.Normalize([Text.NormalizationForm]::FormD) -replace '\p{Mn}', ''     # drop accents: Thiérache -> Thierache
    (($t -split '[^A-Za-z0-9]+' | ? { $_ } | % { $_.Substring(0, 1).ToUpperInvariant() + $_.Substring(1) }) -join '')
}

# --- location ---
$locFull = if ($irJson.location -and $irJson.location.name) { [string]$irJson.location.name } else { [string]$irJson.name }
if (-not $LocationName) { $LocationName = ($locFull -split ',')[0].Trim() }
if (-not $LocationRow) { $LocationRow = PascalCase $LocationName }
if ($LocationRow -notmatch '^[A-Za-z][A-Za-z0-9]*$') { throw "location row '$LocationRow' must be letters and digits (use -LocationRow)" }

# --- country: DT_Countries rows are English names in PascalCase with odd casing (FinlAnd, PolAnd), so match case-insensitively ---
$countryRows = @(
    'Afghanistan', 'Albania', 'Algeria', 'Andorra', 'Angola', 'AntiguaAndBarbuda', 'Argentina', 'Armenia', 'Australia', 'Austria',
    'Azerbaijan', 'Bahamas', 'Bahrain', 'Bangladesh', 'Barbados', 'Belarus', 'Belgium', 'Belize', 'Benin', 'Bolivia',
    'BosniaAndHerzegovina', 'Botswana', 'Brazil', 'Brunei', 'Bulgaria', 'Burkinafaso', 'Burundi', 'CaboVerde', 'Cambodia', 'Cameroon',
    'Canada', 'CentralAfricanRepublic', 'Chad', 'Chile', 'China', 'Colombia', 'Comoros', 'RepublicOfTheCongo', 'Costarica', 'Croatia',
    'Cuba', 'Cyprus', 'CzechRepublic', 'DemocraticRepublicOfTheCongo', 'Denmark', 'Djibouti', 'Dominica', 'DominicanRepublic', 'Ecuador',
    'Egypt', 'Elsalvador', 'EquatorialGuinea', 'Eritrea', 'Estonia', 'Eswatini', 'Ethiopia', 'Fiji', 'FinlAnd', 'France', 'Gabon',
    'Gambia', 'Georgia', 'Germany', 'Ghana', 'Greece', 'Grenada', 'Guatemala', 'Guinea', 'GuineaBissau', 'Guyana', 'Haiti', 'Honduras',
    'HongKong', 'Hungary', 'IcelAnd', 'India', 'Indonesia', 'Iran', 'Iraq', 'IrelAnd', 'Israel', 'Italy', 'CoteDivoire', 'Jamaica',
    'Japan', 'Jordan', 'Kazakhstan', 'Kenya', 'Kiribati', 'Kuwait', 'Kyrgyzstan', 'Laos', 'Latvia', 'Lebanon', 'Lesotho', 'Liberia',
    'Libya', 'Liechtenstein', 'Lithuania', 'Luxembourg', 'Macau', 'Madagascar', 'Malawi', 'Malaysia', 'Maldives', 'Mali', 'Malta',
    'Mauritania', 'Mauritius', 'Mexico', 'Micronesia', 'Moldova', 'Monaco', 'Mongolia', 'Montenegro', 'Morocco', 'Mozambique', 'Myanmar',
    'Namibia', 'Nauru', 'Nepal', 'Netherlands', 'NewZealand', 'Nicaragua', 'Niger', 'Nigeria', 'NorthKorea', 'NorthMacedonia', 'Norway',
    'Oman', 'Pakistan', 'Palau', 'Panama', 'PapuaNewGuinea', 'Paraguay', 'Peru', 'Philippines', 'PolAnd', 'Portugal', 'Qatar', 'Romania',
    'Russia', 'Rwanda', 'SaintKittsAndNevis', 'SaintLucia', 'SaintVincentAndThegrenadines', 'Samoa', 'Sanmarino', 'SaotomeAndPrincipe',
    'SaudiArabia', 'Senegal', 'Serbia', 'Seychelles', 'SierraLeone', 'Singapore', 'Slovakia', 'Slovenia', 'SolomonIslands', 'Somalia',
    'SouthAfrica', 'SouthKorea', 'SouthSudan', 'Spain', 'Srilanka', 'Sudan', 'Suriname', 'Sweden', 'Switzerland', 'Syria', 'Taiwan',
    'Tajikistan', 'Tanzania', 'ThailAnd', 'EastTimor', 'Togo', 'Tonga', 'TrinidadAndTobago', 'Tunisia', 'Turkey', 'Turkmenistan', 'Tuvalu',
    'Uganda', 'Ukraine', 'UnitedArabemirates', 'UnitedKingdom', 'UnitedStates', 'Uruguay', 'Uzbekistan', 'Vanuatu', 'Vaticancity',
    'Venezuela', 'Vietnam', 'Wales', 'Yemen', 'Zambia', 'Zimbabwe'
)   # DT_Countries of ACR build 25170642 (minus "Other")
# ISO codes whose .NET English name differs from the row
$isoRow = @{ CZ = 'CzechRepublic'; KR = 'SouthKorea'; KP = 'NorthKorea'; CG = 'RepublicOfTheCongo'; CD = 'DemocraticRepublicOfTheCongo'
    CI = 'CoteDivoire'; TL = 'EastTimor'; VA = 'Vaticancity'; MK = 'NorthMacedonia'; SZ = 'Eswatini'; CV = 'CaboVerde'; MO = 'Macau'
    HK = 'HongKong'; MM = 'Myanmar'; TR = 'Turkey'; RU = 'Russia'; FM = 'Micronesia'; ST = 'SaotomeAndPrincipe'; BN = 'Brunei'; LA = 'Laos'
    SY = 'Syria'; IR = 'Iran'; TZ = 'Tanzania'; MD = 'Moldova'; BO = 'Bolivia'; VE = 'Venezuela'; VN = 'Vietnam'; GB = 'UnitedKingdom'; UK = 'UnitedKingdom' }
function Find-CountryRow([string]$code) {
    if (-not $code) { return $null }
    $c = $code.Trim()
    if ($c.Length -eq 2 -and $isoRow.ContainsKey($c.ToUpperInvariant())) { return $isoRow[$c.ToUpperInvariant()] }
    $names = @($c)
    if ($c.Length -eq 2) { try { $names = @(([Globalization.RegionInfo]::new($c)).EnglishName) + $names } catch { } }
    foreach ($n in $names) {
        $key = (PascalCase ($n -replace '&', ' and ')).ToLowerInvariant()
        $hit = $countryRows | ? { $_.ToLowerInvariant() -eq $key } | Select-Object -First 1
        if ($hit) { return $hit }
    }
    return $null
}
if (-not $Country) {
    $Country = Find-CountryRow $irJson.location.country
    if (-not $Country) { Write-Warning "no DT_Countries row for location.country '$($irJson.location.country)'; keeping the template's flag (use -Country)" }
}
elseif ($Country -notin $countryRows) {
    $row = Find-CountryRow $Country
    if (-not $row) { throw "-Country '$Country' is not a DT_Countries row" }
    $Country = $row
}

# --- surface: the longest surface of the route ---
if (-not $Surface) {
    $len = @{}
    foreach ($seg in @($irJson.surface_segments)) {
        if (-not $seg) { continue }
        $k = switch -Regex ([string]$seg.surface) { 'asphalt|tarmac|concrete|paved' { 'Tarmac' } 'snow|ice' { 'Snow' } default { 'Gravel' } }
        $len[$k] = [double]$len[$k] + ([double]$seg.to - [double]$seg.from)
    }
    $Surface = if ($len.Count) { ($len.GetEnumerator() | Sort-Object Value -Descending | Select-Object -First 1).Key } else { 'Gravel' }
}
if (-not $Template) { $Template = @{ Tarmac = 'Alsace'; Gravel = 'Wales'; Snow = 'Livigno' }[$Surface] }

if (-not $Description) {
    $attr = @($irJson.sources.attribution | ? { $_ })
    $Description = if ($attr) { "$locFull. Built from $($attr -join ', ')." } else { "$locFull." }
    $credit = [string]$irJson.sources.credit
    if ($credit) { $Description += " $($credit.TrimEnd('.'))." }
}

$km = [math]::Round([double]$irJson.length_m / 1000, 3)
$loc = [ordered]@{ Row = $LocationRow; Template = $Template; Name = $LocationName; Description = $Description }
if ($Tile) { $loc.Tile = $Tile }
if (-not $LogoPng -and (Test-Path (Join-Path $irDir 'menu\logo.png'))) { $LogoPng = Join-Path $irDir 'menu\logo.png' }
if ($Logo) { $loc.Logo = $Logo }
elseif ($LogoPng) { $loc.LogoPng = (Resolve-Path $LogoPng).Path }
else { $loc.GenLogo = $true; $loc.LogoColors = $LogoColors }
if ($Country) { $loc.Country = $Country }
$loc.Surface = $Surface

$spec = [ordered]@{
    Id       = $Id
    IrDir    = $irDir
    Level    = "/Game/$ContentRoot/Stages/$Id/$Id"
    Location = $loc
    # Track.Name / Variants[].Name / StageName: left empty, acr-additive reads them from the IR's `name`
    Track    = [ordered]@{ Template = 'WalesS4HafrenSouth' }
    Variants = @([ordered]@{ Row = "${Id}FullForward"; Template = 'WelesS4HafrenSouthFullForward'; Length = $km })
    Clone    = [ordered]@{
        Packages = [ordered]@{
            '/Game/Levels/WalesS4HafrenSouth' = "/Game/$ContentRoot/Stages/$Id/$Id"
            '/Game/Environments/WalesS4HafrenSouth/DataAssets/DA_WalesS4HafrenSouthBakedData' = "/Game/$ContentRoot/Stages/$Id/DA_${Id}BakedData"
            '/Game/Data/Pacenote/Tables/DT_PacenoteHafrenSouthForward' = "/Game/$ContentRoot/Stages/$Id/DT_Pacenote${Id}Forward"
        }
        Objects  = [ordered]@{
            'WalesS4HafrenSouth' = $Id
            'DA_WalesS4HafrenSouthBakedData' = "DA_${Id}BakedData"
            'DT_PacenoteHafrenSouthForward' = "DT_Pacenote${Id}Forward"
        }
    }
}
if ($SkySection) { $spec.SkySection = $SkySection }
if ($GroundOffset -ne 0) { $spec.GroundOffset = $GroundOffset }
# IR elevations are absolute (metres above sea level), so the menu's min / max / start elevation need no offset
if (-not $NoMenuImages) { $spec.Menu = [ordered]@{ Images = $true; ElevationOffset = 0 } }

New-Item -ItemType Directory -Force $OutDir | Out-Null
$out = Join-Path $OutDir "$($Id.ToLowerInvariant()).json"
Set-Content -Path $out -Value ($spec | ConvertTo-Json -Depth 8) -Encoding utf8
Write-Host "wrote $out"
Write-Host ("  {0} | {1} ({2}, {3}, flag {4}) | {5} km" -f $irJson.name, $LocationName, $LocationRow, $Surface, $(if ($Country) { $Country } else { "template's" }), $km)
