import sys
import defusedxml.ElementTree as ET
for tc in ET.parse(sys.argv[1]).getroot().iter("testcase"):
    if any(c.tag in ("failure", "error") for c in tc): print(f"{tc.get('classname')}::{tc.get('name')}")
