from fdpo.eval.evaluator import EvalRow, EvalResult

rows = [
    EvalRow("a", "A", "A", True, "x"),                 # correct
    EvalRow("b", "B", "A", False, "x"),                # wrong
    EvalRow("c", None, "A", False, "", blocked=True),  # content-filter block
]
r = EvalResult(rows)
print("accuracy   :", r.accuracy, "(expect 0.5 = 1 correct / 2 evaluated)")
print("n_blocked  :", r.n_blocked, "(expect 1)")
print("n_evaluated:", r.n_evaluated, "(expect 2)")
print("xfail      :", r.extraction_failures, "(expect 0 -- block is not a parse fail)")
print("wrong_ids  :", r.wrong_ids(), "(expect {'b'} -- block excluded)")
print("correct_ids:", r.correct_ids(), "(expect {'a'})")
