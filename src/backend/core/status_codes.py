from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class StatusInfo:
    code: int
    message: str
    step: str
    detail: str
    causes: tuple[str, ...] = ()
    actions: tuple[str, ...] = ()


STATUS_CODES: dict[int, StatusInfo] = {
    1000: StatusInfo(1000, "성공", "result", "모든 핵심 발송 단계가 정상 완료되었습니다."),
    2001: StatusInfo(2001, "카카오톡 실행 안 됨", "check_kakao", "카카오톡 PC 창을 찾을 수 없습니다.", ("카카오톡 PC가 꺼져 있음",), ("카카오톡 PC 실행 후 다시 시도",)),
    2002: StatusInfo(2002, "카카오톡 로그인 필요", "check_login", "카카오톡 로그인이 필요합니다.", ("로그아웃 상태", "잠금 화면"), ("카카오톡 로그인 확인",)),
    2003: StatusInfo(2003, "카카오톡 창 인식 실패", "detect_window", "카카오톡 창을 제어할 수 없습니다.", ("창 최소화/권한 문제",), ("카카오톡을 전면에 둔 뒤 다시 시도",)),
    3001: StatusInfo(3001, "채팅방을 찾을 수 없음", "open_chat", "대상자 이름으로 채팅방을 찾지 못했습니다.", ("카카오톡 미로그인", "채팅방 이름 변경", "대상자 정보 오류"), ("채팅방 검색 테스트", "대상자 이름 확인")),
    3002: StatusInfo(3002, "채팅방 열기 실패", "open_chat", "검색된 채팅방을 열지 못했습니다.", ("검색 결과 선택 실패", "카카오톡 UI 응답 지연"), ("카카오톡 재실행", "속도 모드 낮추기")),
    3101: StatusInfo(3101, "대상자 정보 오류", "validate_recipient", "대상자 이름/전화번호 등 필수 정보가 올바르지 않습니다.", ("이름 공백", "잘못된 대상자 데이터"), ("대상자 정보 수정",)),
    3102: StatusInfo(3102, "대상자 중복 오류", "validate_recipient", "대상자 중복 데이터가 감지되었습니다.", ("사번 또는 전화번호 중복",), ("대상자 중복 정리",)),
    4001: StatusInfo(4001, "캠페인 데이터 오류", "validate_campaign", "캠페인 구성 데이터가 비어 있거나 올바르지 않습니다.", ("문구/이미지 없음",), ("캠페인 구성 확인",)),
    4101: StatusInfo(4101, "문구 입력 실패", "input_text", "카카오톡 문구 입력에 실패했습니다.", ("클립보드 실패", "입력창 포커스 실패"), ("카카오톡 창 상태 확인",)),
    4201: StatusInfo(4201, "이미지 첨부 실패", "attach_image", "이미지를 카카오톡에 첨부하지 못했습니다.", ("이미지 변환 실패", "첨부창 제어 실패"), ("이미지 파일 확인", "카카오톡 재실행")),
    4202: StatusInfo(4202, "이미지 파일 없음", "load_image", "캠페인 이미지 파일 또는 이미지 데이터가 없습니다.", ("이미지 삭제됨", "캠페인 데이터 손상"), ("이미지 교체",)),
    4301: StatusInfo(4301, "업로드 타임아웃", "upload_wait", "파일 업로드 완료 신호를 제한 시간 안에 확인하지 못했습니다.", ("네트워크 지연", "PC 부하", "카카오톡 업로드 지연"), ("카카오톡 상태 확인", "잠시 후 F9로 재개")),
    4302: StatusInfo(4302, "업로드 파이프라인 정지", "upload_pipeline", "파일 업로드가 진행 중인 상태로 파이프라인이 멈춘 것으로 보입니다.", ("업로드 지연", "카카오톡 세션 불안정", "채팅창 닫기 충돌"), ("카카오톡 재로그인", "F9로 재개")),
    4303: StatusInfo(4303, "채팅창 종료 실패", "close_chat", "업로드 또는 카카오톡 응답 문제로 채팅창을 닫지 못했습니다.", ("전송 중인 파일 팝업", "카카오톡 응답 없음"), ("카카오톡 재로그인", "F9로 재개")),
    5001: StatusInfo(5001, "전송 동작 실패", "send", "전송 버튼/엔터 동작이 완료되지 않았습니다.", ("카카오톡 UI 응답 지연", "대화창 닫힘"), ("속도 모드 낮추기", "다시 발송")),
    5002: StatusInfo(5002, "엔터 입력 실패", "press_enter", "엔터 입력 전송에 실패했습니다.", ("입력창 포커스 상실",), ("카카오톡 창 확인",)),
    5003: StatusInfo(5003, "클립보드 전송 실패", "clipboard", "클립보드 복사/붙여넣기 과정에 실패했습니다.", ("클립보드 점유", "보안 프로그램 간섭"), ("잠시 후 재시도",)),
    6001: StatusInfo(6001, "사용자 중지", "user_stop", "사용자가 발송을 중지했습니다."),
    6002: StatusInfo(6002, "사용자 취소", "user_cancel", "사용자가 작업을 취소했습니다."),
    7001: StatusInfo(7001, "재시도 후 실패", "retry", "재시도 후에도 발송에 실패했습니다.", ("일시 오류 지속",), ("실패 대상 재시도",)),
    7002: StatusInfo(7002, "최대 재시도 초과", "retry", "설정된 최대 재시도 횟수를 초과했습니다.", ("카카오톡 응답 없음",), ("속도 모드 낮추기", "카카오톡 재실행")),
    9000: StatusInfo(9000, "알 수 없는 오류", "unknown", "분류되지 않은 오류입니다."),
    9001: StatusInfo(9001, "예외 발생", "exception", "예외가 발생했습니다."),
    9002: StatusInfo(9002, "DB 오류", "database", "DB 처리 중 오류가 발생했습니다."),
    9003: StatusInfo(9003, "설정 오류", "settings", "설정값이 올바르지 않습니다."),
}


