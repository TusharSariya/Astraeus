"""Selected IFS records over existing bounded ECMWF transport and isolation.

Spec-Refs: GOV-SPEC-001, GOV-SPEC-004, GOV-SPEC-006.
"""
from collections import OrderedDict
from concurrent.futures import Future
from datetime import UTC, datetime, timedelta
import hashlib
import json
from pathlib import Path
import re
import sys
import tempfile
import threading
import time
from urllib.parse import urljoin

from registry.ifs import BOUNDS, FIELDS, PRODUCTS, field_selection
from ingest.adapters.ecmwf_opendata import ECMWF_OPEN_DATA_BASE, MAX_MEMBER_BYTES, _download_verified_range
from ingest.isolation import run_bounded_process
from .ecmwf_query import ECMWFHTTP, _Links, DECODE_LIMITS, MAX_OUTPUT_BYTES, MAX_METADATA_BYTES, MAX_INDEX_RECORDS
from .ifs_budget import SelectionBudget,SelectionStopped


class IFSUnavailable(ValueError):
    pass


def links(text, directory, pattern):
    parser = _Links(); parser.feed(text)
    result = []
    for href in parser.links:
        name = href.rstrip('/').rsplit('/',1)[-1]
        if re.fullmatch(pattern,name):
            url = urljoin(directory,href)
            if url == directory+name+('/' if href.endswith('/') else ''):
                result.append((name,url))
    return sorted(set(result),reverse=True)


def index_records(text, *, product, run, lead, definition, level, member):
    if len(text.encode()) > MAX_METADATA_BYTES or len(text.splitlines()) > MAX_INDEX_RECORDS:
        raise IFSUnavailable('inventory_bound')
    result=[]
    expected=PRODUCTS[product]
    for line in text.splitlines():
        if not line.strip(): continue
        row=json.loads(line)
        if not isinstance(row,dict): raise IFSUnavailable('inventory_unreadable')
        if row.get('param') not in [definition['parameter'], *definition.get('aliases',[])]: continue
        if row.get('levtype') != definition['level_type']: continue
        if definition['level_type'] != 'sfc' and str(row.get('levelist')) != str(level): continue
        raw_member=row.get('number')
        if expected['record_type']=='pf' and str(raw_member) != member: continue
        if expected['record_type']!='pf' and raw_member not in (None,0,'0'): raise IFSUnavailable('unexpected_member')
        if (row.get('class')!='od' or row.get('model','ifs')!='ifs' or row.get('stream')!=expected['stream']
            or row.get('type')!=expected['record_type'] or str(row.get('date'))!=run.strftime('%Y%m%d')
            or str(row.get('time')).zfill(4)!=run.strftime('%H%M')):
            raise IFSUnavailable('record_identity_mismatch')
        steps=str(row.get('step','')).split('-')
        if not all(s.isdigit() for s in steps) or len(steps)>2 or int(steps[-1])!=lead:
            if not all(s.isdigit() for s in steps) or len(steps)>2:raise IFSUnavailable('record_time_mismatch')
            continue
        offset,length=row.get('_offset'),row.get('_length')
        if type(offset) is not int or type(length) is not int or offset<0 or not 0<length<=MAX_MEMBER_BYTES:
            raise IFSUnavailable('record_range_invalid')
        result.append(row)
    if len(result)>1: raise IFSUnavailable('record_identity_ambiguous')
    if not result: raise IFSUnavailable('field_unpublished')
    return result[0]


