# ACR Map Generator

[English](README.md) | **한국어**

공개 지리 데이터(항공 LiDAR 지형과 OpenStreetMap 도로)로 **Assetto Corsa Rally**용 랠리 스테이지를 만드는 도구입니다.

```
공개 데이터 (LiDAR, OSM) ──► ACR Map Generator ──► Stage IR ──► acr-extrastages ──► ACR 모드
                             (이 저장소)                       (스테이지 빌더)
```

실제 도로를 달릴 수 있는 스테이지로 바꿉니다. 도로 형상, 차가 달리는 물리 지면, 게이트, 계측 지점, 원경 지형을 만들고,
[acr-extrastages](https://github.com/cherrymcgerry/acr-extrastages)의 중간 형식인 **Stage IR**로 내보냅니다.
이 IR을 acr-extrastages가 ACR 모드로 빌드합니다. 이 도구는 공개 데이터만 사용하며, 게임 파일은 읽지도 쓰지도 않습니다.

> 초기 단계입니다. 스테이지 하나(코르시카 Muracciole – Noceta, 16.5 km)를 만들어 게임에서 달려 보았습니다.
> 화면 디테일(지면 텍스처, 나무, 건물)은 아직 없습니다.

## 준비물

- [uv](https://docs.astral.sh/uv/): 처음 실행할 때 Python 3.12와 필요한 패키지를 설치합니다.
- 선택: 스테이지를 미리 보려면 [Blender](https://www.blender.org/), 게임에 넣으려면 acr-extrastages

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

Stage IR은 [acr-extrastages](https://github.com/cherrymcgerry/acr-extrastages)가 본인 PC에서, 본인이 가진 게임을 사용해
ACR 모드로 빌드합니다. DR2가 아닌 IR을 빌드하려면 우리 포크의 IR 모드가 필요합니다
([icq4ever/acr-extrastages](https://github.com/icq4ever/acr-extrastages), `feature/ir-stages` 브랜치, 작업 중).

```
pwsh -File scripts\gen-ir-spec.ps1 -Ir <ACRMapGenerator>\data\<stage>\stage_ir\<id> -Id <AcrId>
pwsh -File mods\additive\build.ps1 -Stages work\acr\specs-ir\<AcrId>.json -Verify
```

메뉴의 스테이지 이름, 지역, 국기, 노면, 길이, 경로·고도 그림은 IR의 `stage.json`에서 가져옵니다.
자세한 내용은 [docs/stage-ir.md](docs/stage-ir.md#building-with-acr-extrastages)를 참고하세요.

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
