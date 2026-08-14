# -*- coding: utf-8 -*-
import sys
from solo import code_review as cr
files = sys.argv[1:]
for f in files:
    res = cr.review_file(f)
    print("="*64)
    print(f, "score=", res["static_score"])
    seen = set()
    for i in res["static_issues"]:
        key = (i["severity"], i["title"], i.get("line"))
        if key in seen:
            continue
        seen.add(key)
        print("  [%s] L%s: %s" % (i["severity"], i.get("line"), i["title"]))
