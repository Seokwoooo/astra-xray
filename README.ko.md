[English](./README.md) | **한국어**

# astra-xray

정리하기 전에 Codex가 Astra에 무엇을 건네는지 먼저 봅니다.

Codex 설정에는 시간이 쌓입니다. 스킬은 늘고 AGENTS.md는 길어집니다.
예전 모델에 맞춘 규칙도 이유가 사라진 뒤까지 남습니다. astra-xray는
Codex가 GPT-6 Astra의 컨텍스트에 넣을 내용과 다시 볼 부분을 보여줍니다.

## 설치

현재 프로젝트에 설치합니다.

```bash
npx skills add Seokwoooo/astra-xray
```

설치가 끝나면 Codex에서 실행합니다.

```text
$astra-xray
```

모든 프로젝트에서 쓰고 싶다면 플래그 하나만 붙이면 됩니다.

```bash
npx skills add Seokwoooo/astra-xray -g
```

설치는 이게 전부입니다. 이 저장소에는 스킬이 하나만 들어 있습니다.
설치기가 스킬과 Codex를 알아서 찾습니다.

Python 3.9 이상이 필요합니다. 스캐너에는 별도 Python 패키지가 필요하지
않습니다.

<details>
<summary>Node.js 없이 직접 설치</summary>

```bash
git clone --depth 1 https://github.com/Seokwoooo/astra-xray.git
mkdir -p ~/.agents/skills
cp -R astra-xray/skills/astra-xray ~/.agents/skills/
```

</details>

## 무엇을 찾나

- 컨텍스트 예산 때문에 잘린 스킬 설명
- 모델이 보는 목록에서 빠진 스킬
- 이름이 겹치는 스킬과 지나치게 넓은 실행 조건
- Codex가 읽거나 건너뛴 AGENTS.md 파일
- 예전 모델을 기준으로 남아 있는 지침
- 현재 Codex와 맞지 않는 설정값
- 한 번 더 살펴봐야 할 설치 스크립트

영어와 한국어 지침을 함께 검사합니다.

## 어떻게 작동하나

**Scan**은 읽기 전용입니다. 현재 프로젝트의 스킬 목록을 계산하고
AGENTS.md가 불러와지는 순서를 따라갑니다. 설정도 바꾸지 않고 확인합니다.

**Propose**는 사용자가 고른 결과만 작은 변경안으로 정리합니다. 각 제안에는
판단 근거가 따라옵니다.

**Apply**는 검증된 zip 백업부터 만듭니다. 승인한 파일만 고친 뒤 다시
검사합니다.

**Restore**는 백업 당시 상태로 돌립니다. 백업 뒤에 추가된 작업을 발견하면
멈춥니다. 덮어쓰기는 사용자가 직접 선택해야 합니다.

스캐너만 바로 실행할 수도 있습니다.

```bash
python3 .agents/skills/astra-xray/scripts/scan.py
```

## 지우지 않는 것

엄격해야 하는 규칙도 있습니다. astra-xray는 프로덕션과 비밀정보를 지키는
규칙을 남깁니다. 배포와 삭제처럼 되돌리기 어려운 작업의 경계도 그대로
지킵니다. 문장은 다듬을 수 있어도 안전장치는 버리지 않습니다.

승인 설정과 샌드박스 설정은 건드리지 않습니다. 훅과 MCP 설정도 그대로
둡니다. 검사 결과와 백업은 `~/.astra-xray` 아래에만 저장합니다.

## 정확도

컨텍스트 예산 계산은 Codex 0.154.0 렌더러를 한 줄씩 옮겼습니다. 고정된
값과 출처는 [`constants.py`](skills/astra-xray/scripts/xray/constants.py)에
모아 두었습니다.

스킬 목록을 가져온 세션은 어떤 모델로 실행해도 됩니다. 그 세션의 역할은
Codex가 불러온 목록을 보여주는 데서 끝납니다. GPT-6 Astra는 별도의 시뮬레이션
대상으로 유지됩니다.

현재 프로젝트와 맞는 최신 목록이 없으면 그 사실부터 밝힙니다. 파일만 보고
계산한 결과에는 낮은 신뢰도의 추정치라는 표시가 붙습니다. 추정치를 실제 실행
증거처럼 말하지 않습니다.

이 점검이 필요한 이유는 OpenAI의
[Astra 스킬과 프롬프트 글](https://developers.openai.com/blog/rethinking-skills-and-prompts-for-gpt-6-astra)과
[최신 모델 가이드](https://developers.openai.com/api/docs/guides/latest-model)에서 확인할 수 있습니다.
예산 계산은 Codex
[`render.rs`](https://github.com/openai/codex/blob/rust-v0.154.0/codex-rs/ext/skills/src/render.rs)를
기준으로 고정했습니다.

## 개발

```bash
python3 -m unittest discover -s tests
```

예산 테스트는 Codex 렌더러의 원본 테스트와 같은 경우를 다룹니다.

## 라이선스

MIT