class IFSNative:
    def __init__(self, *, client=None, clock=time.monotonic, now=lambda:datetime.now(UTC), decoder=None, base=ECMWF_OPEN_DATA_BASE):
        self.client,self.clock,self.now,self.decoder,self.base=client,clock,now,decoder,base.rstrip('/')+'/'
        self.lock=threading.Lock();self.cache=OrderedDict();self.inflight={};self.inventories=OrderedDict();self.indexes=OrderedDict()

    def transport(self,budget):
        return ECMWFHTTP(self.client,clock=self.clock,now=self.now,budget=budget)

    def inventory(self,product,budget,refresh=False):
        if product not in PRODUCTS: raise IFSUnavailable('unsupported_product')
        with self.lock:
            cached=self.inventories.get(product)
            if not refresh and cached and cached[0]>self.clock(): return cached[1]
        transport=self.transport(budget)
        try:
            dates=links(transport.get_text(self.base),self.base,r'\d{8}')[:4]
            runs=[]
            descriptor=PRODUCTS[product]
            for date,date_url in dates:
                cycles=links(transport.get_text(date_url),date_url,r'(00|06|12|18)z')
                for cycle,cycle_url in cycles:
                    run=datetime.strptime(date+cycle[:2],'%Y%m%d%H').replace(tzinfo=UTC)
                    directory=cycle_url+'ifs/0p25/'+descriptor['stream']+'/'
                    try: listing=transport.get_text(directory)
                    except Exception as error:
                        if getattr(getattr(error,'response',None),'status_code',None)==404: continue
                        raise
                    files={}
                    pattern=rf'{run:%Y%m%d%H%M%S}-(?:(\d+)h-)?{descriptor["stream"]}-{descriptor["file_type"]}\.{descriptor["format"]}'
                    for name,url in links(listing,directory,pattern):
                        match=re.fullmatch(pattern,name)
                        lead=int(match[1]) if match[1] else -1
                        files[lead]=url
                    if descriptor['record_type']=='ep':
                        native_files={}
                        for url in set(files.values()):
                            index,_=self.index(url,budget)
                            for line in index.splitlines():
                                if not line.strip():continue
                                row=json.loads(line)
                                if any(row.get('param')==f['parameter'] and product in f['products'] for f in FIELDS.values()):
                                    step=str(row.get('step','')).split('-')[-1]
                                    if step.isdigit():native_files[int(step)]=url
                        files=native_files
                    if files:
                        runs.append({'id':f'ifs:{product}:{run:%Y%m%d%H}','run_time':run.isoformat(),'files':files,
                                     'receipts':list(transport.receipts)})
                    if len(runs)>=12: break
                if len(runs)>=12: break
            with self.lock:
                self.inventories[product]=(self.clock()+60,runs)
                while len(self.inventories)>11:self.inventories.popitem(last=False)
            return runs
        except IFSUnavailable: raise
        except Exception as error:
            from .ifs_budget import SelectionStopped
            if isinstance(error,SelectionStopped):raise
            raise IFSUnavailable('inventory_unreadable') from error
        finally:
            if self.client is None:transport.client.close()

    def index(self,url,budget):
        with self.lock:
            cached=self.indexes.get(url)
            if cached and cached[0]>self.clock(): return cached[1:]
        transport=self.transport(budget)
        try:
            text=transport.get_text(url.removesuffix('.grib2')+'.index')
            receipts=list(transport.receipts)
            with self.lock:
                self.indexes[url]=(self.clock()+60,text,receipts)
                while sum(len(v[1].encode()) for v in self.indexes.values())>8*1024**2:self.indexes.popitem(last=False)
            return text,receipts
        finally:
            if self.client is None:transport.client.close()

    def record(self,product,run,lead,field,level,member,budget,_retry=True):
        budget.check()
        definition=field_selection(product,field,level)
        original_product=product
        mapped=member=='0' and PRODUCTS[product]['control_product'] is not None
        if mapped:
            product=PRODUCTS[product]['control_product']
            control_runs=self.inventory(product,budget)
            run=next((r for r in control_runs if r['run_time']==run['run_time']),None)
            if run is None:raise IFSUnavailable('control_unpublished')
        url=run['files'].get(lead)
        if url is None:raise IFSUnavailable('time_unpublished')
        identity=(product,run['run_time'],url,lead,field,level,member)
        with self.lock:
            cached=self.cache.get(identity)
            if cached and cached[0]>self.clock():
                self.cache.move_to_end(identity)
                from .ifs_budget import register_receipts
                register_receipts(budget,cached[1]['receipts'])
                return self._variant(cached[1],original_product,member,mapped)
            future=self.inflight.get(identity);owner=future is None
            if owner:
                future=Future();self.inflight[identity]=future
        if not owner:
            from concurrent.futures import TimeoutError
            while True:
                budget.check()
                try:return self._variant(future.result(timeout=.1),original_product,member,mapped)
                except TimeoutError:continue
                except SelectionStopped:
                    budget.check()
                    if not _retry:raise
                    return self.record(original_product,run,lead,field,level,member,budget,_retry=False)
        transport=self.transport(budget)
        try:
            text,index_receipts=self.index(url,budget)
            row=index_records(text,product=product,run=datetime.fromisoformat(run['run_time']),lead=lead,definition=definition,level=level,member=member)
            with budget.slots, tempfile.TemporaryDirectory(prefix='ifs-record-') as directory:
                budget.check()
                path=Path(directory)/'record.grib2'
                _download_verified_range(transport,url,path,(row['_offset'],row['_offset']+row['_length']-1))
                request={'product':product,'run_time':run['run_time'],'lead':lead,'field':field,'level':level,'member':member,
                         'record':row,'path':str(path),'bounds':BOUNDS}
                result=self.decoder(request) if self.decoder else self.decode(request,Path(directory)/'record.json')
            budget.check()
            result.update(product=product,run_id=run['id'],field=field,level=level,member=member,
                          retrieved_at=transport.receipts[-1]['completed_at'],expires_at=(datetime.fromisoformat(transport.receipts[-1]['completed_at'])+timedelta(seconds=600)).isoformat(),
                          receipts=index_receipts+transport.receipts)
            encoded=json.dumps(result,allow_nan=False).encode()
            if len(encoded)>MAX_OUTPUT_BYTES:raise IFSUnavailable('decoded_record_bound')
            result['digest']=hashlib.sha256(encoded).hexdigest()
            with self.lock:
                self.cache[identity]=(transport.completed_monotonic+600,result,len(encoded))
                while sum(v[2] for v in self.cache.values())>64*1024**2:self.cache.popitem(last=False)
            from .ifs_budget import register_receipts
            register_receipts(budget,[*run['receipts'],*result['receipts']])
            future.set_result(result)
            return self._variant(result,original_product,member,mapped)
        except BaseException as error:
            with self.lock:
                if self.inflight.get(identity) is future:self.inflight.pop(identity,None)
            future.set_exception(error);raise
        finally:
            with self.lock:
                if self.inflight.get(identity) is future:self.inflight.pop(identity,None)
            if self.client is None:transport.client.close()

    @staticmethod
    def _variant(result,product,member,mapped):
        return {**result,'selection_product':product,'member':member,'control_mapping':(
            {'basis':'https://events.ecmwf.int/event/531/attachments/3520/5948/50r1_AIFS2_presentation.pdf',
             'cycle':'50r1','native_product':result['product'],'control_member':'0'} if mapped else None)}

    def loaded_record(self, product, run_time, lead, field, level, member):
        actual = PRODUCTS[product]['control_product'] if member == '0' and PRODUCTS[product]['control_product'] else product
        with self.lock:
            for identity, (expires, value, _) in self.cache.items():
                if expires > self.clock() and (identity[0],identity[1],identity[3],identity[4],identity[5],identity[6]) == (actual,run_time,lead,field,level,member):
                    return self._variant(value,product,member,actual != product)
        return None

    @staticmethod
    def decode(request,destination):
        run_bounded_process(command=[sys.executable,'-m','weather_api.ifs_native_worker','{output}'],
                            stdin=json.dumps(request).encode(),destination=destination,limits=DECODE_LIMITS,timeout_seconds=120)
        return json.loads(destination.read_bytes())


_service=None

def native_service():
    global _service
    if _service is None:_service=IFSNative()
    return _service
