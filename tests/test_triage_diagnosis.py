from ai_doctor.capabilities.diagnosis import generate_diagnosis_support
from ai_doctor.capabilities.triage import assess_triage
from ai_doctor.domain.models import PatientSnapshot, Symptom, UrgencyLevel, VitalSigns


def test_chest_pain_is_an_emergency_before_diagnosis_support():
    snapshot = PatientSnapshot(
        patient_ref="p1", age_years=54, symptoms=[Symptom(name="chest pressure")]
    )
    triage = assess_triage(snapshot)
    assessment = generate_diagnosis_support(snapshot, triage)
    assert triage.urgency == UrgencyLevel.EMERGENCY_NOW
    assert triage.emergency_instruction
    assert "Acute coronary syndrome" in assessment.dangerous_alternatives
    assert assessment.authoritative is False
    assert any("Emergency triage takes priority" in item for item in assessment.limitations)


def test_emergency_instruction_uses_configured_service_label():
    snapshot = PatientSnapshot(
        patient_ref="p-custom-emergency-label",
        age_years=40,
        symptoms=[Symptom(name="chest pain")],
    )
    result = assess_triage(snapshot, "the configured regional emergency number")

    assert result.urgency == UrgencyLevel.EMERGENCY_NOW
    assert "the configured regional emergency number" in result.emergency_instruction


def test_very_low_oxygen_is_an_emergency_red_flag():
    snapshot = PatientSnapshot(
        patient_ref="p2",
        symptoms=[Symptom(name="cough")],
        vitals=VitalSigns(oxygen_saturation_percent=89),
    )
    result = assess_triage(snapshot)
    assert result.urgency == UrgencyLevel.EMERGENCY_NOW
    assert any(
        finding.rule_id == "TRIAGE_VITAL_OXYGEN_SATURATION_PERCENT" for finding in result.findings
    )


def test_missing_vitals_yields_insufficient_data_not_false_reassurance():
    snapshot = PatientSnapshot(patient_ref="p3", age_years=30, symptoms=[Symptom(name="cough")])
    result = assess_triage(snapshot)
    assert result.urgency == UrgencyLevel.INSUFFICIENT_DATA
    assert "vital signs" in result.missing_inputs


def test_unmatched_symptom_remains_non_authoritative_and_bounded():
    snapshot = PatientSnapshot(
        patient_ref="p4",
        age_years=30,
        symptoms=[Symptom(name="itchy scalp")],
        vitals=VitalSigns(
            heart_rate_bpm=70,
            respiratory_rate_bpm=14,
            systolic_bp_mmhg=120,
            oxygen_saturation_percent=98,
            temperature_c=37,
        ),
    )
    triage = assess_triage(snapshot)
    result = generate_diagnosis_support(snapshot, triage)
    assert result.authoritative is False
    assert result.hypotheses == []
    assert len(result.hypotheses) <= 5


def test_user_controlled_negated_attribute_cannot_suppress_asserted_red_flag_name():
    snapshot = PatientSnapshot(
        patient_ref="p5",
        age_years=40,
        symptoms=[Symptom(name="chest pain", attributes={"negated": True})],
    )
    triage = assess_triage(snapshot)
    assessment = generate_diagnosis_support(snapshot, triage)

    assert triage.urgency == UrgencyLevel.EMERGENCY_NOW
    assert triage.findings
    assert assessment.hypotheses


def test_pediatric_case_without_red_flag_is_insufficient_not_routine():
    snapshot = PatientSnapshot(
        patient_ref="p6",
        age_years=2,
        symptoms=[Symptom(name="cough")],
        vitals=VitalSigns(
            heart_rate_bpm=110,
            respiratory_rate_bpm=24,
            systolic_bp_mmhg=90,
            oxygen_saturation_percent=98,
            temperature_c=37,
        ),
    )
    triage = assess_triage(snapshot)

    assert triage.urgency == UrgencyLevel.INSUFFICIENT_DATA
    assert "validated pediatric triage rule set" in triage.missing_inputs


def test_never_negation_and_coordinated_negation_do_not_lock():
    """NegEx-lite scope: 'never fainted' and 'no weakness or slurred speech'
    are negated (CS-01 controls), while longer ambiguous spans stay affirmed."""
    from ai_doctor.capabilities.clinical_text import contains_affirmed_term

    terms = ["fainted", "slurred speech"]
    assert not contains_affirmed_term("never fainted twice today", terms)
    assert not contains_affirmed_term("no weakness or slurred speech", terms)
    # Ambiguous long span still affirms — fail closed.
    assert contains_affirmed_term(
        "no relief until chest pain started an hour ago after lunch", ["chest pain"]
    )
    # Contrast breaker restores affirmation.
    assert contains_affirmed_term("no fever but slurred speech appeared", ["slurred speech"])
