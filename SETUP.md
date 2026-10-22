# 팬덤 레이더 자동 최신화 준비물

## 현재 구성

- `.github/workflows/refresh.yml`: 기본 브랜치 변경 시, 매일 09:30 `Asia/Seoul`, 또는 수동 실행 때 데이터를 수집하고 GitHub Pages에 바로 배포합니다.
- `refresh.py`: 공개 RSS 검색 피드에서 새 소식을 발견해 `data.json`으로 저장합니다.
- `refresh.py`: 공개 RSS에 이미지가 있거나 직접 연결된 원문이 대표 이미지를 제공하면 카드와 표에 붙입니다. 이미지는 원 출처 서버에서 직접 표시하며 사이트에 복사해 보관하지 않습니다. Google News RSS처럼 실제 기사 이미지 대신 공통 로고만 내보내는 래퍼는 제외하고, 페이지에서 제목과 채널에 맞춘 커버형 썸네일을 만듭니다.
- `sources.json`: 채널별 검색 범위와 수집 개수를 조정합니다.
- `data.json`: 페이지에서 읽을 정규화 데이터 파일입니다.
- `share-card.png`: 카카오톡·메신저·SNS 링크 미리보기에 쓰는 1200×630 공유 이미지입니다. 사이트의 Open Graph/Twitter Card 메타 정보가 이 파일을 가리킵니다.

현재 수집기는 새 소식 발견용입니다. Google News RSS는 채널의 공식 API가 아니며, 펀딩액·서포터 수·판매량·재고 같은 지표를 제공한다고 보장하지 않습니다. 해당 지표는 플랫폼이 허용하는 공개 데이터나 제휴 API를 확보한 뒤 별도 어댑터로 추가해야 합니다. 출처와 수집 시각은 각 항목에 남깁니다.

사이트 공유 버튼은 기기 공유 메뉴를 열고, 지원하지 않는 브라우저에서는 링크를 복사합니다. 개별 소식도 공유할 수 있으며, 메신저의 링크 미리보기는 사이트 대표 이미지와 설명을 사용합니다. SNS에서 예전 미리보기 이미지가 계속 보이면 플랫폼 캐시가 갱신될 때까지 시간이 걸릴 수 있습니다.

## GitHub Pages에 올려 매일 실행하기

1. `outputs` 폴더의 내용을 새 GitHub 저장소의 루트에 올립니다.
2. 저장소의 **Settings → Pages → Build and deployment → Source**에서 **GitHub Actions**를 선택합니다.
3. `main` 브랜치에 `.github/workflows/refresh.yml`이 있는지 확인합니다. 기본 브랜치 이름이 `main`이 아니라면 워크플로 파일의 `push.branches` 값을 그 이름으로 바꿉니다.
4. **Actions → Refresh fandom radar data → Run workflow**를 눌러 최초 수집과 배포를 시작합니다.
5. 실행이 성공하면 워크플로 요약의 `github-pages` 배포 URL에서 사이트를 확인할 수 있습니다. `data.json`은 저장소에 커밋하는 대신 페이지와 함께 배포 산출물에 포함됩니다.
6. 이후 워크플로는 매일 오전 9시 30분 한국 시간에 수집과 배포를 반복합니다.

예약 실행은 GitHub가 제공하는 스케줄러에 따라 지연될 수 있습니다. 기본 브랜치에서 실행되며, 공개 저장소가 60일간 비활성 상태면 예약 실행이 자동 비활성화될 수 있습니다. [예약 실행 문서](https://docs.github.com/en/actions/reference/workflows-and-actions/events-that-trigger-workflows)

GitHub Pages는 사이트를 인터넷에 공개합니다. 공개를 원하지 않는 데이터나 API 키를 사이트 파일에 넣지 마세요. API 키는 저장소의 **Settings → Secrets and variables → Actions**에 Secret으로 등록해야 합니다. GitHub Pages 요금제 이용 조건은 저장소 설정에서 확인하세요. [Pages 게시 방식](https://docs.github.com/en/pages/getting-started-with-github-pages/configuring-a-publishing-source-for-your-github-pages-site)

## 실제 채널 지표를 연결할 때

공개 API 키나 제휴 자격이 필요한 경우 GitHub 저장소의 **Settings → Secrets and variables → Actions**에 비밀 값으로 등록하고, Python 코드에서 환경 변수로 읽도록 어댑터를 추가합니다. API 키를 `sources.json`, `index.html` 또는 Git 저장소에 직접 넣지 마세요. 공개 API가 없는 채널은 페이지에서 허용하는 범위 안의 공개 정보만 수집하거나, 관리자가 검토해 올리는 큐레이션 방식으로 연결해야 합니다.
