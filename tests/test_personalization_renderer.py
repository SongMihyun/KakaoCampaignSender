from __future__ import annotations

from types import SimpleNamespace

from backend.domains.personalization import render_personalized_text


def _contact(**overrides):
    values = {
        "name": "MZ24019 김민수",
        "customer_name": "김민수",
        "customer_honorific": "대표님",
        "customer_position": "대표",
        "agency": "강남대리점",
        "branch": "서울지사",
        "phone": "010-1111-2222",
    }
    values.update(overrides)
    return SimpleNamespace(**values)


def _sender(**overrides):
    values = {
        "sender_name": "송미현",
        "sender_position": "팀장",
        "sender_company": "메리츠화재 강남지점",
        "sender_branch": "강남지점",
        "sender_phone": "010-9999-0000",
        "default_signature": "메리츠화재 송미현 드림",
    }
    values.update(overrides)
    return SimpleNamespace(**values)


def test_customer_name_and_honorific_are_rendered():
    result = render_personalized_text(
        "{{고객명}} {{고객호칭}}, 안녕하세요",
        contact=_contact(),
        sender_profile=_sender(),
    )

    assert result.rendered_text == "김민수 대표님, 안녕하세요"
    assert result.used_variables == ["고객명", "고객호칭"]
    assert result.missing_variables == []
    assert result.unknown_variables == []


def test_kakao_search_name_and_customer_name_are_separate():
    result = render_personalized_text(
        "검색명: {{카카오톡검색명}}\n메시지명: {{고객명}} {{고객호칭}}",
        contact=_contact(),
        sender_profile=_sender(),
    )

    assert result.rendered_text == "검색명: MZ24019 김민수\n메시지명: 김민수 대표님"
    assert result.used_variables == ["카카오톡검색명", "고객명", "고객호칭"]


def test_sender_profile_values_are_rendered():
    result = render_personalized_text(
        "{{발신자소속}} {{발신자직책}} {{발신자명}}입니다.",
        contact=_contact(),
        sender_profile=_sender(),
    )

    assert result.rendered_text == "메리츠화재 강남지점 팀장 송미현입니다."
    assert result.used_variables == ["발신자소속", "발신자직책", "발신자명"]


def test_empty_supported_value_is_missing_and_replaced_with_empty_text():
    result = render_personalized_text(
        "직책: {{고객직책}}",
        contact=_contact(customer_position=""),
        sender_profile=_sender(),
    )

    assert result.rendered_text == "직책: "
    assert result.used_variables == ["고객직책"]
    assert result.missing_variables == ["고객직책"]
    assert result.unknown_variables == []


def test_unknown_variable_is_preserved():
    result = render_personalized_text(
        "{{고객명}}님 {{갱신일}} 안내드립니다.",
        contact=_contact(),
        sender_profile=_sender(),
    )

    assert result.rendered_text == "김민수님 {{갱신일}} 안내드립니다."
    assert result.used_variables == ["고객명"]
    assert result.missing_variables == []
    assert result.unknown_variables == ["갱신일"]


def test_plain_text_without_variables_is_returned_as_is():
    result = render_personalized_text(
        "안녕하세요. 안내드립니다.",
        contact=_contact(),
        sender_profile=_sender(),
    )

    assert result.rendered_text == "안녕하세요. 안내드립니다."
    assert result.used_variables == []
    assert result.missing_variables == []
    assert result.unknown_variables == []


def test_repeated_variable_is_replaced_every_time_but_reported_once():
    result = render_personalized_text(
        "{{고객명}}님 {{고객명}}님께 다시 안내드립니다.",
        contact=_contact(),
        sender_profile=_sender(),
    )

    assert result.rendered_text == "김민수님 김민수님께 다시 안내드립니다."
    assert result.used_variables == ["고객명"]


def test_dict_inputs_and_explicit_variable_overrides_are_supported():
    result = render_personalized_text(
        "{{고객소속}} {{지사명}} {{기본서명}}",
        contact={"agency": "서초대리점", "branch": "서초지사"},
        sender_profile={"default_signature": "기본 서명"},
        variable_values={"기본서명": "override signature"},
    )

    assert result.rendered_text == "서초대리점 서초지사 override signature"
    assert result.used_variables == ["고객소속", "지사명", "기본서명"]


def test_none_template_is_treated_as_empty_text():
    result = render_personalized_text(None, contact=_contact(), sender_profile=_sender())

    assert result.rendered_text == ""
    assert result.used_variables == []
