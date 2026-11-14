# Security policy

## Reporting a vulnerability

Please **don't open a public issue** for security problems, for example a crafted stage file that writes outside
`data/`, unsafe handling of downloaded files, or requests that leak personal data.

Report it privately through GitHub instead: on the repository page, open **Security → Report a vulnerability**
([private advisory form](https://github.com/icq4ever/ACRMapGenerator/security/advisories/new)).
Include what you found, the version (`pyproject.toml`), and how to reproduce it.

## Scope

ACR Map Generator runs locally. It reads stage files from `stages/` and writes only under `data/<stage>/`.
It makes network requests only to the open-data services it uses (IGN Géoplateforme, the Overpass API), with a
generic `User-Agent: acr-map-generator/0.1` and no personal data. It never reads or writes game files.

## Supported versions

Only the latest version gets fixes. This is a hobby project, so there is no guaranteed response time, but reports
are taken seriously.
