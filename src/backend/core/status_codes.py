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
    1000: StatusInfo(1000, "성공", "result", "모든 발송 단계가 정상 완료되었습니다."),
    2001: StatusInfo(2001, "카카오톡 실행 안 됨", "check_kakao", "카카오톡 PC 창을 찾을 수 없습니다.", ("카카오톡 PC가 꺼져 있음",), ("카카오톡 PC 실행 후 다시 시도",)),
    2002: StatusInfo(2002, "카카오톡 로그인 필요", "check_login", "카카오톡 로그인이 필요합니다.", ("로그아웃 상태", "잠금 화면"), ("카카오톡 로그인 확인",)),
    2003: StatusInfo(2003, "카카오톡 창 인식 실패", "detect_window", "카카오톡 창을 제어할 수 없습니다.", ("창 최소화", "권한 문제"), ("카카오톡을 화면 앞으로 가져온 뒤 재시도",)),
    3001: StatusInfo(3001, "채팅방을 찾을 수 없음", "open_chat", "대상자 이름으로 채팅방을 찾지 못했습니다.", ("카카오톡 미로그인", "채팅방 이름 변경", "대상자 정보 오류"), ("채팅방 검색 테스트", "대상자 이름 확인")),
    3002: StatusInfo(3002, "채팅방 열기 실패", "open_chat", "검색된 채팅방을 열지 못했습니다.", ("검색 결과 선택 실패", "카카오톡 UI 응답 지연"), ("카카오톡 재시작", "속도 모드 낮추기")),
    3101: StatusInfo(3101, "대상자 정보 오류", "validate_recipient", "대상자 이름/전화번호 등 필수 정보가 올바르지 않습니다.", ("이름 공백", "잘못된 대상자 데이터"), ("대상자 정보 수정",)),
    3102: StatusInfo(3102, "대상자 중복 오류", "validate_recipient", "대상자 중복 데이터가 감지되었습니다.", ("사번 또는 전화번호 중복",), ("대상자 중복 정리",)),
    4001: StatusInfo(4001, "캠페인 데이터 오류", "validate_campaign", "캠페인 구성 데이터가 비어 있거나 올바르지 않습니다.", ("문구/이미지 없음",), ("캠페인 구성 확인",)),
    4101: StatusInfo(4101, "문구 입력 실패", "input_text", "카카오톡 문구 입력에 실패했습니다.", ("클립보드 실패", "입력창 포커스 실패"), ("카카오톡 창 상태 확인",)),
    4201: StatusInfo(4201, "이미지 첨부 실패", "attach_image", "이미지/파일 첨부 단계에서 일반 실패가 발생했습니다.", ("이미지 변환 실패", "첨부창 제어 실패"), ("이미지 파일 확인", "카카오톡 재시작")),
    4202: StatusInfo(4202, "이미지 파일 없음", "load_image", "캠페인 이미지 파일 또는 이미지 데이터가 없습니다.", ("이미지 삭제", "캠페인 데이터 손상"), ("이미지 교체",)),
    4210: StatusInfo(4210, "파일 없음", "load_file", "첨부할 이미지/파일을 찾을 수 없습니다.", ("파일 삭제", "OneDrive 동기화 지연", "경로 변경"), ("캠페인 이미지 교체", "파일 위치 확인")),
    4211: StatusInfo(4211, "파일 선택창 열기 실패", "file_dialog_open", "파일 선택창이 열리지 않았거나 감지되지 않았습니다.", ("카카오톡 창 포커스 손실", "Windows 파일창 응답 지연"), ("카카오톡 재실행", "속도 NORMAL/SLOW로 재시도")),
    4212: StatusInfo(4212, "파일 경로 입력 실패", "file_dialog_input", "파일 선택창에 경로를 입력하지 못했습니다.", ("입력칸 포커스 실패", "클립보드 설정 실패", "특수문자/긴 경로 문제"), ("파일 경로 단순화", "OneDrive 로컬 동기화 확인")),
    4213: StatusInfo(4213, "파일 열기 버튼 실패", "file_dialog_submit", "파일 선택창에서 열기/Enter 동작이 완료되지 않았습니다.", ("열기 버튼 비활성", "파일창이 닫히지 않음"), ("파일 접근 권한 확인", "카카오톡 재실행")),
    4214: StatusInfo(4214, "업로드 시작 감지 실패", "upload_start", "파일 선택 후 카카오톡 업로드가 시작된 흔적을 확인하지 못했습니다.", ("선택창만 닫힘", "카카오톡 포커스 손실"), ("카카오톡 창 상태 확인", "다시 발송")),
    4215: StatusInfo(4215, "업로드 타임아웃", "upload_wait", "카카오톡 파일 업로드가 제한 시간 안에 끝나지 않았습니다.", ("네트워크 지연", "PC 부하", "카카오톡 업로드 지연"), ("카카오톡 재로그인", "F9로 재개")),
    4216: StatusInfo(4216, "카카오톡 창 포커스 손실", "focus_chat", "파일 첨부 중 카카오톡 채팅창 포커스가 사라졌습니다.", ("다른 창 활성화", "사용자 입력 간섭"), ("발송 중 PC 조작 중지", "카카오톡 창 앞으로 이동")),
    4217: StatusInfo(4217, "파일 경로 클립보드 설정 실패", "clipboard_path", "파일 경로를 클립보드에 넣지 못했습니다.", ("클립보드 점유", "보안 프로그램 간섭"), ("잠시 후 재시도", "클립보드 사용 앱 종료")),
    4218: StatusInfo(4218, "파일 선택창 알 수 없는 상태", "file_dialog_unknown", "파일 선택/업로드 단계에서 분류되지 않은 상태가 발생했습니다.", ("Windows 파일창 비정상 상태", "카카오톡 UI 변경"), ("오류내용 운영자에게 보내기",)),
    4219: StatusInfo(4219, "임시 첨부 파일 복사 실패", "attach_temp_copy", "첨부 파일을 안정적인 임시 경로로 복사하지 못했습니다.", ("원본 파일 접근 권한 문제", "OneDrive 동기화 지연", "디스크 공간 부족"), ("원본 파일 위치 확인", "잠시 후 다시 발송")),
    4220: StatusInfo(4220, "다중 파일 경고 확인 실패", "file_dialog_warning", "Windows 다중 파일 경고창을 확인하지 못했습니다.", ("확인 버튼 감지 실패", "경고창 응답 지연"), ("카카오톡/파일 선택창 상태 확인", "다시 발송")),
    4221: StatusInfo(4221, "카카오 파일 전송 창 미감지", "file_transfer_dialog", "경고창 또는 파일 선택 후 카카오톡 파일 전송 창이 나타나지 않았습니다.", ("파일 선택창만 닫힘", "카카오톡 포커스 손실", "카카오톡 UI 응답 지연"), ("카카오톡 창 상태 확인", "속도 모드 낮추기")),
    4222: StatusInfo(4222, "첨부 개수 불일치", "file_transfer_count", "예상 첨부 개수와 카카오톡 전송 버튼의 개수가 일치하지 않습니다.", ("일부 파일 선택 실패", "카카오톡 전송창 갱신 지연"), ("캠페인 이미지 개수 확인", "다시 발송")),
    4223: StatusInfo(4223, "파일 전송 버튼 감지 실패", "file_transfer_button", "카카오톡 파일 전송 창의 전송 버튼을 누르지 못했습니다.", ("전송 버튼 비활성", "카카오톡 UI 변경", "포커스 손실"), ("카카오톡 창 상태 확인", "다시 발송")),
    4301: StatusInfo(4301, "업로드 타임아웃", "upload_wait", "파일 업로드 완료 신호를 제한 시간 안에 확인하지 못했습니다.", ("네트워크 지연", "PC 부하", "카카오톡 업로드 지연"), ("카카오톡 상태 확인", "일시정지 후 F9로 재개")),
    4302: StatusInfo(4302, "업로드 파이프라인 정지", "upload_pipeline", "파일 업로드가 진행 중인 상태로 파이프라인이 멈춘 것으로 보입니다.", ("업로드 지연", "카카오톡 세션 불안정", "채팅창 닫기 충돌"), ("카카오톡 재로그인", "F9로 재개")),
    4303: StatusInfo(4303, "채팅창 종료 실패", "close_chat", "업로드 또는 카카오톡 응답 문제로 채팅창을 닫지 못했습니다.", ("전송 중 파일 팝업", "카카오톡 응답 없음"), ("카카오톡 재로그인", "F9로 재개")),
    5001: StatusInfo(5001, "전송 동작 실패", "send", "전송 버튼/엔터 동작이 완료되지 않았습니다.", ("카카오톡 UI 응답 지연", "대화창 닫힘"), ("속도 모드 낮추기", "다시 발송")),
    5002: StatusInfo(5002, "엔터 입력 실패", "press_enter", "엔터 입력 전송에 실패했습니다.", ("입력창 포커스 상실",), ("카카오톡 창 확인",)),
    5003: StatusInfo(5003, "클립보드 전송 실패", "clipboard", "클립보드 복사/붙여넣기 과정에 실패했습니다.", ("클립보드 점유", "보안 프로그램 간섭"), ("잠시 후 재시도",)),
    6001: StatusInfo(6001, "사용자 중지", "user_stop", "사용자가 발송을 중지했습니다."),
    6002: StatusInfo(6002, "사용자 취소", "user_cancel", "사용자가 작업을 취소했습니다."),
    7001: StatusInfo(7001, "재시도 후 실패", "retry", "재시도 후에도 발송에 실패했습니다.", ("일시 오류 지속",), ("실패 대상 재발송",)),
    7002: StatusInfo(7002, "최대 재시도 초과", "retry", "설정된 최대 재시도 횟수를 초과했습니다.", ("카카오톡 응답 없음",), ("속도 모드 낮추기", "카카오톡 재시작")),
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
    if "FILE_NOT_FOUND" in s or "IMAGE_FILE_NOT_FOUND" in s or "image_file_not_found" in r or "file_not_found" in r:
        return STATUS_CODES[4210]
    if "FILE_DIALOG_NOT_OPENED" in s or "file_dialog_not_opened" in r:
        return STATUS_CODES[4211]
    if "FILE_DIALOG_PATH_INPUT_FAILED" in s or "file_dialog_path_input_failed" in r:
        return STATUS_CODES[4212]
    if "FILE_DIALOG_OPEN_BUTTON_FAILED" in s or "file_dialog_open_button_failed" in r:
        return STATUS_CODES[4213]
    if "MULTI_FILE_WARNING_CONFIRM_FAILED" in s or "multi_file_warning_confirm_failed" in r:
        return STATUS_CODES[4220]
    if "KAKAO_FILE_TRANSFER_DIALOG_NOT_FOUND" in s or "kakao_file_transfer_dialog_not_found" in r:
        return STATUS_CODES[4221]
    if "KAKAO_FILE_TRANSFER_COUNT_MISMATCH" in s or "kakao_file_transfer_count_mismatch" in r:
        return STATUS_CODES[4222]
    if "KAKAO_FILE_TRANSFER_BUTTON_NOT_FOUND" in s or "kakao_file_transfer_button_not_found" in r:
        return STATUS_CODES[4223]
    if "KAKAO_UPLOAD_NOT_STARTED" in s or "kakao_upload_not_started" in r:
        return STATUS_CODES[4214]
    if "KAKAO_UPLOAD_TIMEOUT" in s or "kakao_upload_timeout" in r:
        return STATUS_CODES[4215]
    if "KAKAO_WINDOW_FOCUS_LOST" in s or "kakao_window_focus_lost" in r:
        return STATUS_CODES[4216]
    if "IMAGE_PATH_CLIPBOARD_SET_FAILED" in s or "image_path_clipboard_set_failed" in r:
        return STATUS_CODES[4217]
    if "FILE_DIALOG_UNKNOWN_STATE" in s or "file_dialog_unknown_state" in r:
        return STATUS_CODES[4218]
    if "ATTACHMENT_TEMP_COPY_FAILED" in s or "attachment_temp_copy_failed" in r or "attach_temp_copy" in r:
        return STATUS_CODES[4219]
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
