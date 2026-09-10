"""Network-free Linux native decoder worker; object RPC is served by its parent."""
import base64
from dataclasses import asdict
from datetime import datetime
import json
import resource
import sys


def main():
    # Set hard process limits before importing the native numerical stack.
    resource.setrlimit(resource.RLIMIT_AS, (2 * 1024**3, 2 * 1024**3))
    resource.setrlimit(resource.RLIMIT_CPU, (80, 80))
    from weather_api.weathernext_native import NativeLimits, NativeStatisticsReader, ObjectIdentity
    from weather_api.weathernext_query import WeatherNextSelection
    def receive():
        line = sys.stdin.buffer.readline(90 * 1024**2)
        if not line.endswith(b'\n'):
            raise ValueError('worker input bound')
        return json.loads(line)
    def emit(value):
        print(json.dumps(value, allow_nan=False), flush=True)
    class Transport:
        def call(self, request):
            emit(request)
            reply = receive()
            if reply.get('error'): raise ValueError('parent acquisition refused')
            return reply
        def describe(self, bucket, name, *, timeout):
            return ObjectIdentity(**self.call({'op':'describe','bucket':bucket,'name':name})['identity'])
        def read(self, identity, *, max_bytes, timeout):
            return base64.b64decode(self.call({'op':'read','identity':asdict(identity),'max_bytes':max_bytes})['body'],validate=True)
    try:
        request = receive()
        from weather_api.weathernext_limits import MAX_ACQUISITION_BYTES, MAX_OBJECT_BYTES, MAX_FIELDS, operation_limit
        cap=request.get('max_received_bytes',16*1024**2)
        if type(cap) is not int or not 0<cap<=MAX_ACQUISITION_BYTES: raise ValueError('worker byte cap')
        selection = WeatherNextSelection(datetime.fromisoformat(request['initialization']),datetime.fromisoformat(request['valid_time']),
                                         request['latitude'],request['longitude'],tuple(request['fields']))
        if len(selection.fields)>MAX_FIELDS: raise ValueError('worker field cap')
        reader = NativeStatisticsReader(Transport(),limits=NativeLimits(metadata_bytes=256*1024,received_bytes=cap,
                                         decoded_chunk_bytes=128*1024**2,object_bytes=MAX_OBJECT_BYTES,operations=operation_limit(len(selection.fields),regional=request.get("regional",False),inventory=request.get("inventory",False)),seconds=85))
        result = (reader.read_grid if request.get("regional", False) else reader.read_point)(
                                         selection,now=datetime.fromisoformat(request['now']),
                                         acquisition_scope=request.get('acquisition_scope','historical'),
                                         **({'inventory': True} if request.get('inventory') else {}),
                                         **({'region': 'atlantic' if request.get('regional')=='atlantic' else 'avalon'} if request.get('regional') else {}))
        output=asdict(result)
        output['initialization']=result.initialization.isoformat()
        output['valid_time']=result.valid_time.isoformat()
        emit({'op':'result','reading':output})
    except Exception:
        emit({'op':'error','error':'WeatherNext bounded native worker failed'})


def http_main():
    # Host-side helper: runtime auth remains in this short-lived process only.
    from weather_api.weathernext_gcs import AccessTokenFile, GcloudProfileToken, WeatherNextGCSTransport
    from weather_api.weathernext_native import ObjectIdentity
    try:
        request=json.loads(sys.stdin.buffer.read(65536))
        expected=ObjectIdentity(**request['expected']) if request['expected'] else None
        provider=AccessTokenFile(request['token_file']) if 'token_file' in request else GcloudProfileToken(request['profile'])
        transport=WeatherNextGCSTransport(token_provider=provider)
        transport._validate('weathernext3_statistics_spatial',request['name'])
        body=transport._get(request['name'],request['params'],cap=request['cap'],timeout=request['timeout'],expected=expected)
        print(json.dumps({'body':base64.b64encode(body).decode('ascii')}),flush=True)
    except Exception as error:
        status=getattr(error,'http_status',None)
        print(json.dumps({'error':'WeatherNext bounded HTTP worker failed','http_status':status if status in (401,403) else None}),flush=True)


if __name__ == '__main__':
    http_main() if sys.argv[1:]==['--http'] else main()
