"""Kernel-bounded validator/selector for one SWPC RTSW JSON document."""
from __future__ import annotations
import json, math, sys
from datetime import UTC, datetime
from typing import Mapping
from ingest.adapters.swpc import RTSW_MAG_FIELDS, _parse_platform_records, _records
from ingest.space_weather import parse_time

MAX_ROWS = 20_000

def validated(raw: bytes):
    payload = json.loads(raw)
    if not isinstance(payload, list) or len(payload) > MAX_ROWS:
        raise ValueError("native row list is missing or exceeds row ceiling")
    expected = {"time_tag", "source", *(field.name for field in RTSW_MAG_FIELDS)}
    seen = set()
    for i, row in enumerate(payload):
        if not isinstance(row, Mapping): raise ValueError(f"row {i} is not an object")
        missing = expected-set(row)
        if missing: raise ValueError(f"row {i} is missing native fields: {', '.join(sorted(missing))}")
        stamp=parse_time(row["time_tag"]) if isinstance(row.get("time_tag"),str) else None
        if stamp is None or stamp.tzinfo is None: raise ValueError(f"row {i} has an invalid timestamp")
        if not isinstance(row.get("source"),str) or not row["source"]: raise ValueError(f"row {i} has invalid source")
        ident=(stamp,row["source"])
        if ident in seen: raise ValueError(f"row {i} duplicates native time/source identity")
        seen.add(ident)
        for field in RTSW_MAG_FIELDS:
            value=row[field.name]
            if field.name in {"active","manual_mode"}:
                if value is not None and not isinstance(value,bool): raise ValueError(f"row {i} native {field.name} is not boolean or null")
            elif value is not None and (isinstance(value,bool) or not isinstance(value,(int,float)) or not math.isfinite(float(value))):
                raise ValueError(f"row {i} native {field.name} is not finite numeric or null")
    rows=_records(payload,required=("time_tag","source","bz_gsm"))
    _parse_platform_records(rows,RTSW_MAG_FIELDS)
    return rows

def main():
    raw=sys.stdin.buffer.read()
    rows=validated(raw)
    at=sys.argv[2]
    if at == "validate":
        print(json.dumps({"rows":len(rows)})); return
    instant=datetime.fromisoformat(at).astimezone(UTC)
    candidates=[]
    for row in rows:
        stamp=parse_time(row["time_tag"]); bz=row["bz_gsm"]
        if stamp<=instant and isinstance(bz,(int,float)) and not isinstance(bz,bool) and math.isfinite(float(bz)):
            candidates.append((stamp,row["source"],row))
    if not candidates: raise ValueError("no finite native Bz row applies")
    newest=max(x[0] for x in candidates); choices=[(s,r) for t,s,r in candidates if t==newest]
    active=[x for x in choices if x[1]["active"] is True]
    source,row=sorted(active if len(active)==1 else choices,key=lambda x:x[0])[0]
    print(json.dumps({"time":newest.isoformat(),"source":source,"row":row,"active_count":len(active)},separators=(",",":")))

if __name__ == "__main__": main()
