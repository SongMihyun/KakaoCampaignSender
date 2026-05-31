# 카카오 로그인 설정

카센더는 베타 사용자 식별과 서비스 접근 제어를 위해 카카오 로그인을 사용합니다.
현재 버전은 별도 DB/Auth Server 없이 카카오 로그인 성공 여부와 토큰 유효성만 확인합니다.
인증 계층은 `AccessPolicy`로 분리되어 있어 향후 `DbAccessPolicy`로 승인, 차단, 라이선스 관리를 연결할 수 있습니다.

## 운영 Redirect URI

현재 로컬 설치형 데스크톱 앱의 공식 운영 Redirect URI는 아래 주소입니다.

```text
http://localhost:8765/auth/kakao/callback
```

카카오 디벨로퍼스에도 위 주소를 그대로 등록해야 합니다. `127.0.0.1` 주소는 운영 기준으로 사용하지 않습니다.

향후 Auth Server 기반 구조로 전환할 때 사용할 수 있는 확장 후보는 아래 주소입니다.

```text
https://auth.kasender.com/auth/kakao/callback
```

현재 단계에서는 localhost callback을 공식 운영 기준으로 사용합니다.

## 카카오 디벨로퍼스 설정

1. 카카오 디벨로퍼스 앱에서 카카오 로그인을 활성화합니다.
2. REST API 키를 `KAKAO_CLIENT_ID`로 사용합니다.
3. Redirect URI에 `http://localhost:8765/auth/kakao/callback`을 등록합니다.
4. Client Secret을 사용하지 않는 경우 `KAKAO_CLIENT_SECRET`은 비워 둡니다.
5. Client Secret을 활성화한 경우에만 `KAKAO_CLIENT_SECRET`을 설정합니다.
6. Admin Key는 앱 설정에 넣지 않습니다.

## .env 설정

프로젝트 루트 또는 배포 환경 설정에 아래 값을 둡니다.

```text
KAKAO_CLIENT_ID=REST_API_KEY
KAKAO_REDIRECT_URI=http://localhost:8765/auth/kakao/callback
KAKAO_CLIENT_SECRET=
KAKAO_LOGIN_PROMPT=login
AUTH_MODE=no_db
AUTH_PROVIDER=kakao
AUTH_PERSIST_SESSION=false
```

## 세션 정책

`AUTH_PERSIST_SESSION=false`는 카센더 내부 인증 세션을 저장하지 않는다는 뜻입니다.
앱을 종료하고 다시 실행하면 로그인 화면이 다시 표시됩니다.

```text
AUTH_PERSIST_SESSION=false
- 카센더 내부 세션 삭제
- 앱 재실행 시 로그인 화면 표시
- 베타/공용 PC 기본 운영 정책

AUTH_PERSIST_SESSION=true
- 카센더 내부 세션 저장 및 복원 허용
- 향후 개인 PC 옵션에서만 사용 예정
```

## 브라우저 카카오 세션 제어

카센더 내부 세션과 브라우저의 카카오 로그인 세션은 서로 다릅니다.
`AUTH_PERSIST_SESSION=false`로 카센더 세션을 삭제해도, 기본 브라우저에 카카오 로그인 쿠키가 남아 있으면 카카오 인증이 바로 통과될 수 있습니다.

이를 제어하기 위해 authorize URL에 `prompt` 파라미터를 붙일 수 있습니다.

```text
KAKAO_LOGIN_PROMPT=login
```

위 값이 설정되어 있으면 카카오 OAuth 요청에 아래 파라미터가 추가됩니다.

```text
prompt=login
```

이 설정은 브라우저에 카카오 세션이 남아 있어도 계정 확인 또는 재로그인을 유도합니다.

브라우저 카카오 세션을 그대로 사용하고 싶다면 값을 비워 둡니다.

```text
KAKAO_LOGIN_PROMPT=
```

카카오 계정 자체를 강제로 로그아웃시키지는 않습니다. 강제 로그아웃은 사용자의 다른 카카오 서비스 이용에 영향을 줄 수 있으므로 기본 동작으로 넣지 않습니다.

## 로그인 흐름

```text
앱 실행
저장 세션 확인
AUTH_PERSIST_SESSION=false면 기존 저장 세션 삭제
세션 없음/만료 시 로그인 화면 표시
기본 브라우저에서 카카오 로그인
localhost callback server가 authorization code 수신
PKCE code_verifier로 token 요청
사용자 정보 조회
AuthSession 생성
NoDbAccessPolicy 확인
메인 화면 진입
```

## 현재 접근 정책

`NoDbAccessPolicy`는 아래 조건을 만족하면 사용을 허용합니다.

```text
provider == KAKAO
provider_user_id 존재
access_token 존재
token 유효
```

비상 로그인은 `provider == BETA_PASSWORD`로 분리되어 있으며, 베타 기간 임시 진입 용도입니다.
