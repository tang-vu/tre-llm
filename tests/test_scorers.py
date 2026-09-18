"""Tre Viet scorers: deterministic checks + rubric stays ungraded."""


from tre_llm.evaluation.scorers import grade
from tre_llm.schemas import EvalItem, EvalResult


def item(kind, expected=None, grading=None, **kw):
    return EvalItem(
        id="t.1", category="x", prompt="p", expected=expected,
        grading=grading or {"kind": kind}, **kw,
    )


def res(text):
    return EvalResult(item_id="t.1", response=text)


def test_exact():
    r = grade(item("exact", expected="Hà Nội"), res("Hà Nội"))
    assert r.passed and r.score == 1.0


def test_contains_accentless_match():
    r = grade(item("contains", expected=["Hà Nội", "Việt Nam"]), res("ha noi la thu do cua viet nam"))
    assert r.score == 1.0  # accent-folded matching


def test_numeric_finds_number():
    r = grade(item("numeric", expected="42"), res("Kết quả là 42 điểm."))
    assert r.passed


def test_json_schema_fields():
    r = grade(
        item("json_schema", expected={"fields": {"ten": "Nam", "tuoi": "30"}}),
        res('{"ten": "Nam", "tuoi": "30"}'),
    )
    assert r.passed, r.detail


def test_json_schema_missing_field():
    r = grade(
        item("json_schema", expected={"fields": {"ten": "Nam", "tuoi": "30"}}),
        res('{"ten": "Nam"}'),
    )
    assert not r.passed and "tuoi" in r.detail


def test_rubric_stays_ungraded_without_judge():
    r = grade(item("rubric", grading={"kind": "rubric", "rubric": "mạch lạc"}), res("văn hay"))
    assert r.score is None and r.passed is None
    assert r.grader == "rubric-ungraded"


def test_citation_rejects_phantom():
    r = grade(
        item("citation_exists", grading={"kind": "citation_exists", "valid_ids": ["1", "2"]}),
        res("Theo [1] và [9]..."),
    )
    assert not r.passed  # [9] không tồn tại


def test_citation_unanswerable_expected():
    r = grade(
        item("citation_exists", grading={"kind": "citation_exists", "expect_unanswerable": True}),
        res("Tài liệu không có thông tin này."),
    )
    assert r.passed


class _FakeJudge:
    def __init__(self, text):
        self._text = text

    def generate(self, req):
        from tre_llm.inference.client import GenerationResult

        return GenerationResult(text=self._text)


def test_rubric_graded_by_judge():
    judge = _FakeJudge('{"score": 2, "nhan_xet": "đủ ý, mạch lạc"}')
    r = grade(
        item("rubric", grading={"kind": "rubric", "rubric": "mạch lạc"}),
        res("văn hay"),
        judge_client=judge, judge_model="judge-model",
    )
    assert r.score == 1.0 and r.passed
    assert r.grader == "judge:judge-model"
    assert "đủ ý" in r.detail


def test_rubric_judge_partial_score():
    judge = _FakeJudge('{"score": 1}')
    r = grade(
        item("rubric", grading={"kind": "rubric", "rubric": "x"}),
        res("ok"),
        judge_client=judge, judge_model="j",
    )
    assert r.score == 0.5 and r.passed  # 1/2 = đạt một phần vẫn tính pass


def test_rubric_judge_bad_output_falls_back_ungraded():
    judge = _FakeJudge("không phải JSON")
    r = grade(
        item("rubric", grading={"kind": "rubric", "rubric": "x"}),
        res("ok"),
        judge_client=judge, judge_model="j",
    )
    assert r.score is None and r.grader == "rubric-ungraded"
    assert "parse" in r.detail


def test_rubric_judge_truncated_json_still_scored():
    # Model nhỏ hay viết nhan_xet dài → JSON cụt đuôi, nhưng "score" vẫn bắt được
    judge = _FakeJudge('{"score": 2, "nhan_xet": "Quang hợp là quá trình dài...')
    r = grade(
        item("rubric", grading={"kind": "rubric", "rubric": "x"}),
        res("ok"),
        judge_client=judge, judge_model="j",
    )
    assert r.score == 1.0 and r.passed and r.grader == "judge:j"
