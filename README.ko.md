# ACR Map Generator

[English](README.md) | **한국어**

공개 지리 데이터(항공 LiDAR 지형과 OpenStreetMap 도로)로 **Assetto Corsa Rally**용 랠리 스테이지를 만드는 도구입니다.

```
공개 데이터 (LiDAR, OSM) ──► 생성기 ──► Stage IR ──► 빌더 ──► ACR 스테이지 모드 ──► 다른 스테이지 모드와 함께 설치
                             (src/)                  (builder/)
```

이 저장소 하나로 실제 도로를 게임 안까지 가져갑니다. **생성기**(`src/`, Python)는 공개 데이터로 도로 형상,
차가 달리는 물리 지면, 게이트, 계측 지점, 원경 지형을 만들어 **Stage IR**로 내보냅니다. **빌더**(`builder/`)는 이 IR을
메뉴 항목이 있는 ACR 스테이지 모드로 빌드하고, 다른 스테이지 모드와 함께 설치합니다. 빌더는 cherrymcgerry의
[ACR Extra Stages](https://github.com/cherrymcgerry/acr-extrastages)를 포크한 것으로, git subtree로 들어 있습니다
([ACR로 빌드하기](#acr로-빌드하기) 참고).

생성기는 공개 데이터만 사용하며, 게임 파일은 읽지도 쓰지도 않습니다. 빌더는 본인 PC에서 본인이 가진 게임으로 실행됩니다.
이 저장소에는 게임 파일이 들어 있지 않습니다.

> 초기 단계입니다. 스테이지 하나(코르시카 Muracciole – Noceta, 16.5 km)를 만들어 게임에서 달려 보았습니다.
> 화면 디테일(지면 텍스처, 나무, 건물)은 아직 없습니다.

이 프로젝트는 AI 코딩 도구를 활용해 개발하며, 모든 변경은 관리자가 검토합니다.

## 준비물

- [uv](https://docs.astral.sh/uv/): 처음 실행할 때 Python 3.12와 필요한 패키지를 설치합니다.
- 선택: 스테이지를 미리 보려면 [Blender](https://www.blender.org/)
- ACR로 빌드하려면(빌더): Windows, 본인이 가진 Assetto Corsa Rally, [.NET 10 SDK](https://dotnet.microsoft.com/),
  [PowerShell 7](https://github.com/PowerShell/PowerShell), [Rust](https://rustup.rs/)(retoc과 매핑 도구용), git.
  빌더의 작업 폴더는 게임과 같은 드라이브에 있어야 합니다(아래 참고).

## 빠른 시작

```
uv run acr-map-generator new my_stage        # 템플릿으로 stages/my_stage.toml 만들기
#   TODO 채우기: 이름, 국가, 도로 번호, 경유 지점(출발, 분기점, 도착)
uv run acr-map-generator validate my_stage   # 파일 검사
uv run acr-map-generator build my_stage      # 데이터를 받고 모든 단계 실행
uv run acr-map-generator status my_stage     # 무엇이 만들어졌고 무엇이 오래됐는지
uv run acr-map-generator list                # 전체 스테이지 목록
```

`build`는 바뀐 부분만 다시 실행합니다. 경유 지점을 고치면 경로부터 그 뒤 단계가 다시 만들어지고,
노면 구간만 고치면 내보내기 단계만 다시 실행됩니다.

Blender에서 결과를 볼 수 있습니다. 차 시점으로 스테이지를 따라가는 카메라가 들어 있습니다(Space로 재생).

```
blender --python scripts/blender_view_package.py -- data/<stage>/package/<package id>
```

## ACR로 빌드하기

`builder/`는 본인 PC에서 본인이 가진 게임을 사용해 Stage IR을 ACR 스테이지 모드로 빌드합니다. cherrymcgerry의
[ACR Extra Stages](https://github.com/cherrymcgerry/acr-extrastages)(MIT OR Apache-2.0)를 우리 포크
[icq4ever/acr-extrastages](https://github.com/icq4ever/acr-extrastages)에서 가져온 것입니다. 포크는 DR2 데이터 없이
Stage IR에서 빌드하기, IR로 메뉴 등록, 페이스노트, 다른 스테이지 모드와 함께 설치하기를 추가했습니다.
라이선스 파일과 고지문은 `builder/` 안에 있습니다.

처음 한 번 준비할 것([builder/docs/ir-stages.md](builder/docs/ir-stages.md#one-time-setup)에 자세히): 빌더는 게임 파일을
하드 링크로 재사용하므로 작업 폴더가 **게임과 같은 드라이브**에 있어야 합니다. 그 드라이브의 폴더를 `ACRXS_WORK`로
지정하고, 그 안에 retoc, 매핑 도구, 설치된 게임 빌드의 usmap을 만들어 둡니다.

```powershell
$env:ACR_GAME_DIR = '<ACR 폴더>'
$env:ACRXS_WORK   = '<게임 드라이브의 폴더>'
$env:ACR_USMAP    = "$env:ACRXS_WORK\mappings\<build>.usmap"
cd builder
pwsh -File scripts\gen-ir-spec.ps1 -Ir ..\data\<stage>\stage_ir\<id> -Id <AcrId> -ContentRoot AcrMg   # IR에서 spec 만들기
pwsh -File mods\additive\build.ps1 -Stages $env:ACRXS_WORK\acr\specs-ir -Prefix zz_acrmg -Verify      # 빌드
pwsh -File scripts\install-ir-stages.ps1 -Prefix zz_acrmg                                             # 설치 (게임 종료 상태)
pwsh -File scripts\install-ir-stages.ps1 -Prefix zz_acrmg -Check                                      # 설치가 최신인지 확인
```

이 도구로 만든 스테이지는 `/Game/AcrMg` 아래 `zz_acrmg_*` 파일로 만들어집니다. 메뉴의 스테이지 이름, 지역, 국기, 노면,
길이, 로고, 경로·고도 그림은 IR의 `stage.json`에서 가져옵니다. 설치할 때는 이미 설치된 다른 스테이지 모드(Sando,
Thiérache 등)의 메뉴 표 위에 우리 표를 쌓습니다. 다른 스테이지 모드를 설치, 업데이트, 삭제했거나 게임이 업데이트되면
설치를 다시 실행하세요.

- **오프라인 전용.** 빌드한 스테이지는 오프라인 싱글 플레이용입니다. 온라인이나 리더보드 모드에서는 쓰지 마세요.
- **상표가 있는 로고는 로컬에만.** 대회나 연맹 마크가 들어간 로고는 git에 올라가지 않는 `local/` 폴더에 두고,
  저장소에는 넣지 않습니다([docs/menu-images.md](docs/menu-images.md)).

더 보기: [builder/docs/ir-stages.md](builder/docs/ir-stages.md) (준비, spec 옵션, 빌드, 설치),
[builder/docs/other-mods.md](builder/docs/other-mods.md) (다른 스테이지 모드와 함께 쓰기),
[builder/docs/stage-ir.md](builder/docs/stage-ir.md#irs-from-other-producers-no-dr2-data) (IR 규약, "IRs from other
producers"), [docs/stage-ir.md](docs/stage-ir.md#building-with-acr-extrastages).

## 결과물

모두 `data/<stage>/`에 저장되며, git에는 올라가지 않습니다.

| 경로 | 내용 |
|---|---|
| `stage_ir/<id>/` | acr-extrastages에 넘길 **Stage IR**: `stage.json`, `collision.glb`, `render/vista.glb` |
| `package/<id>/` | 스테이지 패키지: 타일별 지형 glb, 주행 경로, 메타데이터, 메뉴 이미지 (Blender 뷰어용) |
| `centreline/centreline.geojson` | LiDAR로 측정한 3D 도로 중심선 (폭, 좌우 기울기, 다리 정보 포함) |
| `terrain*/`, `roads/`, `route/` | 내려받은 데이터와 중간 결과 |
| `manifest.json` | 각 데이터의 출처, 라이선스, 빌드 상태 |

## 데이터 출처와 표기

| 데이터 | 출처 | 라이선스 |
|---|---|---|
| 지형 (0.5–25 m) | IGN LiDAR HD (프랑스, 코르시카 포함) | Etalab Licence Ouverte 2.0 |
| 도로 (경로 찾기에만 사용) | OpenStreetMap (Overpass API) | ODbL |
| 지면 색 (20 cm) | IGN BD ORTHO 항공사진 | Etalab Licence Ouverte 2.0 |

이 도구로 만든 결과물에는 출처를 표기해 주세요: **© IGN – LiDAR HD (Etalab 2.0)**,
**© OpenStreetMap contributors (ODbL)**. 스테이지별 표기 문구는 `manifest.json`에 정리됩니다.
배포되는 도로 형상은 LiDAR에서 측정한 것이고, OSM은 경로를 찾는 데만 씁니다.

## 문서

기술 문서는 영어로 작성되어 있습니다.

- [docs/architecture.md](docs/architecture.md): 코드 구조, 파이프라인, 데이터 출처 추가 방법, 스테이지 파일, 개발 규칙
- [docs/how-it-works.md](docs/how-it-works.md): 중심선, 도로 폭과 단면, 다리, 지형 메시, 원경
- [docs/stage-ir.md](docs/stage-ir.md): Stage IR 내보내기와 acr-extrastages로 빌드하는 방법
- [docs/stage_package.md](docs/stage_package.md): 스테이지 패키지 형식
- [docs/data-sources.md](docs/data-sources.md): 공개 LiDAR 조사와 데이터 관련 결정
- [docs/roadmap.md](docs/roadmap.md): 진행 상황과 다음 계획
- [docs/menu-images.md](docs/menu-images.md): 메뉴 로고, 타일, 스테이지 그림 (규격, 위치, 권리)
- [docs/licensing.md](docs/licensing.md): 이 저장소, 원본 데이터, 만들어진 스테이지의 라이선스
- [CONTRIBUTING.md](CONTRIBUTING.md): 스테이지, 데이터 출처, 코드 기여 방법
- [CHANGELOG.md](CHANGELOG.md), [SECURITY.md](SECURITY.md), [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md)

## 주의사항

- **비공식 도구입니다.** 팬이 만든 도구이며, Kunos Simulazioni, Supernova Games, 505 Games, FIA/WRC,
  어떤 랠리 주최 측과도 관계가 없고 승인받지 않았습니다. Assetto Corsa Rally와 대회 이름은 각 소유자의 상표입니다.
  스테이지 파일은 대회 이름을 사실 참고로만 언급합니다.
- **실제 도로에서 쓰지 마세요.** 스테이지는 공개 데이터로 실제 도로를 근사한 것이라 부정확할 수 있습니다.
  길 안내용으로 쓰지 마세요. 이 도로들은 대회 기간이 아니면 일반 차량이 다니는 공공 도로이니 현지 법규를 지켜 주세요.
- **게임 모드는 본인 책임입니다.** 스테이지를 빌드하고 설치할 때는 본인이 가진 게임을 사용합니다. 게임 업데이트 후
  모드가 동작하지 않을 수 있고, 모드를 공유해도 되는지는 게임 약관을 따릅니다. 설치 전에 백업하세요.
- **오프라인·싱글플레이 전용입니다.** 모드 스테이지를 설치한 상태에서는 온라인, 순위표, 경쟁 모드에 들어가지 마세요.
- **데이터 서비스를 배려해 주세요.** IGN Géoplateforme와 Overpass API는 무료 공공 서비스입니다. 파이프라인은 받은 데이터를
  모두 저장해 두니, 강제로 다시 받거나 대량으로 일괄 실행하는 일은 피해 주세요.
- **보증하지 않습니다.** 이 소프트웨어는 "있는 그대로" 제공됩니다(라이선스 참고).

## 후원

후원도 가능합니다. 개발에 큰 힘이 됩니다.

- [GitHub Sponsors](https://github.com/sponsors/icq4ever)
- 카카오페이: <br/>
<img src="assets/kakaoDonation.jpg" alt="카카오페이" width="300">

## 라이선스

- 코드와 문서: MIT 또는 Apache-2.0 중 선택 ([LICENSE-MIT](LICENSE-MIT), [LICENSE-APACHE](LICENSE-APACHE))
- `stages/`의 스테이지 정의: [CC BY-SA 4.0](stages/LICENSE)
- 이 도구로 만든 스테이지에는 원본 데이터의 라이선스도 함께 적용됩니다. [docs/licensing.md](docs/licensing.md)를 참고하세요.
