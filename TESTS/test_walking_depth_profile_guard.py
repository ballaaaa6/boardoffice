from pathlib import Path

from VALIDATION.walking_depth_profile_guard import audit


ROOT = Path(__file__).resolve().parents[1]


def test_unprofiled_front_envelope_guard_is_clean_across_all_floors():
    report = audit(ROOT, write_report=False)

    assert report['status'] == 'PASS'
    assert report['checked_floor_count'] == 25
    assert report['unprofiled_front_envelope_issue_count'] == 0
    assert report['candidate_counts_by_object_type'] == {}
    assert report['profiled_row_count'] > 0