def get_status_info(code: int) -> StatusInfo:
    return STATUS_CODES.get(int(code), STATUS_CODES[9000])


def status_from_result(status: str, reason: str = "") -> StatusInfo:
    s = str(status or "").upper()
    r = str(reason or "").lower()
    if s.startswith("SUCCESS"):
        return STATUS_CODES[1000]
    if "OPEN_CHAT_FAIL" in s or "open_chat_fail" in r:
        return STATUS_CODES[3002]
    if s == "SKIP" or "empty_name" in r:
        return STATUS_CODES[3101]
    if "IMAGE_FILE_NOT_FOUND" in s or "image_file_not_found" in r or "file_not_found" in r:
        return STATUS_CODES[4202]
    if "NOT_FOUND" in s or "not_found" in r or ("chat" in r and "not" in r):
        return STATUS_CODES[3001]
    if "IMAGE_ATTACH_FAILED" in s or "image_attach_failed" in r:
        return STATUS_CODES[4201]
    if "UPLOAD_TIMEOUT" in s or "upload_timeout" in r:
        return STATUS_CODES[4301]
    if "UPLOAD_PIPELINE_STALLED" in s or "upload_pipeline_stalled" in r:
        return STATUS_CODES[4302]
    if "CHAT_CLOSE_TIMEOUT" in s or "chat_close_timeout" in r:
        return STATUS_CODES[4303]
    if "SEND_ACTION_FAILED" in s or "send_action_failed" in r:
        return STATUS_CODES[5001]
    if "TAIL_RETRY" in s and "FAIL" in s:
        return STATUS_CODES[7001]
    if "STOP" in s or "user_stop" in r or "사용자 중지" in reason:
        return STATUS_CODES[6001]
    if "image" in r or "이미지" in reason:
        return STATUS_CODES[4201]
    if "clipboard" in r or "클립보드" in reason:
        return STATUS_CODES[5003]
    if "enter" in r or "엔터" in reason:
        return STATUS_CODES[5002]
    if s.startswith("FAIL"):
        return STATUS_CODES[5001]
    return STATUS_CODES[9000]


def detail_text(code: int) -> str:
    info = get_status_info(code)
    lines = [f"[{info.code}] {info.message}", "", info.detail]
    if info.causes:
        lines += ["", "가능한 원인", *[f"- {x}" for x in info.causes]]
    if info.actions:
        lines += ["", "권장 조치", *[f"- {x}" for x in info.actions]]
    return "\n".join(lines)
