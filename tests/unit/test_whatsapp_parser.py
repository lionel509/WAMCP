import json
import pytest
from app.services.whatsapp_parser import parse_webhook_payload
from pathlib import Path

FIXTURES_DIR = Path("tests/fixtures/whatsapp/raw")

def load_fixture(filename):
    with open(FIXTURES_DIR / filename, "r") as f:
        return json.load(f)

def test_parse_individual_text_unwrapped():
    payload = load_fixture("text_message_unwrapped_individual.json")
    events = parse_webhook_payload(payload)
    
    assert len(events) == 1
    event = events[0]
    
    assert event.message_id == "wamid.HBgLMTUxNikwMDc4MTAVAaASGBQzQUI5MkM5QTMyREQ4RTJGNUYzQQA="
    assert event.sender_participant_id == "15555555555"
    assert event.text_body == "Test"
    assert event.conversation_type == "individual"
    # Derived key check: biz_id:participant_id
    assert event.conversation_id == "875171289009578:15555555555"
    assert event.sender_display_name == "Lionel Weng"

def test_parse_individual_text_enveloped():
    payload = load_fixture("text_message_enveloped_individual.json")
    events = parse_webhook_payload(payload)
    
    assert len(events) == 1
    event = events[0]
    
    # Should be identical to unwrapped result logic
    assert event.message_id == "wamid.HBgLMTUxNikwMDc4MTAVAaASGBQzQUI5MkM5QTMyREQ4RTJGNUYzQQA="
    assert event.conversation_id == "875171289009578:15555555555"
    assert event.text_body == "Test"

def test_parse_group_text_enveloped():
    payload = load_fixture("text_message_enveloped_group.json")
    events = parse_webhook_payload(payload)
    
    assert len(events) == 1
    event = events[0]
    
    assert event.conversation_type == "group"
    assert event.conversation_id == "120363023456789@g.us"
    assert event.sender_participant_id == "15555555555"
    assert event.text_body == "Hello Group"

def test_parse_group_status_sent():
    payload = load_fixture("status_group_sent_enveloped.json")
    events = parse_webhook_payload(payload)
    
    assert len(events) == 1
    event = events[0]
    
    assert event.message_id == "wamid.HBgLMTUxNikwMDc4MTAVAaASGBQzQUI5MkM5QTMyREQ4RTJGNUYzQQA="
    assert event.status == "sent"
    assert event.conversation_type == "group"
    assert event.conversation_id == "120363023456789@g.us"

def test_parse_unsupported_group_message():
    payload = load_fixture("unsupported_message_group_enveloped.json")
    events = parse_webhook_payload(payload)
    
    assert len(events) == 1
    event = events[0]
    
    assert event.message_type == "unsupported"
    assert len(event.errors) > 0
    assert event.errors[0]["code"] == 131051
