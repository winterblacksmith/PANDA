from grounded_answers import AI_UNAVAILABLE_PREFIX, grounded_answer, unsupported_numbers

FACTS = {"matching_records": 68211, "percent_of_dataset": 100.0, "top_species": {"Live oak": 17126},
         "map": {"created": False, "reason": "No usable coordinate columns were detected in this CSV."}}


def test_rounded_numbers_are_accepted_and_invented_ones_rejected():
    facts = '{"records": 68211, "volume": 1650515771, "share": 0.579}'
    assert unsupported_numbers("About 68,000 trees (68k), 1.65 billion cu ft, 57.9% conifer.", facts) == []
    assert unsupported_numbers("There are 75,000 trees.", facts) == [75000.0]
    assert unsupported_numbers("Top 5 species across 3 classes.", facts) == []  # small counts allowed


def test_model_answer_is_used_when_grounded():
    calls = []
    def chat(model, messages, options=None):
        calls.append(messages)
        return "I couldn't draw a map: this CSV has no latitude/longitude columns. It holds 68,211 trees; Live oak leads with 17,126."
    text, ai = grounded_answer(chat, "m", "can you map this data", FACTS, "TEMPLATE")
    assert ai and "map" in text and "TEMPLATE" not in text
    assert "Verified facts" in calls[0][-1]["content"]


def test_invented_number_triggers_one_correction():
    replies = iter(["There are 90,000 trees.", "There are 68,211 trees."])
    seen = []
    def chat(model, messages, options=None):
        seen.append(messages[-1]["content"])
        return next(replies)
    text, ai = grounded_answer(chat, "m", "how many trees", FACTS, "TEMPLATE")
    assert ai and text == "There are 68,211 trees."
    assert "90,000" in seen[1]


def test_unreachable_model_is_labelled():
    text, ai = grounded_answer(lambda *a, **k: "", "m", "q", FACTS, "Found 68,211 records.")
    assert not ai and text.startswith(AI_UNAVAILABLE_PREFIX) and text.endswith("Found 68,211 records.")
