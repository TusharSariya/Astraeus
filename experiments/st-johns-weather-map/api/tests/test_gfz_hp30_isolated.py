from __future__ import annotations

import json, os, subprocess, sys
from datetime import datetime, timezone
from pathlib import Path

import pytest, xarray, zarr

from ingest import gfz_hp30_isolated
from ingest.adapters.gfz import GFZ_DOCUMENT_BYTES, GFZ_OUTPUT_BYTES, GFZHp30Adapter
from ingest.contract import AdapterUnavailable, FetchWindow


def payload(rows=2):
    return {"Hp30":[1.0,None][:rows],"datetime":["2026-09-06T00:00:00Z","2026-09-06T00:30:00Z"][:rows],"meta":{"license":"CC BY 4.0","source":"GFZ Potsdam"}}


def run(tmp_path, action, body):
    output=tmp_path/'hp30.zip'
    result=subprocess.run([sys.executable,"-m","ingest.gfz_hp30_isolated",action,str(output)],input=json.dumps(body).encode(),capture_output=True,
        env={**os.environ,"PYTHONPATH":str(Path(gfz_hp30_isolated.__file__).resolve().parents[1])})
    return result,output


def test_child_preserves_every_row_and_gap(tmp_path):
    result,output=run(tmp_path,"normalize",payload()); assert result.returncode==0
    assert json.loads(result.stdout)["count"]==2
    store=zarr.storage.ZipStore(str(output),mode="r"); ds=xarray.open_zarr(store,consolidated=False)
    assert ds.sizes["valid_time"]==2 and ds.hp30_index.values[0]==1.0 and str(ds.hp30_index.values[1])=='nan'; store.close()


@pytest.mark.parametrize("body",[
    {"Hp30":[1],"datetime":["bad"],"meta":{"license":"CC BY 4.0"}},
    {"Hp30":[1],"datetime":[],"meta":{"license":"CC BY 4.0"}},
    {"Hp30":[1],"datetime":["2026-09-06T00:00:00Z"],"meta":{"license":"CC BY 4.0"},"extra":1},
    {"Hp30":[1],"datetime":["2026-09-06T00:00:00Z"],"meta":{"license":"other"}},
    {"Hp30":[float("inf")],"datetime":["2026-09-06T00:00:00Z"],"meta":{"license":"CC BY 4.0","source":"GFZ Potsdam"}},
    {"Hp30":["NaN"],"datetime":["2026-09-06T00:00:00Z"],"meta":{"license":"CC BY 4.0","source":"GFZ Potsdam"}},
])
def test_child_refuses_any_bad_row_or_field_without_output(tmp_path,body):
    result,output=run(tmp_path,"normalize",body); assert result.returncode!=0 and not output.exists()


def test_operation_bounds_cover_document_output_and_block_allowance(monkeypatch):
    monkeypatch.setattr(GFZHp30Adapter,"_run_isolated",staticmethod(lambda *_: None))
    bounds=GFZHp30Adapter().operation_bounds(FetchWindow(datetime(2026,9,6,tzinfo=timezone.utc)))
    assert (bounds.received_bytes,bounds.store_bytes,bounds.filesystem_bytes,bounds.margin_bytes)==(GFZ_DOCUMENT_BYTES,GFZ_OUTPUT_BYTES,GFZ_OUTPUT_BYTES,4096)


def test_operation_preflight_refuses_kernel_before_network(monkeypatch):
    monkeypatch.setattr(GFZHp30Adapter,"_run_isolated",staticmethod(lambda *_: (_ for _ in ()).throw(RuntimeError("unsupported limits"))))
    with pytest.raises(RuntimeError,match="unsupported limits"):
        GFZHp30Adapter().operation_bounds(FetchWindow(datetime(2026,9,6,tzinfo=timezone.utc)))


@pytest.mark.skipif(sys.platform!='linux',reason='target Linux kernel limits')
def test_real_linux_adapter_limits_and_cleanup(tmp_path):
    adapter=GFZHp30Adapter(); adapter._run_isolated('probe',b'',None)
    raw=json.dumps(payload(),separators=(',',':')).encode(); exact=raw+b' '*(GFZ_DOCUMENT_BYTES-len(raw))
    result=adapter._run_isolated('normalize',exact,tmp_path/'ok.zip'); assert result.output_path.exists()
    with pytest.raises(Exception): adapter._run_isolated('inspect',exact+b' ',None)
    failed=tmp_path/'failed.zip'
    with pytest.raises(Exception): adapter._run_isolated('normalize',b'x'*GFZ_DOCUMENT_BYTES,failed)
    assert not failed.exists()
    assert not list(tmp_path.glob('bounded-decode-*'))
