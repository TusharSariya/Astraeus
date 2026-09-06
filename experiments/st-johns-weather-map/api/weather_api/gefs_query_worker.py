"""Bounded child for one selected GEFS run/lead family."""
import json, os, shutil, sys, tempfile, zipfile
from datetime import datetime
from pathlib import Path
from ingest.adapters.noaa_s3 import NOAAGEFSEnsembleAdapter
from weather_api.gefs_query import GEFSRequestKey, GEFSSelectedLoader, GEFS_OUTPUT_ALLOWANCE_BYTES

def main():
 output=Path(sys.argv[1]); request=json.loads(sys.stdin.buffer.read())
 key=GEFSRequestKey(request["run_id"],datetime.fromisoformat(request["run_time"]),int(request["lead"]),request["product_set"],tuple(request["members"]),tuple(request["fields"]),tuple((n,float(v)) for n,v in request["bounds"]),request["endpoint"])
 key.validate()
 if shutil.disk_usage(output.parent).free<GEFS_OUTPUT_ALLOWANCE_BYTES: raise RuntimeError("GEFS child workspace is below its output allowance")
 with tempfile.TemporaryDirectory(prefix="gefs-child-",dir=output.parent) as directory:
  client = None
  if evidence := os.environ.get("GEFS_CAPTURE_EVIDENCE_DIR"):
   from ingest.http import PoliteClient
   from weather_api.gefs_capture import GEFSAuditClient
   client = GEFSAuditClient(PoliteClient(), Path(evidence))
  entry=GEFSSelectedLoader(NOAAGEFSEnsembleAdapter(client=client,bounds=dict(key.bounds),capture_transport_receipts=True),Path(directory))(key)
  manifest={"run_id":key.run_id,"run_time":key.run_time.isoformat(),"lead":key.lead,"valid_time":entry.valid_time.isoformat(),"fetched_at":entry.fetched_at.isoformat(),"members_present":entry.members_present,"mandatory_failures":entry.mandatory_failures,"optional_absences":entry.optional_absences,"cloud_intervals":{m:[a.isoformat(),b.isoformat()] for m,(a,b) in entry.cloud_intervals.items()},"provenance":entry.provenance}
  with zipfile.ZipFile(output,"w",compression=zipfile.ZIP_STORED) as bundle:
   bundle.writestr("result.json",json.dumps(manifest,sort_keys=True))
   bundle.writestr("artifacts/noaa_gefs_members.zarr.zip",entry.payload)
if __name__=="__main__":main()
